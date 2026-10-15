# Plan: a team template repository

Status: most of this plan is built; what remains is T16 (compute job
support), T17 (Linear setup), T19 (measuring the instructions), T22 (collecting
follow-ups, which waits for T17), and T23's PR 4 (the branch-update workflow).
This document describes a starter repository for the team's projects and the
order to build it in. It is written for the people and agents building the
template. Copy it into the new repository as its first commit.

## Goal

Every new project starts from one repository that already has:

- Instructions that Cursor agents follow (rules and skills).
- Pinned tool versions and one set of commands that people, agents, and
  continuous integration (CI) all run the same way.
- A working example and checks for each core language: Python, TypeScript,
  Rust, and C/C++.
- CI on GitHub Actions that enforces the rules, rather than relying on agents
  to remember them.
- A way for agents to launch long machine-learning or simulation jobs on
  separate compute, safely and within a budget.
- Support for several agents working at once without breaking each other's
  work.

Agents write most of the code. People design the structure and review every
change. The template is built around that split: its main job is to make each
change cheap and reliable for a person to review.

## Terms

| Term | Meaning |
|---|---|
| Rule | A short instruction file in `.cursor/rules/`. "Always applied" rules are loaded into every agent session. |
| Skill | A longer how-to file in `.cursor/skills/`, read by an agent only when its task needs it. |
| Cloud agent | A Cursor agent that runs on its own virtual machine and branch, and opens a pull request (PR). |
| Template repository | A repository new projects are copied from. |
| Copier | A tool that creates a project from a template and can later pull template updates into it. |
| Lockfile | A generated file that records the exact version of every dependency. |
| Merge queue | A GitHub feature that tests each PR combined with everything ahead of it before merging, so two PRs that pass separately can't break `main` together. |
| Mutation testing | A check on test quality: a tool makes small deliberate bugs in the code and reports which ones the tests fail to catch. |
| Hermetic test | A test that depends only on its own inputs: no shared files, ports, databases, or test order. |
| Launcher | The one tool agents use to start compute jobs on other machines. |
| Run record | A small file written by every compute job that records the exact code, image, settings, and hardware used. |
| Handoff | The PR description, which tells the reviewer what was done, how it was checked, and what was not. |

## What the evidence says

These findings shaped the plan. Most are 2026 preprints and some use small
benchmarks, so treat the numbers as direction rather than precise effects.

| # | Finding | What the plan does about it |
|---|---|---|
| F1 | Repository instruction files such as `AGENTS.md` raised cost by about 20% and did not raise success rates. Agents follow every instruction, so unnecessary ones make tasks harder. Repository overviews did not help. [1] | Keep always-applied rules few and short. Put detail in skills. Keep `AGENTS.md` to commands and unusual requirements. |
| F2 | Skills written by people raised success by about 16 points on average (about 5 for software tasks). Skills an agent wrote for itself did not help, and sometimes hurt. Short, focused skills beat long ones. [2] | People write or edit every skill. Changes to `.cursor/` need a person's review. |
| F3 | About half of agent PRs that passed the tests would not have been merged by the projects' maintainers. The main reasons were not really fixing the problem, breaking other code, and poor code quality. [3] | Passing tests is not enough. Add an independent review step, test-quality checks, and a clearer handoff. |
| F4 | Telling agents to "use test-driven development" or "use property-based testing" made little difference; agents went through the motions. Tests that state concrete expected behaviour did help. [4][5] | Don't require a process. Require one named test for each acceptance criterion, and measure test quality with mutation testing. |
| F5 | A second model reviewing finished code helped more than a model planning before the code was written. Good plans help, but a bad plan is worse than none. [6][7] | People approve plans only for larger changes. Every PR gets a review by a separate agent before a person sees it. |
| F6 | Asking agents for a structured handoff made their work easier to review, not more correct. Sections such as "known limitations" appeared only when required. [8] | The PR template requires a short handoff, with one line for any limitation that matters (T24). |
| F7 | In Cursor's experiments with hundreds of agents, agents coordinating through a shared file with locks collapsed to the speed of 1–3 agents. What worked was a planner that splits the work, workers that each own one task on their own copy of the code, and a handoff back to the planner. [9] | Plans and task lists live in Linear, not in a shared file. Each task becomes one agent, one branch, and one PR. |
| F8 | Splitting closely connected code between agents created broken interfaces and rework. Isolated workspaces plus git merges and tests worked well. [10][11] | Agree the interface first and land it, then split the work. Test each PR combined with `main` before merging: up-to-date branches for now, a merge queue later (T4). |
| F9 | At Meta, engineers accepted 73% of tests generated to catch specific deliberate bugs. [12] | Use mutation testing to measure whether agent-written tests catch real mistakes. |

