---
name: prune-review
description: >
  Systematically review the codebase (or one area of it) for dead code,
  speculative abstractions, and stale docs, then remove them in reviewable PRs.
  Use when asked for a codebase review, cleanup, or cruft removal; after a
  breaking change lands; or from a scheduled automation.
---

# Prune review

Agent-written codebases accumulate cruft. Examples include helpers written
"for later", wrappers left behind by a refactor, and tests that only exercise
dead code. Every retained line costs every future reader and agent context.
The default is to delete. Keeping code requires a current caller or a
concrete, near-term plan to use it.

## Scope

- **Scheduled or requested with no area given**: the whole repository.
- **After a breaking change**: the modules the change touched, plus
  everything that imported them before the change.

## 1. Inventory

Build evidence before judging anything:

1. Run the language's unused-code tooling if it's available, for example
   `vulture` or `ruff --select F401,F841` (Python), `knip` or `tsc
   --noUnusedLocals` (TypeScript), or compiler warnings (Rust, C, and
   C++). Treat the output as candidates, not verdicts.
2. For each public symbol in scope, count references outside its own
   definition and its own tests, using `rg -w <name>`.
3. Check for dynamic references before calling anything unused: string
   dispatch, registries, entry points in `pyproject.toml` or `package.json`,
   CLI command tables, config files, reflection, and serialized names.

## 2. Classify

| Finding | Default action |
|---|---|
| No references, or only referenced by its own tests | Delete, with its tests |
| Abstraction with one implementation (interface, factory, base class, plugin hook) | Inline it into the concrete code |
| Config option, flag, or parameter that is never varied | Replace with the constant |
| Compatibility shim, fallback, or deprecated path with no remaining users | Delete |
| Duplicate of an existing helper or stdlib function | Replace callers, delete the copy |
| Commented-out code; TODOs with no owner or issue link | Delete; file an issue if the TODO matters |
| Docs, diagrams, or README sections describing removed or never-built behaviour | Fix, or mark `planned` |
| Test that asserts implementation details rather than behaviour | Rewrite or delete |

Keep code only for one of these reasons, and state which in the report:

- It is used by a documented public API or an external consumer.
- It is referenced dynamically (give the reference).
- It is committed near-term work (link the issue or design doc).

"Might be useful" is not a reason. Version control keeps the history.

Never remove validation at trust boundaries, error handling that prevents
data loss, security checks, or accessibility, even if they look unused.
Check for a reason before removing them.

## 3. Deliver

- Write the report first, as a table: path/symbol, finding, evidence (the
  reference count or the tool output), and action.
- Put removals in their own PRs, never mixed with behaviour changes. Group
  them by area so each PR can be reviewed as one argument. Deletion-only PRs
  may use the oversize override in the `large-changes` skill.
- Put inlining and simplification refactors in separate PRs from pure
  deletions.
- Verify each PR: the build, the full test suite, and the unused-code tooling
  all pass, and the tooling shows fewer candidates than before.
- Update `docs/architecture.md` diagrams for any removed component or edge.

If nothing warrants removal, say so in one line. A review that finds nothing
is a valid result; don't invent findings.
