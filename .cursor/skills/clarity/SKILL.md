---
name: clarity
description: >
  Make modules, docs, diagrams, and interfaces as easy as possible for people
  to understand. Use when creating, splitting, or reorganising a module or
  file; writing or editing a doc page, README, design doc, or ADR; or creating
  or changing a diagram, docs site, terminal output, user interface, or
  colours. The always-applied `clarity` rule covers naming, layout, comments,
  and writing in every change.
---

# Clarity

Everything in a repository is read far more often than it is written. The
goal of every change is that the reader builds a correct mental model with the
least effort. The reader is a competent engineer who is new to this code.

The other rules and skills serve this goal. Ponytail minimalism means fewer
concepts for the reader to hold, not fewer characters: when the shortest code
is harder to follow than a slightly longer version, write the longer version.
`architecture-docs` applies this skill to system structure and diagrams, and
`source-docs` applies it to API reference.

The `clarity` rule is always applied. It holds the checks for naming, layout,
comments, error messages, and writing that every change needs, and the review
checklist to apply before finishing. This skill adds what applies only to
modules and files, documents, and visual design.

## Code structure

- **Organise by what the code does, not by its kind.** Name a module
  `integrator` or `checkpoint`, not `utils`, `helpers`, `managers`, or `common`.
- **Keep related code together.** A reader should understand a behaviour from
  one file. Every hop to another file or through an interface costs the reader
  something, so each one must buy something.

## Visual design and colour

These apply to diagrams, docs sites, terminal output, and user interfaces.
For diagrams, `architecture-docs/references/diagram-style.md` defines the
palette and vocabulary.

- Colour encodes meaning, one meaning per colour, the same across the repo.
  Every encoding has a legend.
- Never rely on colour alone. Pair it with shape, label, or position, so
  colour-blind readers and greyscale prints lose nothing.
- Text meets WCAG AA contrast: at least 4.5:1, or 3:1 for large text.
- Use few colours and one accent. The accent marks the single thing the
  reader should look at first.
- Group with position and whitespace before adding borders or boxes.
- Show hierarchy with size and weight, not with extra colours.

## Writing documents

These add to the writing checks in the `clarity` rule, for doc pages, READMEs,
design docs, and ADRs.

- **Open with the claim.** Include status (planned, stable, deprecated) when it
  isn't obvious.
- **Concrete before abstract.** Show one real example or one end-to-end trace,
  then generalise.
- **Progressive disclosure.** Overview, then mechanism, then edge cases. A
  reader who stops after the first section still has a correct, coarse model.
- **Explain why.** Code shows what. Writing carries intent, trade-offs,
  rejected alternatives, and when to revisit a decision.
- **Quantify.** Write "p95 under 40 ms per time step for a 512³ grid on one
  GPU", not "fast". State units and where numbers came from.
- **Link, don't duplicate.** Each fact lives in one place.

Before finishing, apply the review checklist in the `clarity` rule.
