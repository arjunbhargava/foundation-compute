#!/usr/bin/env bash
# Lists each path a PR changes that .github/CODEOWNERS assigns to a code
# owner, and fails if there is one, so that in auto mode such a PR merges
# only with the owner's bypass (docs/auto-mode.md). owned-paths.yml and
# auto_merge.sh run it. CODEOWNERS is read from the checkout this script is
# in: in Actions, the PR's base branch, as GitHub reads it. A renamed file
# counts under its old path too.
#
# Usage: .github/scripts/owned_paths.sh <PR number>
#
# Needs GITHUB_REPOSITORY, which GitHub Actions sets, and gh authenticated
# with a token that can read the PR. Exits 0 if the PR changes no owned path,
# 1 if it changes one, and 2 if it can't tell, for example when a request
# fails.
set -Eeuo pipefail
# Any failure exits 2, so that a caller can tell it from 1, an owned path.
# -E makes functions and command substitutions inherit this trap.
trap 'exit 2' ERR

# GitHub lists at most this many files for a PR (REST API, "List pull
# requests files").
max_listed_files=3000
codeowners=$(cd "$(dirname "$0")/.." && pwd)/CODEOWNERS

main() {
  if [[ -z ${GITHUB_REPOSITORY:-} || $# -ne 1 ]]; then
    echo "error: usage: GITHUB_REPOSITORY=owner/name $0 <PR number>" >&2
    exit 2
  fi
  local number=$1
  if [[ ! -f $codeowners ]]; then
    echo "error: $codeowners doesn't exist, so the owned paths are unknown." >&2
    exit 2
  fi

  local files
  files=$(gh api --paginate --slurp "repos/$GITHUB_REPOSITORY/pulls/$number/files?per_page=100")
  if (($(jq 'flatten | length' <<< "$files") >= max_listed_files)); then
    echo "error: PR #$number changes at least $max_listed_files files, the most GitHub lists, so the paths it changes are unknown. Split it into smaller PRs." >&2
    exit 2
  fi

  local owned
  owned=$(owned_paths "$(jq -r 'flatten[] | .filename, (.previous_filename // empty)' <<< "$files")")
  if [[ -z $owned ]]; then
    echo "PR #$number changes no path in .github/CODEOWNERS."
    return
  fi
  echo "PR #$number changes these paths, which .github/CODEOWNERS assigns to a code owner, so in auto mode only the owner can merge it, with the admin bypass (docs/auto-mode.md):"
  echo "$owned"
  exit 1
}

# Prints each of the given paths that a line of CODEOWNERS with an owner
# matches. Argument: the paths, one per line.
owned_paths() {
  # check-ignore rejects an empty path.
  if [[ -z $1 ]]; then
    return
  fi
  local work
  work=$(mktemp -d)
  # The pattern of each line that names an owner before any # comment. A
  # line starting with ! is skipped, as GitHub skips it.
  awk '{ owners = 0; for (i = 2; i <= NF && $i !~ /^#/; i++) owners++ }
    $1 !~ /^[#!]/ && owners > 0 { print $1 }' "$codeowners" > "$work/patterns"
  # In an empty repository, check-ignore matches only the patterns file. It
  # exits 1 when no path matches.
  git init --quiet "$work/repository"
  local status=0
  git -C "$work/repository" -c core.excludesFile="$work/patterns" \
    check-ignore --no-index --stdin <<< "$1" || status=$?
  rm -rf "$work"
  if ((status > 1)); then
    exit 2
  fi
}

main "$@"
