#!/usr/bin/env bash
# Tests .github/scripts/lint_workflows.sh on a directory of workflows, with
# the real actionlint, shellcheck, and zizmor. Each case writes one workflow
# and checks the exit status and which tool's findings the output names.
#
# Usage: mise run test:lint-workflows-script
set -euo pipefail

script=$(cd "$(dirname "$0")" && pwd)/lint_workflows.sh
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0

# A workflow neither tool reports.
clean_steps='      - run: echo "hello"'
# The unquoted variable draws SC2086 from shellcheck, which zizmor does not report.
# shellcheck disable=SC2016 # The variable must reach the workflow unexpanded.
actionlint_only_steps='      - run: echo $HOME'
# zizmor reports artipacked for the credentials the checkout persists, which
# actionlint doesn't.
zizmor_only_steps='      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1'

main() {
  expect_result passes_a_clean_workflow "$clean_steps" 0 ""
  expect_result fails_on_a_finding_only_actionlint_reports "$actionlint_only_steps" 1 "SC2086"
  expect_result fails_on_a_finding_only_zizmor_reports "$zizmor_only_steps" 1 "artipacked"
  expect_result checks_a_yaml_extension_file "$actionlint_only_steps" 1 "SC2086" yaml
  expect_result fails_when_the_directory_has_no_workflow "$clean_steps" 1 "no .yml or .yaml workflow" none
  expect_result still_runs_zizmor_after_actionlint_fails "$actionlint_only_steps" 1 "No findings to report"

  if ((failures > 0)); then
    echo "$failures case(s) failed." >&2
    exit 1
  fi
}

# expect_result <name> <steps of the workflow's job> <expected exit status>
# <text the output must contain, or "" for none> [yaml|none: name the file
# test.yaml, or write no file]
expect_result() {
  local name=$1 steps=$2 expected_status=$3 expected_text=$4 variant=${5:-yml}
  local dir=$work/$name
  mkdir "$dir"
  if [[ $variant != none ]]; then
    printf 'name: Test\non: pull_request\npermissions: {}\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n%s\n' \
      "$steps" > "$dir/test.$variant"
  fi

  local status=0
  "$script" "$dir" > "$dir.out" 2>&1 || status=$?

  if ((status != expected_status)); then
    echo "FAIL: $name: exit status $status, expected $expected_status. Output:" >&2
    cat "$dir.out" >&2
    failures=$((failures + 1))
  elif [[ -n $expected_text ]] && ! grep -qF "$expected_text" "$dir.out"; then
    echo "FAIL: $name: the output lacks \"$expected_text\". Output:" >&2
    cat "$dir.out" >&2
    failures=$((failures + 1))
  else
    echo "$name: passed."
  fi
}

main
