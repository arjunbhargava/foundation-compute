# foundation-compute

The project's documentation. The explanation pages are written by hand. The
API reference is generated from doc comments in the source by
`docs/build.sh`, which fails on any undocumented public symbol or broken
reference.

`.github/workflows/docs-site.yml` publishes this site to GitHub Pages from
`main`: after each push, daily, and when run from the Actions tab. The daily
run publishes pull requests that auto-merge, because GitHub starts no
workflow for those merges. Each repository, including each project made from
the template, turns Pages on once, in Settings > Pages > Build and
deployment > Source: GitHub Actions; until then the workflow's deploy job
fails. A project that doesn't want a site disables the workflow in the
Actions tab instead. GitHub Pages is free for public repositories but needs a
paid plan for private ones, and the site of a private repository is still
public.

```{toctree}
:caption: Start here
:maxdepth: 1

README <project-readme>
agent-instructions
```

```{toctree}
:caption: Explanation
:maxdepth: 1

agent-rules-and-skills
architecture
auto-mode
install-script
linear
orchestration
template-plan
template-updates
```

```{toctree}
:caption: API reference
:maxdepth: 1
:glob:

api/*
```
