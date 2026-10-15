# The setup script

`.cursor/install.sh` sets up a machine to match CI: it installs the pinned
mise, then the tools and dependencies the project pins. Run it from anywhere
in the repository with `bash .cursor/install.sh`. A second run downloads
nothing.

## What it does

1. Looks for the mise version pinned at the top of the script, on PATH and at
   the install path. If it finds one, nothing is downloaded.
2. Otherwise downloads that version from mise's GitHub releases for the
   machine's OS and CPU, and checks the download's sha256 against the one
   pinned in the script. On a mismatch it installs nothing and exits with an
   error.
3. Installs mise to `~/.local/bin/mise`, or to `$MISE_INSTALL_PATH` if that
   is set. It uses `sudo` only when the directory isn't writable.
4. Runs `mise install` for the tools pinned in `mise.toml` and
   `.config/mise/conf.d/`, then `mise run setup`. CI jobs set
   `MISE_ENABLE_TOOLS`, and then the script installs only those tools and
   skips `mise run setup`.
5. Checks that `mise` on PATH is the pinned version. If it isn't, the script
   doesn't edit any shell file. In GitHub Actions it appends mise's directory
   to `$GITHUB_PATH`; elsewhere it prints the `export PATH=` line to add to
   `~/.zshrc`, `~/.bashrc`, or `~/.bash_profile`.

## Where it runs

| Where | How the script runs |
|---|---|
| Cursor cloud agent | Automatically, when the machine is set up: `.cursor/environment.json` runs `MISE_INSTALL_PATH=/usr/local/bin/mise bash .cursor/install.sh`. `/usr/local/bin` is on every agent shell's PATH, and `~/.local/bin` is not. |
| Your machine | You run `bash .cursor/install.sh` once after cloning. |
| This repository's CI | Each job in `.github/workflows/ci.yml` runs it first. |
| A dev container, another CI system, or a VM | Run the same command on Linux or macOS, with `MISE_INSTALL_PATH` set to a directory on PATH so that the later steps find `mise`. |

## What it doesn't cover

- Operating systems and CPUs other than macOS and glibc Linux on x86-64 or
  arm64. On another machine the script exits with an error that names
  [mise's installation page](https://mise.jdx.dev/installing-mise.html).
- OS packages, because installing them needs `sudo`. C and C++ need `g++`
  from the OS.
- The GitHub CLI, `gh`, which `.github/rulesets/apply.sh` needs.
- Configuration files for dev containers or for CI systems other than
  GitHub Actions: the repository has none.
