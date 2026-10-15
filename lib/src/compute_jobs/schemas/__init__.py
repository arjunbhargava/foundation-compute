"""JSON Schemas for compute-jobs' file formats, and the version check every reader runs.

Each format has one schema file per major version in this package, named
``<format>.v<major>.schema.json``. Under the versioning policy in
``docs/compute-jobs.md``, an added optional field keeps the major, and any
breaking change increments it. A reader accepts the current and the previous
major, and refuses any other, naming the major it saw.
"""

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Literal

FormatName = Literal["job-file", "progress", "run-record", "archive", "observe"]
"""A format with a schema, which is the job file, ``progress.json``,
``run_record.json``, ``archive.json``, or ``observe --json``'s object."""

CURRENT_MAJOR: dict[FormatName, int] = {
    "job-file": 1,
    "progress": 1,
    "run-record": 1,
    "archive": 1,
    "observe": 1,
}
"""The major version of each format that this release writes."""

_DOCUMENT_NAME: dict[FormatName, str] = {
    "job-file": "the job file",
    "progress": "progress.json",
    "run-record": "run_record.json",
    "archive": "archive.json",
    "observe": "observe --json's output",
}


def load_schema(format_name: FormatName, major: int) -> dict[str, object]:
    """Return the JSON Schema of one major version of a format, as parsed JSON.

    Args:
        format_name: The format.
        major: The major version, >= 1.

    Raises:
        FileNotFoundError: This release has no schema for that major.

    Example:
        >>> load_schema("archive", 1)["required"]
        ['schema_version']
    """
    schema_file = files(__package__).joinpath(f"{format_name}.v{major}.schema.json")
    return json.loads(schema_file.read_text(encoding="utf-8"))


def version_refusal(
    format_name: FormatName,
    document: Mapping[str, object],
    reader: str,
    current_major: int | None = None,
) -> str | None:
    """Check a document's major version, and return why it is refused, if it is.

    The major is ``schema_version``. A job file without it is major 1, and a
    ``progress.json`` without it falls back to v0's ``schema`` field.

    Args:
        format_name: The document's format.
        document: The parsed document, before any other check.
        reader: The command or component reading it, such as ``observe``,
            which the refusal names.
        current_major: The major the reader writes, >= 1; defaults to
            ``CURRENT_MAJOR[format_name]``. The reader accepts it and the one
            before it.

    Returns:
        None if the reader accepts the document's major. Otherwise one line
        saying what the document has, which majors the reader accepts, and
        what to do.

    Example:
        >>> print(version_refusal("progress", {"schema_version": 3}, "observe"))
        progress.json has schema_version 3; this observe reads 1; upgrade compute-jobs
        >>> version_refusal("job-file", {}, "dry-run") is None
        True
    """
    current = CURRENT_MAJOR[format_name] if current_major is None else current_major
    accepted_majors = [major for major in (current - 1, current) if major >= 1]
    field, seen_major = _seen_major(format_name, document)

    seen_integer = None
    if isinstance(seen_major, int) and not isinstance(seen_major, bool):
        seen_integer = seen_major
    if seen_integer in accepted_majors:
        return None

    if field is None:
        has = "no schema_version"
    elif field not in document:
        has = "no schema_version, which means 1"
    else:
        has = f"{field} {json.dumps(seen_major)}"

    if seen_integer is None:
        advice = "the major version must be an integer; check what wrote it"
    elif seen_integer > current:
        advice = "upgrade compute-jobs"
    else:
        advice = f"rewrite it as major {current}, or use an older compute-jobs"

    reads = " and ".join(str(major) for major in accepted_majors)
    return f"{_DOCUMENT_NAME[format_name]} has {has}; this {reader} reads {reads}; {advice}"


def _seen_major(
    format_name: FormatName, document: Mapping[str, object]
) -> tuple[str | None, object]:
    """Return the field the major was read from, or None, and its value."""
    if "schema_version" in document:
        return "schema_version", document["schema_version"]
    if format_name == "progress" and "schema" in document:
        return "schema", document["schema"]
    if format_name == "job-file":
        return "schema_version", 1
    return None, None
