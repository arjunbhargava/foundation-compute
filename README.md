# foundation-compute

The infra half of a compute-jobs system for agents: a shared SkyPilot API
server on EKS, a client package (`compute_jobs_cli`), an in-job wrapper,
and an S3 job archive.

```sh
bash .cursor/install.sh   # install mise and the pinned tools, once
mise run check            # everything CI runs: lint, tests, docs
mise run fmt              # format in place
mise run docs             # build the documentation site
```

[AGENTS.md](AGENTS.md) lists every command and where code lives.
[docs/orchestration.md](docs/orchestration.md) says how orchestrator agents
launch workers.

## Finish setup: manual steps

GitHub copies no repository settings, and Cursor and Linear need setup of
their own. Until these steps are done, auto mode, the documentation site, and
Bugbot's review don't work. The links are for `arjunbhargava/foundation-compute`, the
repository named when the project was created. `mise run setup-status`
prints each step as `done`, `not done`, or `can't check`, with its link.

1. **Let Actions approve pull requests.**
   [Settings > Actions > General](https://github.com/arjunbhargava/foundation-compute/settings/actions):
   turn on "Allow GitHub Actions to create and approve pull requests".
   Unlocks: [auto mode](docs/auto-mode.md)'s approvals. Who: a repository
   admin; an organization owner first, if the organization's setting is off.
2. **Allow auto-merge** in [Settings > General](https://github.com/arjunbhargava/foundation-compute/settings).
   Unlocks: the auto-merge workflow. Who: a repository admin.
3. **Publish the documentation site.**
   [Settings > Pages](https://github.com/arjunbhargava/foundation-compute/settings/pages): set
   Source to GitHub Actions. Unlocks: the deploy job of `docs-site.yml`. Who:
   a repository admin; a private repository needs a paid GitHub plan.
4. **Apply the rulesets.** With `gh` logged in as a repository admin, run
   `mise exec -- .github/rulesets/apply.sh` for review mode, where a person
   approves every pull request, or add `--auto` for auto mode. It also allows
   only merge commits and turns on secret scanning. Unlocks: required checks
   and review. Who: a repository admin; private ones need a paid plan.
5. **Turn on Bugbot** in the [Cursor dashboard](https://www.cursor.com/dashboard/bugbot).
   Unlocks: the review that auto mode waits for. Who: a Cursor team admin, or
   the account owner.
6. **Give the Cursor GitHub app access** to this repository in
   [Installed GitHub apps](https://github.com/settings/installations), if it
   has access only to selected repositories. Unlocks: cloud agents that open
   PRs. Who: the account owner, or an organization owner.
7. **Set `CURSOR_ADMIN_API_KEY` and `CURSOR_API_KEY`** (see `.env.example`)
   as Cursor cloud agent secrets in the
   [Cursor dashboard](https://www.cursor.com/dashboard), and in `.env`
   locally. Unlocks: `mise run spend`. Who: the Cursor account's manager; a
   team admin for the first. No workflow reads a GitHub Actions secret yet.
8. **Set up Linear** as [`docs/linear.md`](docs/linear.md) says. Unlocks:
   issues that agents turn into PRs. Who: a Linear workspace admin.
9. **Optional: schedule `prune-review`** with a
   [Cursor automation](https://cursor.com/automations), as the
   [skill](.cursor/skills/prune-review/SKILL.md) says. Unlocks: regular
   removal of dead code. Who: a Cursor user.

## Pull template updates

In a project with no uncommitted changes, run
`mise exec -- copier update --defaults --trust`, resolve any conflicts it
marks, and run `mise run check`. [Pulling template updates](docs/template-updates.md)
has the details.
