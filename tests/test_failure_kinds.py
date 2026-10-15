import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from compute_jobs_cli import cli
from compute_jobs_cli.arguments import COMMANDS, SERVER_COMMANDS
from compute_jobs_cli.configuration import ENDPOINT_VARIABLE, TOKEN_VARIABLE
from compute_jobs_cli.kinds import FailureKind

Invoke = Callable[[Sequence[str], Mapping[str, str]], tuple[int, list[str]]]

CONFIGURED = {
    ENDPOINT_VARIABLE: "https://jobs.example.org",
    TOKEN_VARIABLE: "token-value",
}

VALID_ARGUMENTS = {
    "dry-run": ["dry-run", "jobs/search.yaml"],
    "launch": ["launch", "jobs/search.yaml"],
    "observe": ["observe", "pr81-search-3f9a2c1d"],
    "cancel": ["cancel", "pr81-search-3f9a2c1d"],
}

V0_NOT_CONFIGURED_MESSAGE = """\
SKYPILOT_API_SERVER_ENDPOINT is not set, so no job can be launched or
observed. This project is a client of a shared SkyPilot API server: ask the
owner to add SKYPILOT_API_SERVER_ENDPOINT and SKYPILOT_SERVICE_ACCOUNT_TOKEN
as Cursor secrets. The server is run with the compute-server-admin skill;
an agent never starts one. Nothing was started.
"""


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

    def run(
        argv: Sequence[str], environment: Mapping[str, str]
    ) -> tuple[int, list[str]]:
        sdk = RecordingSdk()
        exit_code = cli.main(argv, environment, sdk)
        captured = capsys.readouterr()
        assert (sdk.calls, captured.out) == ([], "")
        return exit_code, captured.err.splitlines()

    return run


@pytest.mark.parametrize("command", SERVER_COMMANDS)
def test_ac1_an_unset_variable_exits_2_with_the_v0_message_and_calls_no_sdk(
    command: str, invoke: Invoke
) -> None:
    exit_code, stderr_lines = invoke(VALID_ARGUMENTS[command], {})

    assert exit_code == 2
    assert stderr_lines[0] == "kind=not_configured"
    assert "\n".join(stderr_lines[1:]) + "\n" == V0_NOT_CONFIGURED_MESSAGE


@pytest.mark.parametrize("command", SERVER_COMMANDS)
@pytest.mark.parametrize(
    "environment",
    [
        {ENDPOINT_VARIABLE: "https://jobs.example.org"},
        {TOKEN_VARIABLE: "token-value"},
        {ENDPOINT_VARIABLE: "http://jobs.example.org", TOKEN_VARIABLE: "token-value"},
        {ENDPOINT_VARIABLE: "https://localhost:46580", TOKEN_VARIABLE: "token-value"},
    ],
)
def test_ac1_each_misconfiguration_exits_2_and_calls_no_sdk(
    command: str, environment: dict[str, str], invoke: Invoke
) -> None:
    exit_code, stderr_lines = invoke(VALID_ARGUMENTS[command], environment)

    assert (exit_code, stderr_lines[0]) == (2, "kind=not_configured")
    assert "token-value" not in "\n".join(stderr_lines)


def test_ac1_dry_run_needs_no_server_variables_and_calls_no_sdk(invoke: Invoke) -> None:
    exit_code, stderr_lines = invoke(VALID_ARGUMENTS["dry-run"], {})

    assert (exit_code, stderr_lines[0]) == (1, "kind=internal_error")


@pytest.mark.parametrize("command", COMMANDS)
def test_ac2_an_argument_error_exits_1_not_argparses_2(
    command: str, invoke: Invoke
) -> None:
    exit_code, _ = invoke([*VALID_ARGUMENTS[command], "--unknown-option"], CONFIGURED)

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
    exit_code, stderr_lines = invoke(argv, CONFIGURED)

    assert (exit_code, stderr_lines[0]) == (1, "kind=argument_error")


@pytest.mark.parametrize(
    "argv",
    [["observe"], ["observe", "--pr", "81", "--lines", "40", "--json", "pr81-a-1"]],
)
def test_ac2_each_observe_form_in_the_commands_table_parses(
    argv: list[str], invoke: Invoke
) -> None:
    _, stderr_lines = invoke(argv, CONFIGURED)

    assert "observe is not implemented yet" in stderr_lines[1]


