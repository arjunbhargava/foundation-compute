#!/usr/bin/env bash
# Checks the ruleset files in this directory: each is valid JSON, and the
# auto-mode review ruleset (docs/auto-mode.md) differs from main-review.json
# only in its name, whether review threads must be resolved, and its rule
# requiring the owned-paths and needs-human-review checks, so an edit to one
# review ruleset is made to both. It also checks those values against
# docs/auto-mode.md: auto mode needs exactly 1 approval, which the approval
# workflow gives an agent PR, review mode at least 1, and only auto mode
# needs resolved threads and the two checks. Auto mode must keep code-owner
# review, thread resolution, and the two checks on, because without them, a
# PR could merge with no Bugbot or owner gate.
#
# Usage: mise run lint:rulesets
set -euo pipefail
cd "$(dirname "$0")"

# Requires .github/workflows/owned-paths.yml and needs-human-review.yml to
# pass, as reported by GitHub Actions, integration_id 15368.
auto_mode_checks_rule='{"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": true, "required_status_checks": [{"context": "owned-paths", "integration_id": 15368}, {"context": "needs-human-review", "integration_id": 15368}]}}'

for file in *.json; do
  if ! jq empty "$file"; then
    echo "error: .github/rulesets/$file is not valid JSON; fix the parse error above." >&2
    exit 1
  fi
done

# Arguments: a review ruleset file, a jq condition on its pull_request rule's
# parameters, and the error to print, after the file name, if it is false.
require_review_setting() {
  if ! jq -e ".rules[] | select(.type == \"pull_request\") | .parameters | $2" "$1" > /dev/null; then
    echo "error: $1 $3" >&2
    exit 1
  fi
}
require_review_setting main-review-auto.json '.require_code_owner_review and .required_review_thread_resolution' \
  "must set require_code_owner_review and required_review_thread_resolution to true."
require_review_setting main-review-auto.json '.required_approving_review_count == 1' \
  "must set required_approving_review_count to 1: with 0, a PR without the agent label would merge with no person's approval, and with more, the one approval the approval workflow gives an agent PR isn't enough."
require_review_setting main-review.json '.required_approving_review_count >= 1' \
  "must set required_approving_review_count to at least 1: with 0, a PR would merge with no person's approval."
require_review_setting main-review.json '.required_review_thread_resolution == false' \
  "must set required_review_thread_resolution to false, as the table in docs/auto-mode.md says."

if ! jq -e --argjson rule "$auto_mode_checks_rule" 'any(.rules[]; . == $rule)' main-review-auto.json > /dev/null; then
  echo "error: main-review-auto.json must have this rule, so that a PR that changes a path in .github/CODEOWNERS, or has the needs-human-review label, merges only with the owner's bypass: $auto_mode_checks_rule" >&2
  exit 1
fi

without_auto_mode_fields='del(.name, (.rules[] | select(.type == "pull_request") | .parameters | .required_review_thread_resolution))'
if ! diff -u <(jq -S "$without_auto_mode_fields" main-review.json) \
  <(jq -S --argjson rule "$auto_mode_checks_rule" "$without_auto_mode_fields | del(.rules[] | select(. == \$rule))" main-review-auto.json) >&2; then
  echo "error: main-review.json and main-review-auto.json differ in the lines above, which auto mode doesn't change. Make the same edit to both files; only main-review-auto.json has the rule requiring the owned-paths and needs-human-review checks." >&2
  exit 1
fi

echo "The ruleset files are valid JSON, and the review rulesets differ only in name, thread resolution, and the rule requiring the owned-paths and needs-human-review checks, with the values docs/auto-mode.md gives."
