#!/usr/bin/env bash
# Checks which files .github/scripts/mutate.sh mutates and what its report
# says, without running a mutation tool. It runs the script in a temporary
# git repository with one package in each language, a second Python
<<<<<<< before updating
# distribution in lib/, and two Python scripts in .github/scripts/, where fake uv, cargo, and pnpm record the files or module
# globs they are given and print canned results: one surviving and one caught
# mutant, or two caught mutants if FAKE_ALL_KILLED is set. For the scripts,
# fake uv reports one mutant, which survives unless FAKE_ALL_KILLED is set.
=======
# distribution in lib/ (a uv workspace member), a third in tools/ that has no
# src/, two Python scripts in .github/scripts/, and a copier.yml, which only
# the template repository has, where fake uv, cargo, and pnpm record the files
# or module globs they are given and print canned results: one surviving and
# one caught mutant, or two caught mutants if FAKE_ALL_KILLED is set. For the
# scripts, fake uv reports one mutant, which survives unless FAKE_ALL_KILLED
# is set. With SINGLE_PACKAGE set, fake uv lists no workspace member. If
# FAKE_NO_MUTABLE_CODE is set, the tools find no mutant in the changed files;
# mutmut does so as pytest exits with status 5 for no test and the project has
# no mutant at all ("empty") or only in other files ("elsewhere"), as mutmut
# says nothing matches ("nothing_matches"), or as the tests pass but call no
# function that has a mutant and the project has no mutant at all
# ("no_test_case"). If FAKE_UNTESTED_FUNCTION is set, that happens although
# the changed files have two mutants, which mutmut has generated and not run.
# mutmut fails, although it has no mutant in the changed files, if
# FAKE_MUTMUT_FAILS is "failing_test" (pytest exits with status 1), and,
# although pytest collected no test, if it is "untested_mutant" (a mutant is
# in the changed files).
>>>>>>> after updating
#
# Usage: .github/scripts/mutate_test.sh
set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
# The report would otherwise go to the real job summary in GitHub Actions.
unset GITHUB_STEP_SUMMARY
# git ignores the user's and the system's settings, such as commit signing or
# a hooks directory, which could make the test repository's commit fail.
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1

