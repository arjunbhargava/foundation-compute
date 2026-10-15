# Diagram design system

The goal is diagrams a newcomer can read without help. Each one answers one
question, uses a small, fixed visual vocabulary explained by a legend, and
stays quiet enough that the eye lands on what matters. Colour and line style
always mean something; nothing is decorative.

Diagrams are written in [D2](https://d2lang.com) and laid out by TALA, D2's
orthogonal layout engine (open source since D2 v0.9.0). Each diagram is
rendered to an SVG that is committed next to its source, so GitHub shows it in
markdown and reviewers can diff the text. One shared style file holds every
visual decision.

## Principles

1. **One question per diagram.** Write the question above the diagram and the
   takeaway below it. If the takeaway needs "and", split the diagram.
2. **Place nodes by hand; let the engine route edges.** Place nodes with grids so
   the layout says what the diagram means (stages left to right, steps top to
   bottom), and let TALA route the edges. A layout that the engine invents
   changes unpredictably when a node is added. Readers lose their spatial
   memory of the diagram, and reviewers can't see what changed.
3. **Semantic colour only.** Colour encodes the element's kind, and the kind is
   always shown twice, by colour and by shape, so a colour-blind reader or a
   greyscale print loses nothing.
4. **One accent.** Only core elements and the primary path get orange, so it
   draws the eye to the main story. More accented elements dilute it.
5. **Say what moves.** Edge labels are nouns for what flows (`field
   snapshots`), never verbs like `calls` or `uses`.
6. **Consistent identity.** An element has the same name, kind, and colour in
   every diagram, so readers can follow it as the diagrams zoom in.
7. **Small.** At most ~12 nodes, edge labels of at most 4 words, and a node
   subtitle of one line. Past that, split by level: context, then data flow,
   then one component's internals.
8. **Each diagram shows only what its question needs.** The context diagram
   shows the external services, so the data-flow diagram names them in
   adapter subtitles (`↔ object storage`) instead of drawing them again.

## Palette

Based on [Anthropic's brand palette](https://github.com/anthropics/skills/blob/main/skills/brand-guidelines/SKILL.md):
warm neutrals plus three muted accents. Fills are 20% tints of the accent over
Light. Contrast ratios are WCAG values.

| Token | Light | Dark | Use |
|---|---|---|---|
| Text | `#141413` | `#faf9f5` | All text (≥ 11:1 on every fill in both modes) |
| Background | `#faf9f5` | `#1f1e1d` | Diagram background, boundary fill |
| Surface | `#ffffff` | `#2b2a27` | Module fill |
| Panel | `#f0eee6` | `#262523` | Stage panels, sequence phases |
| Store | `#e8e6dc` | `#3a3935` | Stores, phase outlines |
| Boundary | `#b0aea5` | `#5e5d59` | Boundary outlines |
| Line | `#8a887f` | same | Grey edges and module outlines (≥ 3.6:1 in both modes) |
| Muted | `#5e5d59` | `#b0aea5` | Stage and boundary titles, grey edge labels (≥ 5.2:1) |
| Orange / tint | `#d97757` / `#f3dfd5` | same / `#48322a` | Core, primary path |
| Green / tint | `#788c5d` / `#e0e3d7` | same / `#33362b` | People, and states waiting on a person |
| Blue / tint | `#6a9bcc` / `#dde6ed` | same / `#303a44` | External services |

Dark tints are 22% of the accent over the dark background. `_style.d2` holds
the light values. D2's dark themes don't recolour explicit style colours, so
`render.sh` appends `_dark.css` to each SVG. It remaps every light colour
under `@media (prefers-color-scheme: dark)`, so one SVG follows the viewer's
system setting on GitHub and in the docs site. A new colour in any `.d2` file
needs a dark value in `_dark.css`; `render.sh` fails until it has one. A
viewer who sets GitHub or the site to dark while the system is light still
sees the light diagram, because an SVG image can only read the system
setting.

## Vocabulary

Each kind is a class in `docs/diagrams/_style.d2`. Use only the classes there:
don't set colours inline, and add a new class to the style file and the legend
first.

| Kind | Class | Look |
|---|---|---|
| Person | `person` | Green figure. As a state or participant, use it with `shape: rectangle`. |
| Core: owns state or policy | `core` | Orange box, bold |
| Module: adapter or plumbing we own | `module` | Plain box |
| External service | `external` | Blue box |
| Store: database, file, queue | `store` | Grey cylinder |
| Stage: one step of a flow | `stage` | Shaded panel, title at the bottom |
| Boundary: trust or deployment | `boundary` | Dashed outline |
| Sequence phase | `phase` | Shaded group |
| Layout-only container | `frame` | Invisible. Keeps a child at its natural size inside a grid cell. |
| Empty grid cell | `spacer` | Invisible, one node in size |

| Edge | Class | Meaning |
|---|---|---|
| Primary path | `primary` | Thick orange. The route to read first; keep it to one chain per diagram. |
| Data flow | `flow` | Grey. Something moves; the label says what. |
| Reply, failure, or optional | `aside` | Dashed grey. Responses, error returns, and paths not always taken. |
| Request and response | `flow` on a `<->` edge, label `request → response` | One edge per relationship; the sequence diagram shows the round trip |

Node labels are a title, then an optional subtitle line for the role:
`"Solver\ntime stepping · boundary conditions"`. Separate list items with
` · `. Nodes have a fixed size from their class, so grid rows line up.

## Layout rules

- **Data flow and context: grids.** The root is `grid-rows` or `grid-columns`,
  with one `stage` or `boundary` container per step or zone. Each container
  lays out its nodes on its own grid, with `spacer` cells so that rows align
  across columns.
- **Edges in a grid must join adjacent cells.** An edge that skips a cell is
  drawn straight through it. If two nodes need an edge, rearrange the grid so
  they touch. Otherwise, reconsider whether the diagram needs that edge.
- **Wrap lone nodes in a `frame`,** because grid cells stretch their contents
  to the row size.
- **Sequence diagrams:** `shape: sequence_diagram`. Order participants people
  first, then our code, then externals, and give each its kind's class. Put
  every message inside a `phase` group named `N · Phase`.
- **State diagrams:** use TALA's free layout, with no grid. It draws cycles as
  loops. Make the success loop `primary`, and make failure returns `aside`.
- **A small linear diagram** such as the legend may override the engine:
  `vars: {d2-config: {layout-engine: elk}}` with `direction: right`.
- **D2 syntax limits:** `top`, `left`, `near`, `width` and `height` are
  reserved keys and can't be node names. `stroke-width` must be an integer.

## Files and rendering

```
docs/diagrams/
  _style.d2      shared classes and theme (copy of assets/_style.d2)
  _dark.css      dark palette appended to every SVG (copy of assets/_dark.css)
  render.sh      renders every .d2; --check fails if an SVG is stale
  context.d2     one source per diagram...
  context.svg    ...committed next to its render
```

Each diagram starts with `...@_style`. Embed a diagram with alt text that states
its takeaway: `![Data flow: raw data goes down through Ingest, …](diagrams/dataflow.svg)`.

After editing a `.d2` file, run `docs/diagrams/render.sh`, look at the SVG,
and commit the source and the SVG together. A project's first diagram adds
`docs/diagrams/render.sh --check` to `docs/build.sh`, which the template does
not yet have; from then on a stale SVG fails the docs build. Renders are pinned to
one D2 version, because other versions produce different SVGs. Install it with
`curl -fsSL https://d2lang.com/install.sh | sh -s -- --version v0.9.0`, and
bump the version in `render.sh` in a PR of its own that re-renders everything.

## Page layout

`docs/architecture.md` is laid out in this order:

1. A status line: planned, partial, or implemented.
2. **How to read this doc**: the diagrams in reading order, each with its
   question, plus where the sources live.
3. **Legend**: `legend.svg`, showing one example of each kind and edge the
   repo uses, followed by a table with columns `Element | Looks like | In <repo>`.
   The last column is the repo-specific meaning, for example "External
   service: a paid provider API reached over the network". Note any
   per-diagram meaning, such as green states.
4. **Glossary**: every domain term that appears in a diagram, defined in one
   line each.
5. The diagrams, numbered, each as: heading, question, diagram, takeaway (1–3
   sentences, including any invariant the diagram can't show).

When a PR adds a kind, an edge style, or a term to any diagram, it updates the
legend and glossary in the same PR.

## Review a render

Open each changed SVG, and attach PNGs of the changed diagrams to the PR.
Check for:

- Edges passing through nodes, which breaks the adjacency rule.
- Labels overlapping lines or titles.
- A primary path that doesn't read as one continuous story.
- A diagram wider than about 1000 px. Split it, or stack its stages.
