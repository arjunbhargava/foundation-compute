# foundation-compute

The project's documentation: its own pages first, then the API reference,
which `docs/build.sh` generates from doc comments in the source and fails on
any undocumented public symbol or broken reference. The operating guide holds
the pages that are the same in every project made from the template.

```{toctree}
:caption: This project
:maxdepth: 1

<<<<<<< before updating
agent-instructions
=======
README <project-readme>
architecture
>>>>>>> after updating
```

```{toctree}
:caption: API reference
:maxdepth: 1
:glob:

<<<<<<< before updating
agent-rules-and-skills
architecture
auto-mode
compute-jobs
install-script
linear
orchestration
template-updates
=======
api/*
>>>>>>> after updating
```

```{toctree}
:caption: From the template
:maxdepth: 1

operating-guide
```
