---
name: decompose
description: >
  Turn an approved plan into Linear sub-issues, one per PR, each stating the
  interface it builds or uses, the files it owns, its acceptance criteria, the
  command that checks it, and the sub-issues it waits for. Use when a plan
  approved through the `plan` skill needs more than one PR, or when asked to
  split work into tasks for agents.
---

# Decompose

When many agents work at once, what works is a planner that splits the work
and workers that each own one task on their own branch, without coordinating
with each other (finding F7 in `docs/template-plan.md`). Splitting closely
connected code between agents breaks interfaces and causes rework (F8). So
agree the interface first, land it, and then split the rest.

Start only from a plan a person has approved (`plan` skill). Follow
`docs/linear.md`: the plan's issue becomes the parent, with one sub-issue per
PR.

## Split the work

- Land shared interfaces first, as their own PR: the types, function
  signatures, and data formats that more than one sub-issue uses. Every
  sub-issue that uses them waits for that one.
- Keep closely connected work in one sub-issue rather than splitting it. Work
  is closely connected when its parts can't be built against an interface
  fixed in advance, or when they change the same functions.
- Each sub-issue is one PR within the size limits in `reviewable-prs`.
  Connected work too large for one PR becomes a stack (`large-changes`
  skill): one sub-issue per PR, each waiting for the one before.
- Two sub-issues that can run at the same time don't own the same file.

## Write each sub-issue

Write each sub-issue from the issue template in `docs/linear.md`, adding three
sections, so that it states:

- **Interface** (added): what it builds or uses, by the names in the plan.
- **Files** (added): the files it creates or mainly changes.
- **Acceptance criteria**: from the plan, as behaviour someone can check.
- **Verification command**: the narrowest command that checks every
  criterion, such as the package's own test command.
- **Waits for** (added): the sub-issues that must merge first. Also add each
  as a Linear "blocked by" relation, so Linear shows the sub-issue as blocked.

The Designs section links the approved plan. Don't add `agent-ready`; a person adds it
once everything a sub-issue waits for has merged (`docs/linear.md`). If you
can't create Linear issues, write them out in this form for a person to
create.
