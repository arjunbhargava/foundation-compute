#!/usr/bin/env bash
# Fails if a PR has the needs-human-review label, so that the required check
# of the same name keeps the PR from merging without the owner's bypass in
# auto mode (docs/auto-mode.md). .github/workflows/needs-human-review.yml runs
# it.
#
# Usage: .github/scripts/needs_human_review.sh <label names as a JSON array>
#
# Exits 0 without the label, and 1 with it. Fails, too, if the argument isn't
# a JSON array of strings, so a malformed event can't pass the check.
set -euo pipefail

label_names=${1:?give the label names of the PR as a JSON array of strings}

if ! jq -e 'type == "array" and all(.[]; type == "string")' <<< "$label_names" > /dev/null 2>&1; then
  echo "error: the label names must be a JSON array of strings; got: $label_names" >&2
  exit 1
fi

if jq -e 'index("needs-human-review") != null' <<< "$label_names" > /dev/null; then
  echo "error: this PR has the needs-human-review label, so only the owner merges it, with the admin bypass. Removing the label lets auto mode merge it." >&2
  exit 1
fi
echo "This PR has no needs-human-review label."
