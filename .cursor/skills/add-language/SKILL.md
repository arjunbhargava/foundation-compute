---
name: add-language
description: >
  Checklist for adding a programming language to a project: a documented
  module, a test, format, lint, and type checks, the docs build, a CI job, and
  a test command for the package. Use when a project adds its first code in a
  language it doesn't have yet.
---

# Add a language

These are the steps Stage 2 of the plan in the template repository (https://github.com/arjunbhargava/foundation) took for Python,
TypeScript, Rust, and C and C++ (tasks T6–T9), as a checklist for a project
that adds a language later. Everything lands in one PR: the one that adds the
first code in the language.

## Code and checks

- [ ] A small module with doc comments: the project's first real code in the
      language, or an example that exists only to prove the checks work and
      is deleted when real code arrives.
- [ ] One test, following the `testing` skill.
- [ ] Format, lint, and type checks, with warnings treated as errors. `fmt`
      fixes everything the format check reports, including import order if
      the check covers it.
- [ ] A module boundary check in `lint:<language>`, with one rule that a
      plausible mistake in the example breaks, such as library code
      importing a development-only dependency. Where the build already
      enforces the rule, as Cargo and CMake do, the build is the check. Add
      the language to the "Module boundaries" list under "Where code lives"
      in `AGENTS.md`, naming the file and section its rules go in.
- [ ] Each tool checks only the files it should. Exclude `.cursor/`, which
      people write: ruff also formats Python code blocks in Markdown, so
      `pyproject.toml` excludes it. Expect overlap at the root: Biome checks
      every root JSON file, so `CMakePresets.json` must pass
      `lint:typescript`.
- [ ] The language's block in `docs/build.sh` and its coverage gate,
      following the `source-docs` skill.

## Tools and versions

Each version has exactly one source. Development tools, such as the
formatter, linter, type checker, test runner, and docs generator, go in the
language's lockfile, where Dependabot updates them. A runtime goes in the
version file the language's own tools read, if it has one: `.python-version`
for uv, and `rust-toolchain.toml` for rustup. The language's
`.config/mise/conf.d/<language>.toml` pins the rest: other runtimes, package
managers, and tools that no package manager in the repository installs. A
tool that more than one language, or the docs build, runs goes in `mise.toml`
instead. This is where each version lives:

| Language | Runtime | Package manager | Development tools |
|---|---|---|---|
| Python | `.python-version`, which uv installs | uv, in `mise.toml` | `uv.lock`, from the `dev` group in `pyproject.toml` |
| TypeScript | Node, in `typescript.toml` | pnpm, in `typescript.toml` | `pnpm-lock.yaml`, from exact `devDependencies` in `package.json` |
| Rust | `rust-toolchain.toml`, with clippy and rustfmt, which mise installs | cargo, from the toolchain | cargo-deny, in `rust.toml` |
| C and C++ | The compiler, `g++`, from the OS | None | CMake, Ninja, clang-format, clang-tidy, and Doxygen in `cpp.toml`; Breathe in `docs/uv.lock` |

- [ ] Each of the new language's versions in one file, chosen as above.
      Delete any second pin a tool writes, such as the `packageManager` and
      `devEngines` fields that `pnpm init` adds to `package.json`.
- [ ] Each version the PR pins was released at least 7 days ago, matching
      the Dependabot cooldown below. Dependabot can't read mise's files, so
      their pins are bumped by hand.
- [ ] Each tool installs and works on every platform the `install-script` CI
      job runs `mise run check` on: Linux x86-64, Linux arm64, and macOS. The
      PR adds a file to `.config/mise/conf.d/`, so CI runs that job, which is
      the only test of the platforms you don't have. When mise's default
      source for a tool lacks a platform, use a backend that has it, such as
      `conda:` for conda-forge, as `cpp.toml` does for Doxygen, or `pipx:`
      for PyPI wheels.
- [ ] A tool that no mise backend provides, such as a compiler, comes from the
      OS. `.cursor/install.sh` doesn't install OS packages, because that
      needs sudo, so say why under "Requirements" in `AGENTS.md`, and give
      each OS's install command under "Set up a local machine" in
      `README.md`. Name the tool so that it resolves to a working one on
      every platform and on the cloud agent image: the presets name `g++`,
      because the image's `c++` is a Clang without the C++ standard library.

## Commands

- [ ] `fmt:<language>`, `lint:<language>`, `test:<language>`, and
      `setup:<language>` tasks in `.config/mise/conf.d/<language>.toml`,
      which `fmt`, `lint`, `test`, and `setup` in `mise.toml` pick up. Don't
      edit the shared tasks. `setup:<language>` installs from the lockfile in
      a mode that fails when it doesn't match the manifest, such as
      `uv sync --locked`, so the language's CI job fails on a manifest edited
      without relocking. A language with no package manager has no
      `setup:<language>`.
- [ ] `test:<language>` runs the tests of every package in the language, and
      passes arguments after `--` to the test runner. Add both tasks to the
      Commands table in `AGENTS.md`, with an example of passing arguments to
      the test runner.

## CI and repository settings

- [ ] Its CI job, added as the "To add a language" comment in
      `.github/workflows/ci.yml` says. The language's output in the `changes`
      job lists every file whose change can alter a check's result: its
      directory, manifest, lockfile, and `.config/mise/conf.d/` file, each
      root config file its tools read (such as `tsconfig.json` or
      `.clang-tidy`), and each file that only another job reads. The `docs`
      job runs only when some output is true, so `Doxyfile`, which only the
      docs build reads, is in the `cpp` output.
- [ ] The job's `MISE_ENABLE_TOOLS` lists each tool that `mise.toml` or
      `.config/mise/conf.d/` pins and its commands run, and
      `.cursor/install.sh` installs only those. The job runs
      `mise run setup:<language>`, if the language has one, before lint
      and test. Add the tools the language's docs block runs to the `docs`
      job's list too. mise ignores a tool missing from a list, so the job
      runs `.github/scripts/block_unlisted_tools.sh` after `.cursor/install.sh`.
      The script puts a stub command on the PATH for each pinned tool the
      list leaves out, and a command that runs the stub fails with status 127
      and an error naming the tool and the list to edit. `install.sh` runs
      before the script, so the script can't catch a tool that the install
      itself needs: the C and C++ job lists `uv` because mise installs the
      `pipx:` tools with it, and without it falls back to the runner's pipx
      without any error.
      To check a list, set `MISE_ENABLE_TOOLS` to it locally and run
      `mise exec -- which <tool>` for each tool the job's commands call: each
      must resolve inside mise's directory. Rust's tools resolve to rustup's
      proxies in `~/.cargo/bin` instead, which read `rust-toolchain.toml`.
- [ ] Its language in the `languages` job in `.github/workflows/codeql.yml`,
      listed when its manifest exists.
- [ ] Its package ecosystem in `.github/dependabot.yml`, with the weekly
      schedule and 7-day `cooldown` that every entry has. A language with no
      package manager has no ecosystem: say under "Where code lives" in
      `AGENTS.md` how its first dependency is pinned, following the
      `dependencies` rule, and which ecosystem to add then.
- [ ] Its build output in `.gitignore`, its lockfile marked
      `linguist-generated` in `.gitattributes`, and its manifest and lockfile
      in the `globs` of the `dependencies` rule, if they aren't there
      already. A person makes the rule change, since people edit rules.

## Where the languages are listed

- [ ] Its directory and config files under "Where code lives" in
      `AGENTS.md`.
- [ ] The language, and its example, in the lines that list them: the first
      paragraph of `README.md` and the sentence below the Commands table in
      `AGENTS.md`.
- [ ] `mise run lint:language-listings` passes. It takes the languages from
      the files in `.config/mise/conf.d/`, and fails naming each place in
      this checklist that must list every language but lacks one: the
      language's tasks; its output, job, and `ci-ok` entry in `ci.yml`; its
      line in `codeql.yml`; its block in `docs/build.sh`; its page in
      `docs/api/`; its rows in the Commands table in `AGENTS.md`; and, in
      the template repository, its places in `copier.yml`, `template.toml`,
      `template.yml`, and `README.md`'s lines about Copier's questions. It
      can't check a place that names the language by its display name, such
      as the two above, so check those by hand.

## In the template repository

The template repository, which has `copier.yml`, also needs these:

- [ ] In `copier.yml`: a yes/no question for the language, before `cpp`,
      whose validator stays last and names every language; the language in
      `language_names`; and an `_exclude` block listing its files.
- [ ] Its lines in `AGENTS.md`, `README.md`, and `.github/dependabot.yml`
      written in their `.jinja` twins, inside `{% if <language> %}` blocks.
      `mise run template:sync` then renders the root copies.
- [ ] In `.config/mise/conf.d/template.toml`: `--data <language>=true` in
      `template:check` and `template:sync`; the language in the variant lists
      of `test:template` and `template:check-update`; and its files, name,
      and Dependabot entries in `test:template`.
- [ ] In `.github/workflows/template.yml`: `--data <language>=true` in the
      variant with every language, and a variant for the language alone.

## Show each check failing

Every check must fail when broken. The PR shows this in CI by breaking each
check once, for example by adding an undocumented public function, then
reverting:

1. Make each break locally first, and confirm that it fails the check it
   targets.
2. Push one temporary commit per break, each on top of the last. Order them
   from the check that runs last to the one that runs first, so that each new
   break is the first failure in its run.
3. Wait for each run to finish before pushing the next commit, because a new
   push cancels the PR's older run. The PR edits `ci.yml`, so every job
   runs, and a break can fail several, such as `docs` and `install-script`;
   read the language's own job.
4. CI doesn't run while the PR conflicts with `main`, so merge `main` first.
5. When two checks run in one step, the first can catch a break meant for the
   second. clang-tidy reports compiler warnings, so showing `g++`'s `-Werror`
   took a warning that only GCC reports. Pick a break that only the target
   check catches, and confirm in the log which check failed.
6. Break a check that treats warnings as errors with a warning, not an error,
   so that the run shows warnings fail.
7. Revert every break in one commit, and check that the tree then matches the
   commit before the first break. Under "Verified", give each break one
   line: the check it broke, and a link to its CI run.
