---
name: source-docs
description: >
  Build code documentation from source, in any language, into one site. Use
  when writing the first code in a repo, adding a language to a repo, or
  changing the docs build or its gates. What a doc comment contains, and the
  checks every PR runs, are in the always-applied `docs-from-source` rule.
---

# Docs built from source

Reference documentation is compiled from the source, the way Sphinx autodoc
does it. It is never written by hand. Docstrings and doc comments are the single
source of truth for what an API does. The build turns them into one site,
together with the hand-written explanation pages and architecture diagrams. If
the code and docs disagree, the build fails.

## Rules

1. **Never hand-write API reference.** Hand-written pages are only
   explanation, how-to, or tutorial content (see `architecture-docs`), and they
   link into the generated reference.
   They link only to other docs pages or absolute URLs, and name other repo
   files as code paths (`docs/diagrams/`), because the strict build rejects
   links it can't resolve.
2. **One command builds everything.** `mise run docs` runs `docs/build.sh`
   with the pinned tools, and the script runs every language's generator, then
   the hub build. Agents, CI, and humans all run the same command.
3. **Warnings are errors.** An undocumented public symbol, a broken
   cross-reference, or a malformed docstring fails the build.
4. **Never commit built output.** `docs/_build/` and `docs/_generated/` are
   gitignored.
5. **Every PR that changes public code or docs runs the build.** Its PR body
   lists the build under verification.
6. **The first PR that adds code to a repo also adds the docs build.** Any PR
   that adds a language adds its generator in the same PR.

## Hub and stitching

Use Sphinx as the hub, with MyST for Markdown and the Furo theme, whatever the
languages. It is the only mature hub that can read several languages natively
and also take in Markdown and HTML from other generators. Architecture
diagrams are committed D2 SVGs (see `architecture-docs`), so they appear in the
site as ordinary images. The build fails if any SVG is stale.

Bring each language in through the first option that works, in this order:

1. **Native.** A Sphinx extension reads the source, giving shared search,
   theme, and cross-references.
2. **Markdown.** The language's generator emits Markdown, which MyST renders
   inside the site theme.
3. **Embedded HTML.** The canonical generator's HTML is copied under
   `api/<lang>/` and linked from a stub page. Search and theme are separate,
   but it still lives in one site.

| Language | Integration | Generator | Coverage gate |
|---|---|---|---|
| Python | Native | `sphinx-autoapi` + `napoleon` (parses source, no import) | `ruff` `D` rules, Google convention, ignore `D107`; `nitpicky = True` |
| TypeScript / JS | Markdown | TypeDoc + `typedoc-plugin-markdown`, `--outputFileStrategy modules --hidePageHeader` | `--validation.notDocumented --treatWarningsAsErrors` |
| Rust | Embedded HTML | `cargo doc --no-deps` | `#![deny(missing_docs)]`, `RUSTDOCFLAGS="-D warnings -D missing_docs"` |
| C / C++ | Native | Doxygen XML → Breathe | `EXTRACT_ALL=NO`, `WARN_IF_UNDOCUMENTED=YES`, `WARN_NO_PARAMDOC=YES`, `WARN_AS_ERROR=FAIL_ON_WARNINGS`; a `@file` comment in every header |
| Other | Markdown if the generator can emit it, else embedded HTML | The language's canonical generator | The generator's warnings-as-errors mode |

The Python, TypeScript, Rust, and C/C++ rows, and every gate in them, were
verified end to end: the template's `docs/build.sh` and `docs/conf.py` run
them, and the tasks that added each language (T6–T9 in the
plan in the template repository, https://github.com/arjunbhargava/foundation) broke each gate once to show it fails.

Doxygen reports undocumented functions and macros only in a header that has a
`@file` comment, so `build.sh` fails on a header without one.
`FAIL_ON_WARNINGS` reports every warning before failing; `YES` stops at the
first.

`--hidePageHeader` stops TypeDoc starting each page with a bold copy of its
title and a horizontal rule.

## Setup

A repository made from this template already has the docs build, so edit its
files rather than recreating them: `docs/build.sh`, `docs/conf.py`,
`docs/index.md`, the pages in `docs/api/`, and, for C and C++, `Doxyfile`. A
repository without them copies them from the template repository, then sets
`project` in `docs/conf.py` and fixes the source paths. In `docs/build.sh` and
`docs/conf.py`, a comment naming the language starts each language's block,
which runs only when the language's manifest exists.

- **Remove a language** the repository doesn't use: delete its page in
  `docs/api/`, and for C and C++, `Doxyfile`. Its blocks skip themselves once
  its manifest is gone.
- **Add back one of the four:** copy its page in `docs/api/` from the
  template repository.
- **Add another language:** start from the `docs/build.sh` block of the
  language with the same integration, TypeScript's for Markdown or Rust's for
  embedded HTML, and gate it with the generator's warnings-as-errors mode.
- **Add diagrams** (see `architecture-docs`): put
  `docs/diagrams/render.sh --check` above the language blocks in
  `docs/build.sh`, so a stale SVG fails the build. That check hasn't run in
  the template, which has no diagrams yet.

The build also needs the following, which the template already has:

- `docs/index.md` has two toctrees. The "Explanation" toctree lists
  `architecture` and other hand-written pages. The "API reference" toctree
  globs `api/*`, so it lists each page in `docs/api/`: one per language,
  titled with the language's name.
- For Python and TypeScript, add a stub page whose toctree lists the
  generated pages, `python/<pkg>/index` in `docs/api/python.md` and
  `/_generated/ts/index` in `docs/api/typescript.md`.
- For each embedded-HTML language, add a stub page such as `docs/api/rust.md`
  that links to each crate with an HTML link,
  `<a href="rust/<crate>/index.html">`. A Markdown link fails the build
  (`myst.xref_missing`), because MyST resolves it only to pages Sphinx
  builds, so `build.sh` checks that each linked page exists instead.
- For C and C++, add `docs/api/cpp.md` with a Breathe `doxygennamespace`
  directive for each top-level namespace. `doxygenindex` would also list
  every source directory.
- Declare `sphinx`, `sphinx-autoapi`, `myst-parser`, and `furo`, plus
  `breathe` if the repo has C or C++, in the `dev` group of
  `docs/pyproject.toml`, a uv project of their own, so that Sphinx doesn't
  depend on the Python package. `ruff`, which checks Python docstrings,
  stays with the Python package's dev dependencies. Put the TypeDoc packages
  in `devDependencies`.
- Configure `ruff` as `[tool.ruff.lint]` in this repository's `pyproject.toml`
  does: select the `D` rules, use the Google convention, ignore `D107`, and
  ignore `D` under `tests/`. Copy those tables rather than rewriting them.

- Add `docs/_build/` and `docs/_generated/` to `.gitignore`.

## Verify

The `docs-from-source` rule lists what a doc comment contains, and the build
and screenshots every PR needs. When the build script or the gates change,
also check that each gate still fires: add an undocumented public symbol in
one language, confirm the build fails, then revert.
