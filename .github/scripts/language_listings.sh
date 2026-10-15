#!/usr/bin/env bash
# Checks that each place that must list every language lists each language
# the repository has, so that adding a language can't miss one. The
# languages are the files in .config/mise/conf.d/ other than template.toml,
# and a language's key is its file's name without .toml, such as python.
# The places name a language by its key, as its CI job, its Copier question,
# and its mise tasks, such as lint:python, do. Its manifest, such as
# pyproject.toml, is the first file that its line of the changes job in
# .github/workflows/ci.yml passes to language_changed; codeql.yml and
# docs/build.sh are checked for a test of whether that file exists.
#
# The places in copier.yml, in the template's own files, and in README.md's
# lines about Copier's questions list the template's languages, so only the
# template repository, which has copier.yml, checks them. A place that names
# a language by its display name, such as "C and C++", isn't checked, because
# a project records no display names.
#
# Prints an error for each place that lacks a language, naming the file, the
# place in it, and what to add, then exits with status 1 if there was one.
# Keep it working under bash 3.2, the version macOS ships.
#
# Usage: mise run lint:language-listings
set -euo pipefail
shopt -s nullglob
cd "$(dirname "$0")/../.."

failures=0

main() {
  local languages="" language_file language
  for language_file in .config/mise/conf.d/*.toml; do
    language=$(basename "$language_file" .toml)
    if [[ $language != template ]]; then
      languages="$languages $language"
    fi
  done

  for language in $languages; do
    check_places_in_every_project "$language"
    if [[ -f copier.yml ]]; then
      check_places_in_the_template "$language"
    fi
  done

  if ((failures > 0)); then
    echo "error: the $failures place(s) above lack a language that has a file in .config/mise/conf.d/. Add it to each, as .cursor/skills/add-language/SKILL.md says." >&2
    exit 1
  fi
  echo "Each place that lists the languages lists every language in .config/mise/conf.d/:$languages."
}

check_places_in_every_project() {
  local language=$1
  local mise_file=.config/mise/conf.d/$language.toml
  local ci=.github/workflows/ci.yml

  require_line_containing "$language" "$mise_file" "its tasks" "[tasks.\"fmt:$language\"]"
  require_line_containing "$language" "$mise_file" "its tasks" "[tasks.\"lint:$language\"]"
  require_line_containing "$language" "$mise_file" "its tasks" "[tasks.\"test:$language\"]"

  require_line_containing "$language" "$ci" "the outputs of the changes job" "$language: \${{ steps.diff.outputs.$language }}"
  require_line_containing "$language" "$ci" "the condition of the language's job" "if: needs.changes.outputs.$language == 'true'"
  # ci-ok's needs are the only list in ci.yml at this indentation.
  require_line "$language" "$ci" "the needs of the ci-ok job" "      - $language"

  local manifest
  manifest=$(sed -n "s/.*echo \"$language=\$(language_changed \([^ )]*\).*/\1/p" "$ci" | head -n 1)
  if [[ -z $manifest ]]; then
    report "$language" "$ci" "the diff step of the changes job" \
      "echo \"$language=\$(language_changed <manifest> <its other files>)\"; codeql.yml and docs/build.sh are checked for that manifest once it is there"
  else
    require_line_containing "$language" .github/workflows/codeql.yml "the languages job" "if [[ -f $manifest ]]"
    require_line_containing "$language" docs/build.sh "the blocks that build each language's API reference" "if [[ -f $manifest ]]"
  fi

  if [[ ! -f docs/api/$language.md ]]; then
    report "$language" docs/api/ "the API reference pages" "$language.md"
  fi

  require_line_containing "$language" AGENTS.md "the Commands table" "| \`mise run lint:$language\` |"
  require_line_containing "$language" AGENTS.md "the Commands table" "| \`mise run test:$language\` |"
}

