# foundation-compute

The project's documentation: its own pages first, then the API reference,
which `docs/build.sh` generates from doc comments in the source and fails on
any undocumented public symbol or broken reference. The operating guide holds
the pages that are the same in every project made from the template.

```{toctree}
:caption: This project
:maxdepth: 1

README <project-readme>
architecture
compute-jobs
```

```{toctree}
:caption: API reference
:maxdepth: 1
:glob:

api/*
```

```{toctree}
:caption: From the template
:maxdepth: 1

operating-guide
```
