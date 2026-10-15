"""The job file, a YAML file describing one job: reading it, and naming its job.

``job-file.v1.schema.json`` defines its fields. Whether its profile exists
and allows its nodes and spot choice is ``limits.yaml``'s to say, which
``compute_jobs_admin_policy.placement`` checks.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from jsonschema import ValidationError, validate

from compute_jobs.schemas import CURRENT_MAJOR, load_schema, version_refusal

JobKind = Literal["single", "multi-node", "search"]
"""What a job runs, as in "Job kinds" in ``docs/compute-jobs.md``."""

JOB_NAME_HASH_HEX_DIGITS = 8
"""Hex digits of the job file's SHA-256 in its job name, per contract v0."""


@dataclass(frozen=True)
class JobFile:
    """A valid job file, with each optional field at its default if absent.

    Attributes:
        kind: The job kind.
        profile: The name of a profile in ``limits.yaml``.
        command: The shell command the job runs.
        max_runtime_minutes: The run time after which the job is stopped,
            >= 1.
        budget_usd: The most the job may cost in USD, > 0.
        nodes: Nodes to run on, >= 1; always 1 for a ``single`` job.
        use_spot: Whether to run on spot machines.
        image: The job image; only ``default`` until project images exist.
        uv_extras: The project's extras that the job's ``uv sync`` installs.
        smoke: Whether ``dry-run`` runs the command locally as a smoke test.
        seed: Recorded, and passed to the job as ``COMPUTE_JOB_SEED``.
        settings: Free-form; recorded, and passed to the job as JSON.
        schema_version: The file's major version; 1 when it has none.
    """

    kind: JobKind
    profile: str
    command: str
    max_runtime_minutes: int
    budget_usd: float
    nodes: int = 1
    use_spot: bool = False
    image: str = "default"
    uv_extras: list[str] = field(default_factory=list[str])
    smoke: bool = True
    seed: int | None = None
    settings: dict[str, Any] = field(default_factory=dict[str, Any])
    schema_version: int = 1


@dataclass(frozen=True)
class JobFileRefusal:
    """Why a job file can't be used.

    Attributes:
        failure_kind: ``invalid_job_file`` for a file that isn't a valid job
            file, or ``refused_job_file`` for a valid one at a
            ``schema_version`` this release doesn't read; the client prints
            it as stderr's ``kind=`` line.
        message: One line naming the file, what is wrong, and the fix.
    """

    failure_kind: Literal["invalid_job_file", "refused_job_file"]
    message: str


def read_job_file(path: Path, reader: str) -> JobFile | JobFileRefusal:
    """Read a job file and validate it against its major version's schema.

    Args:
        path: The job file.
        reader: The command reading it, such as ``dry-run``, which a version
            refusal names.

    Returns:
        The job file, or a refusal. The refusal is ``invalid_job_file`` when
        the file isn't YAML, isn't a mapping, or doesn't match the schema (a
        missing, unknown, or mistyped field, an unknown kind, or ``nodes`` on
        a ``single`` job), and ``refused_job_file`` when its integer
        ``schema_version`` isn't one this release reads.

    Raises:
        OSError: The file can't be read.

    Example:
        >>> import tempfile
        >>> job_path = Path(tempfile.mkdtemp()) / "simulate.yaml"
        >>> _ = job_path.write_text(
        ...     "{kind: single, profile: cpu, command: python simulate.py,"
        ...     " max_runtime_minutes: 15, budget_usd: 1}"
        ... )
        >>> read_job_file(job_path, "dry-run").nodes
        1
    """
    try:
        document: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        return JobFileRefusal("invalid_job_file", f"{path} isn't valid YAML: {error}")
    if not isinstance(document, dict):
        return JobFileRefusal(
            "invalid_job_file",
            f"{path} must be a mapping of job file fields, such as kind: single",
        )
    fields = cast(dict[str, Any], document)

    # A schema_version that isn't an integer is a mistyped field, which the
    # schema reports, rather than a version this release doesn't read.
    major = fields.get("schema_version", 1)
    if not isinstance(major, int) or isinstance(major, bool):
        major = CURRENT_MAJOR["job-file"]
    else:
        refusal = version_refusal("job-file", fields, reader)
        if refusal is not None:
            return JobFileRefusal("refused_job_file", f"{path}: {refusal}")

    try:
        validate(fields, load_schema("job-file", major))
    except ValidationError as error:
        return JobFileRefusal(
            "invalid_job_file", f"{path} isn't a valid job file: {_reason(error)}"
        )
    return JobFile(**fields)


def job_name(pr_number: int, path: Path) -> str:
    """Return the job's name: ``pr<PR number>-<file name>-<8 hex digits>``.

    The file name is the job file's without its suffix, and the hex digits
    are the first 8 of the file's SHA-256, so editing the file names a new
    job.

    Args:
        pr_number: The number of the pull request the job runs for, >= 1.
        path: The job file.

    Raises:
        OSError: The file can't be read.

    Example:
        >>> import tempfile
        >>> job_path = Path(tempfile.mkdtemp()) / "search.yaml"
        >>> _ = job_path.write_bytes(b"")
        >>> job_name(81, job_path)
        'pr81-search-e3b0c442'
    """
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"pr{pr_number}-{path.stem}-{digest[:JOB_NAME_HASH_HEX_DIGITS]}"


def _reason(error: ValidationError) -> str:
    """Return the schema error as one clause saying where in the file it is."""
    if error.validator == "not":
        return "nodes is set, but a single job runs on one node; remove nodes, or use kind: multi-node"
    location = "the file" if not error.path else error.json_path.removeprefix("$.")
    return f"in {location}, {error.message}"
