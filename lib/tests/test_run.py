import json
import os
from pathlib import Path

import jsonschema
import pytest
from compute_jobs.archive import ArchiveWriter
from compute_jobs.run import Job, main, run_job
from compute_jobs.schemas import load_schema
from mypy_boto3_s3 import S3Client
from s3_helpers import BUCKET, MACHINE_ID, object_keys, read_object

JOB_NAME = "pr81-search-3f9a2c1d"


def make_job(command: str, kind: str = "single", **overrides: object) -> Job:
    fields: dict[str, object] = {
        "name": JOB_NAME,
        "kind": kind,
        "command": command,
        "checkpoint_dir": "/mnt/checkpoints",
    }
    return Job(**{**fields, **overrides})  # pyright: ignore[reportArgumentType]


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


SHOW_VARIABLES = (
    'printf "%s|%s|%s|%s|%s|%s|%s|%s" "$NNODES" "$NODE_RANK" "$MASTER_ADDR" "$MASTER_PORT"'
    ' "$GPUS_PER_NODE" "$COMPUTE_JOB_SEED" "$COMPUTE_JOB_SMOKE" "$COMPUTE_JOB_CHECKPOINT_DIR"'
    ' > "$COMPUTE_JOB_OUTPUT_DIR/seen.txt"'
)


def seen_variables(s3: S3Client) -> str:
    return read_object(s3, f"machines/{MACHINE_ID}/output/seen.txt").decode()


def test_ac11_exit_0_writes_a_succeeded_run_record_the_log_and_the_output(
    s3: S3Client, tmp_path: Path
) -> None:
    command = (
        'echo hello from the job; echo "42" > "$COMPUTE_JOB_OUTPUT_DIR/result.json"'
    )

    exit_code = run(s3, tmp_path, make_job(command, seed=7))

    record = run_record(s3)
    assert exit_code == 0
    assert (record["state"], record["exit_code"]) == ("succeeded", 0)
    assert (record["job_name"], record["kind"], record["machine_id"]) == (
        JOB_NAME,
        "single",
        MACHINE_ID,
    )
    assert (record["node_rank"], record["nodes"], record["seed"]) == (0, 1, 7)
    assert record["command"] == command
    assert isinstance(record["started_at"], str)
    assert isinstance(record["finished_at"], str)
    assert read_object(s3, f"machines/{MACHINE_ID}/log.txt") == b"hello from the job\n"
    assert read_object(s3, f"machines/{MACHINE_ID}/output/result.json") == b"42\n"
    assert f"index/{JOB_NAME}/{MACHINE_ID}" in object_keys(s3)


def test_ac11_a_nonzero_exit_is_a_failed_run_record_with_the_same_exit_code(
    s3: S3Client, tmp_path: Path
) -> None:
    exit_code = run(s3, tmp_path, make_job("echo about to fail; exit 3"))

    record = run_record(s3)
    assert exit_code == 3
    assert (record["state"], record["exit_code"]) == ("failed", 3)
    assert read_object(s3, f"machines/{MACHINE_ID}/log.txt") == b"about to fail\n"


def test_ac11_the_timeout_is_a_timed_out_run_record(
    s3: S3Client, tmp_path: Path
) -> None:
    exit_code = run(s3, tmp_path, make_job("timeout 1 sleep 30"))

    record = run_record(s3)
    assert exit_code == 124
    assert (record["state"], record["exit_code"]) == ("timed_out", 124)


def test_ac12_one_node_gets_the_distributed_variables_with_one_node_defaults(
    s3: S3Client, tmp_path: Path
) -> None:
    run(s3, tmp_path, make_job(SHOW_VARIABLES, kind="multi-node", seed=1234))

    assert seen_variables(s3) == "1|0|127.0.0.1|29500|0|1234|0|/mnt/checkpoints"


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

    assert seen_variables(s3) == "2|1|10.0.0.5|29500|8||0|/mnt/checkpoints"


@pytest.mark.parametrize(
    ("kind", "node_rank", "runs_command"),
    [
        ("multi-node", "0", True),
        ("multi-node", "1", True),
        ("search", "0", True),
        ("search", "1", False),
        ("single", "0", True),
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
    assert (f"machines/{MACHINE_ID}/output/seen.txt" in object_keys(s3)) is runs_command
    assert record["state"] == "succeeded"
    assert f"index/{JOB_NAME}/{MACHINE_ID}" in object_keys(s3)


def test_a_failed_upload_is_logged_and_does_not_change_the_exit_code(
    s3: S3Client, tmp_path: Path
) -> None:
    (tmp_path / "work").mkdir()
    archive = ArchiveWriter(s3, "a-bucket-that-does-not-exist", JOB_NAME, MACHINE_ID)

    exit_code = run_job(
        make_job("echo ok; exit 4"),
        archive,
        {"PATH": os.environ["PATH"]},
        tmp_path / "work",
    )

    log = (tmp_path / "work" / "log.txt").read_text()
    assert exit_code == 4
    assert "compute-jobs: could not write the run record" in log
    assert "NoSuchBucket" in log


def test_main_runs_the_job_as_the_machine_sts_names(s3: S3Client) -> None:
    arguments = [
        "--job-name", JOB_NAME, "--kind", "single", "--command", "exit 5", "--bucket", BUCKET,
        "--checkpoint-dir", "/c",
    ]  # fmt: skip

    assert main(arguments) == 5

    [record_key] = [key for key in object_keys(s3) if key.endswith("/run_record.json")]
    assert json.loads(read_object(s3, record_key))["state"] == "failed"
