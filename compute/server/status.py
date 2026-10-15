"""Check the shared server and its AWS account without changing either.

``MISE_ENV=admin mise run compute-server:status`` runs this on the owner's
machine ("Admin tasks" in docs/compute-jobs.md). It reads AWS only through
the AWS CLI's get, list, and describe calls, with the profile that
``COMPUTE_SERVER_ADMIN_AWS_PROFILE`` names, and sends the server one request
without a token. It prints each check's result, then lists the failed ones.

Exit codes: 0 when every check passed; 1 when any failed; 2 when nothing could
be checked, because the profile variable is unset, the AWS CLI is missing, or
the profile has no working credentials.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, NamedTuple

from compute_jobs_admin_policy.limits import Limits, shipped_limits, spending_ceiling

PROFILE_VARIABLE = "COMPUTE_SERVER_ADMIN_AWS_PROFILE"
ENDPOINT_VARIABLE = "SKYPILOT_API_SERVER_ENDPOINT"
REGION = "us-east-1"
SERVER_TIMEOUT_S = 10
# Any path the server serves only with a token; that 0.14.0 answers this one
# with 401 is unverified until AC 19's run on the real server.
UNAUTHENTICATED_PATH = "/api/status"
LAUNCHER_ROLE = "compute-jobs-launcher"
DENY_LAUNCH_POLICY = "compute-jobs-deny-launch"
DAILY_BUDGET = "compute-jobs-daily"
FULL_ACTUAL_COST = {"ActionThresholdValue": 100.0, "ActionThresholdType": "PERCENTAGE"}
# The EC2 vCPU quota each limits.yaml quota group stands for, by its name in
# Service Quotas, from
# https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-quotas.html
QUOTA_NAMES = {
    "standard_on_demand": "Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances",
    "g_vt_on_demand": "Running On-Demand G and VT instances",
    "g_vt_spot": "All G and VT Spot Instance Requests",
    "p_on_demand": "Running On-Demand P instances",
    "p_spot": "All P Spot Instance Requests",
}


class AwsError(Exception):
    """An AWS CLI call failed; the message is the CLI's own error."""


Aws = Callable[[str], Any]
"""Runs ``aws <command>`` with the admin profile and returns its parsed JSON output.

The command's words are separated by single spaces, and none contains one.
Raises AwsError when the call fails.
"""

ServerStatus = Callable[[str], int | None]
"""Returns the HTTP status of a GET of a URL without a token, or None on no answer."""


class Result(NamedTuple):
    """One check's outcome: whether it passed, and what was found or what to do."""

    passed: bool
    message: str