main() {
  make_fake_tools
  make_repository

  check python src/pkg/a.py 'pkg.a.x*' "1 of 2 mutants survived"
  check python src/pkg/__init__.py 'pkg.x*' "1 of 2 mutants survived"
<<<<<<< before updating
  check python tests/test_a.py $'pkg.x*\npkg.a.x*\npkg.b.x*' "1 of 2 mutants survived"
  check python lib/src/lpkg/a.py 'lpkg.a.x*' "Python (lib) mutation testing: 1 of 2 mutants survived"
  check python lib/tests/test_l.py $'lpkg.x*\nlpkg.a.x*' "Python (lib) mutation testing: 1 of 2 mutants survived"
=======
  check python tests/test_a.py $'pkg.x*\npkg.a.x*\npkg.b.x*' "Python mutation testing: 1 of 2 mutants survived"
  check python lib/src/lpkg/a.py 'lpkg.a.x*' "Python (lib) mutation testing: 1 of 2 mutants survived"
  check python lib/tests/test_l.py $'lpkg.x*\nlpkg.a.x*' "Python (lib) mutation testing: 1 of 2 mutants survived"
  check python tools/pyproject.toml "" "Python mutation testing: no source or test file changed"
  SINGLE_PACKAGE=1 check python lib/src/lpkg/a.py "" "Python mutation testing: no source or test file changed" "Python (lib)"
>>>>>>> after updating
  check python crates/c/src/x.rs "" "no source or test file changed"
  check rust crates/c/src/x.rs crates/c/src/x.rs "1 of 2 mutants survived"
  check rust crates/c/tests/t.rs $'crates/c/src/lib.rs\ncrates/c/src/x.rs' "1 of 2 mutants survived"
  check rust .github/scripts/mutate.sh $'crates/c/src/lib.rs\ncrates/c/src/x.rs' "1 of 2 mutants survived"
  check typescript packages/p/src/a.ts packages/p/src/a.ts "1 of 2 mutants survived"
  check typescript packages/p/src/a.test.ts $'packages/p/src/a.ts\npackages/p/src/b.ts' "1 of 2 mutants survived"
  check typescript stryker.config.json $'packages/p/src/a.ts\npackages/p/src/b.ts' "1 of 2 mutants survived"

  check python .github/scripts/script_a.py 'script_a.x*' "Python scripts mutation testing: 1 of 1 mutants survived"
  check python .github/scripts/script_a_test.py $'script_a.x*\nscript_b.x*' "Python scripts mutation testing: 1 of 1 mutants survived"
<<<<<<< before updating
  check python .github/scripts/mutate.sh $'lpkg.x*\nlpkg.a.x*\npkg.x*\npkg.a.x*\npkg.b.x*\nscript_a.x*\nscript_b.x*' "Python scripts mutation testing: 1 of 1 mutants survived"
=======
  check python .github/scripts/mutate.sh $'pkg.x*\npkg.a.x*\npkg.b.x*\nlpkg.x*\nlpkg.a.x*\nscript_a.x*\nscript_b.x*' "Python scripts mutation testing: 1 of 1 mutants survived"
>>>>>>> after updating
  check python .github/scripts/shell_script.sh "" "Python scripts mutation testing: no source or test file changed"

  # A project made from the template has no copier.yml, and doesn't mutate the
  # scripts in .github/scripts/.
  PROJECT=1 check python .github/scripts/script_a.py "" "Python mutation testing: no source or test file changed" "Python scripts"
  PROJECT=1 check python .github/scripts/mutate.sh $'pkg.x*\npkg.a.x*\npkg.b.x*\nlpkg.x*\nlpkg.a.x*' "Python mutation testing: 1 of 2 mutants survived" "Python scripts"

  FAKE_NO_MUTABLE_CODE=empty check python src/pkg/a.py 'pkg.a.x*' "Python mutation testing: passed, because the changed files hold no mutable code: src/pkg/a.py"
  FAKE_NO_MUTABLE_CODE=elsewhere check python src/pkg/a.py 'pkg.a.x*' "Python mutation testing: passed, because the changed files hold no mutable code: src/pkg/a.py"
  FAKE_NO_MUTABLE_CODE=nothing_matches check python src/pkg/a.py 'pkg.a.x*' "Python mutation testing: passed, because the changed files hold no mutable code: src/pkg/a.py"
  FAKE_NO_MUTABLE_CODE=no_test_case check python src/pkg/a.py 'pkg.a.x*' "Python mutation testing: passed, because the changed files hold no mutable code: src/pkg/a.py"
  FAKE_NO_MUTABLE_CODE=no_test_case check python lib/src/lpkg/a.py 'lpkg.a.x*' "Python (lib) mutation testing: passed, because the changed files hold no mutable code: lib/src/lpkg/a.py"
  FAKE_UNTESTED_FUNCTION=1 check python src/pkg/a.py 'pkg.a.x*' "Python mutation testing: 2 of 2 mutants survived"
  FAKE_NO_MUTABLE_CODE=empty check rust crates/c/src/x.rs crates/c/src/x.rs "Rust mutation testing: passed, because the changed files hold no mutable code: crates/c/src/x.rs"
  FAKE_NO_MUTABLE_CODE=empty check typescript packages/p/src/a.ts packages/p/src/a.ts "TypeScript mutation testing: passed, because the changed files hold no mutable code: packages/p/src/a.ts"
  FAKE_MUTMUT_FAILS=failing_test check_fails python src/pkg/a.py "mutmut failed"
  FAKE_MUTMUT_FAILS=untested_mutant check_fails python src/pkg/a.py "mutmut failed"
  FAKE_MUTMUT_FAILS=failing_test check_fails python lib/src/lpkg/a.py "mutmut failed"

  FAKE_ALL_KILLED=1 check python src/pkg/a.py 'pkg.a.x*' "0 of 2 mutants survived"
  FAKE_ALL_KILLED=1 check python .github/scripts/script_a.py 'script_a.x*' "Python scripts mutation testing: 0 of 1 mutants survived"
  FAKE_ALL_KILLED=1 check rust crates/c/src/x.rs crates/c/src/x.rs "0 of 2 mutants survived"
  FAKE_ALL_KILLED=1 check typescript packages/p/src/a.ts packages/p/src/a.ts "0 of 2 mutants survived"
<<<<<<< before updating
  echo ".github/scripts/mutate.sh chose the expected files and reported them in all 20 cases."
=======
  echo ".github/scripts/mutate.sh chose the expected files and reported them in all 37 cases."
>>>>>>> after updating
}

