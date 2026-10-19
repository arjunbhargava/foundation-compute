# Pull template updates

A project created from this template can pull the template's later changes
into itself with [Copier](https://copier.readthedocs.io/). Projects follow
the template's `main` branch, which has no release tags. In a project with no
uncommitted changes, run:

```sh
mise exec -- copier update --defaults --trust
```

`--defaults` keeps the answers recorded in `.copier-answers.yml`. `--trust`
lets Copier run the template's task that writes the project's name into its
files. To add a language, also pass its answer, such as `--data rust=true`.
Copier applies the template's changes since the project was created or last
updated, and marks each conflict with the project's own changes between
`<<<<<<<` and `>>>>>>>` lines in the file. Resolve them, rerun `bash .cursor/install.sh`
for any new tools, run `mise run check`, and commit.

Copier doesn't delete a file that an update starts to leave out of projects.
A project created before the template excluded `docs/template-plan.md` keeps
it, and its docs build then fails on a page that no toctree lists, so delete
that file after the first update. The same update replaces an unedited
`README.md`, which was the template's own, with the project's README, and
marks a conflict in one that has been edited: keep the project's text.

## Name a project created before the name and owner questions

The template asks for `project_name`, in kebab-case, and `package_name`, in
snake_case, which defaults to `project_name` with `_` for `-`. It also asks
for `github_owner`, which `.github/CODEOWNERS` names; `github_repository`,
which the README's settings links name and which defaults to the owner's
account and `project_name`; and `copyright_holder` and `copyright_year`,
which `NOTICE` names. A project created before these questions has none of
them in `.copier-answers.yml`, and `--defaults` then answers the template's
own: `foundation`, `arjunbhargava`, `arjunbhargava/<project_name>`, `Arjun`,
and `2026`. So its first update passes each answer that differs,
such as:

```sh
mise exec -- copier update --defaults --trust --data project_name=my-project \
  --data github_owner=octocat --data "copyright_holder=Jane Doe" --data copyright_year=2027
```

Copier records the answers, and later updates need no `--data`. To rename
a project later, pass both `project_name` and `package_name`: an update keeps
the recorded `package_name` rather than deriving it again. The update
also removes the lines for `/AGENTS.md.jinja` and `/copier.yml`, files only
the template has, from the project's `.github/CODEOWNERS`. If the
project renamed `foundation` by hand, the update merges most of the rename
cleanly, and conflicts or extra files remain only where the project also
changed the template's files. Updating foundation-compute, which uses the
default package name, owner, and copyright holder, with
`--data project_name=foundation-compute`, left these:

- A conflict in each file the project edited where the template also
  changed, such as `AGENTS.md` and `src/foundation_compute/__init__.py`. Keep
  the project's text, then bring in any template change still wanted.
- `src/foundation_compute/quadrature.py` and the other example files that
  the project deleted from a directory the update renames, which return
  under the new name. Delete them again.
