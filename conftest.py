"""pytest settings that pyproject.toml can't express: tests of uv workspace members.

pytest's `testpaths` is a fixed list, but the members of a uv workspace are
listed in the root pyproject.toml's `[tool.uv.workspace]`. This file adds each
member's `src/` and `tests/` to the default test paths, so that a new member's
tests run without a second list to update. A project that isn't a workspace
has no member, and runs the `testpaths` unchanged.
"""

import subprocess
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Add each uv workspace member's `src/` and `tests/` to the default test paths.

    Only a run that names no path uses `testpaths`, so a run that names one,
    such as `pytest lib/tests`, runs only what it names.

    Args:
        config: The pytest configuration, whose `args` are the paths to collect.

    Raises:
        subprocess.CalledProcessError: If uv can't list the workspace.
    """
    if config.args_source is not pytest.Config.ArgsSource.TESTPATHS:
        return

    # mutmut runs pytest with --rootdir at its own copy of a distribution,
    # inside that distribution's directory, so the root differs from the
    # directory of the settings file, and the run must test only that copy.
    if config.inipath is None or config.inipath.parent != config.rootpath:
        return

    listing = subprocess.run(
        ["uv", "workspace", "list", "--paths"],
        cwd=config.rootpath,
        check=True,
        capture_output=True,
        text=True,
    )
    root = config.rootpath.resolve()
    for member_path in listing.stdout.split():
        member = Path(member_path).relative_to(root)
        if member == Path():
            continue
        for directory in ("src", "tests"):
            if (root / member / directory).is_dir():
                config.args.append(str(member / directory))