@pytest.mark.parametrize("command", SERVER_COMMANDS)
def test_ac23_not_configured_by_an_unset_variable(command: str, invoke: Invoke) -> None:
    environment = {ENDPOINT_VARIABLE: CONFIGURED[ENDPOINT_VARIABLE]}

    exit_code, stderr_lines = invoke(VALID_ARGUMENTS[command], environment)

    assert (exit_code, stderr_lines[0]) == (2, "kind=not_configured")
    assert f"{TOKEN_VARIABLE} is not set" in stderr_lines[1]


@pytest.mark.parametrize("command", COMMANDS)
def test_ac23_argument_error_by_an_unknown_option(command: str, invoke: Invoke) -> None:
    exit_code, stderr_lines = invoke(
        [*VALID_ARGUMENTS[command], "--unknown-option"], CONFIGURED
    )

    assert (exit_code, stderr_lines[0]) == (1, "kind=argument_error")
    assert "--unknown-option" in stderr_lines[-1]


@pytest.mark.parametrize("command", COMMANDS)
def test_ac23_internal_error_for_a_command_that_is_not_built_yet(
    command: str, invoke: Invoke
) -> None:
    exit_code, stderr_lines = invoke(VALID_ARGUMENTS[command], CONFIGURED)

    assert (exit_code, stderr_lines[0]) == (1, "kind=internal_error")
    assert f"compute-jobs {command} is not implemented yet" in stderr_lines[1]


def test_ac23_internal_error_by_an_unexpected_exception_includes_its_traceback(
    monkeypatch: pytest.MonkeyPatch, invoke: Invoke
) -> None:
    def raise_unexpected_exception(*_: object) -> None:
        raise RuntimeError("the SDK returned garbage")

    monkeypatch.setattr(cli, "run_command", raise_unexpected_exception)

    exit_code, stderr_lines = invoke(VALID_ARGUMENTS["launch"], CONFIGURED)

    assert (exit_code, stderr_lines[0]) == (1, "kind=internal_error")
    assert "RuntimeError('the SDK returned garbage')" in stderr_lines[1]
    assert "Traceback (most recent call last):" in stderr_lines


def test_ac23_exit_0_writes_no_kind_line(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--help"], CONFIGURED)

    assert exit_info.value.code == 0
    assert "kind=" not in capsys.readouterr().err


def test_the_compute_jobs_script_exits_with_the_contract_codes(tmp_path: Path) -> None:
    script = Path(sys.executable).parent / "compute-jobs"

    def run_script(*argv: str, environment: Mapping[str, str]) -> tuple[int, str]:
        process = subprocess.run(
            [str(script), *argv],
            env=environment,
            capture_output=True,
            text=True,
            cwd=tmp_path,
            check=False,
        )
        return process.returncode, process.stderr.splitlines()[0]

    assert run_script("launch", "job.yaml", environment={}) == (
        2,
        "kind=not_configured",
    )
    assert run_script("launch", environment={}) == (1, "kind=argument_error")
    assert run_script("observe", environment=CONFIGURED) == (1, "kind=internal_error")


def test_every_failure_kind_matches_the_contracts_pattern_and_only_not_configured_exits_2() -> (
    None
):
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", kind) for kind in FailureKind)
    assert {kind for kind in FailureKind if kind.exit_code == 2} == {
        FailureKind.NOT_CONFIGURED
    }


def test_ac23_the_kinds_enum_matches_the_failure_kinds_table_in_the_plan() -> None:
    # mutmut runs this file from mutants/tests/, where docs/ is one level higher.
    plan_path = next(
        directory / "docs" / "compute-jobs.md"
        for directory in Path(__file__).parents
        if (directory / "docs" / "compute-jobs.md").exists()
    )
    plan = plan_path.read_text()
    section = plan.split("### Proposed v0.1: failure kinds")[1].split("\n### ")[0]
    rows = re.findall(
        r"^\| `([a-z][a-z0-9_]*)` \| (\d) \|", section, flags=re.MULTILINE
    )

    assert {(kind, int(exit_code)) for kind, exit_code in rows} == {
        (kind.value, kind.exit_code) for kind in FailureKind
    }
