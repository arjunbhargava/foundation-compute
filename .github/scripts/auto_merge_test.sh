#!/usr/bin/env bash
# Tests .github/scripts/auto_merge.sh without calling GitHub. Each case runs
# the script on PR 7 against a fake gh that serves a canned repository, PR,
# Bugbot check runs, and PR files, and compares the `gh pr merge` calls the
# script makes with the expected ones. owned_paths.sh, which the script runs,
# reads this repository's .github/CODEOWNERS, which owns AGENTS.md and not
# docs/linear.md.
#
# Usage: mise run test:auto-merge-script
set -euo pipefail

script=$(cd "$(dirname "$0")" && pwd)/auto_merge.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

agent_pr='{
  "number": 7, "state": "open", "draft": false, "user": {"login": "arjunbhargava"},
  "head": {"sha": "new", "repo": {"full_name": "o/r"}}, "base": {"ref": "main"},
  "labels": [{"name": "agent"}], "auto_merge": null
}'
reviewed='{"id": 2, "status": "completed", "conclusion": "neutral",
  "output": {"summary": "**Final Result:** Bugbot completed review and found 1 potential issue."}}'
cancelled='{"id": 2, "status": "completed", "conclusion": "neutral",
  "output": {"summary": "**Result:** Bugbot run cancelled because the review request was cancelled"}}'
in_progress='{"id": 3, "status": "in_progress", "conclusion": null,
  "output": {"summary": "Bugbot Analysis Progress (1m 2s elapsed)"}}'
turn_on='gh pr merge 7 --repo o/r --auto --merge --match-head-commit new'
turn_off='gh pr merge 7 --repo o/r --disable-auto'
owned_files='[[{"filename": "docs/linear.md"}, {"filename": "AGENTS.md"}]]'

main() {
  make_fake_gh
  expect_merge_calls turns_auto_merge_on_once_bugbot_has_reviewed_the_head_commit \
    . "[$reviewed]" true "$turn_on"
  expect_merge_calls waits_while_bugbot_is_reviewing_the_head_commit \
    . "[$reviewed, $in_progress]" true ""
  expect_merge_calls waits_when_bugbot_run_on_the_head_commit_was_cancelled \
    . "[$cancelled]" true ""
  expect_merge_calls turns_auto_merge_off_after_a_push_bugbot_has_not_reviewed \
    '.auto_merge = {"merge_method": "merge"}' "[]" true "$turn_off"
  expect_merge_calls leaves_auto_merge_on_once_bugbot_has_reviewed_the_head_commit \
    '.auto_merge = {"merge_method": "merge"}' "[$reviewed]" true ""
  expect_merge_calls waits_while_the_pr_is_a_draft \
    '.draft = true' "[$reviewed]" true ""
  expect_merge_calls keeps_auto_merge_off_while_the_pr_has_the_needs_human_review_label \
    '.labels += [{"name": "needs-human-review"}]' "[$reviewed]" true ""
  expect_merge_calls turns_auto_merge_off_when_the_needs_human_review_label_is_added \
    '.labels += [{"name": "needs-human-review"}] | .auto_merge = {"merge_method": "merge"}' "[$reviewed]" true "$turn_off"
  expect_merge_calls does_nothing_when_allow_auto_merge_is_off \
    . "[$reviewed]" false ""
  expect_merge_calls still_turns_auto_merge_off_after_a_push_when_allow_auto_merge_is_off \
    '.auto_merge = {"merge_method": "merge"}' "[]" false "$turn_off"
  expect_merge_calls leaves_closed_prs_alone \
    '.state = "closed"' "[$reviewed]" true ""
  expect_merge_calls leaves_prs_without_the_agent_label_alone \
    '.labels = [{"name": "dependencies"}]' "[$reviewed]" true ""
  expect_merge_calls leaves_dependabot_prs_alone \
    '.user.login = "dependabot[bot]"' "[$reviewed]" true ""
  expect_merge_calls leaves_prs_from_forks_alone \
    '.head.repo.full_name = "fork/r"' "[$reviewed]" true ""
  expect_merge_calls leaves_prs_into_other_branches_alone \
    '.base.ref = "stacked-base"' "[$reviewed]" true ""
  expect_merge_calls fails_when_github_refuses_to_list_bugbot_check_runs \
    . unreadable true "" fails
  expect_merge_calls turns_auto_merge_off_then_fails_when_github_refuses_to_list_bugbot_check_runs \
    '.auto_merge = {"merge_method": "merge"}' unreadable true "$turn_off" fails
  expect_merge_calls keeps_auto_merge_off_when_the_pr_changes_an_owned_path \
    . "[$reviewed]" true "" succeeds "$owned_files"
  expect_merge_calls turns_auto_merge_off_when_a_push_adds_an_owned_path \
    '.auto_merge = {"merge_method": "merge"}' "[$reviewed]" true "$turn_off" succeeds "$owned_files"
  expect_merge_calls turns_auto_merge_off_then_fails_when_the_changed_paths_are_unknown \
    '.auto_merge = {"merge_method": "merge"}' "[$reviewed]" true "$turn_off" fails unreadable

  if ((failures > 0)); then
    exit 1
  fi
  echo "auto_merge.sh made the expected gh pr merge calls in all 20 cases."
}

