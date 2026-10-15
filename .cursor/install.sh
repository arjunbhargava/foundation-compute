#!/usr/bin/env bash
# Sets up a machine to match CI: installs the pinned mise if it is missing,
# then the tools and dependencies that mise.toml and .config/mise/conf.d/
# list. People run it once after cloning, CI jobs run it first, and cloud
# agents run it from environment.json. Safe to rerun: a second run downloads
# nothing.
#
# Usage: bash .cursor/install.sh
#
# CI's language and docs jobs set MISE_ENABLE_TOOLS, which mise reads, to the
# pinned tools that they use. The script then installs only those, and
# skips `mise run setup`, which needs every language's tools; each job runs
# its own language's setup task instead.
#
# Supports macOS and Linux (glibc), each on x86-64 or arm64. Keep it working
# under bash 3.2, the version macOS ships: no associative arrays.
#
# mise goes to ~/.local/bin/mise, which needs no sudo, unless the pinned
# version is already on PATH. MISE_INSTALL_PATH, the variable mise's own
# installer reads, overrides that path; sudo is used only when the user can't
# write its directory. Cloud agents set it to /usr/local/bin/mise, because
# their shells don't have ~/.local/bin on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."

# To bump mise: set mise_version, then copy each asset's sha256 from
# https://github.com/jdx/mise/releases/download/v<version>/SHASUMS256.txt.
mise_version=2026.9.18
mise_asset=""
mise_sha256=""
case "$(uname -s) $(uname -m)" in
  "Linux x86_64")
    mise_asset=linux-x64
    mise_sha256=d24fe0bf7e613824ad99f7b8dac3f2b381a37b9f75f84dd250855217095a8de4
    ;;
  "Linux aarch64" | "Linux arm64")
    mise_asset=linux-arm64
    mise_sha256=2142433ae70decffc5fa24bd160e47931e33f55eb031d128beb97cbae634d168
    ;;
  "Darwin x86_64")
    mise_asset=macos-x64
    mise_sha256=02d8ba561847f996925e361262c0610a24f59fcd9e06ba9ed0b6022e19b317c3
    ;;
  "Darwin arm64")
    mise_asset=macos-arm64
    mise_sha256=484c135bd4329975d608d3f77e26c2ece5d2f5590f18ca71f44440294f8cfa6f
    ;;
esac
mise_install_path=${MISE_INSTALL_PATH:-$HOME/.local/bin/mise}

pinned_mise=""
for candidate in "$(command -v mise || true)" "$mise_install_path"; do
  if [[ -x $candidate && $("$candidate" --version 2> /dev/null) == "$mise_version "* ]]; then
    pinned_mise=$candidate
    break
  fi
done

if [[ -n $pinned_mise ]]; then
  echo "mise $mise_version is already installed at $pinned_mise; nothing to download."
else
  if [[ -z $mise_asset ]]; then
    echo "error: .cursor/install.sh can download mise only for macOS and Linux on x86-64 or arm64, not $(uname -s) $(uname -m)." >&2
    echo "Install mise $mise_version yourself (https://mise.jdx.dev/installing-mise.html), put it on PATH, and rerun this script." >&2
    exit 1
  fi

  download=$(mktemp)
  trap 'rm -f "$download"' EXIT
  curl -fsSL -o "$download" \
    "https://github.com/jdx/mise/releases/download/v$mise_version/mise-v$mise_version-$mise_asset"

  # macOS has shasum but not sha256sum.
  if command -v sha256sum > /dev/null; then
    download_sha256=$(sha256sum "$download")
  else
    download_sha256=$(shasum -a 256 "$download")
  fi
  download_sha256=${download_sha256%% *}
  if [[ $download_sha256 != "$mise_sha256" ]]; then
    echo "error: the downloaded mise-v$mise_version-$mise_asset has sha256 $download_sha256, but .cursor/install.sh pins $mise_sha256, so nothing was installed." >&2
    echo "Rerun to retry the download. If it fails again, check both values against the release's SHASUMS256.txt before changing the pin." >&2
    exit 1
  fi

  install_dir=$(dirname "$mise_install_path")
  mkdir -p "$install_dir"
  if [[ -w $install_dir ]]; then
    install -m 755 "$download" "$mise_install_path"
  else
    sudo install -m 755 "$download" "$mise_install_path"
  fi
  pinned_mise=$mise_install_path
  echo "Installed mise $mise_version at $pinned_mise."
fi

"$pinned_mise" install
if [[ -z ${MISE_ENABLE_TOOLS:-} ]]; then
  "$pinned_mise" run setup
fi

if [[ $(mise --version 2> /dev/null) != "$mise_version "* ]]; then
  mise_dir=$(dirname "$pinned_mise")
  # GitHub Actions puts each directory listed in $GITHUB_PATH on PATH for the
  # job's later steps.
  if [[ -n ${GITHUB_PATH:-} ]]; then
    echo "$mise_dir" >> "$GITHUB_PATH"
  else
    echo
    echo "Setup is complete, but running 'mise' finds $(command -v mise || echo nothing) rather than $pinned_mise."
    echo "Add this line to ~/.zshrc for zsh, ~/.bashrc for bash on Linux, or ~/.bash_profile for bash on macOS, then open a new terminal:"
    echo "  export PATH=\"$mise_dir:\$PATH\""
  fi
fi
