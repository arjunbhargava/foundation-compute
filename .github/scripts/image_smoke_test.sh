#!/usr/bin/env bash
# Checks that the job image has what a compute job needs, from inside the
# image. docs/compute-jobs.md's acceptance criterion 18 requires it to pass on
# every PR and before a release is pushed. It uses no GPU, network, or AWS.
#
# The wrapper, `python -m compute_jobs.run`, is not checked yet: it is not in
# the library until PR 7 of that page merges, which adds its check here.
#
# Usage, from the repository root, with the image built as <image>:
#   docker run --rm --entrypoint bash -v "$PWD/.github/scripts:/scripts:ro" <image> /scripts/image_smoke_test.sh
set -euo pipefail

# The runtime library's version, 12.8, is the one in the Dockerfile's base
# image; the wrapper compares the machine's driver with it.
cuda_runtime_pattern='/usr/local/cuda/targets/x86_64-linux/lib/libcudart.so.12.8.*'

main() {
  check "the user is root, which SkyPilot needs" test "$(id -u)" -eq 0
  check "the system is Ubuntu 24.04" grep -qx 'VERSION_ID="24.04"' /etc/os-release
  check "the CUDA 12.8 runtime library is installed" compgen -G "$cuda_runtime_pattern"
  check "uv runs" uv --version
  check "git, curl, and rsync are installed" bash -c 'command -v git curl rsync'
  check "python is the image's environment" test "$(command -v python)" = /opt/compute-jobs/bin/python
  check "that Python is 3.12 or later" python -c 'import sys; sys.exit(sys.version_info < (3, 12))'
  check "compute_jobs reports a release version" python -c '
import re
from compute_jobs import installed_version
assert re.fullmatch(r"\d+\.\d+\.\d+", installed_version()), installed_version()
'
  check "compute_jobs ships every format's schema" python -c '
from compute_jobs.schemas import CURRENT_MAJOR, load_schema
for format_name, major in CURRENT_MAJOR.items():
    load_schema(format_name, major)
'
  echo "The image's smoke test passed."
}

# Arguments: what the check shows, then the command that fails if it doesn't.
check() {
  local description=$1
  shift
  if ! "$@" > /dev/null; then
    echo "FAIL: $description (command: $*)" >&2
    exit 1
  fi
  echo "ok: $description"
}

main "$@"
