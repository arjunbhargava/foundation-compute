#!/usr/bin/env bash
# Tests .github/scripts/owned_paths.sh without calling GitHub. Each case runs
# a copy of the script, next to the CODEOWNERS below, on PR 7 against a fake
# gh that serves the PR's files, and checks the exit status and the output.
#
# Usage: mise run test:owned-paths-script
set -euo pipefail

script=$(cd "$(dirname "$0")" && pwd)/owned_paths.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

codeowners='# A comment, then a blank line.

/.github/     @owner
/AGENTS.md    @owner
*.toml        @owner # an inline comment
!/mise.toml   @owner
/LICENSE      # a comment, not an owner'
# The end of the line before the list of owned paths, so that an expected
# list is the whole list.
list_start=$'(docs/auto-mode.md):\n'

main() {
  make_fake_gh
  expect_result passes_when_no_changed_path_is_owned \
    '[[{"filename": "docs/linear.md"}, {"filename": "docs/AGENTS.md"}, {"filename": "AGENTS.md.jinja"}, {"filename": "LICENSE"}]]' \
    0 "PR #7 changes no path in .github/CODEOWNERS."
  expect_result passes_when_the_pr_changes_no_file '[[]]' 0 "PR #7 changes no path in .github/CODEOWNERS."
  expect_result fails_listing_only_the_owned_paths \
    '[[{"filename": "docs/linear.md"}, {"filename": "AGENTS.md"}, {"filename": ".github/workflows/ci.yml"}, {"filename": "crates/foundation/Cargo.toml"}]]' \
    1 "$list_start$(printf '%s\n' AGENTS.md .github/workflows/ci.yml crates/foundation/Cargo.toml)"
  expect_result fails_when_an_owned_file_is_renamed_to_an_unowned_path \
    '[[{"filename": "docs/agents.md", "previous_filename": "AGENTS.md"}]]' 1 "${list_start}AGENTS.md"
  expect_result skips_a_negated_line_as_github_does \
    '[[{"filename": "mise.toml"}]]' 1 "${list_start}mise.toml"
  expect_result finds_an_owned_path_on_a_later_page \
    '[[{"filename": "docs/linear.md"}], [{"filename": "AGENTS.md"}]]' 1 "${list_start}AGENTS.md"
  expect_result cannot_tell_when_github_lists_its_most_files \
    "$(jq -nc '[[range(3000) | {filename: "docs/\(.).md"}]]')" 2 "changes at least 3000 files"
  expect_result cannot_tell_when_github_refuses_to_list_the_files \
    unreadable 2 "HTTP 403"
  expect_result cannot_tell_when_git_cannot_match_a_path \
    '[[{"filename": "../outside"}]]' 2 "outside repository"

  if ((failures > 0)); then
    exit 1
  fi
  echo "owned_paths.sh gave the expected exit status and output in all 9 cases."
}

# Puts first on PATH a gh that serves PR 7's files, as pages of JSON arrays,
# from $FAKE_GH_CASE/files.json. Without that file, it refuses the request.
make_fake_gh() {
  mkdir "$work/bin"
  cat > "$work/bin/gh" << 'EOF'
#!/bin/sh
case "$*" in
  "api --paginate --slurp repos/o/r/pulls/7/files?per_page=100")
    cat "$FAKE_GH_CASE/files.json" 2> /dev/null ||
      { echo "gh: Resource not accessible by integration (HTTP 403)" >&2; exit 1; } ;;
  *) echo "fake gh: unexpected call: gh $*" >&2; exit 1 ;;
esac
EOF
  chmod +x "$work/bin/gh"
  PATH=$work/bin:$PATH
}

# Arguments: the case's name; the PR's files, as gh api --paginate --slurp
# prints them, or "unreadable"; the exit status expected; and text the output
# must contain.
expect_result() {
  local name=$1 files=$2 expected_status=$3 expected_text=$4
  local case_dir=$work/$name
  mkdir -p "$case_dir/.github/scripts"
  cp "$script" "$case_dir/.github/scripts/"
  printf '%s\n' "$codeowners" > "$case_dir/.github/CODEOWNERS"
  if [[ $files != unreadable ]]; then
    printf '%s\n' "$files" > "$case_dir/files.json"
  fi
  local status=0 output
  output=$(FAKE_GH_CASE=$case_dir GITHUB_REPOSITORY=o/r "$case_dir/.github/scripts/owned_paths.sh" 7 2>&1) || status=$?
  if ((status != expected_status)) || [[ $output != *"$expected_text"* ]]; then
    fail "$name: owned_paths.sh exited with status $status (expected $expected_status) and printed:
$output
Expected the output to contain:
$expected_text"
  fi
}

fail() {
  echo "FAIL: $1" >&2
  failures=$((failures + 1))
}

main "$@"
