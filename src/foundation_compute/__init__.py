"""Compute infrastructure for agents."""

from importlib.metadata import version as _distribution_version


def version() -> str:
    """Returns the installed version of the foundation-compute distribution."""
    return _distribution_version("foundation-compute")
