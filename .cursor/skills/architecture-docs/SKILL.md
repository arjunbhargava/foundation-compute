---
name: architecture-docs
description: >
  Design sensible architecture and write clear, didactic documentation. Use when
  designing or restructuring modules or system boundaries, writing or revising
  READMEs, design docs, ADRs, or module docs, or explaining how a system works.
  Not for routine code edits that don't change structure or docs.
---

# Architecture and documentation

Good architecture and good documentation both aim to let a newcomer build an
accurate mental model quickly. Choose the structure that is simplest to
explain correctly, and write the explanation that makes the structure obvious.
Ponytail minimalism still applies: no layer, document, or section without a
reader who needs it.

## Architecture

Before proposing structure, state the problem in terms of data and constraints:
inputs, outputs, state, who owns the state, latency/throughput/cost bounds, and
the failure modes that matter. Structure follows from these, not from patterns.

- **Deep modules** (Ousterhout): small interface, substantial hidden
  behaviour. A module whose interface is as complex as its implementation
  should be merged into its caller.
- **Boundaries where change or trust differs.** Split along axes that change
  independently (provider SDK vs. domain logic) or at trust boundaries
  (client vs. server). Don't split along axes that always change together.
- **Dependencies point inward.** Domain logic imports nothing
  provider-specific; adapters depend on the domain, never the reverse.
- **One owner per piece of state.** Name it. Everything else receives it
  explicitly or asks the owner.
- **Invariants are explicit.** Write each one down next to the code that
  enforces it, and enforce it in one place.
- **Make failure a first-class path.** For each external call: what happens on
  timeout, auth failure, partial result? Surface it; don't silently fall back.
- **Concrete first, abstract on the third use.** One implementation gets no
  interface. Two similar ones are often fine. Three justify extraction.

For a non-trivial decision, write it as a short ADR (Nygard format): context,
decision, consequences, and alternatives rejected with the reason. Store as
`docs/adr/NNNN-title.md`; never rewrite an accepted ADR, supersede it.

## Documentation

Classify every document by what the reader is doing (Diátaxis), and don't mix
the four kinds in one section:

| Kind | Reader's goal | Shape |
|---|---|---|
| Tutorial | Learn by doing | Guided path with a guaranteed working result |
| How-to | Accomplish a specific task | Numbered steps, prerequisites, no theory |
| Reference | Look something up | Complete, consistent, terse; generated where possible |
| Explanation | Understand why | Context, trade-offs, alternatives, history |

Write every document by the writing rules in the `clarity` rule and skill. For
architecture docs in particular, a single end-to-end trace (request, then each
component, then response) teaches more than a list of components.

## Diagrams

`docs/architecture.md` holds a maintained set of diagrams. They are the fast
path to the mental model: a reader should understand the system from the
diagrams and their captions, and turn to the prose for the reasons behind it.

The set is fixed, and each diagram answers one question:

| Diagram | Question | D2 layout |
|---|---|---|
| Context | What talks to the system, across which trust boundary? | Grid of columns |
| Data flow | What are the parts, and what moves between them? | Grid of stage columns |
| Main flow | What happens, in order, for the core use case? | `sequence_diagram` |
| State | What states can the stateful part be in, and what moves it? | TALA, free layout |

Add a diagram only for a question the set doesn't answer, such as a second
core flow. Drop one that stops carrying information.

Every diagram follows the design system in
[references/diagram-style.md](references/diagram-style.md). It covers the
palette, the node and edge vocabulary, the shared D2 style, layout rules, the
page layout with its legend and glossary, and how to render and check diagrams. Read it before
creating or editing a diagram. In addition:

- Node names are the identifiers used in code (module, class, or env var), so
  a diagram can be grepped against the source.
- Mark anything not yet implemented as `planned`, for example with a dashed
  edge or a `(planned)` suffix. If none of it exists yet, a single status line
  at the top of the doc is enough. A diagram must never show a design as if
  it already exists.
- Until the code exists, name nodes after the design doc's terms. Rename them
  to code identifiers in the PR that introduces the code.

Maintenance: every PR checks the diagrams against its diff. If it changes
components, dependencies, data flow, state transitions, or external services,
update the affected diagrams in the same PR, and name them in the PR body.
Don't mention diagrams when none changed. A stale diagram is worse than none,
because it teaches the wrong model.

## Placement

- `README.md`: what it is, quickstart, pointer to the rest. Short.
- `docs/architecture.md`: the diagrams, then the prose: system context, main
  data flow, module map, invariants, failure handling.
- `docs/adr/`: decisions.
- Module-level doc comment: that module's responsibility, invariants, and
  what it deliberately does not do.

## Review checklist

Before finishing, check the result against these:

1. Could a new engineer draw the main data flow after reading only the
   overview?
2. Is every term defined once and used consistently?
3. Does every component have one stated responsibility and owner of state?
4. Are failure modes and invariants written down where they're enforced?
5. Does every diagram match the code as of this diff, with any planned parts
   marked?
6. Is there anything (a section, layer, or abstraction) that no reader needs?
   Delete it.
