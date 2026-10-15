from pathlib import Path

import pytest
from compute_jobs.job_file import JobFile, read_job_file
from compute_jobs_admin_policy.limits import shipped_limits
from compute_jobs_admin_policy.placement import JobRequest, PlacementRefusal, place_job

REQUIRED = "command: python run.py\nmax_runtime_minutes: 15\nbudget_usd: 1\n"


def check_job_file(path: Path) -> list[str] | str:
    job_file = read_job_file(path, "dry-run")
    if not isinstance(job_file, JobFile):
        return job_file.failure_kind
    placement = place_job(
        JobRequest(job_file.kind, job_file.profile, job_file.nodes, job_file.use_spot),
        shipped_limits(),
    )
    if isinstance(placement, PlacementRefusal):
        return placement.failure_kind
    return [entry["instance_type"] for entry in placement]


# AC 5, against the shipped limits.yaml: cpu allows 3 nodes, gpu-sim 2.
@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ("kind: single\nprofile: cpu\n", ["m7i.4xlarge"]),
        ("kind: multi-node\nprofile: cpu\nnodes: 1\n", ["m7i.4xlarge"]),
        ("kind: multi-node\nprofile: cpu\nnodes: 3\n", ["m7i.4xlarge"]),
        (
            "kind: search\nprofile: gpu-sim\nnodes: 1\n",
            ["g6e.48xlarge", "g6e.12xlarge"],
        ),
        (
            "kind: search\nprofile: gpu-sim\nnodes: 2\n",
            ["g6e.48xlarge", "g6e.12xlarge"],
        ),
        ("schema_version: 1\nkind: single\nprofile: cpu\n", ["m7i.4xlarge"]),
        ("profile: cpu\n", "invalid_job_file"),
        ("kind: batch\nprofile: cpu\n", "invalid_job_file"),
        ("kind: single\n", "invalid_job_file"),
        ("kind: single\nprofile: gpu-huge\n", "invalid_job_file"),
        ("kind: single\nprofile: cpu\nnodes: 1\n", "invalid_job_file"),
        ("kind: multi-node\nprofile: cpu\nnodes: 4\n", "refused_job_file"),
        ("kind: search\nprofile: gpu-sim\nnodes: 3\n", "refused_job_file"),
    ],
)
def test_the_job_file_accepts_each_kind_and_rejects_bad_kinds_profiles_and_nodes(
    tmp_path: Path, fields: str, expected: list[str] | str
) -> None:
    path = tmp_path / "job.yaml"
    path.write_text(fields + REQUIRED)

    assert check_job_file(path) == expected


def test_a_job_file_without_schema_version_reads_as_major_1(tmp_path: Path) -> None:
    path = tmp_path / "job.yaml"
    path.write_text("kind: single\nprofile: cpu\n" + REQUIRED)

    job_file = read_job_file(path, "dry-run")

    assert isinstance(job_file, JobFile)
    assert job_file.schema_version == 1
