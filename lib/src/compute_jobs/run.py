"""The in-job wrapper: ``python -m compute_jobs.run``, which runs on every machine of a job.

The wrapper checks the GPU driver, exports the distributed variables, runs the
job's command, and writes the machine's part of the job archive: run record,
progress, output, and log. It never calls the SkyPilot server. See ``docs/compute-jobs.md``, "How a job
runs".

Variables the command sees, besides the caller's own:

``NNODES``, ``NODE_RANK``, ``MASTER_ADDR``, ``MASTER_PORT``, ``GPUS_PER_NODE``
    The distributed variables, from SkyPilot's own (``SKYPILOT_NUM_NODES``,
    ``SKYPILOT_NODE_RANK``, the first line of ``SKYPILOT_NODE_IPS``, and
    ``SKYPILOT_NUM_GPUS_PER_NODE``), with defaults for one node.
``COMPUTE_JOB_OUTPUT_DIR``
    A directory whose files are uploaded to ``machines/<machine id>/output/``.
    ``progress.json`` in it is uploaded as the machine's progress, at most
    every 30 s and at the end, and printed to the log as a line starting
    ``COMPUTE_PROGRESS`` at most every 60 s.
``COMPUTE_JOB_CHECKPOINT_DIR``
    The directory the server mounts on ``checkpoints/<job name>/``.
``COMPUTE_JOB_SEED``
    The job file's seed; unset when the job has none.
``COMPUTE_JOB_SETTINGS``
    The job file's ``settings`` as JSON; unset when the job has none. The
    page names no variable for it, so this name is proposed.
``COMPUTE_JOB_SMOKE``
    ``0``, unless the caller set it, as a dry run does.

On a ``search`` job, rank 0 starts a Ray head on ``RAY_PORT`` before the
command and stops it after. Every other rank joins that cluster, runs no
command, and exits 0 when the head's port closes. ``ray`` must be on ``PATH``.
The wrapper ends only the Rays it started, never with ``ray stop``, because
that would also end the Ray that SkyPilot runs the job with.

The command's exit code is the wrapper's, so SkyPilot sees the job fail. A
command stopped by ``timeout`` exits 124 and is recorded as ``timed_out``.
"""

import argparse
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Self, TextIO

from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError

from compute_jobs.archive import PROGRESS_FILE_NAME, ArchiveWriter
from compute_jobs.run_record import RunRecord, final_state

PROGRESS_UPLOAD_INTERVAL_S = 30.0
"""The least time between two uploads of ``progress.json`` or of the log, from
the page's "Progress" section."""

PROGRESS_LOG_INTERVAL_S = 60.0
"""The least time between two ``COMPUTE_PROGRESS`` lines in the log."""

POLL_INTERVAL_S = 5.0
"""How often the wrapper checks whether an upload or a log line is due."""

MASTER_PORT = "29500"
"""``MASTER_PORT``, fixed, as the page says."""

RAY_PORT = 6379
"""The port of the user Ray cluster on a ``search`` job. SkyPilot's own Ray uses
6380, as the page's "How a search fans out" says."""

RAY_HEAD_WAIT_S = 600.0
"""How long a worker waits for rank 0's Ray before it fails the job."""

RAY_STOP_GRACE_S = 10.0
"""How long ``_stop_ray`` waits after SIGTERM before it sends SIGKILL."""

RAY_POLL_INTERVAL_S = 5.0
"""How often a worker checks whether rank 0's Ray is up, and then whether it is
still up."""

JOB_KINDS = ("single", "multi-node", "search")

FAILURE_BEFORE_COMMAND_EXIT_CODE = 1
"""The wrapper's exit code when the archive can't be written or the driver's
CUDA is too old, so the command never ran."""

_DRIVER_CUDA_PATTERN = re.compile(r"CUDA Version:\s*(\d+(?:\.\d+)*)")


@dataclass(frozen=True)
class Job:
    """What the wrapper needs to know about its job, from its command line.

    Attributes:
        name: The job's name, such as ``pr81-search-3f9a2c1d``.
        kind: One of ``JOB_KINDS``.
        command: The job file's command, run by bash.
        checkpoint_dir: The path of the mounted checkpoint directory.
        seed: The job file's seed, or None.
        settings_json: The job file's ``settings`` as a JSON object, or None.
        image_cuda_version: The CUDA version the image needs, such as
            ``12.8``, or None to skip the driver check.
    """

    name: str
    kind: str
    command: str
    checkpoint_dir: str
    seed: int | None = None
    settings_json: str | None = None
    image_cuda_version: str | None = None


