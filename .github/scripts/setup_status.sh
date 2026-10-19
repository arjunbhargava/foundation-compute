#!/usr/bin/env bash
# Reports which of the manual setup steps in README.md ("Finish setup: manual
# steps") are done, so that a person or an agent knows what to do before
# relying on auto mode, the documentation site, or Bugbot.
#
# Usage: mise run setup-status [-- owner/repo]
#
# The repository defaults to the one for the current directory. Each step
# prints "done", "not done", or "can't check", with where to fix or check it.
# The script exits 0 whatever it finds, and prints no token: its messages are
# its own, not gh's. Its only requests, all read-only, are to GitHub's REST API
# through gh:
#
#   GET repos/{repo}
#       .permissions.admin must be true, or every check below prints
#       "can't check" without another request.
#       Step 2: .allow_auto_merge is true.
#       Step 4, merge methods: .allow_merge_commit is true, and
#       .allow_squash_merge and .allow_rebase_merge are false.
#       Step 4, secret scanning: .security_and_analysis.secret_scanning and
#       .secret_scanning_push_protection have status "enabled"; a response
#       without them counts as not done, and the detail says so.
#   GET repos/{repo}/actions/permissions/workflow
#       Step 1: .can_approve_pull_request_reviews is true.
#   GET repos/{repo}/pages
#       Step 3: .build_type is "workflow". HTTP 404 means Pages is off.
#   GET repos/{repo}/rulesets
#       Step 4, rulesets: the ruleset in each file of ../rulesets that sets
#       the checks and the review mode is active, by name only; it doesn't
#       compare rules. Exactly one review ruleset must be active, which says
#       whether auto mode is on.
#
# Steps 5 to 9 (Bugbot, the Cursor GitHub app, Cursor secrets, Linear, the
# automation) have no GitHub API, so they always print "can't check".
set -euo pipefail

rulesets_dir=$(cd "$(dirname "$0")" && pwd)/../rulesets
repo=""
repo_links=""
repo_json=""
settings_unreadable_reason=""

main() {
  stderr_file=$(mktemp)
  trap 'rm -f "$stderr_file"' EXIT
  read_repository "${1:-}"
  local github=https://github.com/$repo_links
  echo "Setup status for $repo_links (README.md, \"Finish setup: manual steps\")"
  check 1 "Allow GitHub Actions to create and approve pull requests" "$github/settings/actions" \
    "repos/$repo/actions/permissions/workflow" '.can_approve_pull_request_reviews == true' "the setting is off"
  check 2 "Allow auto-merge" "$github/settings" \
    repository '.allow_auto_merge == true' "the setting is off"
  check 3 "Pages source is GitHub Actions" "$github/settings/pages" \
    "repos/$repo/pages" '.build_type == "workflow"' "Pages' source is a branch" "Pages is off"
  check_rulesets "$github/settings/rules"
  check 4 "Only merge commits are allowed" "$github/settings" repository \
    '.allow_merge_commit == true and .allow_squash_merge == false and .allow_rebase_merge == false' \
    "squash or rebase merges are allowed, or merge commits aren't; run apply.sh"
  check_secret_scanning "$github/settings/security_analysis"
  report_unchecked_steps "$github"
}

# Finds the repository from an argument, which may be empty, or from gh. Sets
# repo_json, or settings_unreadable_reason when the repository's settings
# can't be read, so that no check guesses.
read_repository() {
  repo=$1
  if [[ -z $repo ]] && command -v gh > /dev/null; then
    repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner 2> /dev/null) || repo=""
  fi
  repo_links=${repo:-OWNER/REPO}
  if ! command -v gh > /dev/null; then
    settings_unreadable_reason="gh isn't installed; install it from https://cli.github.com/ and run \`gh auth login\`"
  elif [[ -z $repo ]]; then
    settings_unreadable_reason="the repository is unknown; run this in a clone with a GitHub remote, or pass owner/repo"
  elif ! api_get "repos/$repo"; then
    settings_unreadable_reason=$(describe_api_failure "repos/$repo")
  elif [[ $(jq -r '.permissions.admin // false' <<< "$api_body") != true ]]; then
    settings_unreadable_reason="gh's account isn't an admin of $repo, and these settings need admin access"
  else
    repo_json=$api_body
  fi
}

# Runs `gh api` on a path. Sets api_body and api_outcome (ok, not_logged_in,
# forbidden, not_found, or failed), and fails unless it is ok.
api_get() {
  if api_body=$(gh api --paginate "$1" 2> "$stderr_file"); then
    api_outcome=ok
    return 0
  fi
  case $(< "$stderr_file") in
    *"gh auth login"* | *"(HTTP 401)"*) api_outcome=not_logged_in ;;
    *"(HTTP 403)"*) api_outcome=forbidden ;;
    *"(HTTP 404)"*) api_outcome=not_found ;;
    *) api_outcome=failed ;;
  esac
  return 1
}

