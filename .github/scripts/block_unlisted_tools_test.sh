#!/usr/bin/env bash
# Checks that .github/scripts/block_unlisted_tools.sh blocks a tool that
# mise.toml or .config/mise/conf.d/ pins and MISE_ENABLE_TOOLS leaves out,
# with an error that names the tool and the list to edit, and leaves a listed
# tool alone. It needs mise on PATH, but not the tools mise pins.
#
# Usage: .github/scripts/block_unlisted_tools_test.sh
set -euo pipefail

script=$(cd "$(dirname "$0")" && pwd)/block_unlisted_tools.sh
cd "$(dirname "$0")/../.."
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

export MISE_ENABLE_TOOLS=uv GITHUB_JOB=test-job RUNNER_TEMP=$work GITHUB_PATH=$work/github-path
bash "$script"
stub_dir=$(cat "$GITHUB_PATH")

if [[ -e $stub_dir/uv ]]; then
  echo "FAIL: block_unlisted_tools.sh blocked uv, which MISE_ENABLE_TOOLS lists." >&2
  exit 1
fi

# Every project pins jq and pipx:copier in mise.toml. Only one with Rust pins
# rust, whose commands are cargo and rustc rather than its name.
blocked_commands=(jq copier)
if [[ -f rust-toolchain.toml ]]; then
  blocked_commands+=(cargo)
fi

for blocked in "${blocked_commands[@]}"; do
  status=0
  message=$("$stub_dir/$blocked" 2>&1) || status=$?
  if ((status == 0)) || [[ $message != *"$blocked"* || $message != *"MISE_ENABLE_TOOLS"* || $message != *"test-job job in .github/workflows/ci.yml"* ]]; then
    echo "FAIL: $blocked exited with status $status and printed '$message'; expected a non-zero status and an error naming $blocked, MISE_ENABLE_TOOLS, and the job's entry in ci.yml." >&2
    exit 1
  fi
done

echo "block_unlisted_tools.sh blocked ${blocked_commands[*]}, and left uv alone."
