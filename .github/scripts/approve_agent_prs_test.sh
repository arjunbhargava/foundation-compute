#!/usr/bin/env bash
# Tests .github/scripts/approve_agent_prs.sh without calling GitHub. Each case
# runs the script on PR 7 against a fake gh that serves canned rulesets, a PR,
# and the PR's reviews, and checks whether the script approves the PR, what it
# prints, and whether it succeeds.
#
# Usage: mise run test:approve-agent-prs-script
set -euo pipefail

script=$(cd "$(dirname "$0")" && pwd)/approve_agent_prs.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

agent_pr='{
  "number": 7, "state": "open", "head": {"repo": {"full_name": "o/r"}},
  "labels": [{"name": "agent"}]
}'
# The rulesets and reviews are pages of JSON arrays, as gh api --paginate
# --slurp prints them; auto mode's ruleset is on the second page.
auto_mode='[[{"name": "main: checks", "enforcement": "active"}, {"name": "main: review", "enforcement": "disabled"}],
  [{"name": "main: review (auto mode)", "enforcement": "active"}]]'
review_mode='[[{"name": "main: review", "enforcement": "active"}, {"name": "main: review (auto mode)", "enforcement": "disabled"}]]'
both_review_rulesets='[[{"name": "main: review", "enforcement": "active"}, {"name": "main: review (auto mode)", "enforcement": "active"}]]'
no_reviews='[[]]'
bugbot_comment='{"user": {"login": "cursor[bot]"}, "state": "COMMENTED"}'
person_approval='{"user": {"login": "a-collaborator"}, "state": "APPROVED"}'
bot_approval='{"user": {"login": "github-actions[bot]"}, "state": "APPROVED"}'
bot_dismissed='{"user": {"login": "github-actions[bot]"}, "state": "DISMISSED"}'
approval='approve 7'

main() {
  make_fake_gh
  expect_approval approves_an_agent_pr_in_auto_mode \
    "$auto_mode" . "$no_reviews" allowed "$approval" "PR #7: approved"
  expect_approval approves_nothing_in_review_mode \
    "$review_mode" . "$no_reviews" allowed "" "Auto mode is off"
  expect_approval approves_nothing_while_both_review_rulesets_are_active \
    "$both_review_rulesets" . "$no_reviews" allowed "" "Auto mode is off"
  expect_approval leaves_prs_without_the_agent_label_alone \
    "$auto_mode" '.labels = [{"name": "dependencies"}]' "$no_reviews" allowed "" "it has no agent label"
  expect_approval does_not_approve_a_pr_with_the_needs_human_review_label \
    "$auto_mode" '.labels += [{"name": "needs-human-review"}]' "$no_reviews" allowed "" "it has the needs-human-review label"
  expect_approval leaves_prs_from_forks_alone \
    "$auto_mode" '.head.repo.full_name = "fork/r"' "$no_reviews" allowed "" "it comes from a fork"
  expect_approval leaves_closed_prs_alone \
    "$auto_mode" '.state = "closed"' "$no_reviews" allowed "" "it is closed"
  expect_approval approves_a_pr_at_most_once \
    "$auto_mode" . "[[$bugbot_comment], [$bot_approval]]" allowed "" "has reviewed it before (APPROVED)"
  expect_approval does_not_approve_again_after_its_approval_is_dismissed \
    "$auto_mode" . "[[$bot_dismissed]]" allowed "" "has reviewed it before (DISMISSED)"
  expect_approval approves_when_only_other_accounts_have_reviewed \
    "$auto_mode" . "[[$bugbot_comment, $person_approval]]" allowed "$approval" "PR #7: approved"
  expect_approval fails_naming_the_setting_when_github_refuses_the_approval \
    "$auto_mode" . "$no_reviews" refused "" "Allow GitHub Actions to create and approve pull requests" fails
  expect_approval fails_when_github_refuses_to_list_the_rulesets \
    unreadable . "$no_reviews" allowed "" "HTTP 403" fails

  if ((failures > 0)); then
    exit 1
  fi
  echo "approve_agent_prs.sh approved, or left alone, PR 7 as expected in all 12 cases."
}

# Puts first on PATH a gh that answers approve_agent_prs.sh's requests from the
# files in $FAKE_GH_CASE, and appends "approve 7" to its approvals file for
# each approval. Without a rulesets file, it refuses that request; with a
# refuse-approval file, it refuses the approval, as GitHub does while Actions
# may not approve PRs.
make_fake_gh() {
  mkdir "$work/bin"
  cat > "$work/bin/gh" << 'EOF'
#!/bin/sh
case "$*" in
  "api --paginate --slurp repos/o/r/rulesets?includes_parents=false")
    cat "$FAKE_GH_CASE/rulesets.json" 2> /dev/null ||
      { echo "gh: Resource not accessible by integration (HTTP 403)" >&2; exit 1; } ;;
  "api repos/o/r/pulls/7") cat "$FAKE_GH_CASE/pr.json" ;;
  "api --paginate --slurp repos/o/r/pulls/7/reviews") cat "$FAKE_GH_CASE/reviews.json" ;;
  "api --method POST repos/o/r/pulls/7/reviews --silent -f event=APPROVE -f body="*)
    if [ -e "$FAKE_GH_CASE/refuse-approval" ]; then
      echo "gh: GitHub Actions is not permitted to approve pull requests. (HTTP 422)" >&2
      exit 1
    fi
    echo "approve 7" >> "$FAKE_GH_CASE/approvals" ;;
  *) echo "fake gh: unexpected call: gh $*" >&2; exit 1 ;;
esac
EOF
  chmod +x "$work/bin/gh"
  PATH=$work/bin:$PATH
}

# Arguments: the case's name; the repository's rulesets, or "unreadable"; a jq
# filter that turns the agent PR into the case's PR; the PR's reviews; whether
# GitHub "allowed" or "refused" the approval; the approvals expected, "approve
# 7" or nothing; text the script's output must contain; and whether the
# script "succeeds", the default, or "fails".
expect_approval() {
  local name=$1 rulesets=$2 pr_filter=$3 reviews=$4 approval_setting=$5 expected=$6 expected_text=$7
  local expected_outcome=${8:-succeeds}
  local case_dir=$work/$name
  mkdir "$case_dir"
  if [[ $rulesets != unreadable ]]; then
    echo "$rulesets" > "$case_dir/rulesets.json"
  fi
  jq "$pr_filter" <<< "$agent_pr" > "$case_dir/pr.json"
  echo "$reviews" > "$case_dir/reviews.json"
  if [[ $approval_setting == refused ]]; then
    touch "$case_dir/refuse-approval"
  fi
  touch "$case_dir/approvals"

  local status=0 output approvals outcome=succeeds
  output=$(FAKE_GH_CASE=$case_dir GITHUB_REPOSITORY=o/r "$script" 7 2>&1) || status=$?
  if ((status != 0)); then
    outcome=fails
  fi
  approvals=$(cat "$case_dir/approvals")
  if [[ $outcome != "$expected_outcome" || $approvals != "$expected" || $output != *"$expected_text"* ]]; then
    fail "$name: approve_agent_prs.sh exited with status $status (expected: it $expected_outcome), printed:
$output
(expected it to contain: $expected_text)
and made these approvals: ${approvals:-(none)}; expected: ${expected:-(none)}"
  fi
}

fail() {
  echo "FAIL: $1" >&2
  failures=$((failures + 1))
}

main "$@"
