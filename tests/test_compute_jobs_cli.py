import importlib.metadata
import sys
import tomllib
from pathlib import Path

import compute_jobs_cli

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def test_the_installed_version_is_the_one_in_pyproject_toml() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text())
    assert compute_jobs_cli.installed_version() == pyproject["project"]["version"]


def test_skypilot_0_14_0_is_installed_on_python_3_13() -> None:
    # Importing sky writes to ~/.sky and warns, so this reads the metadata.
    assert importlib.metadata.version("skypilot") == "0.14.0"
    assert sys.version_info[:2] == (3, 13)
