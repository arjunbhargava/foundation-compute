# Operating guide

How people and agents work in any repository made from the template. It is
the same in every project, and the template's maintainers own it. A project's
own design belongs in its [architecture](architecture.md) page and its API
reference, not here.

## Pages

- [Agent instructions](agent-instructions.md): the commands to run, where code
  lives, and the requirements every change follows.
- [Agent rules and skills](agent-rules-and-skills.md): the rules and skills in
  `.cursor/` that Cursor agents follow, and what each requires.
- [Auto mode](auto-mode.md): when an agent's pull request merges without a
  person's review.
- [Orchestrating long-running agent work](orchestration.md): how an
  orchestrator agent launches workers, limits their cost, and hands off.
- [Linear conventions](linear.md): how to file issues so that agents can turn
  each into one pull request.
- [The setup script](install-script.md): what `.cursor/install.sh` installs and
  when it downloads nothing.
- [Pull template updates](template-updates.md): how a project takes the
  template's later changes with Copier.

```{toctree}
:hidden:
:maxdepth: 1

agent-instructions
agent-rules-and-skills
auto-mode
orchestration
linear
install-script
template-updates
```

## Publishing the site

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
