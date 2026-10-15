#!/usr/bin/env bash
# Mutation-tests the code that the current branch changed, and reports each
# mutant that survived. A mutant is a small deliberate bug, such as `<`
# replaced by `<=`. It survives when every test still passes, which marks
# behaviour that no test checks.
#
# Usage: .github/scripts/mutate.sh python|rust|typescript [base]
#
# Changed means different from the merge base with base (default
# origin/main), including uncommitted changes. The mutated files are the
# changed source files, plus every source file of a package whose tests
# changed, because a changed test can stop checking any code in its package.
# A change to this script, its workflow, or stryker.config.json mutates
# every package.
#
# For python, the Python scripts in .github/scripts/ count as one more package,
# reported separately. The shell scripts there aren't mutated, because mutmut
# reads only Python and no shell mutation tool is pinned.
#
# The report goes to stdout and, in GitHub Actions, to the job summary.
# Surviving mutants don't fail the script: for now, mutation testing reports
# and doesn't block merging (T14 in the plan in the template repository, https://github.com/arjunbhargava/foundation). It fails only when
# the tool does, for example when a test fails before any code is mutated.
#
# Keep it working under bash 3.2, the version macOS ships: no mapfile.
set -euo pipefail
cd "$(dirname "$0")/../.."

language=${1:-}
base=${2:-origin/main}
if ! merge_base=$(git merge-base "$base" HEAD); then
  echo "error: HEAD and '$base' have no merge base. Fetch the base, for example with 'git fetch origin main', or pass another one." >&2
  exit 1
fi

main() {
  case $language in
    python) mutate_python ;;
    rust) mutate_rust ;;
    typescript) mutate_typescript ;;
    *)
      echo "error: .github/scripts/mutate.sh mutates python, rust, or typescript, not '$language'." >&2
      exit 1
      ;;
  esac
}

mutate_python() {
  mutate_python_source
  mutate_python_scripts
}