def main(
    environ: Mapping[str, str],
    aws_with_profile: Callable[[str], Aws],
    server_status: ServerStatus,
    limits: Limits,
) -> int:
    """Run every check, print each result and the failures, and return the exit code.

    Args:
        environ: The environment, which gives the profile and the endpoint.
        aws_with_profile: Makes the AWS CLI caller for a profile name.
        server_status: Sends the server's request without a token.
        limits: The ``limits.yaml`` to check.

    Returns:
        0, 1, or 2, as the module docstring says.
    """
    profile = environ.get(PROFILE_VARIABLE, "")
    if not profile:
        print(
            f"{PROFILE_VARIABLE} is not set, so nothing was checked. Set it to the AWS "
            "CLI profile of your IAM Identity Center login to the agent-jobs account.",
            file=sys.stderr,
        )
        return 2
    aws = aws_with_profile(profile)
    try:
        account_id: str = aws("sts get-caller-identity")["Account"]
    except AwsError as error:
        print(
            f"The AWS CLI profile {profile} gave no working credentials, so nothing was "
            f"checked: {error}\nLog in with `aws sso login --profile {profile}`, then rerun.",
            file=sys.stderr,
        )
        return 2

    results = [
        check_spending_ceiling(limits),
        *check_quotas(limits, aws),
        check_budget_action(account_id, aws),
        check_server(environ.get(ENDPOINT_VARIABLE, ""), server_status),
    ]
    for result in results:
        print(f"{'ok' if result.passed else 'FAILED'}: {result.message}")
    failures = [result.message for result in results if not result.passed]
    if not failures:
        print("Every check passed.")
        return 0
    sys.stdout.flush()
    print(f"\n{len(failures)} of {len(results)} checks failed:", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    return 1


def check_spending_ceiling(limits: Limits) -> Result:
    """Check that the quotas, full of the dearest enabled entries, fit the daily cap."""
    ceiling = spending_ceiling(limits)
    refusal = ceiling.refusal()
    if refusal is not None:
        return Result(False, refusal)
    return Result(
        True,
        f"limits.yaml's spending ceiling is ${ceiling.usd_per_hour:.2f} an hour, "
        f"within ${ceiling.cap_usd_per_hour:.2f}",
    )


def check_quotas(limits: Limits, aws: Aws) -> list[Result]:
    """Check that no EC2 vCPU quota exceeds its group's in limits.yaml.

    A larger quota lets more run at once than the spending ceiling counts. A
    quota never changed has no applied value, so its default counts.
    """
    try:
        defaults = aws(
            "service-quotas list-aws-default-service-quotas --service-code ec2"
        )
        applied = aws("service-quotas list-service-quotas --service-code ec2")
    except AwsError as error:
        return [Result(False, f"couldn't read EC2's quotas: {error}")]
    quotas = defaults["Quotas"] + applied["Quotas"]
    vcpus_by_name = {quota["QuotaName"]: quota["Value"] for quota in quotas}

    results: list[Result] = []
    for group, vcpus in limits["quotas"].items():
        name = QUOTA_NAMES.get(group, group)
        live_vcpus = vcpus_by_name.get(name)
        if live_vcpus is None:
            message = f"EC2 has no quota named {name!r}, for limits.yaml's {group}"
        elif live_vcpus > vcpus:
            message = (
                f"EC2's quota {name!r} is {live_vcpus:g} vCPUs, above limits.yaml's "
                f"{group}: {vcpus}, so the spending ceiling understates; lower the "
                f"quota, or raise {group} and rerun"
            )
        else:
            results.append(Result(True, f"{name}: {live_vcpus:g} of {vcpus} vCPUs"))
            continue
        results.append(Result(False, message))
    return results


def check_budget_action(account_id: str, aws: Aws) -> Result:
    """Check that the daily budget denies launches at 100% of actual cost."""
    try:
        actions = aws(
            f"budgets describe-budget-actions-for-budget --account-id {account_id} "
            f"--budget-name {DAILY_BUDGET}"
        )["Actions"]
    except AwsError as error:
        return Result(
            False, f"couldn't read the budget {DAILY_BUDGET}'s actions: {error}"
        )

    for action in actions:
        attachment = action["Definition"].get("IamActionDefinition", {})
        if (
            action["NotificationType"] == "ACTUAL"
            and action["ActionThreshold"] == FULL_ACTUAL_COST
            and attachment.get("PolicyArn") == deny_launch_policy_arn(account_id)
            and LAUNCHER_ROLE in attachment.get("Roles", [])
        ):
            return Result(True, f"the budget {DAILY_BUDGET} denies launches at 100%")
    return Result(
        False,
        f"the budget {DAILY_BUDGET} has no action attaching {DENY_LAUNCH_POLICY} to "
        f"{LAUNCHER_ROLE} at 100% of actual cost; add it as docs/compute-jobs.md "
        'says in "Setup for the owner", step 9',
    )


def check_server(endpoint: str, server_status: ServerStatus) -> Result:
    """Check that the server answers, and refuses a request without a token."""
    if not endpoint:
        return Result(
            False,
            f"{ENDPOINT_VARIABLE} is not set, so the server wasn't checked; set it to "
            "the server's https:// URL",
        )
    status = server_status(endpoint.rstrip("/") + UNAUTHENTICATED_PATH)
    if status is None:
        return Result(
            False, f"the server at {endpoint} didn't answer within {SERVER_TIMEOUT_S} s"
        )
    if status != 401:
        return Result(
            False,
            f"the server at {endpoint} answered a request without a token with HTTP "
            f"{status}, not 401; check that apiService.enableUserManagement is true",
        )
    return Result(True, f"the server at {endpoint} refuses a request without a token")


def deny_launch_policy_arn(account_id: str) -> str:
    """Return the ARN of the deny-launch policy in the account."""
    return f"arn:aws:iam::{account_id}:policy/{DENY_LAUNCH_POLICY}"


def aws_cli(profile: str) -> Aws:
    """Return a caller of the installed AWS CLI with the profile, in us-east-1."""

    def call(command: str) -> Any:
        options = ["--profile", profile, "--region", REGION, "--output", "json"]
        try:
            completed = subprocess.run(
                ["aws", *command.split(" "), *options],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise AwsError(
                "the AWS CLI isn't on PATH; run this through "
                "`MISE_ENV=admin mise run compute-server:status`, which installs it"
            ) from error
        if completed.returncode != 0:
            raise AwsError(
                completed.stderr.strip() or f"aws exited {completed.returncode}"
            )
        return json.loads(completed.stdout)

    return call


def unauthenticated_status(url: str) -> int | None:
    """Return the HTTP status of a GET of the URL without a token, or None on no answer."""
    try:
        with urllib.request.urlopen(url, timeout=SERVER_TIMEOUT_S) as response:
            return response.status
    except urllib.error.HTTPError as error:
        error.close()
        return error.code
    except OSError:
        return None


if __name__ == "__main__":
    sys.exit(main(os.environ, aws_cli, unauthenticated_status, shipped_limits()))
