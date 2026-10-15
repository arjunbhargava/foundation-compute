# Auto mode

In auto mode, an agent pull request (PR) into `main` merges without a
person's review when it changes no path in `.github/CODEOWNERS`, CI passes,
and every review thread is resolved. A workflow approves the PR in place of
a person, and CI and Bugbot are the gate, so exploratory work that needs
several rounds doesn't wait for review on each. It is a switch for the whole
repository; a PR without the `agent` label still needs a person's approval.

<<<<<<< before updating
Status: in progress (T23 in the plan in the [template repository](https://github.com/arjunbhargava/foundation)). The
=======
Status: in progress (T23 in [the template plan](https://github.com/arjunbhargava/foundation/blob/main/docs/template-plan.md)). The
>>>>>>> after updating
review ruleset, the approval workflow, the auto-merge workflow, and the
owned-paths and needs-human-review checks are in place. Until the branch-update workflow lands, a PR
that falls behind `main` waits for someone to update it.

## What changes

Auto mode swaps the review ruleset. The `main: checks` ruleset is the same in
both modes: `ci-ok` and `pr-size` must pass on a branch that is up to date
with `main`.

| Requirement | Review mode: `main: review` | Auto mode: `main: review (auto mode)` |
|---|---|---|
| Approving reviews | 1, from a person | 1, which the approval workflow gives an agent PR |
| Code owner's approval when a PR changes an owned path | Set | Set, but it didn't stop agent PR #54 ([below](#why-code-owner-review-isnt-enough)) |
| `owned-paths` check: the PR changes no owned path | Not required | Required |
| `needs-human-review` check: the PR has no `needs-human-review` label | Not required | Required |
| Every review thread resolved | Not required | Required |

In auto mode, the approval workflow's approval meets the count of 1, the
`owned-paths` check fails while the PR changes an owned path, the
`needs-human-review` check fails while the PR has that label, and each Bugbot
finding blocks the merge until its thread is resolved. The auto-merge
workflow turns on auto-merge once Bugbot has reviewed the latest commit, if
the PR changes no owned path, and GitHub merges once every requirement
holds, in any order. The count of 1 keeps auto mode to agent PRs: with 0, a
PR without the `agent` label, which the workflow doesn't approve, would merge
too.

`.github/rulesets/main-review.json` and `main-review-auto.json` hold the two
rulesets. `mise run lint:rulesets` fails if they differ in anything else.

### Why code-owner review isn't enough

In the template repository, PR #54 changed only `AGENTS.md` and the template
file it is generated from, which `.github/CODEOWNERS` assigns to the owner,
and merged in auto mode on 2026-10-12 with only the approval workflow's approval. GitHub requested no
code owner's review and reported the review decision as `APPROVED`, and
auto-merge, turned on by `github-actions[bot]`, which can't bypass, merged
it. The likely cause: agent PRs are opened from the owner's account, the
owner is the only code owner, and GitHub doesn't require a review from a
PR's author. GitHub's documentation doesn't cover this case, and testing it
needs a second account with write access. The same cause explains PR #47,
so #47 doesn't show that code-owner review needs a required approval. The
`owned-paths` check holds whatever the cause.

## The owned-paths check

`.github/workflows/owned-paths.yml` runs `.github/scripts/owned_paths.sh` when
a PR is opened, reopened, pushed to, or edited, which includes a change of
base branch. It fails, listing the paths, if the PR changes a path, or a
renamed file's old path, that a line of `.github/CODEOWNERS` with an owner
matches. It also fails when it can't tell, for example for a PR of 3000
files or more, the most GitHub lists.

- **Neither the PR nor an approval can make it pass.** `pull_request_target`
  runs the base branch's copy of the workflow, the script, and CODEOWNERS,
  and no code from the PR. The ruleset accepts the check only from GitHub
  Actions (`integration_id` 15368).
- **It fails in both modes**, though only the auto-mode ruleset requires it:
  a pass recorded in review mode would stay on the PR's commit and count
  once auto mode is on.
- **The admin bypass skips it**, because the auto-mode ruleset, whose bypass
  list has the admin role, requires it, and `main: checks`, which no one can
  bypass, doesn't.
- **It can count more paths as owned than GitHub does, never fewer.** It
  matches with git's gitignore rules, so `docs/*` also matches files in
  subdirectories, and it ignores a line with no owner rather than letting it
  take away an earlier line's owner. Like GitHub, it skips a line starting
  with `!`.

## The needs-human-review label

The `needs-human-review` label on a PR means a person must review it before
it merges, so auto mode leaves it to the owner. An agent adds it in two
cases, as `AGENTS.md` tells it to:

- **A person asks to review the PR**, in a Linear issue, in Cursor, or in
  chat. The agent that handles the request labels the PR it opens, and an
  orchestrator puts the request in the worker's prompt
  ([orchestration.md](orchestration.md#what-a-worker-prompt-contains)).
- **The agent judges the PR to need it**, because it adds an important
  feature or makes an architectural decision. The PR body says why under
  "Needs a person".

While a PR has the label, the approval workflow doesn't approve it, the
auto-merge workflow keeps auto-merge off, and turns it off if it was on, and
the `needs-human-review` check, which `.github/workflows/needs-human-review.yml`
runs with `.github/scripts/needs_human_review.sh`, fails, so only the owner's bypass merges it. When the owner removes the
label, the check runs again and passes, the approval workflow approves the PR
if it never has, and the auto-merge workflow turns auto-merge on once Bugbot
has reviewed the latest commit.

The workflow changes alone aren't enough, because an approval the bot gave
before the label was added still counts, so anyone with write access, an
agent's token included, could merge the PR from the merge box. Dismissing
that approval instead would conflict with the approval workflow's rule of
approving a PR at most once, so removing the label couldn't bring it back.

Agents add the label through the Cursor GitHub App, acting as the owner, and
the owner adds it in the web UI; GitHub starts workflows for both, as it
doesn't for `GITHUB_TOKEN` ([below](#the-auto-merge-workflow)). On PR #75,
the workflows' run started 2 seconds after an agent added the label. Until
the check's new run starts, a PR whose auto-merge is on and that meets every
other requirement can still merge.

## The approval workflow

`.github/workflows/approve-agent-prs.yml` approves an open PR from a branch in
this repository that has the `agent` label, while `main: review (auto mode)`
is active and `main: review` isn't. In review mode it approves nothing,
because `main: review` would count its approval as a person's. It runs when
`agent-label.yml` finishes, after each push and when a PR is opened or
reopened, when a person adds the `agent` label, and when the
`needs-human-review` label is removed; the workflow's comments say why.

It approves a PR at most once, and doesn't act on a push: neither ruleset
dismisses approvals on a push, and `owned-paths` runs again on each push, so
a push that adds an owned path still stops the merge.
Because it never approves twice, dismissing its approval makes that PR wait
for a person. It needs "Allow GitHub Actions to create and approve pull
requests" on, in Settings > Actions > General > Workflow permissions;
otherwise the approval fails and the PR waits for a person.

## The auto-merge workflow

`.github/workflows/auto-merge.yml` turns on GitHub's auto-merge, with a merge
commit, for an agent PR once Bugbot has reviewed the PR's latest commit.
GitHub then merges the PR when the rulesets allow it. If the PR already meets
them, the workflow merges it at once. It waits for Bugbot because until
Bugbot posts, there are no review threads to block the merge.

It manages a PR that has the `agent` label, which `agent-label.yml` adds,
comes from a branch in this repository, not a fork, merges into `main`, and
wasn't opened by Dependabot. For such a PR:

- **Auto-merge stays off while the PR is a draft**, or while Bugbot hasn't
  finished reviewing its latest commit. A cancelled Bugbot run doesn't count.
  Bugbot gives it the same `neutral` conclusion as a review with findings, so
  the workflow reads the run's summary.
- **Auto-merge stays off while the PR has the `needs-human-review` label**,
  and adding the label turns it off ([above](#the-needs-human-review-label)).
- **A push turns auto-merge off** until Bugbot has reviewed the new commit,
  because GitHub keeps auto-merge on after a push by anyone with write access.
- **Auto-merge stays off while the PR changes an owned path**, and the owner
  merges the PR with the bypass. The required check alone isn't enough:
  when two workflows report checks of the same name, GitHub counts each
  result as it arrives
  ([github/docs#34568](https://github.com/github/docs/issues/34568)), so a PR
  that adds a workflow whose `owned-paths` job passes at once could merge
  before the real check fails.
- **While "Allow auto-merge" is off**, in Settings > General > Pull
  Requests, the workflow neither turns auto-merge on nor merges. It still
  turns auto-merge off after a push, because GitHub doesn't say that turning
  the setting off cancels auto-merge on PRs that already have it.

In review mode, the approval workflow approves nothing, so auto-merge waits
for a person's approval. The owner can't approve PRs from their own account,
so they still merge those with the admin bypass. A collaborator's approval
would merge the PR without a click, which that approval already allows.

The workflow doesn't:

- **Update a PR that is behind `main`.** `main: checks` requires an
  up-to-date branch, so the PR waits until someone updates it, or until the
  branch-update workflow, the last part of T23, does.
- **Start workflows on `main`.** GitHub makes the merge as
  `github-actions[bot]` and starts no workflows for what `GITHUB_TOKEN` does,
  so CodeQL's analysis of `main` doesn't run after an auto-merged PR.
- **Notice the `agent` label being added.** `agent-label.yml` adds it with
  `GITHUB_TOKEN` too. On PRs #35, #37, and #38 it landed within 2 seconds of
  Bugbot starting, 3 to 6 minutes before Bugbot finished. A PR labelled after
  Bugbot finishes waits until its next push, or until it is marked ready.

To stop one PR from merging, add the `needs-human-review` label to it. To stop all
of them, turn off "Allow auto-merge".

## What still needs the owner

A PR that changes a path in `.github/CODEOWNERS` needs the owner in both
modes. Agent PRs are authored by the owner's account, and GitHub doesn't let
authors approve their own PRs, so the owner merges these with the admin
bypass: in review mode because the PR needs a person's approval, and in auto
mode because `owned-paths` fails. Those paths include CI and the rulesets
(`.github/`), the commands CI runs (`mise.toml` and `.config/mise/`), the
agent instructions (`.cursor/` and `AGENTS.md`), and the files that configure
checks, dependencies, and module boundaries, such as `biome.json`,
`docs/build.sh`, `Cargo.toml`, and `pyproject.toml`. A change to one of those can weaken a
check or add a dependency, which D7 already requires the owner to approve.

## Switching auto mode on and off

Auto mode needs "Allow GitHub Actions to create and approve pull requests"
and "Allow auto-merge" on, and Bugbot on for the repository.
`mise run setup-status` reports which manual setup steps are done.

```sh
mise exec -- .github/rulesets/apply.sh --dry-run --auto  # print the changes
mise exec -- .github/rulesets/apply.sh --auto            # switch on
mise exec -- .github/rulesets/apply.sh                   # switch off
```

`--auto` creates or updates `main: review (auto mode)`, then disables
`main: review`; without the flag, the script does the reverse. It needs `gh`
logged in as a repository admin. Without a shell, use Settings > Rules >
Rulesets: the first time, import `main-review-auto.json` with New ruleset >
Import a ruleset; then set the enforcement status of one review ruleset to
Active and the other to Disabled. After `main-review-auto.json` changes, as
when it gained the rule that requires `owned-paths` and
`needs-human-review`, the ruleset on GitHub
matches it only once `apply.sh --auto` runs again, or once it is deleted and
imported again in Settings.

Switching off, the script first dismisses the approval workflow's approvals
on open PRs: in review mode each would count as a person's, so a PR that
auto mode held back on an unresolved thread would merge. Switching off in
Settings skips this, so dismiss them by hand first. A dismissed approval
isn't given again, and a PR opened before auto mode was on gets its approval
on its next push.

### Checking auto mode on scratch PRs

These steps check GitHub's behaviour, which CI can't. Run them once after
switching auto mode on. Make each commit with
`git commit --author "Cursor Agent <cursoragent@cursor.com>"`, so that
`agent-label.yml` labels the PR.

1. Turn on "Allow GitHub Actions to create and approve pull requests" in
   Settings > Actions > General, and turn off "Allow auto-merge" in
   Settings > General, so the scratch PRs don't merge.
2. Run `mise exec -- .github/rulesets/apply.sh --auto`.
3. Open PR A from a new branch, changing only `docs/linear.md`. Within two
   minutes it has the `agent` label and the bot's approval, and `owned-paths`
   passes. Once checks pass and any threads are resolved,
   `gh pr view --json reviewDecision` prints `APPROVED`, and the merge box
   allows merging without the bypass.
4. Open PR B the same way, changing only `AGENTS.md`. It has the bot's
   approval, and `owned-paths` fails, listing `AGENTS.md`. The merge box says
   the required check failed, and only the bypass merges it, even if
   `reviewDecision` prints `APPROVED`.
5. Push a commit to A that changes `AGENTS.md`. The bot doesn't approve
   again, `owned-paths` fails on the new commit, and only the bypass merges
   A.
6. Run `mise exec -- .github/rulesets/apply.sh`, which dismisses the bot's
   approvals on A and B. Close both, delete their branches, and turn "Allow
   auto-merge" back on.

## Instruction for worker prompts

Add these lines to the prompt of each agent that works in auto mode:

> Resolve a Bugbot review thread only after you fix its finding. If you
> dispute a finding, reply saying why and leave the thread open, so the PR
> waits for the owner. Mark the PR ready for review when your work is done,
> because a draft doesn't merge.

An unresolved thread blocks merging. In auto mode, threads are the only gate
against merging a flawed PR that passes CI, so only the owner closes a
disputed one.

## Auditing and reverting

Every PR merges as a merge commit (D6), so each auto-merged PR is one commit
on `main`, and one revert undoes it. To list the PRs merged since auto mode
was switched on, here from 2026-10-10:

```sh
gh pr list --state merged --label agent --search "merged:>=2026-10-10" \
  --json number,title,mergedAt,mergeCommit
```

Read each with `gh pr diff <number>`; its CI runs and Bugbot's review are on
the PR page. To revert one, branch from `main`, run
`git revert -m 1 <merge commit>`, and open a PR. `-m 1` keeps `main`'s side
of the merge, which undoes everything the PR changed.

## Limits

- **Spend: $500 per day** across all cloud agent runs on this repository.
  It counts cloud agent runs only, as `mise run spend` counts them, not
  editor or Bugbot usage. It is a starting value, to revise with
  `mise run spend` data. The repository can't stop a run partway through, so
  the real cap is the spend limit the owner sets in the Cursor dashboard. The
  orchestrator checks the day's spend at each pause with
  `mise run spend -- --since "$(date -u +%F)"`, whose "Repository
  github.com/<owner>/<repo>" row plus its "Repository unknown" row is the
  most this repository spent since 00:00 UTC; a run lands in "unknown" when the
  Cloud Agents API's listing lacks it, so the first row alone can undercount.
  The "All N cloud agent runs" row includes every repository on the team's
  account. The repository rows need `CURSOR_API_KEY`.
- **Size: 500 changed lines per PR**, the ceiling `pr-size` enforces in both
  modes. A PR whose description starts with `Oversize:` passes `pr-size`, and
  Bugbot then checks that the `large-changes` skill allows it.
