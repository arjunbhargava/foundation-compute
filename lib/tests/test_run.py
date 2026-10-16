import json
import os
import stat
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from boto3.exceptions import S3UploadFailedError
from compute_jobs.archive import ArchiveWriter
from compute_jobs.run import Job, ProgressPublisher, main, run_job
from compute_jobs.schemas import load_schema
from mypy_boto3_s3 import S3Client
from s3_helpers import BUCKET, MACHINE_ID, object_keys, read_object

JOB_NAME = "pr81-search-3f9a2c1d"
SYSTEM_PATH = os.environ["PATH"]


def make_job(
    command: str,
    kind: str = "single",
    seed: int | None = None,
    image_cuda_version: str | None = None,
) -> Job:
    return Job(
        JOB_NAME,
        kind,
        command,
        "/mnt/checkpoints",
        seed,
        image_cuda_version,
    )


def run(
    s3: S3Client,
    tmp_path: Path,
    job: Job,
    environ: dict[str, str] | None = None,
) -> int:
    (tmp_path / "work").mkdir()
    archive = ArchiveWriter(s3, BUCKET, job.name, MACHINE_ID)
    return run_job(
        job, archive, {"PATH": SYSTEM_PATH, **(environ or {})}, tmp_path / "work"
    )


def fake_nvidia_smi(directory: Path, cuda_version: str) -> dict[str, str]:
    """Return an environment whose PATH has an ``nvidia-smi`` that reports a CUDA version."""
    directory.mkdir()
    program = directory / "nvidia-smi"
    program.write_text(
        f"#!/bin/sh\necho '| NVIDIA-SMI 550.54 | Driver Version: 550.54 | CUDA Version: {cuda_version} |'\n"
    )
    program.chmod(program.stat().st_mode | stat.S_IEXEC)
    return {"PATH": f"{directory}:{os.environ['PATH']}"}


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


def test_ac11_a_driver_with_an_older_cuda_than_the_image_fails_before_the_command(
    s3: S3Client, tmp_path: Path
) -> None:
    environ = fake_nvidia_smi(tmp_path / "bin", "12.4")
    job = make_job(
        'echo ran > "$COMPUTE_JOB_OUTPUT_DIR/ran.txt"', image_cuda_version="12.8"
    )

    exit_code = run(s3, tmp_path, job, environ)

    record = run_record(s3)
    assert exit_code == 1
    assert (record["state"], record["ran_command"]) == ("failed", False)
    assert "driver supports CUDA 12.4, image needs 12.8" in str(record["failure"])
    assert record["driver_cuda_version"] == "12.4"
    assert f"machines/{MACHINE_ID}/output/ran.txt" not in object_keys(s3)


@pytest.mark.parametrize("driver_cuda_version", ["12.8", "12.10", "13.0", None])
def test_a_driver_with_the_images_cuda_or_newer_or_no_driver_runs_the_command(
    s3: S3Client, tmp_path: Path, driver_cuda_version: str | None
) -> None:
    if driver_cuda_version is None:
        (tmp_path / "bin").mkdir()
        environ = {"PATH": str(tmp_path / "bin")}
    else:
        environ = fake_nvidia_smi(tmp_path / "bin", driver_cuda_version)

    exit_code = run(s3, tmp_path, make_job("true", image_cuda_version="12.8"), environ)

    assert exit_code == 0
    assert run_record(s3).get("driver_cuda_version") == driver_cuda_version


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

    exit_code = run_job(job, archive, {"PATH": SYSTEM_PATH}, tmp_path / "work")

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


def put_object_count(s3: S3Client) -> list[str]:
    """Return a list that gains the key of every ``PutObject`` call on ``s3``."""
    keys: list[str] = []

    def record_key(params: dict[str, Any], **_: object) -> None:
        keys.append(params["Key"])

    s3.meta.events.register("before-parameter-build.s3.PutObject", record_key)
    return keys


def test_ac9_progress_is_uploaded_at_most_every_30_seconds(
    s3: S3Client, tmp_path: Path
) -> None:
    progress_file = tmp_path / "progress.json"
    publisher = ProgressPublisher(
        progress_file,
        ArchiveWriter(s3, BUCKET, JOB_NAME, MACHINE_ID),
        lambda line: None,
    )
    puts = put_object_count(s3)
    progress_key = f"machines/{MACHINE_ID}/progress.json"

    def report(step: int) -> None:
        progress_file.write_text(
            json.dumps({"schema": 1, "step": step, "updated_at": "t"})
        )

    report(1)
    publisher.publish_if_due(1000.0)
    report(2)
    publisher.publish_if_due(1010.0)
    publisher.publish_if_due(1029.9)
    assert puts.count(progress_key) == 1
    assert json.loads(read_object(s3, progress_key))["step"] == 1

    publisher.publish_if_due(1030.0)
    assert puts.count(progress_key) == 2
    assert json.loads(read_object(s3, progress_key))["step"] == 2

    publisher.publish_if_due(1100.0)
    assert puts.count(progress_key) == 2