## Decisions

Each decision has a recommended default. Agents proceed with the default unless
a person has recorded a different choice here.

| # | Decision | Recommended default | Why |
|---|---|---|---|
| D1 | How projects are created from the template and receive later updates | Copier | A GitHub template copies files once; later changes to rules and skills never reach existing projects. Copier can pull them in later, and can include only the languages a project needs. Cost: one more tool, and some combinations of languages go untested. |
| D2 | Tool version manager and command runner | `mise` | `mise.toml` pins the tools that more than one language, or the docs build, runs (such as `uv`) and defines the shared commands; each language's own tools and commands are in `.config/mise/conf.d/<language>.toml`. Works the same locally, in agents, and in CI. |
| D3 | Python dependency manager | `uv`; switch to `pixi` for projects that need compiled scientific libraries | `uv` is fast and handles normal Python packages. `pixi` uses conda-forge, which also packages MPI, HDF5, CUDA libraries, and compilers. |
| D4 | Where compute jobs run | SkyPilot | One job description runs on the major clouds, GPU providers, Kubernetes, or a Slurm cluster. Switch to Slurm with Apptainer if the team has a university or lab cluster, since those clusters usually don't allow Docker. |
| D5 | Licence | **Decided:** Apache-2.0, copyright the repository owner | Permissive, requires attribution through `NOTICE`, and grants an explicit patent licence. Projects may pick their own. |
| D6 | Merge method | Merge commits; no squash | The rules ask for commit history that reads as the review story. Squashing erases it. |
| D7 | Which changes need a person to approve a plan before coding | New module; change to a public interface or data format; new dependency; compute spend above the cost limit | Planning has a cost and only pays off for larger changes. |
| D8 | Cost limit for one agent-launched compute job before asking a person | **Decided:** no per-job limit for now; total agent compute spend at most $10,000 per day | Enforce the daily cap with the provider's budget controls (T16), not only the rule. Revisit the per-job limit when T16 lands. |
| D9 | Open agent PRs allowed per reviewer | **Decided:** 5, raised from 3 on 2026-10-02 | People review everything, so review time, not agent count, limits throughput. The owner raised it to 5 after Stage 2, because 3 made progress too slow. Adjust from data. |
| D10 | Cursor plan | Ask the owner | Team pools of the team's own GPU machines for agents need the Enterprise plan. |
| D11 | Which model each agent runs on | **Decided (2026-10-03):** design work (plans, rulesets, CI security, and changes that span several areas, such as T18) runs on Claude Opus 5.5 at xhigh effort. The orchestrator, and tasks with checkable acceptance criteria and a local change, run on Claude Sonnet 5.5 at high effort. A Sonnet task that fails twice on the same CI failure or Bugbot finding is relaunched on Opus from its branch. **Changed (2026-10-14):** design work on Opus runs at medium effort with `fast=false`, to lower cost. xhigh effort is reserved for an extremely challenging or confusing feature, and the orchestrator says why in its launch message to the owner. A relaunch after two failures is at medium effort, unless the failure itself looks confusing. Everything else is unchanged. | Spends the most capable model only where a mistake is costly. Revisit with T25's data: a cheaper model saves money only if it doesn't add review rounds. |

## The work

Each task below is one PR of about 300 changed lines, and at most 500,
following `reviewable-prs`. Each must pass CI on its own. "Needs" lists the
tasks that must be merged first. Tasks with the same needs can run in
parallel, each with its own agent.

Some steps are settings in GitHub, Cursor, or Linear rather than files. Agents
can't change those settings, so they're marked **(person)**.

### Stage 1: start the repository

**T1. Create the repository with the agent instructions.** Needs: nothing.

- **(person)** Create the new repository. Mark it as a template in GitHub
  settings if D1 is "GitHub template".
