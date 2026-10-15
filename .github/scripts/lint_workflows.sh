#!/usr/bin/env bash
# Checks the GitHub Actions workflows in a directory with actionlint, which
# finds syntax and type errors and, through shellcheck, errors in run:
# scripts, and with zizmor, which finds security problems. Both tools always
# run, so one failure doesn't hide the other's findings; the script exits 1 if
# either reports a finding.
#
# zizmor runs with --offline, which skips its audits that query GitHub, so
# the result doesn't depend on a token or the network.
#
# Usage: mise run lint:workflows
# The optional argument is the directory to check, default .github/workflows,
# which the test of this script changes.
set -uo pipefail
shopt -s nullglob

workflows_dir=${1:-.github/workflows}
status=0

# GitHub runs both .yml and .yaml files.
workflow_files=("$workflows_dir"/*.yml "$workflows_dir"/*.yaml)
if ((${#workflow_files[@]} == 0)); then
  echo "error: no .yml or .yaml workflow in $workflows_dir; pass the directory that holds the workflows" >&2
  exit 1
fi

actionlint "${workflow_files[@]}" || status=1
zizmor --offline --no-progress "${workflow_files[@]}" || status=1

exit "$status"
