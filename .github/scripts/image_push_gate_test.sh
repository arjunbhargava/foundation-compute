#!/usr/bin/env bash
# Tests .github/scripts/image_push_gate.sh: each case runs it with some of the
# release environment's variables set, and checks the `configured` output and
# whether the skip notice, which names each unset variable, is printed.
#
# Usage: mise run test:image-push-gate-script
set -euo pipefail

script=$(cd "$(dirname "$0")" && pwd)/image_push_gate.sh
failures=0

main() {
  local role_arn=arn:aws:iam::123456789012:role/compute-jobs-image-push

  expect_gate both_variables_set "$role_arn" us-east-1 true ""
  expect_gate role_unset "" us-east-1 false "COMPUTE_JOBS_ECR_PUSH_ROLE_ARN"
  expect_gate region_unset "$role_arn" "" false "COMPUTE_JOBS_AWS_REGION"
  expect_gate both_unset "" "" false "COMPUTE_JOBS_ECR_PUSH_ROLE_ARN COMPUTE_JOBS_AWS_REGION"

  if ((failures > 0)); then
    exit 1
  fi
  echo "image_push_gate.sh gave the expected output in all 4 cases."
}

# Arguments: the case's name, the role ARN and region it sets (empty means
# unset), the expected `configured` value, and the text of the notice that
# must be printed, empty if none.
expect_gate() {
  local name=$1 role_arn=$2 region=$3 expected_configured=$4 expected_notice=$5
  local output_file printed configured
  output_file=$(mktemp)
  printed=$(
    COMPUTE_JOBS_ECR_PUSH_ROLE_ARN=$role_arn COMPUTE_JOBS_AWS_REGION=$region \
      GITHUB_OUTPUT=$output_file "$script" 2>&1
  )
  configured=$(cat "$output_file")
  rm -f "$output_file"

  local notice_matches=true
  if [[ -z $expected_notice && -n $printed ]]; then
    notice_matches=false
  elif [[ -n $expected_notice && $printed != *"::notice title=Image push skipped::"*"has no value for $expected_notice."* ]]; then
    notice_matches=false
  fi
  if [[ $configured != "configured=$expected_configured" || $notice_matches != true ]]; then
    echo "FAIL: $name: output was '$configured' (expected configured=$expected_configured), printed:
$printed
(expected notice naming: ${expected_notice:-no notice})" >&2
    failures=$((failures + 1))
  fi
}

main "$@"
