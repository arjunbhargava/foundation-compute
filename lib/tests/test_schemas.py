import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from compute_jobs.schemas import CURRENT_MAJOR, FormatName, load_schema, version_refusal
from jsonschema import Draft202012Validator, ValidationError, validate

FIXTURES = Path(__file__).parent / "fixtures"
LIB = Path(__file__).parent.parent
FORMATS = list(CURRENT_MAJOR)


def read_fixtures(format_name: FormatName, validity: str) -> dict[str, Any]:
    path = FIXTURES / f"{format_name}.v{CURRENT_MAJOR[format_name]}.{validity}.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("format_name", FORMATS)
def test_each_schema_accepts_its_valid_fixtures_and_rejects_its_invalid_ones(
    format_name: FormatName,
) -> None:
    schema = load_schema(format_name, CURRENT_MAJOR[format_name])
    Draft202012Validator.check_schema(schema)
    valid = read_fixtures(format_name, "valid")
    invalid = read_fixtures(format_name, "invalid")

    def is_valid(document: Any) -> bool:
        try:
            validate(document, schema, cls=Draft202012Validator)
        except ValidationError:
            return False
        return True

    assert valid and invalid
    assert [name for name, document in valid.items() if not is_valid(document)] == []
    assert [name for name, document in invalid.items() if is_valid(document)] == []


@pytest.mark.parametrize("format_name", FORMATS)
def test_the_version_check_accepts_the_current_and_previous_major_and_refuses_others_naming_the_major(
    format_name: FormatName,
) -> None:
    def refusal(seen_major: int, current_major: int) -> str | None:
        return version_refusal(
            format_name, {"schema_version": seen_major}, "observe", current_major
        )

    shipped = CURRENT_MAJOR[format_name]
    assert refusal(shipped, shipped) is None
    assert refusal(2, 2) is None
    assert refusal(1, 2) is None

    next_major = refusal(3, 2)
    assert next_major is not None
    assert (
        "has schema_version 3; this observe reads 1 and 2; upgrade compute-jobs"
        in next_major
    )

    older_major = refusal(1, 3)
    assert older_major is not None
    assert "has schema_version 1; this observe reads 2 and 3" in older_major


def test_a_job_file_without_schema_version_is_major_1() -> None:
    assert (
        version_refusal("job-file", {"kind": "single"}, "dry-run", current_major=2)
        is None
    )
    assert version_refusal(
        "job-file", {"kind": "single"}, "dry-run", current_major=3
    ) == (
        "the job file has no schema_version, which means 1; this dry-run reads 2 and 3; "
        "rewrite it as major 3, or use an older compute-jobs"
    )
    assert version_refusal("job-file", {"schema_version": 99}, "dry-run") == (
        "the job file has schema_version 99; this dry-run reads 1; upgrade compute-jobs"
    )


def test_progress_readers_prefer_schema_version_and_fall_back_to_schema() -> None:
    assert version_refusal("progress", {"schema": 1}, "observe") is None
    assert version_refusal(
        "progress", {"schema": 1, "schema_version": 2}, "observe"
    ) == (
        "progress.json has schema_version 2; this observe reads 1; upgrade compute-jobs"
    )
    assert version_refusal("progress", {"schema": 2}, "observe") == (
        "progress.json has schema 2; this observe reads 1; upgrade compute-jobs"
    )


@pytest.mark.parametrize(
    "format_name", ["progress", "run-record", "archive", "observe"]
)
def test_a_document_without_a_major_is_refused(format_name: FormatName) -> None:
    refusal = version_refusal(format_name, {}, "observe")
    assert refusal is not None
    assert "has no schema_version; this observe reads 1" in refusal


@pytest.mark.parametrize("seen_major", ["1", 1.0, True, None])
def test_a_major_that_is_not_an_integer_is_refused_naming_it(
    seen_major: object,
) -> None:
    refusal = version_refusal("archive", {"schema_version": seen_major}, "wrapper")
    assert refusal == (
        f"archive.json has schema_version {json.dumps(seen_major)}; this wrapper reads 1; "
        "the major version must be an integer; check what wrote it"
    )


def test_the_installed_wheel_contains_every_schema(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv is not on PATH; run the tests through `mise run test`"
    venv_python = tmp_path / "venv" / "bin" / "python"

    def run(*command: str | Path) -> str:
        return subprocess.run(
            command, check=True, capture_output=True, text=True
        ).stdout

    run(uv, "build", "--wheel", "--offline", "--out-dir", tmp_path, LIB)
    (wheel,) = tmp_path.glob("compute_jobs-*.whl")
    run(uv, "venv", "--offline", "--python", sys.executable, tmp_path / "venv")
    run(uv, "pip", "install", "--offline", "--no-deps", "--python", venv_python, wheel)
    loaded = run(
        venv_python,
        "-c",
        "import compute_jobs.schemas as s; print(s.__file__);"
        "print(sorted(s.load_schema(f, m)['title'] for f, m in s.CURRENT_MAJOR.items()))",
    ).splitlines()

    assert Path(loaded[0]).is_relative_to(tmp_path / "venv")
    expected_titles = sorted(
        str(load_schema(format_name, major)["title"])
        for format_name, major in CURRENT_MAJOR.items()
    )
    assert loaded[1] == repr(expected_titles)