- Copy from the `slang` repository: `.cursor/rules/`, `.cursor/skills/`, and
  `docs/template-plan.md` (this file).
- Remove everything specific to slang. The skills mention slang as an example
  in a few places; replace those with neutral examples.
- Write a short `README.md` covering what the template is, how to start a
  project from it, and links to this plan and the skills.
- Done when: no file mentions slang, and every link in the README works.

**T2. Basic repository files.** Needs: T1.

- `.editorconfig` (UTF-8, LF line endings, final newline).
- `.gitattributes`: LF line endings. Mark lockfiles and generated SVGs as
  generated, so GitHub collapses them in diffs.
- `.gitignore` for all four languages, plus `docs/_build/`,
  `docs/_generated/`, and `.env`.
- `.env.example`, listing environment variables by name with no values.
- `LICENSE` (D5) and `CODEOWNERS`. `CODEOWNERS` requires a person's review for
  `.cursor/`, `docs/architecture.md`, and public interface files.
- Done when: the files exist and CI (once T4 lands) passes on them.

**T3. Tool versions, shared commands, and agent setup.** Needs: T1.

- `mise.toml` pins tool versions and defines the commands `setup`, `fmt`,
  `lint`, `test`, `docs`, and `check`. `check` runs everything CI runs. Each
  command starts as a placeholder that each language task fills in.
- `.cursor/environment.json`: the install step runs `mise install` and
  `mise run setup`, so a cloud agent's machine matches CI.
- `AGENTS.md`: only the commands, where code lives, and requirements an agent
  wouldn't guess. Add a "Cursor Cloud specific instructions" section. No
  overview of the repository (see F1).
- Done when: a fresh cloud agent can run `mise run check` with no other setup.

**T4. CI skeleton and repository protection.** Needs: T3.

- `.github/workflows/ci.yml`:
  - One job per language, each running only when files of that language
    change. Language tasks add their jobs; this task adds the structure.
  - A docs job that runs `docs/build.sh` once it exists.
  - Triggers on pull requests and on `merge_group`, the event the merge queue
    uses.
  - Cancels older runs of the same PR when a new commit arrives.
  - Installs mise with `.cursor/install.sh`, the same version agents use, and
    runs the shared `mise run` commands.
  - One job, `ci-ok`, passes only when every other job passed or was skipped.
    It is the only required CI check, so language tasks add jobs without
    changing the rulesets.
- A PR size check that fails above 500 changed lines, not counting files
  marked `linguist-generated` in `.gitattributes`, unless the PR description
  starts with `Oversize:`.
- A workflow that labels a PR `agent` when any of its commits is authored by
  `cursoragent@cursor.com`, creating the label if it is missing.
- Security defaults:
  - Workflows get read-only permissions unless a job needs more.
  - Actions are pinned to an exact commit.
  - Dependabot opens action updates. Each language task adds its package
    ecosystem.
  - CodeQL code scanning covers all four languages. CodeQL fails on a
    language with no code, so T4 scans `actions` and each language task adds
    its own.
- Two rulesets in `.github/rulesets/`, and `apply.sh`, which applies them with
  `gh api` because GitHub doesn't copy settings from templates. Agent PRs are
  authored by the owner's account, and GitHub doesn't let authors approve
  their own PRs, so checks and review are separate rulesets:
  - `main: checks`: `ci-ok` and the size check must pass on a branch that is
    up to date with `main`, and force pushes are blocked. Nobody can bypass
    it.
  - `main: review`: one approval, including a code owner's. Repository admins
    can bypass it, but only through a pull request.

  The script also allows only merge commits (D6) and turns on secret scanning
  with push protection.
- No merge queue for now. GitHub offers merge queues only to repositories
  owned by an organization, and this one is owned by a user. Requiring
  up-to-date branches gives the same guarantee, that `main` only receives
  tested combinations, at the cost of updating and retesting a PR whenever
  `main` moves ahead of it. To switch after moving the repository to an
  organization:
  1. In `.github/rulesets/main-checks.json`, add a `merge_queue` rule with
     `merge_method` `MERGE`, and set `strict_required_status_checks_policy`
     to `false`. `apply.sh` lists the full rule.
  2. Rerun `apply.sh`. CI already runs on `merge_group`.
