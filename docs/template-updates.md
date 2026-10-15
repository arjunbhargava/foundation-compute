# Pull template updates

A project created from this template can pull the template's later changes
into itself with [Copier](https://copier.readthedocs.io/). Projects follow
the template's `main` branch, which has no release tags. In a project with no
uncommitted changes, run:

```sh
mise exec -- copier update --defaults
```

`--defaults` keeps the answers recorded in `.copier-answers.yml`. To add a
language, also pass its answer, such as `--data rust=true`. Copier applies
the template's changes since the project was created or last updated, and
marks each conflict with the project's own changes between `<<<<<<<` and
`>>>>>>>` lines in the file. Resolve them, rerun `bash .cursor/install.sh`
for any new tools, run `mise run check`, and commit.
