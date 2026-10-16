"""The run record: what one machine writes about its part of a job.

The wrapper in ``compute_jobs.run`` writes it to
``machines/<machine id>/run_record.json`` in the archive, first with the state
``running`` and again when the command ends. Its JSON Schema is
``run-record.v1.schema.json`` in ``compute_jobs.schemas``.
"""

from dataclasses import asdict, dataclass
from typing import Literal

State = Literal["running", "succeeded", "failed", "timed_out"]
"""``running`` until the command ends; then ``succeeded`` (exit 0),
``timed_out`` (exit 124, which ``timeout`` returns when it stops the command),
or ``failed`` (anything else, including a failed preflight check)."""

TIMEOUT_EXIT_CODE = 124
"""The exit code of ``timeout`` when the time limit stopped its command."""

SCHEMA_VERSION = 1
"""The major version of the run record that this release writes."""


@dataclass(frozen=True)
class RunRecord:
    """One machine's account of a job, as written to ``run_record.json``.

    Attributes:
        job_name: The job's name, such as ``pr81-search-3f9a2c1d``.
        kind: The job kind: ``single``, ``multi-node``, or ``search``.
        machine_id: The machine's id in the archive (its role session's
            ``aws:userid``).
        node_rank: This machine's rank, 0 to ``nodes`` - 1.
        nodes: The number of machines in the job, >= 1.
        state: Where the command is; see ``State``.
        started_at: When the wrapper started, an RFC 3339 time in UTC.
        command: The job file's command.
        ran_command: False when this machine had nothing to run, which is
            true of every rank except 0 in a ``search`` job.
        seed: The job file's seed, or None if it has none.
        settings: The job file's ``settings``, or None if it has none.
        image_cuda_version: The CUDA version the image needs, or None when
            the wrapper wasn't told one.
        driver_cuda_version: The CUDA version the GPU driver supports, or
            None when the machine has no readable driver.
        exit_code: The command's exit code, or the wrapper's own when the
            command never ran; None while ``state`` is ``running``.
        finished_at: When the command ended, an RFC 3339 time in UTC, or None
            while ``state`` is ``running``.
        failure: Why the job failed before its command ran, or None.
    """

    job_name: str
    kind: str
    machine_id: str
    node_rank: int
    nodes: int
    state: State
    started_at: str
    command: str
    ran_command: bool = True
    seed: int | None = None
    settings: dict[str, object] | None = None
    image_cuda_version: str | None = None
    driver_cuda_version: str | None = None
    exit_code: int | None = None
    finished_at: str | None = None
    failure: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the record as a JSON-ready dict, with ``schema_version`` first.

        Fields that are None are left out, so a reader sees only what is known.

        Example:
            >>> record = RunRecord(
            ...     "pr1-a-0", "single", "m", 0, 1, "running", "2026-10-15T03:26:00Z", "true"
            ... )
            >>> record.to_dict()["schema_version"]
            1
            >>> "exit_code" in record.to_dict()
            False
        """
        fields = {
            name: value for name, value in asdict(self).items() if value is not None
        }
        return {"schema_version": SCHEMA_VERSION, **fields}


def final_state(exit_code: int) -> State:
    """Return the state a command's exit code means.

    Args:
        exit_code: The command's exit code.

    Example:
        >>> [final_state(code) for code in (0, 1, 124)]
        ['succeeded', 'failed', 'timed_out']
    """
    if exit_code == 0:
        return "succeeded"
    if exit_code == TIMEOUT_EXIT_CODE:
        return "timed_out"
    return "failed"
