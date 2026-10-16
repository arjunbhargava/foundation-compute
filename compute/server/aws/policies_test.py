"""Static checks of the IAM policies in this directory; README.md says why each statement exists."""

import json
import re
from pathlib import Path
from typing import Any

POLICY_DIRECTORY = Path(__file__).parent
POLICY_FILES = sorted(POLICY_DIRECTORY.glob("*.json"))
BUCKET = "arn:aws:s3:::<bucket>"
JOB_REPOSITORY = "arn:aws:ecr:us-east-1:<account_id>:repository/compute-jobs/job"
JOB_ROLE = "arn:aws:iam::<account_id>:role/compute-jobs-job"
S3_READ_ACTIONS = {"s3:GetBucketLocation", "s3:GetObject", "s3:ListBucket"}
# AWS supports no resource narrower than "*" for these.
ACTIONS_ALLOWED_ON_EVERY_RESOURCE = {"ec2:Describe*", "ecr:GetAuthorizationToken"}


def load(file_name: str) -> dict[str, Any]:
    return json.loads((POLICY_DIRECTORY / file_name).read_text(encoding="utf-8"))


def as_list(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else value


def allowed_grants(policy: dict[str, Any]) -> set[tuple[str, str]]:
    """Return each (action, resource) pair the policy's Allow statements grant."""
    return {
        (action, resource)
        for statement in policy["Statement"]
        if statement["Effect"] == "Allow"
        for action in as_list(statement["Action"])
        for resource in as_list(statement["Resource"])
    }


def resources_of(grants: set[tuple[str, str]], service: str) -> set[str]:
    return {resource for action, resource in grants if action.startswith(f"{service}:")}


def object_writes(grants: set[tuple[str, str]]) -> set[tuple[str, str]]:
    return {
        (a, r) for a, r in grants if a.startswith("s3:") and a not in S3_READ_ACTIONS
    }


def statement(file_name: str, sid: str) -> dict[str, Any]:
    return next(s for s in load(file_name)["Statement"] if s["Sid"] == sid)


def test_job_role_writes_only_under_its_machine_index_and_checkpoints() -> None:
    grants = allowed_grants(load("job.json"))

    assert object_writes(grants) == {
        ("s3:PutObject", f"{BUCKET}/machines/${{aws:userid}}/*"),
        ("s3:PutObject", f"{BUCKET}/index/*"),
        ("s3:PutObject", f"{BUCKET}/checkpoints/*"),
        ("s3:DeleteObject", f"{BUCKET}/checkpoints/*"),
    }


def test_job_role_pulls_only_from_the_job_repository() -> None:
    grants = allowed_grants(load("job.json"))

    assert {(a, r) for a, r in grants if a.startswith("ecr:")} == {
        ("ecr:GetAuthorizationToken", "*"),
        ("ecr:BatchCheckLayerAvailability", JOB_REPOSITORY),
        ("ecr:BatchGetImage", JOB_REPOSITORY),
        ("ecr:GetDownloadUrlForLayer", JOB_REPOSITORY),
    }


def test_job_role_ends_only_the_instance_it_runs_on() -> None:
    assert statement("job.json", "EndOwnInstance")["Condition"] == {
        "ArnEquals": {
            "ec2:SourceInstanceARN": "arn:aws:ec2:us-east-1:<account_id>:instance/${ec2:InstanceID}"
        }
    }
    trust = statement("job-trust.json", "Ec2InstancesAssumeJobRole")
    assert trust["Principal"] == {"Service": "ec2.amazonaws.com"}


def test_image_push_role_trusts_only_the_release_environment() -> None:
    (trust,) = load("image-push-trust.json")["Statement"]

    assert trust["Effect"] == "Allow"
    assert trust["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert trust["Principal"] == {
        "Federated": "arn:aws:iam::<account_id>:oidc-provider/token.actions.githubusercontent.com"
    }
    # StringEquals, not StringLike: a wildcard in sub would admit other refs or repositories.
    assert trust["Condition"] == {
        "StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
            "token.actions.githubusercontent.com:sub": "repo:arjunbhargava/foundation-compute:environment:release",
        }
    }


def test_image_push_role_pushes_only_to_the_job_repository() -> None:
    grants = allowed_grants(load("image-push.json"))

    assert resources_of(grants, "ecr") - {"*"} == {JOB_REPOSITORY}
    assert {a for a, r in grants if r == "*"} == {"ecr:GetAuthorizationToken"}
    assert ("ecr:PutImage", JOB_REPOSITORY) in grants
    assert {a.split(":")[0] for a, _ in grants} == {"ecr"}


def test_launcher_passes_only_the_job_role_and_only_to_ec2() -> None:
    grants = allowed_grants(load("launcher.json"))
    pass_role = statement("launcher.json", "PassJobRoleToEc2")

    assert {r for a, r in grants if a == "iam:PassRole"} == {JOB_ROLE}
    assert pass_role["Condition"] == {
        "StringEquals": {"iam:PassedToService": "ec2.amazonaws.com"}
    }


def test_launcher_writes_objects_only_under_uploads() -> None:
    grants = allowed_grants(load("launcher.json"))

    assert {r for _, r in object_writes(grants)} == {f"{BUCKET}/uploads/*"}
    assert resources_of(grants, "s3") == {BUCKET, f"{BUCKET}/uploads/*"}
    assert resources_of(grants, "ecr") == {JOB_REPOSITORY}


def test_launcher_changes_machines_only_in_this_account_and_region() -> None:
    public_images = "arn:aws:ec2:us-east-1::image/ami-*"
    grants = allowed_grants(load("launcher.json"))
    changed = {r for a, r in grants if a.startswith("ec2:") and a != "ec2:Describe*"}

    assert {a for a, r in grants if r == public_images} == {"ec2:RunInstances"}
    for resource in changed - {public_images}:
        assert resource.startswith("arn:aws:ec2:us-east-1:<account_id>:"), resource


def test_observer_user_only_reads_the_archive() -> None:
    assert allowed_grants(load("observer.json")) == {
        ("s3:GetBucketLocation", BUCKET),
        ("s3:ListBucket", BUCKET),
        ("s3:GetObject", f"{BUCKET}/*"),
    }


def test_deny_launch_policy_denies_starting_any_machine() -> None:
    (deny,) = load("deny-launch.json")["Statement"]

    assert deny["Effect"] == "Deny"
    assert set(deny["Action"]) == {"ec2:RunInstances", "ec2:StartInstances"}
    assert deny["Resource"] == "*"
    assert "Condition" not in deny


def test_wildcards_appear_only_where_aws_supports_nothing_narrower() -> None:
    for path in POLICY_FILES:
        if "trust" in path.name:
            continue
        for action, resource in allowed_grants(load(path.name)):
            assert "*" not in action or action == "ec2:Describe*", (path.name, action)
            if resource == "*":
                assert action in ACTIONS_ALLOWED_ON_EVERY_RESOURCE, (path.name, action)


def test_each_policy_has_unique_documented_sids_and_known_placeholders() -> None:
    readme = (POLICY_DIRECTORY / "README.md").read_text(encoding="utf-8")

    for path in POLICY_FILES:
        policy = load(path.name)
        sids = [s["Sid"] for s in policy["Statement"]]
        assert policy["Version"] == "2012-10-17", path.name
        assert len(sids) == len(set(sids)), path.name
        for sid in sids:
            assert f"`{sid}`" in readme, (path.name, sid)
        placeholders = set(re.findall(r"<[^>]*>", path.read_text(encoding="utf-8")))
        assert placeholders <= {"<account_id>", "<bucket>"}, (path.name, placeholders)
