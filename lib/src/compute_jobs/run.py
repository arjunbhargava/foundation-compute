"""The in-job wrapper: ``python -m compute_jobs.run``, which runs on every machine of a job.

The wrapper exports the distributed variables, runs the job's command, and
writes the machine's part of the job archive: run record, output, and log. It
never calls the SkyPilot server. See ``docs/compute-jobs.md``, "How a job
runs".

Variables the command sees, besides the caller's own:

``NNODES``, ``NODE_RANK``, ``MASTER_ADDR``, ``MASTER_PORT``, ``GPUS_PER_NODE``
    The distributed variables, from SkyPilot's own (``SKYPILOT_NUM_NODES``,
    ``SKYPILOT_NODE_RANK``, the first line of ``SKYPILOT_NODE_IPS``, and
    ``SKYPILOT_NUM_GPUS_PER_NODE``), with defaults for one node.
``COMPUTE_JOB_OUTPUT_DIR``
    A directory whose files are uploaded to ``machines/<machine id>/output/``.
``COMPUTE_JOB_CHECKPOINT_DIR``
    The directory the server mounts on ``checkpoints/<job name>/``.
``COMPUTE_JOB_SEED``
    The job file's seed; unset when the job has none.
``COMPUTE_JOB_SMOKE``
    ``0``, unless the caller set it, as a dry run does.

The command's exit code is the wrapper's, so SkyPilot sees the job fail. A
command stopped by ``timeout`` exits 124 and is recorded as ``timed_out``.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Self, TextIO

from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError

from compute_jobs.archive import ArchiveWriter
from compute_jobs.run_record import RunRecord, final_state

MASTER_PORT = "29500"
"""``MASTER_PORT``, fixed, as the page says."""

JOB_KINDS = ("single", "multi-node", "search")

ARCHIVE_FAILURE_EXIT_CODE = 1
"""The wrapper's exit code when the archive can't be opened and the command
never ran."""


@dataclass(frozen=True)
class Job:
    """What the wrapper needs to know about its job, from its command line.

    Attributes:
        name: The job's name, such as ``pr81-search-3f9a2c1d``.
        kind: One of ``JOB_KINDS``.
        command: The job file's command, run by bash.
        checkpoint_dir: The path of the mounted checkpoint directory.
        seed: The job file's seed, or None.
    """

    name: str
    kind: str
    command: str
    checkpoint_dir: str
    seed: int | None = None


def main(argv: Sequence[str] | None = None) -> int:
    """Run a job's command on this machine and archive the results.

    Args:
        argv: The command line without the program name; defaults to
            ``sys.argv[1:]``. Run it with ``--help`` for the options.

    Returns:
        The command's exit code; 1 if the archive can't be opened; and 0 on
        every rank but 0 of a ``search`` job, which has no command to run.
    """
    arguments = _build_parser().parse_args(argv)
    job = Job(
        name=arguments.job_name,
        kind=arguments.kind,
        command=arguments.command,
        checkpoint_dir=arguments.checkpoint_dir,
        seed=arguments.seed,
    )

    try:
        archive = ArchiveWriter.connect(arguments.bucket, job.name)
    except (BotoCoreError, ClientError) as error:
        print(
            f"compute-jobs: cannot open the archive bucket {arguments.bucket}: {error}. "
            "Check the machine's role and the bucket name; the command was not run.",
            file=sys.stderr,
        )
        return ARCHIVE_FAILURE_EXIT_CODE

    with tempfile.TemporaryDirectory(prefix="compute-job-") as working_dir:
        return run_job(job, archive, dict(os.environ), Path(working_dir))


def run_job(
    job: Job, archive: ArchiveWriter, environ: Mapping[str, str], working_dir: Path
) -> int:
    """Run the job's command on this machine, and write its part of the archive.

    A failed upload is written to the log and does not change the exit code.
    The final run record is written last, so a record with a final state means
    the log and output were uploaded before it.

    Args:
        job: The job.
        archive: Where this machine's objects go.
        environ: The environment the command inherits, such as SkyPilot's
            variables and ``PATH``.
        working_dir: An existing empty directory for the log and the output
            directory.

    Returns:
        The exit code described in ``main``.
    """
    with _JobLog(working_dir / "log.txt", sys.stdout) as log:
        return _run_and_archive(job, archive, environ, working_dir, log)


def distributed_environment(environ: Mapping[str, str]) -> dict[str, str]:
    r"""Return the distributed variables for this machine, from SkyPilot's.

    Args:
        environ: The environment, possibly with ``SKYPILOT_NUM_NODES``,
            ``SKYPILOT_NODE_RANK``, ``SKYPILOT_NODE_IPS`` (one address per
            line, rank 0's first), and ``SKYPILOT_NUM_GPUS_PER_NODE``.

    Returns:
        ``NNODES``, ``NODE_RANK``, ``MASTER_ADDR``, ``MASTER_PORT``, and
        ``GPUS_PER_NODE``, as strings. Without SkyPilot's variables the machine
        is the only node: 1 node, rank 0, master address 127.0.0.1, 0 GPUs.

    Example:
        >>> variables = distributed_environment(
        ...     {"SKYPILOT_NUM_NODES": "2", "SKYPILOT_NODE_RANK": "1",
        ...      "SKYPILOT_NODE_IPS": "10.0.0.5\n10.0.0.6", "SKYPILOT_NUM_GPUS_PER_NODE": "8"}
        ... )
        >>> variables["MASTER_ADDR"], variables["NODE_RANK"], variables["MASTER_PORT"]
        ('10.0.0.5', '1', '29500')
    """
    node_addresses = environ.get("SKYPILOT_NODE_IPS", "").split()
    return {
        "NNODES": environ.get("SKYPILOT_NUM_NODES", "1"),
        "NODE_RANK": environ.get("SKYPILOT_NODE_RANK", "0"),
        "MASTER_ADDR": node_addresses[0] if node_addresses else "127.0.0.1",
        "MASTER_PORT": MASTER_PORT,
        "GPUS_PER_NODE": environ.get("SKYPILOT_NUM_GPUS_PER_NODE", "0"),
    }


def _run_and_archive(
    job: Job,
    archive: ArchiveWriter,
    environ: Mapping[str, str],
    working_dir: Path,
    log: "_JobLog",
) -> int:
    distributed = distributed_environment(environ)
    node_rank = int(distributed["NODE_RANK"])
    output_dir = working_dir / "output"
    output_dir.mkdir()

    record = RunRecord(
        job_name=job.name,
        kind=job.kind,
        machine_id=archive.machine_id,
        node_rank=node_rank,
        nodes=int(distributed["NNODES"]),
        state="running",
        started_at=_now(),
        command=job.command,
        seed=job.seed,
    )
    _best_effort("write the marker", archive.write_marker, log.write)
    _best_effort(
        "write the run record",
        lambda: archive.write_run_record(record.to_dict()),
        log.write,
    )

    if job.kind == "search" and node_rank != 0:
        exit_code = 0
        record = replace(record, ran_command=False)
    else:
        command_environment = _command_environment(
            job, environ, distributed, output_dir
        )
        exit_code = _run_command(job.command, command_environment, log)

    _best_effort(
        "upload log.txt",
        lambda: archive.upload_file(working_dir / "log.txt", "log.txt"),
        log.write,
    )
    _best_effort(
        "upload the output",
        lambda: archive.upload_output_directory(output_dir),
        log.write,
    )
    record = replace(
        record, state=final_state(exit_code), exit_code=exit_code, finished_at=_now()
    )
    _best_effort(
        "write the run record",
        lambda: archive.write_run_record(record.to_dict()),
        log.write,
    )
    return exit_code


def _command_environment(
    job: Job,
    environ: Mapping[str, str],
    distributed: Mapping[str, str],
    output_dir: Path,
) -> dict[str, str]:
    command_environment = {
        **environ,
        **distributed,
        "COMPUTE_JOB_OUTPUT_DIR": str(output_dir),
        "COMPUTE_JOB_CHECKPOINT_DIR": job.checkpoint_dir,
        "COMPUTE_JOB_SMOKE": environ.get("COMPUTE_JOB_SMOKE", "0"),
    }
    if job.seed is not None:
        command_environment["COMPUTE_JOB_SEED"] = str(job.seed)
    return command_environment


def _run_command(command: str, environ: Mapping[str, str], log: "_JobLog") -> int:
    """Run the command with bash, copy its output to the log, and return its exit code.

    A command killed by signal ``n`` returns ``128 + n``, as a shell does.
    """
    with subprocess.Popen(
        command,
        shell=True,
        executable="/bin/bash",
        env=dict(environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
        return_code = process.wait()
    return 128 - return_code if return_code < 0 else return_code


class _JobLog:
    """The job's log: a file that the wrapper uploads, copied to a stream."""

    def __init__(self, path: Path, echo: TextIO) -> None:
        self._file = path.open("w", encoding="utf-8")
        self._echo = echo
        self._lock = threading.Lock()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exception_details: object) -> None:
        self._file.close()

    def write(self, text: str) -> None:
        with self._lock:
            self._file.write(text)
            self._file.flush()
            self._echo.write(text)
            self._echo.flush()


def _best_effort(
    description: str,
    action: Callable[[], object],
    write_log: Callable[[str], object],
) -> None:
    try:
        action()
    except (BotoCoreError, ClientError, S3UploadFailedError, OSError) as error:
        write_log(f"compute-jobs: could not {description}: {error}\n")


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m compute_jobs.run",
        description="Run a job's command on this machine.",
    )
    parser.add_argument("--job-name", required=True, help="the job's name")
    parser.add_argument("--kind", required=True, choices=JOB_KINDS)
    parser.add_argument(
        "--command", required=True, help="the job file's command, run by bash"
    )
    parser.add_argument("--bucket", required=True, help="the archive bucket")
    parser.add_argument(
        "--checkpoint-dir", required=True, help="the mounted checkpoint directory"
    )
    parser.add_argument("--seed", type=int, help="the job file's seed")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