def test_ac9_a_failed_progress_upload_is_retried_and_made_again_at_the_end(
    s3: S3Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    progress_file = tmp_path / "progress.json"
    progress_file.write_text(json.dumps({"schema": 1, "step": 1, "updated_at": "t"}))
    writer = ArchiveWriter(s3, BUCKET, JOB_NAME, MACHINE_ID)
    lines: list[str] = []
    attempts: list[str] = []
    real_upload = ArchiveWriter.upload_file

    def flaky_upload(self: ArchiveWriter, path: Path, name: str) -> None:
        attempts.append(name)
        if len(attempts) == 1:
            raise S3UploadFailedError("the connection dropped")
        real_upload(self, path, name)

    monkeypatch.setattr(ArchiveWriter, "upload_file", flaky_upload)
    publisher = ProgressPublisher(progress_file, writer, lines.append)

    publisher.publish_if_due(1000.0)
    publisher.publish_if_due(1001.0, final=True)

    assert len(attempts) == 2
    assert "could not upload progress.json" in lines[0]
    assert (
        json.loads(read_object(s3, f"machines/{MACHINE_ID}/progress.json"))["step"] == 1
    )


def test_ac9_progress_is_logged_as_a_compute_progress_line_at_most_every_60_seconds(
    s3: S3Client, tmp_path: Path
) -> None:
    progress_file = tmp_path / "progress.json"
    lines: list[str] = []
    publisher = ProgressPublisher(
        progress_file, ArchiveWriter(s3, BUCKET, JOB_NAME, MACHINE_ID), lines.append
    )

    def report(step: int) -> None:
        progress_file.write_text(
            json.dumps({"schema": 1, "step": step, "updated_at": "t"})
        )

    report(1)
    publisher.publish_if_due(0.0)
    report(2)
    publisher.publish_if_due(30.0)
    publisher.publish_if_due(59.9)
    assert lines == ['COMPUTE_PROGRESS {"schema":1,"step":1,"updated_at":"t"}\n']

    publisher.publish_if_due(60.0)
    publisher.publish_if_due(120.0)
    assert lines[1:] == ['COMPUTE_PROGRESS {"schema":1,"step":2,"updated_at":"t"}\n']


def test_ac9_the_wrapper_uploads_the_progress_the_command_writes_beside_its_output(
    s3: S3Client, tmp_path: Path
) -> None:
    command = (
        'echo \'{"schema": 1, "schema_version": 1, "step": 3, "updated_at": "2026-10-15T03:26:00Z"}\''
        ' > "$COMPUTE_JOB_OUTPUT_DIR/progress.json"; echo "done" > "$COMPUTE_JOB_OUTPUT_DIR/result.json"'
    )

    run(s3, tmp_path, make_job(command))

    progress = json.loads(read_object(s3, f"machines/{MACHINE_ID}/progress.json"))
    jsonschema.validate(progress, load_schema("progress", 1))
    assert progress["step"] == 3
    keys = object_keys(s3)
    assert f"machines/{MACHINE_ID}/output/progress.json" not in keys
    assert f"machines/{MACHINE_ID}/output/result.json" in keys
    assert b'COMPUTE_PROGRESS {"schema":1,"schema_version":1,"step":3' in read_object(
        s3, f"machines/{MACHINE_ID}/log.txt"
    )


def test_ac9_progress_is_logged_while_the_command_is_still_running(
    s3: S3Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("compute_jobs.run.POLL_INTERVAL_S", 0.05)
    command = (
        'echo \'{"schema": 1, "updated_at": "t"}\' > "$COMPUTE_JOB_OUTPUT_DIR/progress.json";'
        " sleep 1; echo after the pause"
    )

    run(s3, tmp_path, make_job(command))

    log = read_object(s3, f"machines/{MACHINE_ID}/log.txt").decode()
    assert log.index("COMPUTE_PROGRESS") < log.index("after the pause")


def test_main_refuses_a_cuda_version_that_is_not_a_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = [
        "--job-name", JOB_NAME, "--kind", "single", "--command", "true", "--bucket", BUCKET,
        "--checkpoint-dir", "/c", "--image-cuda-version", "twelve",
    ]  # fmt: skip

    with pytest.raises(SystemExit) as raised:
        main(arguments)

    assert raised.value.code == 2
    assert "'twelve' is not a CUDA version such as 12.8" in capsys.readouterr().err
