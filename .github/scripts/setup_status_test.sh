#!/usr/bin/env bash
# Tests .github/scripts/setup_status.sh without calling GitHub. Each case
# writes the responses a fake gh serves, runs the script, and checks the
# status it prints for each step. The fake serves the file named after the
# path it is asked for, with / replaced by _, such as repos_o_r_pages, prints
# that file's .error and fails if it exists, and otherwise fails with HTTP 404.
#
# Usage: mise run test:setup-status-script
set -euo pipefail

script=$(cd "$(dirname "$0")" && pwd)/setup_status.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
api=$work/api
failures=0
cases=0
case_name=""
output=""

main() {
  make_fake_gh

  new_case auto_mode_is_on
  run_script o/r
  expect_count "[done] " 6
  expect_contains "[done] 4. Rulesets for main (auto mode is on)"

  new_case review_mode_is_on
  edit_json "$api/repos_o_r_rulesets" 'map(if .name == "main: review" then .enforcement = "active"
    elif .name == "main: review (auto mode)" then .enforcement = "disabled" else . end)'
  run_script o/r
  expect_contains "[done] 4. Rulesets for main (review mode: auto mode is off)"

  new_case nothing_is_set_up
  edit_json "$api/repos_o_r" '.allow_auto_merge = false | .allow_merge_commit = false | .allow_squash_merge = true
    | .security_and_analysis.secret_scanning.status = "disabled"'
  echo '{"can_approve_pull_request_reviews": false}' > "$api/repos_o_r_actions_permissions_workflow"
  rm "$api/repos_o_r_pages"
  echo '[]' > "$api/repos_o_r_rulesets"
  run_script o/r
  expect_count "[not done] " 6

  new_case both_review_rulesets_are_active
  edit_json "$api/repos_o_r_rulesets" 'map(.enforcement = "active")'
  run_script o/r
  expect_contains "both review rulesets are active"

  new_case github_refuses_the_pages_request
  rm "$api/repos_o_r_pages"
  echo "gh: Must have admin rights to Repository. (HTTP 403)" > "$api/repos_o_r_pages.error"
  run_script o/r
  expect_contains "[can't check] 3."
  expect_contains "GitHub refused repos/o/r/pages (HTTP 403)"

  new_case gh_account_is_not_an_admin
  edit_json "$api/repos_o_r" '.permissions.admin = false'
  run_script o/r
  expect_count "[can't check] " 11
  expect_contains "gh's account isn't an admin of o/r"

  new_case gh_is_not_logged_in
  rm "$api/repos_o_r"
  echo "To get started with GitHub CLI, please run:  gh auth login" > "$api/repos_o_r.error"
  run_script o/r
  expect_contains "gh isn't logged in"

  new_case gh_is_not_installed
  mkdir "$work/tools"
  for tool in jq dirname mktemp rm; do
    ln -s "$(command -v "$tool")" "$work/tools/$tool"
  done
  run_with_path "$work/tools" o/r
  expect_contains "gh isn't installed"
  expect_contains "Where: https://github.com/o/r/settings/actions"

  new_case repository_is_unknown
  echo "no git remotes" > "$api/repo_view.error"
  run_script
  expect_contains "the repository is unknown"
  expect_contains "Where: https://github.com/OWNER/REPO/settings/actions"

  if ((failures > 0)); then
    exit 1
  fi
  echo "setup_status.sh printed the expected status in all $cases cases."
}

make_fake_gh() {
  mkdir "$work/bin"
  cat > "$work/bin/gh" << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ $1 == repo ]]; then
  if [[ -f $FAKE_GH_API/repo_view.error ]]; then cat "$FAKE_GH_API/repo_view.error" >&2; exit 1; fi
  echo o/r
  exit 0
fi
path=${*: -1}
file=$FAKE_GH_API/$(tr '/?' '__' <<< "$path")
if [[ -f $file.error ]]; then cat "$file.error" >&2; exit 1; fi
if [[ ! -f $file ]]; then echo "gh: Not Found (HTTP 404)" >&2; exit 1; fi
cat "$file"
EOF
  chmod +x "$work/bin/gh"
}

# Starts a case with every setting on and auto mode on, as the API reports it.
new_case() {
  case_name=$1
  cases=$((cases + 1))
  rm -rf "$api" "$work/tools"
  mkdir "$api"
  jq -n '{allow_auto_merge: true, allow_merge_commit: true, allow_squash_merge: false,
    allow_rebase_merge: false, permissions: {admin: true},
    security_and_analysis: {secret_scanning: {status: "enabled"},
      secret_scanning_push_protection: {status: "enabled"}}}' > "$api/repos_o_r"
  echo '{"can_approve_pull_request_reviews": true}' > "$api/repos_o_r_actions_permissions_workflow"
  echo '{"build_type": "workflow"}' > "$api/repos_o_r_pages"
  jq -n '[{name: "main: checks", enforcement: "active"}, {name: "main: review", enforcement: "disabled"},
    {name: "main: review (auto mode)", enforcement: "active"}, {name: "other", enforcement: "active"}]' \
    > "$api/repos_o_r_rulesets"
}

# Rewrites a JSON file with a jq program.
edit_json() {
  local file=$1
  shift
  jq "$@" "$file" > "$file.new"
  mv "$file.new" "$file"
}

run_script() {
  run_with_path "$work/bin:$PATH" "$@"
}

# Runs the script with a PATH, and fails the case unless it exits 0.
run_with_path() {
  local path=$1 status=0
  shift
  output=$(FAKE_GH_API=$api PATH=$path "$BASH" "$script" "$@" 2>&1) || status=$?
  if ((status != 0)); then
    fail "setup_status.sh exited with status $status, but it must always exit 0; it printed:
$output"
  fi
}

expect_contains() {
  if [[ $output != *"$1"* ]]; then
    fail "the output lacks: $1
It was:
$output"
  fi
}

expect_count() {
  local count
  count=$(grep -cF -- "$1" <<< "$output" || true)
  if ((count != $2)); then
    fail "the output has $count lines containing \"$1\", expected $2. It was:
$output"
  fi
}

fail() {
  echo "FAIL: $case_name: $1" >&2
  failures=$((failures + 1))
}

main "$@"