describe_api_failure() {
  case $api_outcome in
    not_logged_in) echo "gh isn't logged in; run \`gh auth login\`" ;;
    forbidden) echo "GitHub refused $1 (HTTP 403); gh's account needs admin access to $repo" ;;
    not_found) echo "GitHub has no $1; the repository may not exist, or gh's account can't see it" ;;
    *) echo "gh api $1 failed for a reason this script doesn't classify; run it by hand to see why" ;;
  esac
}

# Arguments: status, step number, title, detail (may be empty), and the page
# that fixes or shows the step.
report() {
  local status=$1 step=$2 title=$3 detail=$4 url=$5
  echo "[$status] $step. $title"
  if [[ -n $detail ]]; then
    echo "    $detail"
  fi
  if [[ $status != "done" ]]; then
    echo "    Where: $url"
  fi
}

# Reports a step by a jq test of one response. Arguments: step, title, url,
# the source ("repository" for repo_json, or an API path), the jq test, what
# to say when it fails, and optionally what to say when the path is HTTP 404.
check() {
  local step=$1 title=$2 url=$3 source=$4 test=$5 failure_detail=$6 not_found_detail=${7:-}
  local body=$repo_json
  if [[ -n $settings_unreadable_reason ]]; then
    report "can't check" "$step" "$title" "$settings_unreadable_reason" "$url"
    return 0
  fi
  if [[ $source != repository ]]; then
    if ! api_get "$source"; then
      if [[ $api_outcome == not_found && -n $not_found_detail ]]; then
        report "not done" "$step" "$title" "$not_found_detail" "$url"
      else
        report "can't check" "$step" "$title" "$(describe_api_failure "$source")" "$url"
      fi
      return 0
    fi
    body=$api_body
  fi
  if jq -e "$test" <<< "$body" > /dev/null; then
    report "done" "$step" "$title" "" "$url"
  else
    report "not done" "$step" "$title" "$failure_detail" "$url"
  fi
}

check_rulesets() {
  local url=$1 title="Rulesets for main"
  local checks review auto_review
  checks=$(jq -r .name "$rulesets_dir/main-checks.json")
  review=$(jq -r .name "$rulesets_dir/main-review.json")
  auto_review=$(jq -r .name "$rulesets_dir/main-review-auto.json")
  # Names of the active rulesets, one per line, for is_active.
  if [[ -z $settings_unreadable_reason ]] && api_get "repos/$repo/rulesets"; then
    active_ruleset_names=$(jq -r -s 'flatten | .[] | select(.enforcement == "active") | .name' <<< "$api_body")
  else
    report "can't check" 4 "$title" "${settings_unreadable_reason:-$(describe_api_failure "repos/$repo/rulesets")}" "$url"
    return 0
  fi

  local fix="run \`mise exec -- .github/rulesets/apply.sh\`, with \`--auto\` for auto mode"
  if ! is_active "$checks"; then
    report "not done" 4 "$title" "\"$checks\" isn't active; $fix" "$url"
  elif is_active "$review" && is_active "$auto_review"; then
    report "not done" 4 "$title" "both review rulesets are active; $fix" "$url"
  elif is_active "$auto_review"; then
    report "done" 4 "$title (auto mode is on)" "" "$url"
  elif is_active "$review"; then
    report "done" 4 "$title (review mode: auto mode is off)" "" "$url"
  else
    report "not done" 4 "$title" "neither \"$review\" nor \"$auto_review\" is active; $fix" "$url"
  fi
}

is_active() {
  [[ $'\n'$active_ruleset_names$'\n' == *$'\n'"$1"$'\n'* ]]
}

check_secret_scanning() {
  check 4 "Secret scanning with push protection" "$1" repository \
    '.security_and_analysis | .secret_scanning.status == "enabled" and .secret_scanning_push_protection.status == "enabled"' \
    "off, or GitHub doesn't report it, as for a private repository without GitHub Secret Protection; run apply.sh"
}

report_unchecked_steps() {
  local github=$1 reason="no GitHub API reports this; check it by hand"
  report "can't check" 5 "Bugbot is on for the repository" "$reason" https://www.cursor.com/dashboard/bugbot
  report "can't check" 6 "The Cursor GitHub app has access to the repository" "$reason" https://github.com/settings/installations
  report "can't check" 7 "CURSOR_ADMIN_API_KEY and CURSOR_API_KEY are Cursor cloud agent secrets" "$reason" https://www.cursor.com/dashboard
  report "can't check" 8 "Linear is set up as docs/linear.md says" "$reason" "$github/blob/main/docs/linear.md"
  report "can't check" 9 "A Cursor automation runs prune-review (optional)" "$reason" https://cursor.com/automations
}

main "$@"