- **(person)** Run `apply.sh`.
- Done when: a test PR above 500 lines fails the size check, and a PR merges
  only after its required checks pass on a branch that is up to date with
  `main`.

**T5. PR template.** Needs: T1. Can run alongside T2–T4.

- `.github/pull_request_template.md`, with the sections `reviewable-prs`
  lists, in its order. T24 cut them from seven to four.
- Update `reviewable-prs` to match.
- Done when: the template and the rule list the same sections in the same
  order.

### Stage 2: languages

Each language task adds:

- A small example module with documentation comments.
- One test.
- Formatting, lint, and type checks, with warnings treated as errors.
- Its block in `docs/build.sh`.
- Its CI job.
- A command that tests only that package.

The example exists to prove the checks work. A project deletes it when its
first real code arrives.

Every check must fail when broken. The PR shows this by breaking the check once
(for example, adding an undocumented public function), then reverting.

**T6. Python, and the documentation build.** Needs: T3, T4.

- `uv` for dependencies, Python version, and the lockfile; `ruff` for format and
  lint (including documentation-comment rules); `pyright` for types; `pytest`
  for tests, including the examples inside documentation comments.
- Tests run in parallel (`pytest -n auto`), so tests that depend on shared
  state or on order fail early.
- The documentation build from the `source-docs` skill lands here, because its
  site generator, Sphinx, is a Python tool: `docs/conf.py`, `docs/index.md`,
  and `docs/build.sh`.
- Done when: `mise run check` and `docs/build.sh` pass, and each check fails
  when broken.

**T7. TypeScript.** Needs: T6.

- `pnpm` workspace, `tsc` in strict mode, Biome for format and lint, `vitest`
  for tests, TypeDoc for documentation.

**T8. Rust.** Needs: T6.

- `rust-toolchain.toml`, a workspace with one crate, `rustfmt`,
  `clippy` with warnings as errors, `#![deny(missing_docs)]`, and `cargo-deny`
  to check dependency licences and known vulnerabilities.
- Rewrite the Rust row of the `dependencies` rule, and make `deny.toml`'s
  allow-list the single list of allowed licences, with the rule pointing at it.

**T9. C and C++.** Needs: T6.

- CMake with `CMakePresets.json`, `clang-format`, `clang-tidy`, `ctest`, and
  Doxygen with Breathe for documentation.
- One CI job builds with AddressSanitizer and UndefinedBehaviorSanitizer,
  which catch memory errors and undefined behaviour at run time.
- The `source-docs` skill lists the Doxygen settings as not yet tested end to
  end; confirm them here and update the skill.
- Leave the choice of C/C++ package manager (vcpkg or CMake `FetchContent`) to
  each project.

T7, T8, and T9 can run in parallel.

### Stage 3: agent instructions

Write every new rule and skill by hand, or have an agent draft it and a person
edit it (F2). Keep each skill short and focused.

**T10. Restructure the always-applied rules.** Needs: T1.

- Today, four rules load into every session, and two of them require reading a
  skill of about 120 lines first; `clarity` does this before writing any text,
  so almost every task loads it. F1 suggests this costs more than it
  returns.
- Keep each always-applied rule to a short checklist. Load the full skill only
  when the task needs it. Don't change what the rules require.
- This changes structure only. New content goes in T11 and T12.

**T11. New rules.** Needs: T10.

- `secrets` (always applied, about 10 lines): secrets come from environment
  variables, set through the Cursor dashboard for agents. Never commit them or
  write them to logs. `.env.example` lists the names.
- `dependencies`: a new dependency needs a one-line reason in the PR, a
  committed lockfile, and a passing licence check. On a lockfile merge
  conflict, regenerate the lockfile; never edit it by hand.
- `compute-cost` (always applied): the cost limit (D8), and stop to ask a
  person above it.

**T12. New skills.** Needs: T10. Split into two PRs if over 500 lines.

