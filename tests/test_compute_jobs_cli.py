import tomllib
from pathlib import Path

import compute_jobs_cli

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def test_the_installed_version_is_the_one_in_pyproject_toml() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text())
    assert compute_jobs_cli.installed_version() == pyproject["project"]["version"]