# Puts first on PATH a gh that answers auto_merge.sh's requests from the files
# in $FAKE_GH_CASE, and appends each `gh pr merge` call to its merge-calls
# file. Only the head commit, "new", has Bugbot check runs. Without a
# check-runs file, it refuses that request as GitHub does a token without
# checks: read in a private repository, and without a files file, it refuses
# to list the PR's files.
make_fake_gh() {
  mkdir "$work/bin"
  cat > "$work/bin/gh" << 'EOF'
#!/bin/sh
case "$*" in
  "api repos/o/r") cat "$FAKE_GH_CASE/repository.json" ;;
  "api repos/o/r/pulls/7") cat "$FAKE_GH_CASE/pr.json" ;;
  "api --method GET repos/o/r/commits/new/check-runs -f app_id=1210556 -f check_name=Cursor Bugbot")
    cat "$FAKE_GH_CASE/check-runs.json" 2> /dev/null ||
      { echo "gh: Resource not accessible by integration (HTTP 403)" >&2; exit 1; } ;;
  "api --paginate --slurp repos/o/r/pulls/7/files?per_page=100")
    cat "$FAKE_GH_CASE/files.json" 2> /dev/null ||
      { echo "gh: Resource not accessible by integration (HTTP 403)" >&2; exit 1; } ;;
  "pr merge "*) echo "gh $*" >> "$FAKE_GH_CASE/merge-calls" ;;
  *) echo "fake gh: unexpected call: gh $*" >&2; exit 1 ;;
esac
EOF
  chmod +x "$work/bin/gh"
  PATH=$work/bin:$PATH
}

# Arguments: the case's name; a jq filter that turns the agent PR into the
# case's PR; Bugbot's check runs on the head commit, as a JSON array, or
# "unreadable"; the repository's allow_auto_merge setting; the `gh pr merge`
# calls expected, one per line; whether the script "succeeds", the default,
# or "fails"; and the PR's files, as gh api --paginate --slurp prints them,
# or "unreadable", by default docs/linear.md alone.
expect_merge_calls() {
  local name=$1 pr_filter=$2 check_runs=$3 allow_auto_merge=$4 expected=$5 expected_outcome=${6:-succeeds}
  local files=${7:-'[[{"filename": "docs/linear.md"}]]'}
  local case_dir=$work/$name
  mkdir "$case_dir"
  echo "{\"default_branch\": \"main\", \"allow_auto_merge\": $allow_auto_merge}" > "$case_dir/repository.json"
  jq "$pr_filter" <<< "$agent_pr" > "$case_dir/pr.json"
  if [[ $check_runs != unreadable ]]; then
    echo "{\"check_runs\": $check_runs}" > "$case_dir/check-runs.json"
  fi
  if [[ $files != unreadable ]]; then
    echo "$files" > "$case_dir/files.json"
  fi
  touch "$case_dir/merge-calls"

  local status=0 output calls outcome=succeeds
  output=$(FAKE_GH_CASE=$case_dir GITHUB_REPOSITORY=o/r "$script" 7 2>&1) || status=$?
  if ((status != 0)); then
    outcome=fails
  fi
  calls=$(cat "$case_dir/merge-calls")
  if [[ $outcome != "$expected_outcome" || $calls != "$expected" ]]; then
    fail "$name: auto_merge.sh exited with status $status (expected: it $expected_outcome), printed:
$output
and made these gh pr merge calls:
${calls:-(none)}
Expected these calls:
${expected:-(none)}"
  fi
}

fail() {
  echo "FAIL: $1" >&2
  failures=$((failures + 1))
}

main "$@"
