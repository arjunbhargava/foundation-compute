# foundation

A starter repository for engineers who work with Cursor agents. Agents write
most of the code and people review every change, so the template makes each
change cheap and reliable to review. It provides instructions that agents
follow, pinned tools and shared commands, example code and checks for
Python, CI, and support for agent-launched compute jobs.
Most of it is built; [the plan](docs/template-plan.md) lists what remains:
T16 (compute job support), T17 (Linear setup), T19 (measuring the
instructions), T22 (collecting follow-ups, which waits for T17), and T23's
PR 4 (the branch-update workflow).

## Get started with an agent

Give a Cursor agent this prompt, replacing `my-project` and `<languages>`:

> Create a new project named `my-project` from the Copier template
> `gh:arjunbhargava/foundation`, with these languages: `<languages>`. Follow
> "Get started with an agent" in
> https://github.com/arjunbhargava/foundation/blob/main/README.md: copy the
> template, run `git init`, run `bash .cursor/install.sh` (if it says mise
> isn't on PATH, add the directory it names to PATH), then `mise run check`.
> Report anything that fails.

The agent copies the template with this command, which answers every
question, so Copier never prompts. Each language is `true` or `false`, and at
least one must be `true`:

```sh
mise exec uv@0.12.21 pipx:copier@9.18.2 -- copier copy --defaults \
  --data python=true --data rust=true --data typescript=false --data cpp=false \
  gh:arjunbhargava/foundation my-project
```

Creating and checking a project needs no secret. For the agent's pull requests
to merge without a person ([auto mode](docs/auto-mode.md)), Bugbot must review
the repository, and "Allow GitHub Actions to create and approve pull requests"
(Settings > Actions > General) and "Allow auto-merge" (Settings > General)
must be on.

## Set up a local machine

Run `bash .cursor/install.sh` from the project's root. It installs the
pinned mise to `~/.local/bin`, unless that version is already installed, then
the tools `mise.toml` pins, and runs `mise run setup`. It doesn't edit shell
files: if `mise` isn't on PATH, it ends by printing the `export PATH=` line to
add to your shell's startup file.

- **Cursor cloud agent:** automatic. `.cursor/environment.json` runs the
  script with `MISE_INSTALL_PATH=/usr/local/bin/mise`, which is on PATH.
- **Dev container, other CI, or a VM:** run the same command on glibc
  Linux or macOS; [what it doesn't cover](docs/install-script.md).

## Get started by hand

Run the Copier command above, or leave out `--defaults` and the `--data`
flags to answer one yes/no question per language: `python`, `rust`,
`typescript`, and `cpp`. Then set up, check, and commit the project:

```sh
cd my-project
git init  # copier update needs a git repository
bash .cursor/install.sh
mise run check  # everything CI runs; must pass before a pull request
git add -A && git commit -m "Create the project from the foundation template"
```

Then create its GitHub repository, push, run
[`.github/rulesets/apply.sh`](.github/rulesets/apply.sh) (needs `gh`), and add
the repository to Linear as [`docs/linear.md`](docs/linear.md) says.

## Learn more

- [How the repository works](docs/architecture.md)
- [Agent rules and skills](docs/agent-rules-and-skills.md)
- [Orchestrating agents](docs/orchestration.md)
- [Auto mode](docs/auto-mode.md)
- [Pulling template updates](docs/template-updates.md)
- [Commands](AGENTS.md): every `mise run <command>`, the same for people, agents, and CI
