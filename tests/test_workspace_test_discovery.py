import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFTEST = REPOSITORY_ROOT / "conftest.py"
MEMBER_TEST_PATHS = [
    "lib/src",
    "lib/tests",
    "compute/server/admin_policy/src",
    "compute/server/admin_policy/tests",
]


def default_test_paths_after_conftest() -> list[str]:
    if not CONFTEST.is_file():
        pytest.skip("mutmut's copy of the distribution has no conftest.py")
    specification = importlib.util.spec_from_file_location("root_conftest", CONFTEST)
    assert specification is not None and specification.loader is not None
    conftest = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(conftest)

    config = SimpleNamespace(
        args_source=pytest.Config.ArgsSource.TESTPATHS,
        inipath=REPOSITORY_ROOT / "pyproject.toml",
        rootpath=REPOSITORY_ROOT,
        args=["src", "tests", ".github/scripts"],
    )
    conftest.pytest_configure(config)
    return config.args


def test_a_run_without_paths_collects_each_workspace_members_src_and_tests() -> None:
    assert default_test_paths_after_conftest() == [
        "src",
        "tests",
        ".github/scripts",
        *MEMBER_TEST_PATHS,
    ]
