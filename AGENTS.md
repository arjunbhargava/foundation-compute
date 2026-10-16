# Agent instructions

## Commands

`mise.toml` defines the shared commands, and each language's file in
`.config/mise/conf.d/` defines that language's, so people, agents, and CI run
the same thing:

| Command | What it does |
|---|---|
| `mise run setup` | Install project dependencies. |
| `mise run setup-status` | Report which of README.md's manual setup steps are `done`, `not done`, or `can't check`, with a link for each, using `gh` and its API; always exits 0 and prints no secret. Arguments after `--` go to the script: `mise run setup-status -- owner/repo`. |
| `mise run fmt` | Format all code in place. `fmt:<language>` formats one language. |
| `mise run lint` | Check formatting, lint, and types without changing files. |
| `mise run lint:python` | Run only the Python checks. |
| `mise run lint:rulesets` | Check that the ruleset files in `.github/rulesets/` are valid JSON and that the two review rulesets differ only in name, thread resolution, and auto mode's owned-paths and needs-human-review checks. |
| `mise run lint:workflows` | Run only the GitHub Actions workflow checks: actionlint, and zizmor's offline security audits. A finding in a workflow is suppressed with a `# zizmor: ignore[<audit>]` comment. |
| `mise run lint:language-listings` | Check that each place that must list every language, such as the CI jobs and this table, lists each language in `.config/mise/conf.d/`, and name each place that lacks one. |
| `mise run test` | Run all tests. |
| `mise run test:python` | Run only the Python tests and docstring examples, of all three distributions. Arguments after `--` go to pytest: `mise run test:python -- lib` runs only the library's. |
| `mise run test:lint-workflows-script` | Check that `.github/scripts/lint_workflows.sh` fails on a finding from either actionlint or zizmor, and runs both. |
| `mise run test:language-listings-script` | Check that `lint:language-listings` passes for the repository, and names each place that lacks a new language, on copies of the files it reads. |
| `mise run test:rulesets` | Check the changes `.github/rulesets/apply.sh` makes with and without `--auto`, and that `lint:rulesets` catches broken ruleset files, with a fake `gh`. |
| `mise run test:auto-merge-script` | Check when `.github/scripts/auto_merge.sh` turns auto-merge on and off, and which PRs it leaves alone, with a fake `gh`. |
| `mise run test:approve-agent-prs-script` | Check which PRs `.github/scripts/approve_agent_prs.sh` approves, in auto mode and review mode, with a fake `gh`. |
| `mise run test:needs-human-review-script` | Check that `.github/scripts/needs_human_review.sh` fails a PR with the `needs-human-review` label and passes one without. |
| `mise run test:owned-paths-script` | Check which changed paths `.github/scripts/owned_paths.sh` finds in `.github/CODEOWNERS`, and when it can't tell, with a fake `gh`. |
| `mise run test:mutate-script` | Check which files `.github/scripts/mutate.sh` mutates and what it reports, with fake mutation tools. |
| `mise run mutate` | Mutation-test the code changed since the merge base with `origin/main`, and report each mutant no test caught, or pass with one line saying that no changed file holds mutable code. `mutate:<language>` runs one language. Only the template repository, which alone has `copier.yml`, also mutates the changed `.github/scripts/*.py`, and no tool mutates the shell scripts there. `check` doesn't run it, because it's slow. |
| `mise run docs` | Build the documentation site. |
| `mise run test:docs` | Check that `docs/conf.py` points the links in `README.md` and `AGENTS.md` at the site's pages, turns those to other repository paths into text, and still fails on a path that is missing or outside the repository, by building a small site. |
| `mise run spend` | Report tokens and cost per Cursor cloud agent run over the last 7 days, from the Cursor Admin API, with each run's task, repository, and branch and a subtotal per repository; needs `CURSOR_ADMIN_API_KEY`, and `CURSOR_API_KEY` for the labels. Arguments after `--` go to the script: `mise run spend -- --since 2026-09-26`. |
| `mise run check` | Run everything CI runs. |

Run `mise run check` before opening a PR; it must pass. It checks every
language the project has: Python.

## Where code lives

