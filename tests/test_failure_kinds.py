import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from compute_jobs_cli import cli
from compute_jobs_cli.arguments import COMMANDS
from compute_jobs_cli.kinds import FailureKind

Invoke = Callable[[Sequence[str]], tuple[int, list[str]]]

VALID_ARGUMENTS = {
    "dry-run": ["dry-run", "jobs/search.yaml"],
    "launch": ["launch", "jobs/search.yaml"],
    "observe": ["observe", "pr81-search-3f9a2c1d"],
    "cancel": ["cancel", "pr81-search-3f9a2c1d"],
}


class RecordingSdk:
    """A fake SkyPilot SDK that records each call and never touches a network."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def launch(self, job_name: str, task_yaml: str) -> None:
        self.calls.append(f"launch {job_name}")

    def queue(self) -> Sequence[Mapping[str, object]]:
        self.calls.append("queue")
        return []

    def cancel(self, job_name: str) -> None:
        self.calls.append(f"cancel {job_name}")


@pytest.fixture
def invoke(capsys: pytest.CaptureFixture[str]) -> Invoke:
    """Run main with a recording SDK that must stay unused; return exit code and stderr lines."""

    def run(argv: Sequence[str]) -> tuple[int, list[str]]:
        sdk = RecordingSdk()
        exit_code = cli.main(argv, sdk)
        captured = capsys.readouterr()
        assert (sdk.calls, captured.out) == ([], "")
        return exit_code, captured.err.splitlines()

    return run


@pytest.mark.parametrize("command", COMMANDS)
def test_ac2_an_argument_error_exits_1_not_argparses_2(
    command: str, invoke: Invoke
) -> None:
    exit_code, _ = invoke([*VALID_ARGUMENTS[command], "--unknown-option"])

    assert exit_code == 1


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["unknown-command"],
        ["dry-run"],
        ["launch", "a.yaml", "b.yaml"],
        ["cancel"],
        ["observe", "--pr", "eighty-one"],
        ["observe", "--lines", "0"],
        ["observe", "--js"],
    ],
)
def test_ac2_each_malformed_command_line_exits_1(
    argv: list[str], invoke: Invoke
) -> None:
    exit_code, stderr_lines = invoke(argv)

    assert (exit_code, stderr_lines[0]) == (1, "kind=argument_error")


@pytest.mark.parametrize(
    "argv",
    [["observe"], ["observe", "--pr", "81", "--lines", "40", "--json", "pr81-a-1"]],
)
def test_ac2_each_observe_form_in_the_commands_table_parses(
    argv: list[str], invoke: Invoke
) -> None:
    _, stderr_lines = invoke(argv)

    assert "observe is not implemented yet" in stderr_lines[1]


@pytest.mark.parametrize("command", COMMANDS)
def test_ac23_argument_error_by_an_unknown_option(command: str, invoke: Invoke) -> None:
    exit_code, stderr_lines = invoke([*VALID_ARGUMENTS[command], "--unknown-option"])

    assert (exit_code, stderr_lines[0]) == (1, "kind=argument_error")
    assert "--unknown-option" in stderr_lines[-1]


@pytest.mark.parametrize("command", COMMANDS)
def test_ac23_internal_error_for_a_command_that_is_not_built_yet(
    command: str, invoke: Invoke
) -> None:
    exit_code, stderr_lines = invoke(VALID_ARGUMENTS[command])

    assert (exit_code, stderr_lines[0]) == (1, "kind=internal_error")
    assert f"compute-jobs {command} is not implemented yet" in stderr_lines[1]


def test_ac23_internal_error_by_an_unexpected_exception_includes_its_traceback(
    monkeypatch: pytest.MonkeyPatch, invoke: Invoke
) -> None:
    def raise_unexpected_exception(*_: object) -> None:
        raise RuntimeError("the SDK returned garbage")

    monkeypatch.setattr(cli, "run_command", raise_unexpected_exception)

    exit_code, stderr_lines = invoke(VALID_ARGUMENTS["launch"])

    assert (exit_code, stderr_lines[0]) == (1, "kind=internal_error")
    assert "RuntimeError('the SDK returned garbage')" in stderr_lines[1]
    assert "Traceback (most recent call last):" in stderr_lines


def test_ac23_exit_0_writes_no_kind_line(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--help"])

    assert exit_info.value.code == 0
    assert "kind=" not in capsys.readouterr().err


def test_the_compute_jobs_script_exits_with_the_contract_codes(tmp_path: Path) -> None:
    script = Path(sys.executable).parent / "compute-jobs"

    def run_script(*argv: str) -> tuple[int, str]:
        process = subprocess.run(
            [str(script), *argv],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            check=False,
        )
        return process.returncode, process.stderr.splitlines()[0]

    assert run_script("launch") == (1, "kind=argument_error")
    assert run_script("launch", "job.yaml") == (1, "kind=internal_error")


def test_every_failure_kind_matches_the_contracts_pattern_and_only_not_configured_exits_2() -> (
    None
):
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", kind) for kind in FailureKind)
    assert {kind for kind in FailureKind if kind.exit_code == 2} == {
        FailureKind.NOT_CONFIGURED
    }
