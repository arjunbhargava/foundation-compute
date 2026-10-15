# Agent rules and skills

The instructions that Cursor agents follow are in `.cursor/`.

Rules in [`.cursor/rules/`](https://github.com/arjunbhargava/foundation-compute/tree/main/.cursor/rules) load into every agent session,
except `dependencies`, which loads when an agent reads or edits a dependency
manifest or lockfile:

| Rule | Requires |
|---|---|
| [`clarity`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/rules/clarity.mdc) | Code, docs, and PRs are written for a competent engineer new to the code, and checked against the rule's review checklist before finishing. |
| [`compute-cost`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/rules/compute-cost.mdc) | Agent compute jobs share a cap of $10,000 a day. An agent asks a person before a job that would take its task over the task's compute budget, and before every job until the `compute-jobs` skill exists. |
| [`dependencies`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/rules/dependencies.mdc) | A new dependency comes with a one-line reason, an allowed licence, and a committed lockfile. A lockfile merge conflict is resolved by relocking, never by hand. |
| [`docs-from-source`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/rules/docs-from-source.mdc) | API reference is generated from doc comments, never written by hand, and each doc comment states the contract a caller needs. |
| [`ponytail`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/rules/ponytail.mdc) | The simplest solution that works, once the problem is understood. |
| [`reviewable-prs`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/rules/reviewable-prs.mdc) | About 300 changed lines per PR and at most 500, one logical change each, and a short body that follows the PR template. |
| [`secrets`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/rules/secrets.mdc) | Secrets come from environment variables, are listed by name in `.env.example`, and never appear in commits or logs. |

Skills in [`.cursor/skills/`](https://github.com/arjunbhargava/foundation-compute/tree/main/.cursor/skills) are read only when a task needs
them:

| Skill | Use when |
|---|---|
| [`add-language`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/skills/add-language/SKILL.md) | Adding a programming language to a project: its checks, docs build, CI job, and test command. |
| [`architecture-docs`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/skills/architecture-docs/SKILL.md) | Designing module or system boundaries, or writing READMEs, design docs, ADRs, and architecture diagrams. |
| [`clarity`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/skills/clarity/SKILL.md) | Creating or reorganising a module or file, writing a document, or designing a diagram, docs site, terminal output, or user interface. |
| [`decompose`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/skills/decompose/SKILL.md) | Splitting an approved plan into Linear sub-issues, one per PR, for agents to work on in parallel. |
| [`large-changes`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/skills/large-changes/SKILL.md) | Planning a change likely to exceed 500 changed lines: splitting it into stacked PRs, or justifying one oversize PR. |
| [`plan`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/skills/plan/SKILL.md) | Before coding a change that decision D7 in the plan in the template repository says needs an approved plan: a new module, a public interface or data format change, a new dependency, or compute spend above the cost limit. |
| [`prune-review`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/skills/prune-review/SKILL.md) | Finding and removing dead code, speculative abstractions, and stale docs, on request or after a breaking change. |
| [`source-docs`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/skills/source-docs/SKILL.md) | Writing the first code in the repository, adding a language, or changing the docs build or its gates. |
| [`testing`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/skills/testing/SKILL.md) | Writing or changing tests, including the checks and tolerances numerical code needs. |

Changes to rules and skills are written or edited by a person, not generated
by an agent for itself, because only the former have been shown to help
<<<<<<< before updating
(finding F2 in the plan in the [template repository](https://github.com/arjunbhargava/foundation)).
=======
(finding F2 in [the plan](https://github.com/arjunbhargava/foundation/blob/main/docs/template-plan.md)).
>>>>>>> after updating

Bugbot, Cursor's review agent, reviews every PR before a person does, using
the checks in [`.cursor/BUGBOT.md`](https://github.com/arjunbhargava/foundation-compute/blob/main/.cursor/BUGBOT.md).
