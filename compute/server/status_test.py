import copy
import http.server
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest
import status
from compute_jobs_admin_policy.limits import Limits, shipped_limits

REPOSITORY = Path(__file__).parents[2]
ACCOUNT_ID = "123456789012"
PROFILE = {status.PROFILE_VARIABLE: "agent-jobs-admin"}
CONFIGURED = {**PROFILE, status.ENDPOINT_VARIABLE: "https://compute-jobs.test"}
BUDGET_ACTION = {
    "NotificationType": "ACTUAL",
    "ActionThreshold": status.FULL_ACTUAL_COST,
    "Definition": {
        "IamActionDefinition": {
            "PolicyArn": f"arn:aws:iam::{ACCOUNT_ID}:policy/compute-jobs-deny-launch",
            "Roles": ["compute-jobs-launcher"],
        }
    },
}


def healthy_account(limits: Limits) -> dict[str, Any]:
    """Return a fake AWS CLI's answers, by command, for an account set up as limits says."""
    quotas = [
        {"QuotaName": status.QUOTA_NAMES[g], "Value": v}
        for g, v in limits["quotas"].items()
    ]
    return {
        "sts get-caller-identity": {"Account": ACCOUNT_ID},
        "service-quotas list-aws-default-service-quotas": {"Quotas": []},
        "service-quotas list-service-quotas": {"Quotas": quotas},
        "budgets describe-budget-actions-for-budget": {"Actions": [BUDGET_ACTION]},
    }


def fake_aws(answers: dict[str, Any], calls: list[str]) -> status.Aws:
    """Return an AWS CLI caller that answers by a command's first two words, recording each."""

    def call(command: str) -> Any:
        calls.append(command)
        answer = answers[" ".join(command.split(" ")[:2])]
        if isinstance(answer, status.AwsError):
            raise answer
        return answer

    return call


def run_status(
    environ: dict[str, str], answers: dict[str, Any], server: int | None, limits: Limits
) -> tuple[int, list[str]]:
    calls: list[str] = []
    exit_code = status.main(
        environ, lambda _: fake_aws(answers, calls), lambda _: server, limits
    )
    return exit_code, calls


@pytest.mark.parametrize("aws_on_path", [True, False])
def test_status_exits_with_a_message_not_a_traceback_without_aws_credentials(
    aws_on_path: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if aws_on_path:
        fake_cli = tmp_path / "aws"
        fake_cli.write_text(
            "#!/bin/sh\necho 'Unable to locate credentials.' >&2\nexit 253\n"
        )
        fake_cli.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    exit_code = status.main(CONFIGURED, status.aws_cli, lambda _: 401, shipped_limits())

    expected = (
        "Unable to locate credentials." if aws_on_path else "the AWS CLI isn't on PATH"
    )
    assert exit_code == 2
    assert expected in capsys.readouterr().err


def test_status_passes_when_the_server_and_account_match_limits(
    capsys: pytest.CaptureFixture[str],
) -> None:
    limits = shipped_limits()

    exit_code, calls = run_status(CONFIGURED, healthy_account(limits), 401, limits)

    assert exit_code == 0
    assert "Every check passed." in capsys.readouterr().out
    assert {" ".join(c.split(" ")[:2]) for c in calls} == set(healthy_account(limits))


def test_status_lists_each_failed_check(capsys: pytest.CaptureFixture[str]) -> None:
    limits = shipped_limits()
    answers = healthy_account(limits)
    answers["service-quotas list-service-quotas"]["Quotas"][1]["Value"] = 768
    answers["budgets describe-budget-actions-for-budget"] = {"Actions": []}

    exit_code, _ = run_status(CONFIGURED, answers, 200, limits)

    errors = capsys.readouterr().err
    assert exit_code == 1
    assert "3 of 8 checks failed:" in errors
    assert "'Running On-Demand G and VT instances' is 768 vCPUs, above" in errors
    assert (
        "has no action attaching compute-jobs-deny-launch to compute-jobs-launcher"
        in errors
    )
    assert "with HTTP 200, not 401" in errors


def test_status_fails_when_the_spending_ceiling_exceeds_the_daily_cap(
    capsys: pytest.CaptureFixture[str],
) -> None:
    limits = copy.deepcopy(shipped_limits())
    limits["quotas"]["p_on_demand"] = 384
    for entry in limits["profiles"]["gpu-train-large"]["entries"]:
        entry["enabled"] = True

    exit_code, _ = run_status(CONFIGURED, healthy_account(limits), 401, limits)

    assert exit_code == 1
    assert "spending ceiling is $470.63 an hour" in capsys.readouterr().err


def test_status_fails_when_the_server_does_not_answer_or_is_not_set(
    capsys: pytest.CaptureFixture[str],
) -> None:
    limits = shipped_limits()

    assert run_status(CONFIGURED, healthy_account(limits), None, limits)[0] == 1
    assert run_status(PROFILE, healthy_account(limits), 401, limits)[0] == 1

    errors = capsys.readouterr().err
    assert "the server at https://compute-jobs.test didn't answer within 10 s" in errors
    assert (
        "SKYPILOT_API_SERVER_ENDPOINT is not set, so the server wasn't checked"
        in errors
    )


def test_unauthenticated_status_returns_the_servers_http_status() -> None:
    class Refuse(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_error(401)

    server = http.server.HTTPServer(("127.0.0.1", 0), Refuse)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/api/status"
    try:
        assert status.unauthenticated_status(url) == 401
    finally:
        server.shutdown()
        server.server_close()


def run_mise(
    arguments: list[str], mise_env: str | None
) -> subprocess.CompletedProcess[str]:
    unset = {"MISE_ENV", status.PROFILE_VARIABLE}
    environ = {k: v for k, v in os.environ.items() if k not in unset}
    if mise_env is not None:
        environ["MISE_ENV"] = mise_env
    # Only uv, so that mise doesn't download the AWS CLI that mise.admin.toml pins.
    environ["MISE_ENABLE_TOOLS"] = "uv"
    return subprocess.run(
        ["mise", *arguments],
        cwd=REPOSITORY,
        env=environ,
        capture_output=True,
        text=True,
        check=False,
    )


def mise_task_names(mise_env: str | None) -> list[str]:
    listing = run_mise(["tasks", "ls", "--json"], mise_env)
    assert listing.returncode == 0, listing.stderr
    return [task["name"] for task in json.loads(listing.stdout)]


def test_default_mise_configuration_lists_no_compute_server_task() -> None:
    default_tasks = mise_task_names(None)

    assert not [name for name in default_tasks if name.startswith("compute-server:")]
    assert "compute-server:status" in mise_task_names("admin")


def test_admin_status_task_exits_with_a_message_when_the_profile_is_unset() -> None:
    completed = run_mise(["run", "compute-server:status"], "admin")

    assert completed.returncode != 0
    assert (
        "COMPUTE_SERVER_ADMIN_AWS_PROFILE is not set, so nothing was checked"
        in completed.stderr
    )
    assert "Traceback" not in completed.stderr
