#!/usr/bin/env bash
# Applies the repository settings that GitHub doesn't copy from a template
# (T4 in the plan in the template repository, https://github.com/arjunbhargava/foundation). Safe to rerun.
#
#   1. Merge commits become the only merge method (D6). Both review rulesets
#      allow only merge commits too, but admins can bypass them.
#   2. main-checks.json, template-checks.json if it exists, and one review
#      ruleset are each created, or updated if a ruleset with the same name
#      exists. Only the template repository has template-checks.json, which
#      requires the template-ok check of .github/workflows/template.yml;
#      copier.yml leaves both out of projects. The review ruleset is
#      main-review.json, or main-review-auto.json with --auto
#      (docs/auto-mode.md). In the JSON, integration_id 15368 is the GitHub
#      Actions app, so only Actions can report the required checks, and
#      actor_id 5 with actor_type RepositoryRole is the admin role.
#   3. Without --auto, if the auto-mode ruleset exists, each approval by
#      github-actions[bot] on an open PR is dismissed: main: review would count
#      it as a person's, so a PR that auto mode held back on an unresolved
#      review thread would merge. After step 2, approve-agent-prs.yml gives no
#      new ones.
#   4. The other review ruleset, if it exists, is disabled. It is disabled
#      after step 2, so a failure between the two leaves both in force rather
#      than neither.
#   5. Secret scanning and push protection are turned on. This step is last
#      because it fails on a private repository without GitHub Secret
#      Protection, and the steps before it still apply.
#
# Usage: mise exec -- .github/rulesets/apply.sh [--dry-run] [--auto] [owner/repo]
#
# Needs gh logged in as a repository admin. The repository defaults to the
# one for the current directory. --dry-run prints each change instead of
# making it; it still reads the existing rulesets to decide between create
# and update. --auto turns auto mode on; running without it turns it off.
#
# Switching to a merge queue, which GitHub offers only to repositories owned
# by an organization:
#   1. In main-checks.json, and in template-checks.json if it exists, set
#      strict_required_status_checks_policy to false. Add this rule to
#      main-checks.json. Apart from merge_method, the values are GitHub's
#      defaults.
#        { "type": "merge_queue", "parameters": {
#            "merge_method": "MERGE", "grouping_strategy": "ALLGREEN",
#            "check_response_timeout_minutes": 60, "max_entries_to_build": 5,
#            "max_entries_to_merge": 5, "min_entries_to_merge": 1,
#            "min_entries_to_merge_wait_minutes": 5 } }
#   2. Rerun this script. CI already runs on merge_group.
set -euo pipefail
cd "$(dirname "$0")"

dry_run=false
review_file=main-review.json
unused_review_file=main-review-auto.json
while [[ ${1:-} == --* ]]; do
  case $1 in
    --dry-run) dry_run=true ;;
    --auto)
      review_file=main-review-auto.json
      unused_review_file=main-review.json
      ;;
    *)
      echo "error: unknown option $1. The options are --dry-run and --auto." >&2
      exit 2
      ;;
  esac
  shift
done
repo=${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}

# Makes one change, or prints it under --dry-run. Arguments: a description,
# the HTTP method, and the API path. The JSON body is read from stdin.
apply() {
  local description=$1 method=$2 path=$3
  if $dry_run; then
    echo "Would $description: $method $path"
    jq .
  else
    gh api --method "$method" "$path" --input - --silent
    echo "Done: $description"
  fi
}

apply "allow only merge commits" PATCH "repos/$repo" << 'EOF'
{ "allow_merge_commit": true, "allow_squash_merge": false, "allow_rebase_merge": false }
EOF

existing_rulesets=$(gh api --paginate "repos/$repo/rulesets?includes_parents=false")
# Prints the ID of the existing ruleset named in a ruleset file, or nothing.
existing_ruleset_id() {
  jq -r --arg name "$(jq -r .name "$1")" '.[] | select(.name == $name) | .id' <<< "$existing_rulesets"
}

ruleset_files=(main-checks.json)
if [[ -f template-checks.json ]]; then
  ruleset_files+=(template-checks.json)
fi
ruleset_files+=("$review_file")
for file in "${ruleset_files[@]}"; do
  name=$(jq -r .name "$file")
  id=$(existing_ruleset_id "$file")
  if [[ -n $id ]]; then
    apply "update ruleset \"$name\" (id $id)" PUT "repos/$repo/rulesets/$id" < "$file"
  else
    apply "create ruleset \"$name\"" POST "repos/$repo/rulesets" < "$file"
  fi
done

# Dismisses each approval by github-actions[bot] on an open PR (step 3).
dismiss_approval_workflow_approvals() {
  local open_prs number approval_ids review_id
  open_prs=$(gh api --paginate --slurp "repos/$repo/pulls?state=open" | jq -r 'flatten[].number')
  for number in $open_prs; do
    approval_ids=$(gh api --paginate --slurp "repos/$repo/pulls/$number/reviews" |
      jq -r 'flatten[] | select(.user.login == "github-actions[bot]" and .state == "APPROVED") | .id')
    for review_id in $approval_ids; do
      apply "dismiss the approval github-actions[bot] gave PR #$number (review $review_id)" PUT \
        "repos/$repo/pulls/$number/reviews/$review_id/dismissals" << 'EOF'
{ "message": "Auto mode is off, so this PR needs a person's approval (docs/auto-mode.md).", "event": "DISMISS" }
EOF
    done
  done
}

unused_id=$(existing_ruleset_id "$unused_review_file")
if [[ -n $unused_id && $unused_review_file == main-review-auto.json ]]; then
  dismiss_approval_workflow_approvals
fi
if [[ -n $unused_id ]]; then
  apply "disable ruleset \"$(jq -r .name "$unused_review_file")\" (id $unused_id)" PUT "repos/$repo/rulesets/$unused_id" << 'EOF'
{ "enforcement": "disabled" }
EOF
fi

apply "turn on secret scanning with push protection" PATCH "repos/$repo" << 'EOF'
{
  "security_and_analysis": {
    "secret_scanning": { "status": "enabled" },
    "secret_scanning_push_protection": { "status": "enabled" }
  }
}
EOF
