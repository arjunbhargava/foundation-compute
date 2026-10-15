---
name: large-changes
description: >
  Split a change that exceeds the 500-line PR ceiling in `reviewable-prs` into
  stacked PRs, or justify a single oversize PR. Use when a task looks likely to
  exceed 500 changed lines, before starting it.
---

# Large changes

When a task exceeds the ceiling, stack it: plan the sequence of PRs first,
make each one build and pass tests on its own, and base each branch on the
previous one. Prefer landing an unused-but-tested piece before the change that
wires it in.

## Oversize overrides

Exceeding 500 lines is allowed only when splitting would leave an intermediate
state that doesn't build, is incorrect, or is harder to review than the whole.
Allowed categories:

- **Mechanical**: rename, move, format, or codemod. State the exact command
  that produced it, so review means rerunning it and checking the diff matches.
  It contains no hand edits; put any fix-ups in a separate commit.
- **Deletion-only**: removal of dead code with no behaviour change.
- **Atomic**: a change that must land together, such as an interface change
  and all its callers, or a schema migration and the code that reads it.

An oversize PR starts its body with
`Oversize: <category> — <why it can't be split>`. It must also list what to
read closely and what can be skimmed. "It was faster" is not a reason.
