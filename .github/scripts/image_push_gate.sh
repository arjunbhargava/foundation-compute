#!/usr/bin/env bash
# Decides whether .github/workflows/compute-image.yml may push the job image,
# which needs the two variables of the GitHub environment `release` that the
# owner sets in step 8 of "Setup for the owner" in docs/compute-jobs.md. Until
# then the workflow skips the push with a notice instead of failing.
#
# Usage: COMPUTE_JOBS_ECR_PUSH_ROLE_ARN=<ARN> COMPUTE_JOBS_AWS_REGION=<region> \
#          .github/scripts/image_push_gate.sh
#
# Appends `configured=true` or `configured=false` to the file named by
# GITHUB_OUTPUT. Always exits 0 when GITHUB_OUTPUT is set.
set -euo pipefail

: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is not set; GitHub Actions sets it, so run this in a workflow step}"

unset_variables=()
for variable in COMPUTE_JOBS_ECR_PUSH_ROLE_ARN COMPUTE_JOBS_AWS_REGION; do
  if [[ -z ${!variable:-} ]]; then
    unset_variables+=("$variable")
  fi
done

if ((${#unset_variables[@]} > 0)); then
  echo "::notice title=Image push skipped::The GitHub environment 'release' has no value for ${unset_variables[*]}. Set them as step 8 of 'Setup for the owner' in docs/compute-jobs.md says, then rerun this workflow."
  echo "configured=false" >> "$GITHUB_OUTPUT"
else
  echo "configured=true" >> "$GITHUB_OUTPUT"
fi
