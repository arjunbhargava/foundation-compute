#!/usr/bin/env bash
# Tests the scripts in .github/rulesets/ without calling GitHub. apply.sh runs
# with --dry-run against a fake gh that lists canned existing rulesets, and
# each case compares the changes apply.sh would make with the expected ones.
# Each case runs apply.sh in a copy of this directory, as a project has it
# (without template-checks.json) or as the template repository has it (with
# one), so the test gives the same result in both. check.sh runs on copies of
# the ruleset files, each broken in one way.
#
# Usage: mise run test:rulesets
set -euo pipefail

rulesets_dir=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

main() {
  make_fake_gh
  local project=$work/project-rulesets template=$work/template-rulesets
  mkdir "$project"
  cp "$rulesets_dir/apply.sh" "$rulesets_dir"/main-*.json "$project/"
  cp -R "$project" "$template"
  echo '{"name": "main: template checks"}' > "$template/template-checks.json"
  local checks='{"id": 1, "name": "main: checks"}'
  local review='{"id": 2, "name": "main: review"}'
  local auto='{"id": 3, "name": "main: review (auto mode)"}'

  expect_changes default_mode_makes_the_same_changes_as_before_auto_mode "$project" "[$checks, $review]" '
Would allow only merge commits: PATCH repos/o/r
Would update ruleset "main: checks" (id 1): PUT repos/o/r/rulesets/1
Would update ruleset "main: review" (id 2): PUT repos/o/r/rulesets/2
Would turn on secret scanning with push protection: PATCH repos/o/r'

  expect_changes auto_mode_creates_its_ruleset_then_disables_main_review "$project" "[$checks, $review]" '
Would allow only merge commits: PATCH repos/o/r
Would update ruleset "main: checks" (id 1): PUT repos/o/r/rulesets/1
Would create ruleset "main: review (auto mode)": POST repos/o/r/rulesets
Would disable ruleset "main: review" (id 2): PUT repos/o/r/rulesets/2
Would turn on secret scanning with push protection: PATCH repos/o/r' --auto

  expect_changes default_mode_switches_back_from_auto_mode_dismissing_only_the_bots_approvals "$project" "[$checks, $review, $auto]" '
Would allow only merge commits: PATCH repos/o/r
Would update ruleset "main: checks" (id 1): PUT repos/o/r/rulesets/1
Would update ruleset "main: review" (id 2): PUT repos/o/r/rulesets/2
Would dismiss the approval github-actions[bot] gave PR #7 (review 11): PUT repos/o/r/pulls/7/reviews/11/dismissals
Would disable ruleset "main: review (auto mode)" (id 3): PUT repos/o/r/rulesets/3
Would turn on secret scanning with push protection: PATCH repos/o/r'

  expect_changes template_repository_creates_the_template_checks_ruleset "$template" "[$checks, $review]" '
Would allow only merge commits: PATCH repos/o/r
Would update ruleset "main: checks" (id 1): PUT repos/o/r/rulesets/1
Would create ruleset "main: template checks": POST repos/o/r/rulesets
Would update ruleset "main: review" (id 2): PUT repos/o/r/rulesets/2
Would turn on secret scanning with push protection: PATCH repos/o/r'

  if ! "$rulesets_dir/check.sh" > /dev/null; then
    fail "check_passes_on_the_committed_rulesets: check.sh failed on the files in .github/rulesets/."
  fi
  expect_check_error check_fails_on_invalid_json main-checks.json '{' \
    "main-checks.json is not valid JSON"
  expect_check_error check_fails_when_the_review_rulesets_differ_elsewhere main-review-auto.json \
    "$(jq '.bypass_actors = []' "$rulesets_dir/main-review-auto.json")" \
    "differ in the lines above"
  expect_check_error check_fails_when_auto_mode_drops_thread_resolution main-review-auto.json \
    "$(with_review_setting main-review-auto.json required_review_thread_resolution false)" \
    "must set require_code_owner_review and required_review_thread_resolution to true"
  expect_check_error check_fails_when_auto_mode_requires_no_approval main-review-auto.json \
    "$(with_review_setting main-review-auto.json required_approving_review_count 0)" \
    "main-review-auto.json must set required_approving_review_count to 1"
  expect_check_error check_fails_when_review_mode_requires_no_approval main-review.json \
    "$(with_review_setting main-review.json required_approving_review_count 0)" \
    "main-review.json must set required_approving_review_count to at least 1"
  expect_check_error check_fails_when_the_review_rulesets_differ_in_approval_count main-review.json \
    "$(with_review_setting main-review.json required_approving_review_count 2)" \
    "differ in the lines above"
  expect_check_error check_fails_when_review_mode_requires_thread_resolution main-review.json \
    "$(with_review_setting main-review.json required_review_thread_resolution true)" \
    "main-review.json must set required_review_thread_resolution to false"
  expect_check_error check_fails_when_auto_mode_drops_the_owned_paths_check main-review-auto.json \
    "$(jq 'del(.rules[] | select(.type == "required_status_checks"))' "$rulesets_dir/main-review-auto.json")" \
    "main-review-auto.json must have this rule"
  expect_check_error check_fails_when_auto_mode_drops_the_needs_human_review_check main-review-auto.json \
    "$(jq 'del(.rules[].parameters.required_status_checks[]? | select(.context == "needs-human-review"))' "$rulesets_dir/main-review-auto.json")" \
    "main-review-auto.json must have this rule"
  expect_check_error check_fails_when_review_mode_requires_the_owned_paths_check main-review.json \
    "$(jq --slurpfile auto "$rulesets_dir/main-review-auto.json" \
      '.rules += [$auto[0].rules[] | select(.type == "required_status_checks")]' "$rulesets_dir/main-review.json")" \
    "differ in the lines above"

  if ((failures > 0)); then
    exit 1
  fi
  echo "apply.sh made the expected changes in all 4 cases, and check.sh passed the committed rulesets and failed all 10 broken ones."
}