mutate_python_source() {
  local files
  files=$(files_to_mutate tests/ 'src/*.py')
  if [[ -z $files ]]; then
    report Python "" 0 0 ""
    return
  fi

  # mutmut names each mutant <module>.x<function>__mutmut_<n>, and the module
  # of a package's __init__.py is the package. So a package's glob also
  # matches its submodules whose names start with x, which only tests extra
  # mutants.
  local module_globs=() path module
  for path in $files; do
    module=${path#src/}
    module=${module%.py}
    module=${module%/__init__}
    module_globs+=("${module//\//.}.x*")
  done

  run_mutmut Python "$files" "${module_globs[@]}"
}

# The scripts in .github/scripts/ are imported by bare name, as in `import
# agent_spend`, but mutmut counts a test as covering a mutant only if the test
# imports the module under the name mutmut derives from the file's path
# relative to the project, with a leading src/ removed. So mutmut runs in a
# scratch project with the scripts in src/ and their tests in tests/, so a
# survivor's diff names a script as src/<script>.py. Its
# pytest settings are the root pyproject.toml's, except for pytest-xdist,
# which mutmut can't see through, and testpaths.
mutate_python_scripts() {
  local scripts='.github/scripts/*.py' script_tests='.github/scripts/*_test.py'
  local files
  files=$(files_to_mutate "$script_tests" "$scripts" ":(exclude)$script_tests")
  if [[ -z $files ]]; then
    report "Python scripts" "" 0 0 ""
    return
  fi

  local project_root=$PWD scratch=.mutants-scripts
  rm -rf "$scratch"
  mkdir -p "$scratch/src" "$scratch/tests"
  git ls-files -z -- "$scripts" ":(exclude)$script_tests" | xargs -0 -I{} cp {} "$scratch/src/"
  git ls-files -z -- "$script_tests" | xargs -0 -I{} cp {} "$scratch/tests/"
  cat > "$scratch/pyproject.toml" << 'SETTINGS'
[tool.pytest]
addopts = ["--doctest-modules"]
strict = true
filterwarnings = ["error"]
SETTINGS

  local module_globs=() path module
  for path in $files; do
    module=${path##*/}
    module_globs+=("${module%.py}.x*")
  done

  # uv runs in the scratch directory, where mutmut reads its settings, but
  # with the root project's environment.
  (cd "$scratch" && UV_PROJECT=$project_root run_mutmut "Python scripts" "$files" "${module_globs[@]}")
}

# Runs mutmut in the current directory on the modules that match the globs,
# and reports the surviving mutants. files is the list of mutated source
# files, for the report.
run_mutmut() {
  local label=$1 files=$2
  shift 2

  # mutmut reuses results from earlier runs, which a changed test can make
  # wrong.
  rm -rf mutants
  mkdir mutants
  if ! uv run mutmut run "$@" 2>&1 | tee mutants/run.log; then
    if grep -qF "Filtered for specific mutants, but nothing matches" mutants/run.log; then
      report "$label" "$files" 0 0 "mutmut found no code to mutate in these files."
      return
    fi
    echo "error: mutmut failed; its output is above." >&2
    return 1
  fi

  # Each line is "<mutant>: <status>". mutmut generates mutants in every file,
  # and leaves those outside the globs "not checked". "no tests" means no test
  # calls the mutated function.
  local results survivors survived_count tested_count status_counts
  results=$(uv run mutmut results --all true)
  survivors=$(awk -F': ' '$2 == "survived" || $2 == "no tests" { print $1 }' <<< "$results")
  survived_count=$(count_lines "$survivors")
  tested_count=$(awk -F': ' '$2 != "not checked" { n++ } END { print n + 0 }' <<< "$results")
  status_counts=$(awk -F': ' '$2 != "not checked" { count[$2]++ } END { for (status in count) printf "%s%d %s", (n++ ? ", " : ""), count[status], status }' <<< "$results")

  # A command substitution fails the script, under set -e, only if it is
  # the whole right-hand side of an assignment, so each is assigned before
  # report prints it.
  local mutant survivor_diffs
  survivor_diffs=$(for mutant in $survivors; do uv run mutmut show "$mutant" || exit 1; done)
  report "$label" "$files" "$survived_count" "$tested_count" "mutmut: $status_counts." \
    "$(printf '```diff\n%s\n```' "$survivor_diffs")"
}

mutate_rust() {
  local files crate
  files=$(for crate in crates/*/; do files_to_mutate "${crate}tests/" "${crate}src/*.rs"; done)
  if [[ -z $files ]]; then
    report Rust "" 0 0 ""
    return
  fi

  local file_options=() path
  for path in $files; do
    file_options+=(--file "$path")
  done
  # cargo-mutants builds the mutants in a copy of the source tree.
  # --gitignore true leaves out what git ignores: 500 MB of .venv,
  # node_modules, and build output here, and mutmut's mutants/, which
  # mutate:python rewrites while `mise run mutate` runs both.
  local status=0
  cargo mutants --gitignore true --no-shuffle --output target "${file_options[@]}" || status=$?
  # 2 means some mutants survived, and 3 that some timed out: results to
  # report, not failures.
  if ((status != 0 && status != 2 && status != 3)); then
    echo "error: cargo mutants exited with status $status; its output is above." >&2
    return "$status"
  fi

  local results_dir=target/mutants.out mutant_count
  mutant_count=$(jq length "$results_dir/mutants.json")
  if ((mutant_count == 0)); then
    report Rust "$files" 0 0 "cargo-mutants found no code to mutate in these files."
    return
  fi

  local survived_count outcome_counts
  survived_count=$(jq .missed "$results_dir/outcomes.json")
  outcome_counts=$(jq -r '"cargo-mutants: \(.caught) caught, \(.missed) missed, \(.timeout) timed out, \(.unviable) unviable (failed to build)."' "$results_dir/outcomes.json")
  local missed_mutants
  missed_mutants=$(cat "$results_dir/missed.txt")
  report Rust "$files" "$survived_count" "$mutant_count" "$outcome_counts" \
    "$(printf '```text\n%s\n```' "$missed_mutants")"
}

mutate_typescript() {
  local files package
  files=$(for package in packages/*/; do files_to_mutate "${package}*.test.ts" "${package}src/*.ts" ":(exclude)${package}*.test.ts"; done)
  if [[ -z $files ]]; then
    report TypeScript "" 0 0 ""
    return
  fi

  # StrykerJS reads its settings from stryker.config.json, which can't hold
  # comments, so they are explained here:
  # - plugins names the vitest runner, which StrykerJS can't find by itself in
  #   pnpm's node_modules.
  # - vitest.related false makes its first test run execute every test, not
  #   only those that import the mutated files. Otherwise, when no test
  #   imports them, it stops without a report, and untested code goes
  #   unreported.
  # - ignorePatterns copies only packages/ into its sandbox, leaving out
  #   .venv, target/, and mutmut's mutants/, which mutate:python rewrites
  #   while `mise run mutate` runs both.
  # - cleanTempDir always deletes the sandbox after a failed run too, as
  #   well as after a successful one. vitest would otherwise run the copied
  #   tests in it.
  # It exits 0 when mutants survive, because the config sets no thresholds.
  local report_file=reports/mutation/mutation.json
  rm -f "$report_file"
  if ! pnpm exec stryker run --mutate "${files//$'\n'/,}"; then
    echo "error: StrykerJS failed; its output is above." >&2
    return 1
  fi

  local mutant_count
  mutant_count=$(jq '[.files[].mutants[]] | length' "$report_file")
  if ((mutant_count == 0)); then
    report TypeScript "$files" 0 0 "StrykerJS found no code to mutate in these files."
    return
  fi

  # NoCoverage means no test runs the mutated code.
  local survivors survived_count status_counts
  survivors=$(jq '[.files | to_entries[] | .key as $file | .value.mutants[] | select(.status == "Survived" or .status == "NoCoverage") | . + {file: $file}] | sort_by(.file, .location.start.line, .location.start.column)' "$report_file")
  survived_count=$(jq length <<< "$survivors")
  status_counts=$(jq -r '[.files[].mutants[].status] | group_by(.) | map("\(length) \(.[0])") | join(", ")' "$report_file")
  local survivor_lines
  survivor_lines=$(jq -r '.[] | "\(.file):\(.location.start.line):\(.location.start.column): \(.mutatorName), replaced with \(.replacement // "" | gsub("\\s+"; " ")) (\(.status))"' <<< "$survivors")
  report TypeScript "$files" "$survived_count" "$mutant_count" "StrykerJS: $status_counts." \
    "$(printf '```text\n%s\n```' "$survivor_lines")"
}

# Prints the source files to mutate in one package, given a pathspec for its
# tests and then one or more for its sources: all the sources if any of its
# tests changed, and otherwise those that changed. A change to this script,
# its workflow, or stryker.config.json, which only mutation testing reads,
# counts as a change to every package's tests, so that the PR making it runs
# every step here in CI. In a git pathspec, * also matches /,
# so src/*.py includes src/foundation/quadrature.py.
files_to_mutate() {
  local tests=$1
  shift
  if git diff --quiet "$merge_base" -- "$tests" .github/scripts/mutate.sh .github/workflows/mutation.yml stryker.config.json; then
    git diff --name-only --diff-filter=d "$merge_base" -- "$@"
  else
    git ls-files -- "$@"
  fi
}

# Prints one language's report, and in GitHub Actions appends it to the job
# summary. With surviving mutants, it reads their list from stdin.
report() {
  local language=$1 files=$2 survived=$3 total=$4 tool_counts=$5 survivor_list=${6:-}
  if [[ -z $files ]]; then
    echo "### $language mutation testing: no source or test file changed since the merge base with $base"
  else
    echo "### $language mutation testing: $survived of $total mutants survived"
    echo
    echo "Mutated files: ${files//$'\n'/, }"
    echo
    echo "$tool_counts"
    if ((survived > 0)); then
      echo
      echo "Every test still passes with each change below. Add a test that fails on it, or say in the PR why the change can't alter behaviour."
      echo
      echo "$survivor_list"
    fi
  fi | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
}

# Prints the number of non-empty lines in its argument.
count_lines() {
  awk 'NF { n++ } END { print n + 0 }' <<< "$1"
}

main "$@"
