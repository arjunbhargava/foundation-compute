import json
import os
from pathlib import Path

import jsonschema
import pytest
from boto3.exceptions import S3UploadFailedError
from compute_jobs.archive import ArchiveWriter
from compute_jobs.run import Job, main, run_job
from compute_jobs.schemas import load_schema
from mypy_boto3_s3 import S3Client
from s3_helpers import BUCKET, MACHINE_ID, object_keys, read_object

JOB_NAME = "pr81-search-3f9a2c1d"


def make_job(command: str, kind: str = "single", seed: int | None = None) -> Job:
    return Job(JOB_NAME, kind, command, "/mnt/checkpoints", seed)


def run(
    s3: S3Client,
    tmp_path: Path,
    job: Job,
    environ: dict[str, str] | None = None,
) -> int:
    (tmp_path / "work").mkdir()
    archive = ArchiveWriter(s3, BUCKET, job.name, MACHINE_ID)
    return run_job(
        job, archive, {"PATH": os.environ["PATH"], **(environ or {})}, tmp_path / "work"
    )


def run_record(s3: S3Client) -> dict[str, object]:
    record = json.loads(read_object(s3, f"machines/{MACHINE_ID}/run_record.json"))
    jsonschema.validate(record, load_schema("run-record", 1))
    return record


SEEN_KEY = f"machines/{MACHINE_ID}/output/seen.txt"
SHOW_VARIABLES = (
    'printf "%s|%s|%s|%s|%s|%s|%s|%s" "$NNODES" "$NODE_RANK" "$MASTER_ADDR" "$MASTER_PORT"'
    ' "$GPUS_PER_NODE" "$COMPUTE_JOB_SEED" "$COMPUTE_JOB_SMOKE" "$COMPUTE_JOB_CHECKPOINT_DIR"'
    ' > "$COMPUTE_JOB_OUTPUT_DIR/seen.txt"'
)


def test_ac11_exit_0_writes_a_succeeded_run_record_the_log_and_the_output(
    s3: S3Client, tmp_path: Path
) -> None:
    command = (
        'echo hello from the job; echo "42" > "$COMPUTE_JOB_OUTPUT_DIR/result.json"'
    )

    assert run(s3, tmp_path, make_job(command, seed=7)) == 0

    record = run_record(s3)
    assert (record["state"], record["exit_code"]) == ("succeeded", 0)
    assert (record["node_rank"], record["nodes"], record["seed"]) == (0, 1, 7)
    assert read_object(s3, f"machines/{MACHINE_ID}/log.txt") == b"hello from the job\n"
    assert read_object(s3, f"machines/{MACHINE_ID}/output/result.json") == b"42\n"
    assert f"index/{JOB_NAME}/{MACHINE_ID}" in object_keys(s3)


@pytest.mark.parametrize(
    ("command", "exit_code", "state"),
    [
        ("echo about to fail; exit 3", 3, "failed"),
        ("timeout 1 sleep 30", 124, "timed_out"),
    ],
)
def test_ac11_a_nonzero_exit_and_the_timeout_are_a_failed_and_a_timed_out_run_record(
    s3: S3Client, tmp_path: Path, command: str, exit_code: int, state: str
) -> None:
    assert run(s3, tmp_path, make_job(command)) == exit_code

    record = run_record(s3)
    assert (record["state"], record["exit_code"]) == (state, exit_code)


def test_ac12_one_node_gets_the_distributed_variables_with_one_node_defaults(
    s3: S3Client, tmp_path: Path
) -> None:
    run(s3, tmp_path, make_job(SHOW_VARIABLES, kind="multi-node", seed=1234))

    assert (
        read_object(s3, SEEN_KEY).decode()
        == "1|0|127.0.0.1|29500|0|1234|0|/mnt/checkpoints"
    )


def test_ac12_two_nodes_get_skypilots_rank_master_address_and_gpu_count(
    s3: S3Client, tmp_path: Path
) -> None:
    skypilot = {
        "SKYPILOT_NUM_NODES": "2",
        "SKYPILOT_NODE_RANK": "1",
        "SKYPILOT_NODE_IPS": "10.0.0.5\n10.0.0.6\n",
        "SKYPILOT_NUM_GPUS_PER_NODE": "8",
    }

    run(s3, tmp_path, make_job(SHOW_VARIABLES, kind="multi-node"), skypilot)

    assert (
        read_object(s3, SEEN_KEY).decode() == "2|1|10.0.0.5|29500|8||0|/mnt/checkpoints"
    )


@pytest.mark.parametrize(
    ("kind", "node_rank", "runs_command"),
    [
        ("multi-node", "1", True),
        ("search", "0", True),
        ("search", "1", False),
    ],
)
def test_ac12_the_command_runs_on_every_node_of_multi_node_and_on_rank_0_of_search(
    s3: S3Client, tmp_path: Path, kind: str, node_rank: str, runs_command: bool
) -> None:
    skypilot = {"SKYPILOT_NUM_NODES": "2", "SKYPILOT_NODE_RANK": node_rank}

    exit_code = run(s3, tmp_path, make_job(SHOW_VARIABLES, kind=kind), skypilot)

    record = run_record(s3)
    assert exit_code == 0
    assert record["ran_command"] is runs_command
    assert (SEEN_KEY in object_keys(s3)) is runs_command
    assert record["state"] == "succeeded"
    assert f"index/{JOB_NAME}/{MACHINE_ID}" in object_keys(s3)


def test_a_job_whose_archive_cannot_be_written_fails_before_the_command(
    s3: S3Client, tmp_path: Path
) -> None:
    (tmp_path / "work").mkdir()
    archive = ArchiveWriter(s3, "a-bucket-that-does-not-exist", JOB_NAME, MACHINE_ID)
    job = make_job('echo ran > "$COMPUTE_JOB_OUTPUT_DIR/ran.txt"')

    exit_code = run_job(job, archive, {"PATH": os.environ["PATH"]}, tmp_path / "work")

    assert exit_code == 1
    assert "cannot write to the archive" in (tmp_path / "work" / "log.txt").read_text()
    assert not (tmp_path / "work" / "output" / "ran.txt").exists()


def test_a_failed_upload_after_the_command_is_in_the_uploaded_log_and_keeps_the_exit_code(
    s3: S3Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_: object) -> int:
        raise S3UploadFailedError("the connection dropped")

    monkeypatch.setattr(ArchiveWriter, "upload_output_directory", refuse)

    exit_code = run(s3, tmp_path, make_job("echo ok; exit 4"))

    assert exit_code == 4
    assert run_record(s3)["exit_code"] == 4
    uploaded_log = read_object(s3, f"machines/{MACHINE_ID}/log.txt").decode()
    assert "could not upload the output: the connection dropped" in uploaded_log


def test_main_runs_the_job_as_the_machine_sts_names(s3: S3Client) -> None:
    arguments = [
        "--job-name", JOB_NAME, "--kind", "single", "--command", "exit 5", "--bucket", BUCKET,
        "--checkpoint-dir", "/c",
    ]  # fmt: skip

    assert main(arguments) == 5

    [record_key] = [key for key in object_keys(s3) if key.endswith("/run_record.json")]
    assert json.loads(read_object(s3, record_key))["state"] == "failed"