# Writes fake uv, cargo, and pnpm, which append the module globs or files
# they are given to $work/tool-arguments, one per line.
make_fake_tools() {
  mkdir "$work/bin"
  cat > "$work/bin/uv" << 'EOF'
#!/usr/bin/env bash
case "$*" in
  "workspace list --paths")
    # Like uv, print the current directory with its symbolic links resolved,
    # which differs from $PWD on macOS, where the temporary directory is one.
    root=$(pwd -P)
    echo "$root"
    if [[ -z ${SINGLE_PACKAGE:-} ]]; then
      echo "$root/lib"
      echo "$root/tools"
    fi
    ;;
  "run mutmut run "*)
    if [[ ${PYTEST_ADDOPTS:-} != "-n 0" ]]; then
      echo "fake uv: mutmut must run pytest in one process, but PYTEST_ADDOPTS is '${PYTEST_ADDOPTS:-}'." >&2
      exit 1
    fi
    if [[ $PWD == */.mutants-scripts ]]; then
      # The scratch project has the scripts, without their tests, in src/, the
      # tests, without the scripts, in tests/, and the root's environment.
      [[ -f src/script_a.py && -f src/script_b.py && ! -e src/script_a_test.py && -f tests/script_a_test.py && ! -e tests/script_a.py && -f pyproject.toml && -n ${UV_PROJECT:-} ]] || { echo "fake uv: the scratch project is wrong: $(find . -type f | sort | tr '\n' ' ')" >&2; exit 1; }
    else
      # mutmut runs in a distribution's directory, with the root's environment.
      [[ -f pyproject.toml && -d src && -n ${UV_PROJECT:-} ]] || { echo "fake uv: mutmut ran outside a distribution's directory, in $PWD" >&2; exit 1; }
    fi
    printf '%s\n' "${@:4}" >> "$FAKE_TOOL_ARGUMENTS"
    if [[ ${FAKE_NO_MUTABLE_CODE:-} == nothing_matches ]]; then
      echo "Filtered for specific mutants, but nothing matches" >&2
      exit 1
    fi
    if [[ ${FAKE_MUTMUT_FAILS:-} == failing_test ]]; then
      echo "failed to collect stats. runner returned 1" >&2
      exit 1
    fi
    if [[ ${FAKE_NO_MUTABLE_CODE:-} == no_test_case || -n ${FAKE_UNTESTED_FUNCTION:-} ]]; then
      echo "Stopping early, because we could not find any test case for any mutant. It seems that the selected tests do not cover any code that we mutated."
      exit 1
    fi
    if [[ -n ${FAKE_NO_MUTABLE_CODE:-} || -n ${FAKE_MUTMUT_FAILS:-} ]]; then
      echo "failed to collect stats. runner returned 5" >&2
      exit 1
    fi
    ;;
  "run mutmut results --all true")
    package=pkg
    [[ $PWD == */lib ]] && package=lpkg
    if [[ ${FAKE_NO_MUTABLE_CODE:-} == empty || ${FAKE_NO_MUTABLE_CODE:-} == no_test_case ]]; then
      exit 0
    fi
    if [[ -n ${FAKE_UNTESTED_FUNCTION:-} ]]; then
      printf '    %s.a.x_f__mutmut_1: not checked\n    %s.a.x_f__mutmut_2: not checked\n    %s.b.x_g__mutmut_1: not checked\n' "$package" "$package" "$package"
      exit 0
    fi
    if [[ ${FAKE_NO_MUTABLE_CODE:-} == elsewhere ]]; then
      printf '    other.x_f__mutmut_1: not checked\n'
      exit 0
    fi
    if [[ ${FAKE_MUTMUT_FAILS:-} == untested_mutant ]]; then
      printf '    %s.a.x_f__mutmut_1: not checked\n' "$package"
      exit 0
    fi
    if [[ ${FAKE_MUTMUT_FAILS:-} == failing_test ]]; then
      exit 0
    fi
    if [[ $PWD == */.mutants-scripts ]]; then
      printf '    script_a.x_f__mutmut_1: %s\n' "$([[ -n ${FAKE_ALL_KILLED:-} ]] && echo killed || echo survived)"
      exit 0
    fi
    printf '    %s.a.x_f__mutmut_1: %s\n    %s.a.x_f__mutmut_2: killed\n    %s.b.x_g__mutmut_1: not checked\n' "$package" "$([[ -n ${FAKE_ALL_KILLED:-} ]] && echo killed || echo survived)" "$package" "$package"
    ;;
  "run mutmut show "*) echo "# $4: survived" ;;
  *) echo "fake uv: unexpected arguments: $*" >&2; exit 1 ;;
