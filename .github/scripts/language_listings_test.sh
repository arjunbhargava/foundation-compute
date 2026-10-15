#!/usr/bin/env bash
# Tests .github/scripts/language_listings.sh on copies of the files it reads:
# as they are, with a language that no place lists, and with the places that
# test for each language's manifest emptied. Each case runs the copy's script
# and checks the exit status and the places its errors name.
#
# Usage: mise run test:language-listings-script
set -euo pipefail
cd "$(dirname "$0")/../.."
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

main() {
  copy_repository passes_for_the_repository
  expect_result passes_for_the_repository 0 "lists every language in .config/mise/conf.d/"

  # A language with its tasks, which no place lists.
  local name=fails_naming_each_place_a_new_language_is_missing_from
  copy_repository $name
  printf '[tasks."%s:new_language"]\n' fmt lint test > "$work/$name/.config/mise/conf.d/new_language.toml"
  local lacks=" lacks new_language in"
  local expected=(".github/workflows/ci.yml$lacks" "docs/api/$lacks" "AGENTS.md$lacks")
  if [[ -f copier.yml ]]; then
    expected+=("copier.yml$lacks" ".config/mise/conf.d/template.toml$lacks" ".github/workflows/template.yml$lacks" "README.md$lacks")
  fi
  expect_result $name 1 "${expected[@]}"

  name=fails_naming_codeql_and_the_docs_build_when_they_test_for_no_manifest
  copy_repository $name
  local file
  for file in .github/workflows/codeql.yml docs/build.sh; do
    grep -vF 'if [[ -f ' "$file" > "$work/$name/$file"
  done
  expect_result $name 1 ".github/workflows/codeql.yml lacks" "docs/build.sh lacks"

  if ((failures > 0)); then
    exit 1
  fi
  echo "language_listings.sh gave the expected exit status and errors in all 3 cases."
}

# Copies the script and the files it reads to $work/<name>. Copying the whole
# tree instead fails at times under `mise run check`, whose docs build
# creates and deletes files in docs/api/python/ while the tests run.
copy_repository() {
  local file
  for file in .github/scripts/language_listings.sh .config/mise/conf.d/*.toml .github/workflows/*.yml \
    docs/build.sh docs/api/*.md AGENTS.md README.md copier.yml; do
    if [[ -f $file ]]; then
      mkdir -p "$work/$1/$(dirname "$file")"
      cp "$file" "$work/$1/$file"
    fi
  done
}

# Runs the script in the copy of the repository named <name>.
# Arguments: the case's name, the exit status expected, and texts the output
# must contain.
expect_result() {
  local name=$1 expected_status=$2
  shift 2
  local status=0 output text
  output=$("$work/$name/.github/scripts/language_listings.sh" 2>&1) || status=$?
  if ((status != expected_status)); then
    fail "$name: language_listings.sh exited with status $status, expected $expected_status. Output:
$output"
    return
  fi
  for text in "$@"; do
    if [[ $output != *"$text"* ]]; then
      fail "$name: the output lacks \"$text\". Output:
$output"
      return
    fi
  done
  echo "$name: passed."
}

fail() {
  echo "FAIL: $1" >&2
  failures=$((failures + 1))
}

main "$@"
