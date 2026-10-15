#!/usr/bin/env bash
# Tests .github/scripts/needs_human_review.sh: each case runs it on a PR's
# label names and checks whether it passes or fails, and what it prints.
#
# Usage: mise run test:needs-human-review-script
set -euo pipefail

script=$(cd "$(dirname "$0")" && pwd)/needs_human_review.sh
failures=0

main() {
  expect_check fails_when_the_pr_has_the_needs_human_review_label \
    '["agent", "needs-human-review"]' fails "has the needs-human-review label"
  expect_check passes_when_the_pr_has_other_labels \
    '["agent", "needs-human-review-later"]' passes "has no needs-human-review label"
  expect_check passes_when_the_pr_has_no_labels \
    '[]' passes "has no needs-human-review label"
  expect_check fails_when_the_label_names_are_not_a_json_array \
    'needs-human-review' fails "must be a JSON array of strings"

  if ((failures > 0)); then
    exit 1
  fi
  echo "needs_human_review.sh passed or failed as expected in all 4 cases."
}

# Arguments: the case's name, the label names as a JSON array, whether the
# script "passes" or "fails", and text its output must contain.
expect_check() {
  local name=$1 label_names=$2 expected_outcome=$3 expected_text=$4
  local status=0 output outcome=passes
  output=$("$script" "$label_names" 2>&1) || status=$?
  if ((status != 0)); then
    outcome=fails
  fi
  if [[ $outcome != "$expected_outcome" || $output != *"$expected_text"* ]]; then
    echo "FAIL: $name: needs_human_review.sh exited with status $status (expected: it $expected_outcome), printed:
$output
(expected it to contain: $expected_text)" >&2
    failures=$((failures + 1))
  fi
}

main "$@"