esac
EOF
  # Exits 2, as cargo-mutants does when a mutant survives.
  cat > "$work/bin/cargo" << 'EOF'
#!/usr/bin/env bash
while (($# > 0)); do
  if [[ $1 == --file ]]; then
    echo "$2" >> "$FAKE_TOOL_ARGUMENTS"
  fi
  shift
done
mkdir -p target/mutants.out
if [[ -n ${FAKE_NO_MUTABLE_CODE:-} ]]; then
  echo '[]' > target/mutants.out/mutants.json
  exit 0
fi
echo '[{}, {}]' > target/mutants.out/mutants.json
if [[ -n ${FAKE_ALL_KILLED:-} ]]; then
  echo '{"total_mutants": 2, "missed": 0, "caught": 2, "timeout": 0, "unviable": 0}' > target/mutants.out/outcomes.json
  : > target/mutants.out/missed.txt
  exit 0
fi
echo '{"total_mutants": 2, "missed": 1, "caught": 1, "timeout": 0, "unviable": 0}' > target/mutants.out/outcomes.json
echo 'crates/c/src/x.rs:1:1: replace f with g' > target/mutants.out/missed.txt
exit 2
EOF
  # Exits 0, as StrykerJS does when a mutant survives.
  cat > "$work/bin/pnpm" << 'EOF'
#!/usr/bin/env bash
while (($# > 0)); do
  if [[ $1 == --mutate ]]; then
    tr , '\n' <<< "$2" >> "$FAKE_TOOL_ARGUMENTS"
  fi
  shift
done
mkdir -p reports/mutation
if [[ -n ${FAKE_NO_MUTABLE_CODE:-} ]]; then
  echo '{"files": {"packages/p/src/a.ts": {"mutants": []}}}' > reports/mutation/mutation.json
  exit 0
fi
survivor_status=Survived
[[ -n ${FAKE_ALL_KILLED:-} ]] && survivor_status=Killed
cat > reports/mutation/mutation.json << REPORT
{"files": {"packages/p/src/a.ts": {"mutants": [
  {"mutatorName": "EqualityOperator", "replacement": "x <= 2", "status": "$survivor_status", "location": {"start": {"line": 1, "column": 1}}},
  {"mutatorName": "BooleanLiteral", "replacement": "false", "status": "Killed", "location": {"start": {"line": 2, "column": 1}}}
]}}}
REPORT
EOF
  chmod +x "$work/bin/uv" "$work/bin/cargo" "$work/bin/pnpm"
  export PATH="$work/bin:$PATH" FAKE_TOOL_ARGUMENTS="$work/tool-arguments"
}

make_repository() {
  mkdir -p "$work/repo/.github/scripts" "$work/repo/src/pkg" "$work/repo/tests" \
<<<<<<< before updating
    "$work/repo/lib/src/lpkg" "$work/repo/lib/tests" \
    "$work/repo/crates/c/src" "$work/repo/crates/c/tests" "$work/repo/packages/p/src"
  cd "$work/repo"
  cp "$script_dir/mutate.sh" .github/scripts/
  touch pyproject.toml src/pkg/__init__.py src/pkg/a.py src/pkg/b.py tests/test_a.py \
    lib/pyproject.toml lib/src/lpkg/__init__.py lib/src/lpkg/a.py lib/tests/test_l.py \
=======
    "$work/repo/lib/src/lpkg" "$work/repo/lib/tests" "$work/repo/tools" \
    "$work/repo/crates/c/src" "$work/repo/crates/c/tests" "$work/repo/packages/p/src"
  cd "$work/repo"
  cp "$script_dir/mutate.sh" .github/scripts/
  touch copier.yml pyproject.toml src/pkg/__init__.py src/pkg/a.py src/pkg/b.py tests/test_a.py \
    lib/pyproject.toml lib/src/lpkg/__init__.py lib/src/lpkg/a.py lib/tests/test_l.py tools/pyproject.toml \
>>>>>>> after updating
    crates/c/src/lib.rs crates/c/src/x.rs crates/c/tests/t.rs \
    packages/p/src/a.ts packages/p/src/b.ts packages/p/src/a.test.ts stryker.config.json \
    .github/scripts/script_a.py .github/scripts/script_b.py .github/scripts/script_a_test.py \
    .github/scripts/shell_script.sh
  git init --quiet
  git add .
  git -c user.name=test -c user.email=test@example.com commit --quiet --message base
}

# Changes one file, runs .github/scripts/mutate.sh for one language, and
# fails unless the tool got the expected globs or files and the report has
# the expected headline, and lacks the optional text. The script must exit 0,
# though the fake cargo exits 2. With PROJECT set, the repository lacks
# copier.yml, as a project made from the template does.
check() {
  local language=$1 changed_file=$2 expected_arguments=$3 expected_headline=$4 unexpected_text=${5:-}
  local report arguments status=0
  report=$(run_mutate "$language" "$changed_file") || status=$?
  if ((status != 0)); then
    echo "FAIL: after a change to $changed_file, mutate.sh $language exited with status $status, not 0." >&2
    exit 1
  fi
  arguments=$(cat "$FAKE_TOOL_ARGUMENTS")
  if [[ $arguments != "$expected_arguments" ]]; then
    echo "FAIL: after a change to $changed_file, mutate.sh $language passed [${arguments//$'\n'/ }] to the tool, not [${expected_arguments//$'\n'/ }]." >&2
    exit 1
  fi
  if [[ $report != *"$expected_headline"* ]]; then
    echo "FAIL: after a change to $changed_file, mutate.sh $language reported:" >&2
    echo "$report" >&2
    echo "which lacks '$expected_headline'." >&2
    exit 1
  fi
  if [[ -n $unexpected_text && $report == *"$unexpected_text"* ]]; then
    echo "FAIL: after a change to $changed_file, mutate.sh $language reported:" >&2
    echo "$report" >&2
    echo "which has '$unexpected_text'." >&2
    exit 1
  fi
}

# Like check, but fails unless the script exits with a non-zero status and
# prints the expected error.
check_fails() {
  local language=$1 changed_file=$2 expected_error=$3
  local output status=0
  output=$(run_mutate "$language" "$changed_file" 2>&1) || status=$?
  if ((status == 0)); then
    echo "FAIL: after a change to $changed_file, mutate.sh $language exited with status 0, not an error." >&2
    exit 1
  fi
  if [[ $output != *"$expected_error"* ]]; then
    echo "FAIL: after a change to $changed_file, mutate.sh $language printed:" >&2
    echo "$output" >&2
    echo "which lacks '$expected_error'." >&2
    exit 1
  fi
}

# Resets the repository, changes one file, and prints the report of
# .github/scripts/mutate.sh for one language.
run_mutate() {
  local language=$1 changed_file=$2
  git checkout --quiet -- .
  git clean --quiet --force -d
  if [[ -n ${PROJECT:-} ]]; then
    rm copier.yml
  fi
  : > "$FAKE_TOOL_ARGUMENTS"
  echo "# changed" >> "$changed_file"
  .github/scripts/mutate.sh "$language" HEAD
}

main