# Puts first on PATH a gh that answers only apply.sh's requests: the existing
# rulesets, with the JSON array in FAKE_EXISTING_RULESETS, and one open PR,
# 7. PR 7's reviews are a person's approval and a dismissed approval by
# github-actions[bot] on the first page, and an approval by
# github-actions[bot], review 11, on the second.
make_fake_gh() {
  mkdir "$work/bin"
  cat > "$work/bin/gh" << 'EOF'
#!/bin/sh
case "$*" in
  *"/rulesets?includes_parents=false"*) printf '%s\n' "$FAKE_EXISTING_RULESETS" ;;
  "api --paginate --slurp repos/o/r/pulls?state=open") echo '[[{"number": 7}]]' ;;
  "api --paginate --slurp repos/o/r/pulls/7/reviews")
    echo '[[{"id": 12, "user": {"login": "a-collaborator"}, "state": "APPROVED"},
      {"id": 13, "user": {"login": "github-actions[bot]"}, "state": "DISMISSED"}],
      [{"id": 11, "user": {"login": "github-actions[bot]"}, "state": "APPROVED"}]]' ;;
  *) echo "fake gh: unexpected call: gh $*" >&2; exit 1 ;;
esac
EOF
  chmod +x "$work/bin/gh"
  PATH=$work/bin:$PATH
}

# Arguments: the case's name, the directory whose apply.sh runs, the existing
# rulesets as a JSON array, the "Would ..." lines apply.sh --dry-run must
# print, after a leading newline, and apply.sh's other options.
expect_changes() {
  local name=$1 directory=$2 existing=$3 expected=${4#$'\n'}
  shift 4
  local status=0 output changes
  output=$(FAKE_EXISTING_RULESETS=$existing "$directory/apply.sh" --dry-run "$@" o/r 2>&1) || status=$?
  changes=$(grep '^Would' <<< "$output" || true)
  if ((status != 0)) || [[ $changes != "$expected" ]]; then
    fail "$name: apply.sh exited with status $status and printed:
$output
Expected these changes:
$expected"
  fi
}

# Arguments: the case's name, a ruleset file, the content that replaces it in a
# copy of this directory, and text that check.sh's error must contain.
expect_check_error() {
  local name=$1 file=$2 content=$3 expected_error=$4
  local copy=$work/$name
  mkdir "$copy"
  cp "$rulesets_dir/check.sh" "$rulesets_dir"/*.json "$copy/"
  printf '%s\n' "$content" > "$copy/$file"
  local status=0 output
  output=$("$copy/check.sh" 2>&1) || status=$?
  if ((status == 0)) || [[ $output != *"$expected_error"* ]]; then
    fail "$name: check.sh exited with status $status and printed '$output'; expected a non-zero status and an error containing '$expected_error'."
  fi
}

# Prints a review ruleset file from this directory with one parameter of its
# pull_request rule set. Arguments: the file, the parameter, and its JSON value.
with_review_setting() {
  jq --arg name "$2" --argjson value "$3" \
    '(.rules[] | select(.type == "pull_request") | .parameters[$name]) = $value' "$rulesets_dir/$1"
}

fail() {
  echo "FAIL: $1" >&2
  failures=$((failures + 1))
}

main "$@"
