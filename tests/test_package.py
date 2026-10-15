import tomllib
from pathlib import Path

import foundation_compute


def test_the_version_is_the_one_in_pyproject_toml() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    assert foundation_compute.version() == pyproject["project"]["version"]
