---
name: plan
description: >
  Write a short plan covering the problem, the interface, the files touched,
  and the acceptance criteria, then stop until a person approves it. Use when
  a change meets decision D7 in `docs/template-plan.md`, before writing its
  code: a new module, a change to a public interface or data format, or a new
  dependency.
---

# Plan

Some changes need a plan that a person approves before any code is written:
those that meet decision D7 in `docs/template-plan.md`. Check a task against
D7 before starting, and again if the work grows, for example when it turns out
to need a new module. Below the threshold, write no plan. Planning pays
off only for larger changes, and a bad plan is worse than none (finding F5).

D7's last trigger, compute spend above the cost limit, is handled when a job
is launched rather than before coding: the `compute-cost` rule says when to
ask, with an estimate, in the PR.

## Write the plan

Use these headings, and keep each to a few lines:

- **Problem**: what is wrong or missing, and why it matters. Link the issue.
- **Interface**: what callers will see: public functions and types, data
  formats, and commands, with units, valid ranges, and errors. For a new
  dependency, give its name, its licence, and why nothing already installed
  covers it.
- **Files touched**: each file to be created or changed, with one line on
  what changes in it.
- **Acceptance criteria**: behaviour someone can check. Each becomes a named
  test (`testing` skill).
- **Open questions**: anything you would otherwise have to guess; omit if none.

If the work needs more than one PR, say so; once the plan is approved, the
`decompose` skill splits it into sub-issues.

## Stop for approval

Post the plan where the person who approves it will read it: on the Linear
issue the task came from, or in reply to whoever asked for it. Don't commit it
to the repository; plans live in Linear, not in shared files (finding F7).

Then stop. Write no code until a person approves the plan. If they ask for
changes, revise it and stop again. The PR notes, in one line, any difference
from the approved plan that matters (`reviewable-prs`). A new dependency the
plan doesn't name doesn't stop the work; the PR marks it "(not in the plan)".
