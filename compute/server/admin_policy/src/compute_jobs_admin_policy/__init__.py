"""The SkyPilot admin policy that the shared server applies to every request."""

from importlib.metadata import version


def installed_version() -> str:
    """Return the installed compute-jobs-admin-policy distribution's version.

    One release tag, ``v<version>``, releases all three distributions at the
    same version.

    Raises:
        importlib.metadata.PackageNotFoundError: The distribution isn't
            installed, such as when the package is imported from a source
            checkout that uv hasn't synced.

    Example:
        >>> installed_version().count(".")
        2
    """
    return version("compute-jobs-admin-policy")