def main(argv: Sequence[str] | None = None) -> int:
    """Run a job's command on this machine and archive the results.

    Args:
        argv: The command line without the program name; defaults to
            ``sys.argv[1:]``. Run it with ``--help`` for the options.

    Returns:
        The command's exit code; 1 if the archive can't be opened or written, or the
        driver's CUDA is older than the image's; and, on a ``search`` job's ranks
        other than 0, 0 once rank 0's Ray has stopped.
    """
    arguments = _build_parser().parse_args(argv)
    job = Job(
        name=arguments.job_name,
        kind=arguments.kind,
        command=arguments.command,
        checkpoint_dir=arguments.checkpoint_dir,
        seed=arguments.seed,
        settings_json=arguments.settings_json,
        image_cuda_version=arguments.image_cuda_version,
    )

    try:
        archive = ArchiveWriter.connect(arguments.bucket, job.name)
    except (BotoCoreError, ClientError) as error:
        print(
            f"compute-jobs: cannot open the archive bucket {arguments.bucket}: {error}. "
            "Check the machine's role and the bucket name; the command was not run.",
            file=sys.stderr,
        )
        return FAILURE_BEFORE_COMMAND_EXIT_CODE

    with tempfile.TemporaryDirectory(prefix="compute-job-") as working_dir:
        return run_job(job, archive, dict(os.environ), Path(working_dir))


def run_job(
    job: Job, archive: ArchiveWriter, environ: Mapping[str, str], working_dir: Path
) -> int:
    """Run the job's command on this machine, and write its part of the archive.

    The command runs only if the marker can be written, so a job whose archive
    is unreachable fails at once, not after hours of work nobody can read. After
    that, a failed upload is written to the log and does not change the exit
    code. The final run record is written last, so a record with a final state
    means the output and log were uploaded before it, and the uploaded log
    mentions a failed output upload.

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

    progress = ProgressPublisher(output_dir / PROGRESS_FILE_NAME, archive, log.write)
    log_upload = _ChangedFileUploader(
        working_dir / "log.txt", "log.txt", archive, log.write, _size_of
    )
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
        settings=None if job.settings_json is None else json.loads(job.settings_json),
        image_cuda_version=job.image_cuda_version,
    )
    try:
        archive.write_marker()
    except (BotoCoreError, ClientError) as error:
        log.write(
            f"compute-jobs: cannot write to the archive: {error}. "
            "Check the machine's role and the bucket name; the command was not run.\n"
        )
        return FAILURE_BEFORE_COMMAND_EXIT_CODE
    _best_effort(
        "write the run record",
        lambda: archive.write_run_record(record.to_dict()),
        log.write,
    )

    driver_version, failure = _check_driver(job.image_cuda_version, environ)
    record = replace(record, driver_cuda_version=driver_version)
    if failure is not None:
        log.write(f"compute-jobs: {failure}\n")
        exit_code = FAILURE_BEFORE_COMMAND_EXIT_CODE
        record = replace(record, ran_command=False, failure=failure)
    else:
        command_environment = _command_environment(
            job, environ, distributed, output_dir
        )
        run_on_this_machine = _runner(job, node_rank, command_environment, log)
        if job.kind == "search" and node_rank != 0:
            record = replace(record, ran_command=False)
        stop_publishing = threading.Event()
        publisher = threading.Thread(
            target=_publish_periodically,
            args=(stop_publishing, [progress.publish_if_due, log_upload.upload_if_due]),
            daemon=True,
        )
        publisher.start()
        try:
            exit_code = run_on_this_machine()
        finally:
            stop_publishing.set()
            publisher.join()

    progress.publish_if_due(time.monotonic(), final=True)
    _best_effort(
        "upload the output",
        lambda: archive.upload_output_directory(output_dir),
        log.write,
    )
    log_upload.upload_if_due(time.monotonic(), final=True)
    record = replace(
        record, state=final_state(exit_code), exit_code=exit_code, finished_at=_now()
    )
    _best_effort(
        "write the run record",
        lambda: archive.write_run_record(record.to_dict()),
        log.write,
    )
    return exit_code


def _runner(
    job: Job, node_rank: int, environ: Mapping[str, str], log: "_JobLog"
) -> Callable[[], int]:
    """Return what this machine does: run the command, host Ray, or serve it."""
    if job.kind != "search":
        return lambda: _run_command(job.command, environ, log)
    if node_rank == 0:
        return lambda: _run_command_on_ray_head(job.command, environ, log)
    return lambda: _hold_as_ray_worker(environ, log)


def _run_command_on_ray_head(
    command: str, environ: Mapping[str, str], log: "_JobLog"
) -> int:
    """Start Ray's head, run the command, and stop Ray, returning the exit code."""
    address = (environ["MASTER_ADDR"], RAY_PORT)
    head = _start_ray(
        f"--head --port={RAY_PORT} --include-dashboard=false --disable-usage-stats "
        f"--node-ip-address={shlex.quote(address[0])}",
        environ,
        log,
    )
    try:
        if not _wait_for_ray_head(address, head, log):
            return head.poll() or FAILURE_BEFORE_COMMAND_EXIT_CODE
        return _run_command(command, environ, log)
    finally:
        _stop_ray(head)


