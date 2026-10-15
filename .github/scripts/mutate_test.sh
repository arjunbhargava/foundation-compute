#!/usr/bin/env bash
# Checks which files .github/scripts/mutate.sh mutates and what its report
# says, without running a mutation tool. It runs the script in a temporary
# git repository with one package in each language and two Python scripts in
# .github/scripts/, where fake uv, cargo, and pnpm record the files or module
# globs they are given and print canned results: one surviving and one caught
# mutant, or two caught mutants if FAKE_ALL_KILLED is set. For the scripts,
# fake uv reports one mutant, which survives unless FAKE_ALL_KILLED is set.
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
  check python tests/test_a.py $'pkg.x*\npkg.a.x*\npkg.b.x*' "1 of 2 mutants survived"
  check python crates/c/src/x.rs "" "no source or test file changed"
  check rust crates/c/src/x.rs crates/c/src/x.rs "1 of 2 mutants survived"
  check rust crates/c/tests/t.rs $'crates/c/src/lib.rs\ncrates/c/src/x.rs' "1 of 2 mutants survived"
  check rust .github/scripts/mutate.sh $'crates/c/src/lib.rs\ncrates/c/src/x.rs' "1 of 2 mutants survived"
  check typescript packages/p/src/a.ts packages/p/src/a.ts "1 of 2 mutants survived"
  check typescript packages/p/src/a.test.ts $'packages/p/src/a.ts\npackages/p/src/b.ts' "1 of 2 mutants survived"
  check typescript stryker.config.json $'packages/p/src/a.ts\npackages/p/src/b.ts' "1 of 2 mutants survived"

  check python .github/scripts/script_a.py 'script_a.x*' "Python scripts mutation testing: 1 of 1 mutants survived"
  check python .github/scripts/script_a_test.py $'script_a.x*\nscript_b.x*' "Python scripts mutation testing: 1 of 1 mutants survived"
  check python .github/scripts/mutate.sh $'pkg.x*\npkg.a.x*\npkg.b.x*\nscript_a.x*\nscript_b.x*' "Python scripts mutation testing: 1 of 1 mutants survived"
  check python .github/scripts/shell_script.sh "" "Python scripts mutation testing: no source or test file changed"

  FAKE_ALL_KILLED=1 check python src/pkg/a.py 'pkg.a.x*' "0 of 2 mutants survived"
  FAKE_ALL_KILLED=1 check python .github/scripts/script_a.py 'script_a.x*' "Python scripts mutation testing: 0 of 1 mutants survived"
  FAKE_ALL_KILLED=1 check rust crates/c/src/x.rs crates/c/src/x.rs "0 of 2 mutants survived"
  FAKE_ALL_KILLED=1 check typescript packages/p/src/a.ts packages/p/src/a.ts "0 of 2 mutants survived"
  echo ".github/scripts/mutate.sh chose the expected files and reported them in all 18 cases."
}

# Writes fake uv, cargo, and pnpm, which append the module globs or files
# they are given to $work/tool-arguments, one per line.
make_fake_tools() {
  mkdir "$work/bin"
  cat > "$work/bin/uv" << 'EOF'
#!/usr/bin/env bash
case "$*" in
  "run mutmut run "*)
    if [[ $PWD == */.mutants-scripts ]]; then
      # The scratch project has the scripts, without their tests, in src/, the
      # tests, without the scripts, in tests/, and the root's environment.
      [[ -f src/script_a.py && -f src/script_b.py && ! -e src/script_a_test.py && -f tests/script_a_test.py && ! -e tests/script_a.py && -f pyproject.toml && -n ${UV_PROJECT:-} ]] || { echo "fake uv: the scratch project is wrong: $(find . -type f | sort | tr '\n' ' ')" >&2; exit 1; }
    fi
    printf '%s\n' "${@:4}" >> "$FAKE_TOOL_ARGUMENTS"
    ;;
  "run mutmut results --all true")
    if [[ $PWD == */.mutants-scripts ]]; then
      printf '    script_a.x_f__mutmut_1: %s\n' "$([[ -n ${FAKE_ALL_KILLED:-} ]] && echo killed || echo survived)"
      exit 0
    fi
    printf '    pkg.a.x_f__mutmut_1: %s\n    pkg.a.x_f__mutmut_2: killed\n    pkg.b.x_g__mutmut_1: not checked\n' "$([[ -n ${FAKE_ALL_KILLED:-} ]] && echo killed || echo survived)"
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
    "$work/repo/crates/c/src" "$work/repo/crates/c/tests" "$work/repo/packages/p/src"
  cd "$work/repo"
  cp "$script_dir/mutate.sh" .github/scripts/
  touch src/pkg/__init__.py src/pkg/a.py src/pkg/b.py tests/test_a.py \
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
# the expected headline. The script must exit 0, though the fake cargo
# exits 2.
check() {
  local language=$1 changed_file=$2 expected_arguments=$3 expected_headline=$4
  git checkout --quiet -- .
  git clean --quiet --force -d
  : > "$FAKE_TOOL_ARGUMENTS"
  echo "# changed" >> "$changed_file"

  local report arguments status=0
  report=$(.github/scripts/mutate.sh "$language" HEAD) || status=$?
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
}

main
