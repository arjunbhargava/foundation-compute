# The job image: every compute job runs in it (docs/compute-jobs.md, "The job
# image"). Build it from the repository root, at the release tag or commit
# whose `lib/` should be installed:
#
#   docker build -t compute-jobs-job .
#
# SkyPilot needs a Debian-based image whose user is root, which this is.
# Dependabot's docker ecosystem updates both digests below.

# CUDA 12.8 runtime on Ubuntu 24.04. `compute_jobs.run` compares the
# machine's driver against this version before it runs a job's command.
FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04@sha256:ebef3c171eeef0298e4eb2e4be843105edf3b8b0ac45e0b43acee358e8046867

# The uv version is the one mise.toml pins.
COPY --from=ghcr.io/astral-sh/uv:0.12.21@sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711 /uv /uvx /usr/local/bin/

# python3 is Ubuntu 24.04's 3.12, which compute-jobs supports (>=3.12).
# curl, git, and rsync are what a job's setup and SkyPilot's file sync use.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl git python3 rsync \
    && rm -rf /var/lib/apt/lists/*

# The library comes from the checkout being built, so the image's wrapper is
# always the same version as the tag. The environment is outside /root and
# the job's working directory, so a job's own `uv sync` doesn't touch it.
COPY lib /tmp/compute-jobs-source
RUN uv venv /opt/compute-jobs --python /usr/bin/python3 \
    && uv pip install --python /opt/compute-jobs/bin/python /tmp/compute-jobs-source \
    && rm -rf /tmp/compute-jobs-source

# Puts `python -m compute_jobs.run` on the PATH.
ENV PATH=/opt/compute-jobs/bin:$PATH