- `testing`:
  - One named test per acceptance criterion.
  - Tests are hermetic and can run in parallel.
  - Every external resource a test or job creates (bucket, port, tracker run)
    has the branch name or run ID in its name.
  - Paid or live-service tests run only when asked for, never in normal CI.
  - For numerical code, the checks that catch the most errors: the error
    shrinks at the expected rate as the step size shrinks; conserved
    quantities (energy, mass, momentum) stay within a stated bound; results
    match known exact solutions; results respect the problem's symmetries.
    Compare floating-point values with stated tolerances, never exact
    equality.
- `plan`: for changes that meet the D7 threshold, write a short plan covering
  the problem, the interface, the files touched, and the acceptance criteria.
  Then stop until a person approves it.
- `decompose`: turn an approved plan into Linear sub-issues. Each sub-issue
  states the interface it builds or uses, the files it owns, acceptance
  criteria, the command that checks it, and which other sub-issues it waits
  for. Land shared interfaces first, as their own PR. Keep closely connected
  work in one task rather than splitting it (F8).
- `add-language`: the steps from Stage 2 as a checklist, so a project can add
  a language later.

**T20. Rename the `spec` skill to `plan`.** Needs: T12.

- The skill writes what D7, the PR template, and `docs/linear.md` call a
  plan, and the `clarity` rule asks for one name per concept (found in PR
  #12). Rename the directory and every reference to it, with no other change,
  as a mechanical PR.

### Stage 4: review and quality checks

**T13. Independent review before a person reviews.** Needs: T5. See F3 and
F5.

- `.cursor/BUGBOT.md` tells Cursor's review agent to check the diff against
  the issue's acceptance criteria and the repository rules.
- **(person)** Turn on Bugbot for the repository.
- The agent fixes what the reviewer finds before asking for a person's review.

**T14. Mutation testing.** Needs: T7, T8, T9.

- Run mutation testing on changed code in CI (F4, F9). At first it reports results
  only; it doesn't block merging. Tools: `cargo-mutants` (Rust), `mutmut`
  (Python), StrykerJS (TypeScript), Mull (C/C++; the least mature).
- Decide after a month of data whether to make it blocking. The data for each
  PR in that month comes from the runs of `.github/workflows/mutation.yml`:
  - Each language's counts, from the line
    `### <Language> mutation testing: <survived> of <total> mutants survived`
    that starts its report. `gh run list --workflow mutation.yml` lists the
    runs, and `gh run view <run ID> --log | grep 'mutation testing:'` prints
    the lines. GitHub keeps logs for 90 days by default.
  - The job's wall time, from `startedAt` and `completedAt` in
    `gh run view <run ID> --json jobs`.
  - For a sample of surviving mutants, whether a person judges each one a gap
    in the tests or a change that can't alter behaviour.

**T15. Enforce module boundaries.** Needs: T7, T8, T9.

- People own the structure, so check it with tools instead of relying on
  instructions. Use `import-linter` for Python and `dependency-cruiser` for
  TypeScript. For Rust, crate dependencies plus `cargo-deny` bans enforce it.
  For C/C++, use CMake target visibility.
- The example modules get one boundary rule each, to prove the check works.

**T21. Fixes from the first language tasks.** Needs: T7, T8, T9.

The language tasks were the first users of several skills and of CI with
four languages, and their PRs listed what to fix. Split into one PR for the
skills and one for CI.

- `add-language`: add what T6–T9 found missing or wrong. Development tools go
  in the lockfile, not `mise.toml`; each version has one source; a language
  adds `lint:<language>` and `test:<language>` and edits only `setup` and
  `fmt`; the CI filter includes root config files and files other jobs read;
  tools must work on every platform the `install-script` job runs on; what to
  do when a tool can't come from mise, or the language has no package
  manager; the Dependabot cooldown; and how to show each check failing
  without one break hiding another.
- `source-docs`: intersphinx in the Sphinx configuration it gives projects; the
  Rust stub page's link, which fails under MyST; and `-D missing_docs` in
  `RUSTDOCFLAGS`.
- `testing`: name the marker in each language that keeps paid and
  live-service tests out of `mise run test`.
- CI: install only the tools each job needs, or cache mise's directory;
  check that each lockfile matches its manifest (`uv sync --locked`,
  `pnpm install --frozen-lockfile`, `cargo build --locked`); run cargo-deny's
  advisory check on a schedule; and group the `changes` job's
  `$GITHUB_OUTPUT` lines (actionlint SC2129).
- Dependabot can't update the pins in `mise.toml`. Bump them by hand, or move
  to Renovate if that becomes a burden.

**T24. Smaller PRs and shorter descriptions.** Needs: T13.

PR descriptions were often longer than the code they described, and full of
"why I didn't do X" prose. The owner decided:

- Four PR sections: **What and why** (at most 3 sentences; link the issue),
  **Verified** (commands and CI links, one line each; which test covers each
  acceptance criterion, in a line, not a table), **Needs a person**
  (decisions only), and **Follow-ups** (one line each; filing them in Linear
  is optional). Omit an empty section rather than writing "None".
- Drop "How to review" (commit messages carry it), "What was not verified"
  and "Changes from the plan" (one line under Verified or Needs a person,
  only when it matters), and "Diagrams" (mention them only when they change;
  the `architecture-docs` requirement stays).
- No "why I didn't" prose; mention a rejected option only when a reviewer
  would otherwise ask, in one sentence. Link evidence instead of pasting it:
  a check-failure demonstration is one line per check, with its run link.
- Description length: about 150 words for a PR under 100 changed lines, at
  most 300 otherwise. Task size: aim for 300 changed lines, with 500 the
  ceiling; one language or one concern per PR.
- The `dependencies` rule's development-only licences include Creative
  Commons licences on data, such as caniuse-lite's CC-BY-4.0 (#28).
- Done when: no file asks for a removed section or "None".

### Stage 5: compute jobs

**T16. Compute job support.** Needs: T6, D4, D8.

**Deferred** (owner, 2026-10-02): the owner will run compute jobs on their own
cloud, so D4's choice of launcher waits until that setup is known. T18 doesn't
wait for this task.

- A base container image (`Dockerfile`) with pinned CUDA versions. CI builds
  it, tags it with the commit, and pushes it to GitHub's container registry.
  Jobs use the image's digest, so the exact image is recorded.
- A run record helper. Every job writes the commit, whether there were
  uncommitted changes, the image digest, the full settings, random seeds, the
  hardware and driver, and start and end times.
- The `compute-jobs` skill covers:
  - How to launch a job, check its status, and fetch results with the
    launcher (D4).
  - Default limits: maximum run time, automatic shutdown when idle,
    interruptible machines with checkpoints, and a cap on GPU count.
  - How to report results in the PR.
- How agents learn a job finished: a GitHub Actions workflow launches the job
  and waits for it. A Cursor Automation on "workflow run completed" then
  starts a follow-up agent to read the results. Use the Cursor API or a webhook
  only if this doesn't cover a case.
- Tests that need a GPU are marked and run nightly, or on request, on a
  self-hosted GPU runner. Ordinary CI uses small CPU-sized settings.
- Large data and checkpoints go to object storage (S3 or similar), never git.
- **(person)** Create a separate cloud account or project for agent jobs, with
  provider-side budget limits and a service account. Add its credentials as
  Cursor secrets. If using an egress allowlist, add the cloud, registry,
  tracker, and storage domains.
- Replace the `compute-cost` rule's "the `compute-jobs` skill doesn't exist
  yet" clause with one tied to the provider-side budget being set.

### Stage 6: Linear

**T17. Linear setup.** Needs: T5. Mostly **(person)**.

- Connect the Cursor and Linear integrations, and the Linear GitHub
  integration.
- Create a label group named exactly `repo`, with one label per repository
  (`owner/name`), and put it on each Linear project. This tells Cursor which
  repository an issue belongs to.
- Set the default repository, model, and base branch in the Cursor dashboard.
- Create a Linear issue template:
  - Goal (1–2 sentences).
  - Acceptance criteria, written as checkable behaviour.
  - The command that verifies it.
  - Out of scope.
  - Compute budget.
  - Links to designs.
- Add an `agent-ready` label. Assign only those issues to agents.
- Use one sub-issue per PR for work split into several PRs, so merging the
  first PR doesn't close the whole issue.
- In the repository: `docs/linear.md`, listing these conventions in a few
  lines.

**T22. Collect follow-ups from merged PRs.** Needs: T13, T17.

Every PR lists work for later under "Follow-ups" and decisions under "Needs
a person" (T24), but nothing collects them afterwards, so they are lost
unless someone rereads old PRs. This task adds a scheduled Cursor Automation
that does that, alongside `prune-review`.

- A skill, or a section of `prune-review`, covers the run: read those two
  sections of PRs merged since the last run, or the sections that held the
  same items in PRs from before T24; drop items `main` has already
  fixed; and file each remaining item as a Linear issue without
  `agent-ready`, so a person decides what agents work on. Decisions go in a
  separate list for a person, not into PRs.
- A scheduled automation, weekly or after a set number of merges, runs this
  and `prune-review` together. Each fix lands as its own small PR.
- Done when: a run on this repository files the open items from PRs #1–#17
  that the housekeeping PR didn't fix, and none it did.

### Stage 7: template mechanics

**T18. Convert to Copier.** Needs: all earlier tasks except T16, D1.

- Turn the repository into a Copier template with one yes/no question per
  language.
- CI creates a project with all languages, then one project per single
  language (five variants), and runs `mise run check` in each.
- If D1 is "GitHub template", replace this task with documented steps for
  deleting unused languages.

### Later

**T19. Measure the instructions.** After about 10 real tasks have been done in
projects that use the template.

- Rerun closed tasks with different instructions (for example, with and without
  a rule). Score each run by hidden tests and a person's "would merge"
  judgement.
- Track: PRs merged without change requests, review rounds per PR, review
  time, and reverts within 30 days.
- Repeat after each model upgrade, and remove instructions that no longer
  help.

**T23. Auto mode for exploratory tasks.** Needs: T13.

**In progress** (owner, 2026-10-10). PR 1 (#38) added the review ruleset, the
CODEOWNERS entries, and `docs/auto-mode.md`, PR 2 (#43) the auto-merge
workflow, and PR 3 (#50) the approval workflow. After PR #54, a fix (#55)
added the owned-paths check, which replaces code-owner review as the owner's
gate in auto mode. PR 4, the branch-update workflow, is left.

Some tasks need several rounds of exploration, and waiting for a person's
review on each round stalls them. In auto mode, a repository's agent PRs merge
without a person's approval, with CI and Bugbot as the gate. The design so
far:

- `.github/rulesets/apply.sh --auto` applies a second review ruleset with one
  required approval, which a workflow gives agent PRs, the `owned-paths`
  check (so owned paths still need the owner), and
  `required_review_thread_resolution` on, so Bugbot's findings
  block merging until their threads are resolved. `main: checks` is
  unchanged. `mise.toml`, `.config/mise/`, `AGENTS.md`, and the files that
  configure checks become owned paths, so an agent PR can't change what CI
  runs, the agent instructions, or a check without the owner. The ruleset
  still sets code-owner review, but that alone let agent PR #54, which
  changed only `AGENTS.md`, merge (2026-10-12); the `owned-paths` check is
  what stops owned paths in auto mode.
- GitHub's native auto-merge, not a custom merge workflow: it already waits
  for every ruleset, and Actions has no trigger for a resolved review thread.
  A workflow turns on auto-merge for an `agent` PR once the `Cursor Bugbot`
  check completes, because before then there are no threads to block it, and
  turns it off on each push until Bugbot has reviewed the new commit.
- After each merge, a workflow updates the open agent PRs that are behind
  `main`. It needs a GitHub App token: updates made with `GITHUB_TOKEN` start
  no workflows, so `ci-ok` would never report, and the owner's token would
  bypass code-owner review, because the owner is a bypass actor. The
  auto-merge workflow merges with `GITHUB_TOKEN`, so its merges start no
  `push` or `pull_request` `closed` runs either. Switching it to the App
  token lets the update workflow start on those merges, and CodeQL analyse
  `main` again.
- `docs/auto-mode.md` says what auto mode allows, what still needs the owner,
  and how to audit and revert. Merge commits (D6) make each revert one commit.
- Limits (owner, 2026-10-10): $500 per day of cloud agent spend to start,
  checked with `mise run spend` and capped in the Cursor dashboard, and the
  500-line PR ceiling. `docs/auto-mode.md` gives the details.

**T25. Track agent spend.** Needs: **(person)** a Cursor Admin API key in
the cloud-agent secret `CURSOR_ADMIN_API_KEY`. **Done** in #35 (`mise run
spend`).

- The agent API's agent and run records have no token or cost fields. The
  Admin API's usage events (`POST /teams/filtered-usage-events`) do.
- A script reports tokens and cost per agent run, or per day and model if
  usage events don't identify the run. The orchestrator runs it at each pause
  and gives the totals to the owner.
- Done when: a report covering the last week's agents matches the dashboard's
  totals.

## Order and parallel work

```text
T1 ─┬─ T2
    ├─ T3 ── T4 ── T6 ─┬─ T7 ─┐
    │                  ├─ T8 ─┼─ T14, T15, T21
    │                  ├─ T9 ─┘
    │                  └─ T16 (also needs D4, D8)
    ├─ T5 ─┬─ T13 ─┬─ T24
    │      │       ├─ T23
    │      └─ T17 ─┴─ T22
    └─ T10 ─┬─ T11
            └─ T12 ── T20
T18 needs everything above except T16, T22, and T23.
T25 needs only the admin key.
```

Right after T1, four tasks (T2, T3, T5, T10) can start at once. Keep the
number of open agent PRs within the review limit in D9 rather than starting
everything that is ready. Start a task only when everything it needs has
merged.

## How agents work on this repository

- One task, one Linear sub-issue, one agent, one branch, one PR.
- A planner (a person, or an agent using `decompose` once T12 exists) creates
  the tasks. Workers don't coordinate with each other; they report back
  through the PR description.
- An orchestrating agent hands off to a fresh one, with a written summary of
  the state, after every few merges. Each turn resends its whole context, so
  the cost of a turn grows with every message it has received. Workers report
  back once, when their PR is ready or blocked.
- Shared state lives in git and Linear only. No shared task files, no shared
  databases or fixed ports, and every external resource name includes the
  branch or run ID.
- An agent that finds a problem outside its task lists it under Follow-ups
  instead of fixing it.
- Each PR is tested combined with `main` before merging. For now that means
  requiring up-to-date branches; a merge queue replaces it once the
  repository moves to an organization (T4).
- For a hard task, run several agents on it separately and review only the
  best result. Parallel agents should not multiply review work.

## Not in scope

- A custom system for coordinating agents. Cursor already provides subagents,
  an API, automations, and Linear routing.
- Agents talking to each other directly, or shared memory files.
- A dedicated agent for merging other agents' work. Required up-to-date
  branches, and later a merge queue, cover it, and Cursor found such a role
  slowed things down [9].
- Release automation, deployment, and choices of C/C++ package manager or
  experiment tracker. These belong to each project.
- Go. It appears in the `source-docs` skill but isn't a team language; remove
  it in T1.

## Sources

1. Gloaguen et al., [Evaluating AGENTS.md](https://arxiv.org/abs/2602.11988), ICLR 2026 workshop.
2. [SkillsBench](https://arxiv.org/abs/2602.12670), 2026.
3. METR, [Many SWE-bench-passing PRs would not be merged](https://metr.org/notes/2026-03-10-many-swe-bench-passing-prs-would-not-be-merged-into-main/), March 2026.
4. Fowler, [TDD inside the agent loop](https://martinfowler.com/articles/exploring-gen-ai/tdd-in-the-agent-loop.html).
5. Luu, [How well do agents use test and verification techniques?](https://danluu.com/agentic-testing/)
6. [Review beats planning](https://arxiv.org/abs/2603.03406), 2026. Small models on short programming problems; weak evidence for larger work.
7. [From plan to action: how well do agents follow the plan?](https://arxiv.org/abs/2604.12147), 2026.
8. [Software delegation contracts](https://arxiv.org/abs/2606.17099), 2026. A pilot study of 64 runs.
9. Cursor, [Scaling long-running autonomous coding](https://cursor.com/blog/scaling-agents) and [Towards self-driving codebases](https://cursor.com/blog/self-driving-codebases).
10. [Cohesion-aware task partitioning for multi-agent coding](https://www.alphaxiv.org/overview/2606.00953), 2026.
11. [CAID: effective strategies for asynchronous software engineering agents](https://www.alphaxiv.org/abs/2603.21489), 2026.
12. Meta, [Mutation-guided LLM-based test generation](https://arxiv.org/abs/2501.12862), 2025.
