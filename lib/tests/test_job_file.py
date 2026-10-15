import json
from pathlib import Path

import pytest
import yaml
from compute_jobs.job_file import JobFile, JobFileRefusal, job_name, read_job_file

FIXTURES = Path(__file__).parent / "fixtures"


def fixtures(validity: str) -> list[dict[str, object]]:
    documents = json.loads((FIXTURES / f"job-file.v1.{validity}.json").read_text())
    return list(documents.values())


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "job.yaml"
    path.write_text(text)
    return path


@pytest.mark.parametrize("document", fixtures("valid"))
def test_each_valid_fixture_reads_with_its_fields(
    tmp_path: Path, document: dict[str, object]
) -> None:
    job_file = read_job_file(write(tmp_path, yaml.safe_dump(document)), "dry-run")

    assert isinstance(job_file, JobFile)
    assert {name: getattr(job_file, name) for name in document} == document


@pytest.mark.parametrize("document", fixtures("invalid"))
def test_each_invalid_fixture_is_an_invalid_job_file(
    tmp_path: Path, document: dict[str, object]
) -> None:
    refusal = read_job_file(write(tmp_path, yaml.safe_dump(document)), "dry-run")

    assert isinstance(refusal, JobFileRefusal)
    assert refusal.failure_kind == "invalid_job_file"


@pytest.mark.parametrize(
    ("text", "failure_kind", "message"),
    [
        ("kind: [", "invalid_job_file", "isn't valid YAML"),
        ("- kind: single\n", "invalid_job_file", "must be a mapping"),
        (
            "kind: single\nprofile: cpu\nnodes: 2\ncommand: x\nmax_runtime_minutes: 1\nbudget_usd: 1\n",
            "invalid_job_file",
            "a single job runs on one node",
        ),
        (
            "kind: single\nprofile: cpu\ngpus: 1\ncommand: x\nmax_runtime_minutes: 1\nbudget_usd: 1\n",
            "invalid_job_file",
            "'gpus' was unexpected",
        ),
        (
            "schema_version: 99\nkind: single\n",
            "refused_job_file",
            "schema_version 99; this dry-run reads 1",
        ),
    ],
)
def test_read_job_file_names_the_failure_kind_and_the_fault(
    tmp_path: Path, text: str, failure_kind: str, message: str
) -> None:
    refusal = read_job_file(write(tmp_path, text), "dry-run")

    assert isinstance(refusal, JobFileRefusal)
    assert refusal.failure_kind == failure_kind
    assert message in refusal.message


def test_the_job_name_is_the_pr_the_file_stem_and_8_hex_digits_of_its_sha256(
    tmp_path: Path,
) -> None:
    path = tmp_path / "search.yaml"
    path.write_text("kind: search\n")
    first_name = job_name(81, path)
    path.write_text("kind: search\nnodes: 2\n")

    assert first_name == "pr81-search-40695b8f"
    assert job_name(81, path) != first_name
