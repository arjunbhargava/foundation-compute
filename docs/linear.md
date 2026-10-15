# Linear conventions

Work is planned as Linear issues, and Cursor cloud agents turn each issue into
one pull request (PR). This page is for people and agents who file or pick up
issues. The repository owner sets up the Linear and Cursor settings
these conventions rely on (task T17 in the plan in the [template repository](https://github.com/arjunbhargava/foundation)).

## Filing an issue

- Start every issue from the issue template below. Write each acceptance
  criterion as behaviour someone can check, because each one becomes a named
  test in the PR.
- Split work that needs several PRs into a parent issue with one sub-issue
  per PR, each sub-issue from the template. Linear marks an issue done when
  every PR linked to it has merged, and the next PR in a stack is usually not
  open when the first merges, so one shared issue would close after the first
  PR. The parent stays open until its sub-issues are done.
- Each Linear project carries a label from the `repo` label group, named
  after its repository as `owner/name`, for example
  `arjunbhargava/foundation`. Cursor takes an issue's repository from the
  first of: `[repo=owner/name]` in the issue text, a `repo` label on the
  issue, a `repo` label on its project, or the default repository in the
  Cursor dashboard
  ([Cursor docs](https://cursor.com/docs/integrations/linear#repository-selection)).
- Linear keeps issue labels and project labels apart, so the `repo` group
  exists in both. A new repository made from this template adds its label to
  both groups, then puts it on its Linear projects. If Linear's or Cursor's
  GitHub app has access only to selected repositories, add the new one there
  too.

## Handing an issue to an agent

- A person adds the `agent-ready` label when the template is filled in,
  everything the issue needs has merged, and any plan the change needs
  (decision D7 in the plan in the [template repository](https://github.com/arjunbhargava/foundation)) is approved. Sub-issues don't inherit labels, so
  add it to each sub-issue.
- Delegate only `agent-ready` issues to Cursor: pick Cursor in the assignee
  field, or mention `@Cursor` in a comment. Linear keeps the person as the
  assignee and records Cursor as the delegate.
- Each delegated issue becomes one agent, one branch, and one PR. The PR
  description includes `Fixes <issue ID>`, for example `Fixes ENG-123`, as
  `.github/pull_request_template.md` asks. Linear links the PR to that issue,
  or sub-issue, and marks it done when the PR merges.
- An agent lists a problem outside its issue under Follow-ups instead of
  fixing it; any issue it files uses the template, without `agent-ready`.

## Issue template

Paste this template into Linear under Settings > Templates. The line under each
heading is a hint for the person filing the issue; mark it as placeholder
text in Linear's template editor.

```markdown
## Goal

What this issue achieves and why, in one or two sentences.

## Acceptance criteria

- [ ] Behaviour someone can check, for example: `mise run lint` fails when a public function has no doc comment.

## Verification command

The command that checks every criterion, for example `mise run test`.

## Out of scope

What this issue deliberately leaves out.

## Compute budget

The most this issue may spend on compute jobs, in US dollars, or 0 if it launches none.

## Designs

Links to designs, plans, or related issues. Delete this section when there are none.
```