def _hold_as_ray_worker(environ: Mapping[str, str], log: "_JobLog") -> int:
    """Join the head's Ray cluster and stay until the head's port closes.

    Returns 0 once rank 0's Ray is gone, and otherwise the exit code of the
    ``ray`` that stopped while the head was still up, or 1 if the head never
    came up.
    """
    address = (environ["MASTER_ADDR"], RAY_PORT)
    if not _wait_for_ray_head(address, None, log):
        return FAILURE_BEFORE_COMMAND_EXIT_CODE

    worker = _start_ray(
        f"--address={shlex.quote(address[0])}:{address[1]} --disable-usage-stats",
        environ,
        log,
    )
    try:
        while worker.poll() is None and _accepts_connections(address):
            time.sleep(RAY_POLL_INTERVAL_S)
        if _accepts_connections(address):
            return worker.poll() or FAILURE_BEFORE_COMMAND_EXIT_CODE
        return 0
    finally:
        _stop_ray(worker)


def _start_ray(
    arguments: str, environ: Mapping[str, str], log: "_JobLog"
) -> "subprocess.Popen[str]":
    """Run ``ray start <arguments> --block`` in a process group of its own.

    Ray's output goes to the log. The group lets ``_stop_ray`` end this Ray
    without ``ray stop``, which ends every Ray on the machine, including the
    one SkyPilot runs the job with.
    """
    process = subprocess.Popen(
        f"exec ray start {arguments} --block",
        shell=True,
        executable="/bin/bash",
        env=dict(environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    threading.Thread(target=_copy_to_log, args=(process, log), daemon=True).start()
    return process


def _copy_to_log(process: "subprocess.Popen[str]", log: "_JobLog") -> None:
    assert process.stdout is not None
    with process.stdout:
        for line in process.stdout:
            log.write(line)


def _stop_ray(process: "subprocess.Popen[str]") -> None:
    """End a Ray from ``_start_ray`` and its children, with SIGKILL after a grace period."""
    for signal_number in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, signal_number)
            process.wait(timeout=RAY_STOP_GRACE_S)
            return
        except ProcessLookupError:
            process.wait()
            return
        except subprocess.TimeoutExpired:
            continue


def _wait_for_ray_head(
    address: tuple[str, int],
    own_process: "subprocess.Popen[str] | None",
    log: "_JobLog",
) -> bool:
    """Wait until the head's port accepts connections, or ``own_process`` exits."""
    deadline_s = time.monotonic() + RAY_HEAD_WAIT_S
    while not _accepts_connections(address):
        if own_process is not None and own_process.poll() is not None:
            return False
        if time.monotonic() > deadline_s:
            log.write(
                f"compute-jobs: Ray's head at {address[0]}:{address[1]} did not come "
                f"up within {RAY_HEAD_WAIT_S:.0f} s; check rank 0's log.\n"
            )
            return False
        time.sleep(RAY_POLL_INTERVAL_S)
    return True


def _accepts_connections(address: tuple[str, int]) -> bool:
    try:
        socket.create_connection(address, timeout=2).close()
    except OSError:
        return False
    return True


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
    if job.settings_json is not None:
        command_environment["COMPUTE_JOB_SETTINGS"] = job.settings_json
    return command_environment


def _check_driver(
    image_cuda_version: str | None, environ: Mapping[str, str]
) -> tuple[str | None, str | None]:
    """Return the driver's CUDA version, and why it is too old, if it is.

    A machine without ``nvidia-smi``, or with output that has no CUDA
    version, passes: a CPU profile has no driver, and an unreadable one is
    not proof that the job would fail.
    """
    try:
        smi = subprocess.run(
            ["nvidia-smi"],
            env=dict(environ),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None, None
    match = _DRIVER_CUDA_PATTERN.search(smi.stdout)
    if match is None:
        return None, None

    driver_version = match.group(1)
    if image_cuda_version is not None and _as_tuple(driver_version) < _as_tuple(
        image_cuda_version
    ):
        return driver_version, (
            f"driver supports CUDA {driver_version}, image needs {image_cuda_version}; "
            "ask the owner for a machine image with a newer driver"
        )
    return driver_version, None


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


class _ChangedFileUploader:
    """Uploads a file when its fingerprint changed, at most every ``PROGRESS_UPLOAD_INTERVAL_S``."""

    def __init__(
        self,
        path: Path,
        name: str,
        archive: ArchiveWriter,
        write_log: Callable[[str], object],
        fingerprint: Callable[[Path], object],
    ) -> None:
        self._path = path
        self._name = name
        self._archive = archive
        self._write_log = write_log
        self._fingerprint = fingerprint
        self._last_upload_s: float | None = None
        self._uploaded_fingerprint: object = None

    def upload_if_due(self, now_s: float, final: bool = False) -> bool:
        """Upload if the file changed since the last upload and the interval has passed.

        ``final`` ignores the interval. A failed upload is retried on the next call.
        Returns whether it uploaded.
        """
        if not self._path.exists():
            return False
        fingerprint = self._fingerprint(self._path)
        interval_passed = (
            self._last_upload_s is None
            or now_s - self._last_upload_s >= PROGRESS_UPLOAD_INTERVAL_S
        )
        if fingerprint == self._uploaded_fingerprint or not (final or interval_passed):
            return False

        self._last_upload_s = now_s
        uploaded = _best_effort(
            f"upload {self._name}",
            lambda: self._archive.upload_file(self._path, self._name),
            self._write_log,
        )
        if uploaded:
            self._uploaded_fingerprint = fingerprint
        return uploaded


class ProgressPublisher:
    """Uploads ``progress.json`` every 30 s and prints it as a ``COMPUTE_PROGRESS`` line every 60 s.

    ``path`` is where ``progress.json`` is written, which may not exist yet;
    ``write_log`` receives each line, newline included, and each upload failure.
    """

    def __init__(
        self, path: Path, archive: ArchiveWriter, write_log: Callable[[str], object]
    ) -> None:
        self._path = path
        self._write_log = write_log
        self._uploader = _ChangedFileUploader(
            path, PROGRESS_FILE_NAME, archive, write_log, _content_of
        )
        self._last_line_s: float | None = None
        self._last_line_content: str | None = None

    def publish_if_due(self, now_s: float, final: bool = False) -> None:
        """Upload and log the progress, each if it changed and its interval has passed.

        Args:
            now_s: The current time in seconds on any clock that doesn't go
                backwards, such as ``time.monotonic``.
            final: True at the end of the job, which ignores both intervals.

        A failed upload is written to the log, not raised. The file must be
        replaced atomically by its writer, since a half-written file would be
        uploaded as it is.
        """
        self._uploader.upload_if_due(now_s, final)
        if not self._path.exists():
            return
        line_due = (
            self._last_line_s is None
            or now_s - self._last_line_s >= PROGRESS_LOG_INTERVAL_S
        )
        try:
            content = json.dumps(
                json.loads(self._path.read_text()), separators=(",", ":")
            )
        except (OSError, ValueError):
            return
        if content != self._last_line_content and (final or line_due):
            self._last_line_s = now_s
            self._last_line_content = content
            self._write_log(f"COMPUTE_PROGRESS {content}\n")


def _publish_periodically(
    stop: threading.Event, publishers: Sequence[Callable[[float], object]]
) -> None:
    while not stop.wait(POLL_INTERVAL_S):
        for publish in publishers:
            publish(time.monotonic())


def _best_effort(
    description: str,
    action: Callable[[], object],
    write_log: Callable[[str], object],
) -> bool:
    try:
        action()
    except (BotoCoreError, ClientError, S3UploadFailedError, OSError) as error:
        write_log(f"compute-jobs: could not {description}: {error}\n")
        return False
    return True


def _content_of(path: Path) -> bytes:
    """Fingerprint a file that can be rewritten with the same size, like ``progress.json``."""
    return path.read_bytes()


def _size_of(path: Path) -> int:
    """Fingerprint a file that is only appended to, like the log."""
    return path.stat().st_size


def _as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _cuda_version(text: str) -> str:
    if not re.fullmatch(r"\d+(\.\d+)*", text):
        raise argparse.ArgumentTypeError(f"{text!r} is not a CUDA version such as 12.8")
    return text


def _json_object(text: str) -> str:
    try:
        parsed = json.loads(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{text!r} is not JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError(f"{text!r} is not a JSON object")
    return text


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
    parser.add_argument(
        "--settings-json",
        type=_json_object,
        help="the job file's settings, as a JSON object",
    )
    parser.add_argument(
        "--image-cuda-version",
        type=_cuda_version,
        help="the CUDA version the image needs, such as 12.8; omit to skip the driver check",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