check_places_in_the_template() {
  local language=$1
  local tasks=.config/mise/conf.d/template.toml
  local workflow=.github/workflows/template.yml

  require_line "$language" copier.yml "the questions" "$language:"
  require_word "$language" copier.yml "the condition of the last question's validator" \
    "$(text_between copier.yml '{% if not (' ')')" "$language"
  require_word "$language" copier.yml "the error message of the last question's validator" \
    "$(text_between copier.yml 'at least one of' ', for example')" "$language"
  require_line_containing "$language" copier.yml "language_names" "{%- if $language %}"
  require_line_containing "$language" copier.yml "_exclude" "{% if not $language %}"

  # Each task's first copier copy command ends with its destination.
  # shellcheck disable=SC2016 # The task's variable, unexpanded.
  local destination='. "$work/project"'
  require_word "$language" "$tasks" "the copier copy command of template:check" \
    "$(text_between "$tasks" '[tasks."template:check"]' "$destination")" "--data $language=true"
  require_word "$language" "$tasks" "the copier copy command of template:sync" \
    "$(text_between "$tasks" '[tasks."template:sync"]' "$destination")" "--data $language=true"
  # template:check-update's variants are every language, then each alone:
  # for languages in "python rust" python rust; do
  local variants
  variants=$(text_between "$tasks" 'for languages in "' '; do')
  require_word "$language" "$tasks" "the variant with every language in template:check-update" "${variants%%\"*}" "$language"
  require_word "$language" "$tasks" "the variants with one language in template:check-update" "${variants#*\"}" "$language"
  require_word "$language" "$tasks" "the copier copy command with no language in test:template" \
    "$(text_between "$tasks" '[tasks."test:template"]' "$destination")" "--data $language=false"
  require_word "$language" "$tasks" "the languages of test:template" "$(text_between "$tasks" 'languages="' '"')" "$language"
  require_word "$language" "$tasks" "language_files in test:template" "$(text_between "$tasks" 'language_files() {' 'esac')" "$language)"
  require_word "$language" "$tasks" "language_name in test:template" "$(text_between "$tasks" 'language_name() {' 'esac')" "$language)"

  require_word "$language" "$workflow" "the variant job's variant with every language" \
    "$(text_between "$workflow" 'languages: every language' '}')" "--data $language=true"
  require_line_containing "$language" "$workflow" "the variant job's variants with one language" "data: --data $language=true }"

  local readme_command
  readme_command=$(text_between README.md 'copier copy --defaults' 'gh:')
  if [[ " $readme_command " != *" --data $language=true "* && " $readme_command " != *" --data $language=false "* ]]; then
    report "$language" README.md "the copier copy command" "\"--data $language=true\" or \"--data $language=false\""
  fi
  require_word "$language" README.md "the list of Copier's questions" \
    "$(text_between README.md 'one yes/no question per language:' '.')" "\`$language\`"
}

# Arguments: a language, a file, the place in the file, and the text that
# some line of the file must contain.
require_line_containing() {
  if ! grep -qF -- "$4" "$2"; then
    report "$1" "$2" "$3" "a line containing \"$4\""
  fi
}

# Arguments: a language, a file, the place in the file, and a line the file
# must have.
require_line() {
  if ! grep -qxF -- "$4" "$2"; then
    report "$1" "$2" "$3" "the line \"$4\""
  fi
}

# Arguments: a language, a file, the place in the file, the text of that
# place, and a word the text must contain with a space or nothing on each
# side, such as python, python), or --data python=true.
require_word() {
  if [[ " $4 " != *" $5 "* ]]; then
    report "$1" "$2" "$3" "\"$5\""
  fi
}

# Prints the text between the first occurrence of a start text in a file and
# the next occurrence of an end text, or nothing if the file has no such
# text. Line breaks count as spaces, and the printed text has each comma
# replaced by a space, so that require_word finds a word a comma follows.
# Arguments: a file, the start text, and the end text.
text_between() {
  local text
  text=$(tr '\n' ' ' < "$1")
  if [[ $text != *"$2"*"$3"* ]]; then
    return
  fi
  text=${text#*"$2"}
  text=${text%%"$3"*}
  printf '%s\n' "${text//,/ }"
}

# Arguments: a language, a file, the place in the file, and what to add.
report() {
  echo "error: $2 lacks $1 in $3. Add $4." >&2
  failures=$((failures + 1))
}

main "$@"
