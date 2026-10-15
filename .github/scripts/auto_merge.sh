#!/usr/bin/env bash
# Turns GitHub's auto-merge on for each agent PR given once Bugbot has
# reviewed the PR's head commit, and off while it hasn't, so that a PR never
# merges before Bugbot's findings on its latest commit can block it
# (docs/auto-mode.md). .github/workflows/auto-merge.yml runs it.
#
# A PR this script doesn't manage is left alone: one that isn't open, was
# opened by Dependabot, comes from a fork, merges into a branch other than the
# default branch, or has no agent label. For the others, auto-merge is turned
# off while the PR is a draft, has the needs-human-review label, Bugbot
# hasn't finished reviewing its head commit, or the PR changes a path in .github/CODEOWNERS, which only the
# owner merges (owned_paths.sh). Otherwise it is turned on, with a merge
# commit (D6 in docs/template-plan.md), unless the repository's "Allow
# auto-merge" setting is off. When the PR already meets every requirement,
# gh merges it at once instead of turning on auto-merge.
#
# Usage: .github/scripts/auto_merge.sh <PR number>...
#
# Needs GITHUB_REPOSITORY, which GitHub Actions sets, and gh authenticated
# with a token that can read check runs and merge PRs: in Actions, GH_TOKEN
# with checks: read, contents: write, and pull-requests: write. It fails if a
# request fails; if GitHub refuses to list Bugbot's check runs, or
# owned_paths.sh can't tell which paths the PR changes, it first turns
# auto-merge off, as it does when Bugbot hasn't reviewed.
set -euo pipefail

: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set; set it to the repository as owner/name}"

# The Cursor GitHub App, which reports the Cursor Bugbot check. Another app
# or a workflow can name a check "Cursor Bugbot", but can't report it as this
# app.
bugbot_app_id=1210556
owned_paths_script=$(cd "$(dirname "$0")" && pwd)/owned_paths.sh

main() {
  local repository
  repository=$(gh api "repos/$GITHUB_REPOSITORY")
  local number
  for number in "$@"; do
    update_auto_merge "$number" "$repository"
  done
}

# Turns auto-merge on or off for one PR, or leaves it alone, and prints what
# it did and why. Arguments: the PR's number, and the repository as JSON from
# the REST API.
update_auto_merge() {
  local number=$1 repository=$2
  local pr
  pr=$(gh api "repos/$GITHUB_REPOSITORY/pulls/$number")

  local reason
  reason=$(reason_to_leave_alone "$pr" "$(jq -r .default_branch <<< "$repository")")
  if [[ -n $reason ]]; then
    echo "PR #$number: left alone, because $reason."
    return
  fi

  local head_sha auto_merge_on bugbot_check_runs check_runs_refused=false
  head_sha=$(jq -r .head.sha <<< "$pr")
  auto_merge_on=$(jq '.auto_merge != null' <<< "$pr")
  # A refused request leaves Bugbot's review unknown, so auto-merge goes off,
  # as for no review, and then the run fails, so that someone sees why.
  if bugbot_check_runs=$(gh api --method GET "repos/$GITHUB_REPOSITORY/commits/$head_sha/check-runs" \
    -f app_id="$bugbot_app_id" -f check_name="Cursor Bugbot"); then
    reason=$(reason_to_wait "$pr" "$bugbot_check_runs")
  else
    check_runs_refused=true
    reason="GitHub refused to list Bugbot's check runs on $head_sha; the job's token needs checks: read"
  fi
  # The required owned-paths check alone isn't enough (docs/auto-mode.md).
  local owned_paths_status=0 owned_paths_unknown=false
  if [[ -z $reason ]]; then
    "$owned_paths_script" "$number" || owned_paths_status=$?
    case $owned_paths_status in
      0) ;;
      1) reason="it changes a path in .github/CODEOWNERS, listed above, so only the owner merges it" ;;
      *)
        owned_paths_unknown=true
        reason="owned_paths.sh couldn't tell which paths it changes, as it says above"
        ;;
    esac
  fi
  if [[ -n $reason ]]; then
    if [[ $auto_merge_on == true ]]; then
      gh pr merge "$number" --repo "$GITHUB_REPOSITORY" --disable-auto
      echo "PR #$number: turned auto-merge off, because $reason."
    else
      echo "PR #$number: auto-merge stays off, because $reason."
    fi
    if [[ $check_runs_refused == true || $owned_paths_unknown == true ]]; then
      return 1
    fi
    return
  fi

  if [[ $(jq .allow_auto_merge <<< "$repository") != true ]]; then
    echo "PR #$number: left alone, because \"Allow auto-merge\" is off in Settings > General > Pull Requests."
    return
  fi
  if [[ $auto_merge_on == true ]]; then
    echo "PR #$number: auto-merge is already on."
    return
  fi
  gh pr merge "$number" --repo "$GITHUB_REPOSITORY" --auto --merge --match-head-commit "$head_sha"
  echo "PR #$number: Bugbot has reviewed $head_sha, so auto-merge is on, or the PR is merged if it already met every requirement."
}

# Prints why this script doesn't manage the PR, or nothing if it does.
# Arguments: the PR as JSON from the REST API, and the default branch.
reason_to_leave_alone() {
  jq -r --arg repository "$GITHUB_REPOSITORY" --arg default_branch "$2" '
    if .state != "open" then "it is \(.state)"
    elif .user.login == "dependabot[bot]" then "Dependabot opened it"
    elif .head.repo.full_name != $repository then "it comes from a fork"
    elif .base.ref != $default_branch then "it merges into \(.base.ref), not \($default_branch)"
    elif (any(.labels[]; .name == "agent") | not) then "it has no agent label"
    else empty
    end' <<< "$1"
}

# Prints why the PR mustn't merge yet, or nothing if it may. Arguments: the PR,
# and Bugbot's check runs on its head commit, as JSON from the REST API.
reason_to_wait() {
  if [[ $(jq .draft <<< "$1") == true ]]; then
    echo "it is a draft"
  elif jq -e 'any(.labels[]; .name == "needs-human-review")' <<< "$1" > /dev/null; then
    echo "it has the needs-human-review label, so the owner reviews and merges it"
  elif ! bugbot_reviewed "$2"; then
    echo "Bugbot hasn't finished reviewing its head commit, $(jq -r .head.sha <<< "$1")"
  fi
}

# Succeeds if the latest of Bugbot's check runs finished a review. Bugbot
# reports the conclusion neutral both when it posts findings and when its run
# is cancelled, so only the summary tells a review from a cancelled run.
# Argument: Bugbot's check runs on a commit, as JSON from the REST API.
bugbot_reviewed() {
  jq -e '.check_runs | max_by(.id) |
    .status == "completed" and (.output.summary // "" | contains("Bugbot completed review"))' <<< "$1" > /dev/null
}

main "$@"
