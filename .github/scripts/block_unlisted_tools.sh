#!/usr/bin/env bash
# Makes a CI job fail when its commands run a tool that mise.toml or
# .config/mise/conf.d/ pins but the job's MISE_ENABLE_TOOLS leaves out. mise
# ignores such a tool, so without this the command would silently run
# whatever version the runner has.
#
# For each unlisted tool, this writes an executable with the tool's command
# name that prints an error naming the tool and the list to edit, then exits
# with status 127. It puts their directory first on the PATH of the job's
# later steps. Listed tools are unaffected, because mise puts their
# directories ahead of it when it runs a task.
#
# Run it in a CI job after .cursor/install.sh, which needs the real tools, for
# example `bash .github/scripts/block_unlisted_tools.sh`. It needs
# MISE_ENABLE_TOOLS, GITHUB_JOB, GITHUB_PATH, and RUNNER_TEMP, which GitHub
# Actions sets, except MISE_ENABLE_TOOLS, which the job sets.
set -euo pipefail

: "${MISE_ENABLE_TOOLS:?MISE_ENABLE_TOOLS is not set; set it to a comma-separated list of tools in the job in .github/workflows/ci.yml}"

stub_dir=$RUNNER_TEMP/unlisted-tool-stubs
mkdir -p "$stub_dir"

# Unsetting MISE_ENABLE_TOOLS makes `mise ls --current` show every tool in
# mise.toml and .config/mise/conf.d/, and rust, which rust-toolchain.toml pins,
# whether installed or not. Without --current it would also show tools
# installed on the machine that the project doesn't pin.
for tool in $(env -u MISE_ENABLE_TOOLS mise ls --current --no-header | awk '{print $1}'); do
  case ",$MISE_ENABLE_TOOLS," in
    *",$tool,"*) continue ;;
  esac

  # A tool's command is its name without the backend, such as pipx:, except
  # rust, whose commands include cargo and rustc.
  commands=${tool##*:}
  if [[ $tool == rust ]]; then
    commands="cargo rustc"
  fi

  for command in $commands; do
    cat > "$stub_dir/$command" << EOF
#!/bin/sh
echo "::error::$command ran in the $GITHUB_JOB job, but mise.toml or .config/mise/conf.d/ pins $tool and MISE_ENABLE_TOOLS for $GITHUB_JOB does not list it, so the runner's own $command would run. Add $tool to MISE_ENABLE_TOOLS in the $GITHUB_JOB job in .github/workflows/ci.yml." >&2
exit 127
EOF
    chmod +x "$stub_dir/$command"
  done
done

echo "$stub_dir" >> "$GITHUB_PATH"