- Three Python distributions, each with its code in `src/`, its tests in
  `tests/`, and its own `pyproject.toml`, in one uv workspace whose root is
  the root `pyproject.toml`:
  - `foundation-compute`, at the root: the client, `compute_jobs_cli`, home
    of the `compute-jobs` executable.
  - `compute-jobs`, in `lib/`: the library job code imports,
    `compute_jobs`.
  - `compute-jobs-admin-policy`, in `compute/server/admin_policy/`: the
    server's admin policy, `compute_jobs_admin_policy`.

  `docs/compute-jobs.md` says what each contains and who installs it.
- `pyproject.toml`: the workspace, the client's dependencies, and the tool
  settings for all three. `uv.lock` locks the dependencies of all three, and
  `.python-version` pins Python 3.13, the newest SkyPilot 0.14.0 supports.
- `conftest.py`: adds the `src/` and `tests/` of each uv workspace member to
  the paths pytest runs when it is given none.
- Another Python distribution: list it as a member in `[tool.uv.workspace]`
  in `pyproject.toml`, and give it a `pyproject.toml`, `src/<package>/`, and
  `tests/` of its own. The tests, `docs/build.sh`, `docs/conf.py`, and
  `mise run mutate` take their list of distributions from the members, and
  `mutate` reports each separately; a member without a `src/` is skipped. A
  new member also needs its package added by hand to the toctree in
  `docs/api/python.md` and to `[tool.importlinter]`. pytest imports test
  files by path, so two members may have a test file of the same name, and a
  test can't import a helper beside it by name.
- Module boundaries, which `mise run lint` checks. Add a project's own boundaries:
  - Python: a contract under `[tool.importlinter]` in `pyproject.toml`. The
    client may import the library; the library never imports the client,
    and the admin policy imports neither.
- `.github/scripts/`: the repository's own tooling, which people, agents, and
  CI run through `mise run`, such as `mutate.sh` and `agent_spend.py`. Each
  script is tested by the `_test` file next to it.
- `docs/`: hand-written pages. `docs/build.sh` adds the API reference,
  generated from doc comments. Sphinx and its extensions are a uv project of
  their own, `docs/pyproject.toml`, locked in `docs/uv.lock`, so that Sphinx
  doesn't depend on the Python package.
- `docs/orchestration.md`: how an orchestrator agent launches workers, limits
  cost, and hands off to a fresh orchestrator. Before you launch or message
  any other agent, read it and the `orchestrate` skill.

Each language task adds its directory and lists it here.

## Requirements

- Pin every tool at an exact version: in its language's
  `.config/mise/conf.d/<language>.toml`, or in `mise.toml` if more than one
  language, or the docs build, runs it. Don't install tools another way,
  except these:
  - Add a Python package, such as ruff or pyright, with
    `mise exec -- uv add --dev <package>`, which pins it in `uv.lock`.
  - Add a docs build tool with
    `mise exec -- uv add --project docs --dev <package>`, which pins it in
    `docs/uv.lock`.
- On a project's first task, or when asked, run `mise run setup-status`
  before you rely on auto mode, Pages, or Bugbot, and tell the person each
  step it prints as `not done` or `can't check`, with its link.
- Don't change `.cursor/rules/` or `.cursor/skills/` unless the task is about
  them. People write those files (finding F2 in the plan in the template repository, https://github.com/arjunbhargava/foundation).
- The PR body follows the `reviewable-prs` rule.
- Before asking a person to review a PR, fix each finding in Bugbot's review
  of the latest push (the `Cursor Bugbot` check), or reply saying why it is
  wrong. If Bugbot doesn't run, say so under "Verified".
- Add the `needs-human-review` label to your PR when a person asks to
  review it, in a Linear issue, in Cursor, or in chat, and pass the request
  on to any agent you launch for that work. Also add it, saying why under
  "Needs a person" in the PR body, when the PR adds an important feature or
  makes an architectural decision. This is the one label you may add without
  being asked, whatever a tool's description says. Don't remove it; the
  owner does. `docs/auto-mode.md` says what it does.

## Cursor Cloud specific instructions

- `.cursor/environment.json` runs `.cursor/install.sh` when the machine is
  set up. It installs the pinned mise to `/usr/local/bin`, which is on every
  agent shell's PATH, then runs `mise install` and `mise run setup`. If
  `mise` or a tool is missing, rerun
  `MISE_INSTALL_PATH=/usr/local/bin/mise bash .cursor/install.sh`.
