"""The ``compute-jobs`` executable: parse arguments, check configuration, run a command."""

import argparse
import os
import sys
import traceback
from collections.abc import Mapping, Sequence

from compute_jobs_cli.arguments import SERVER_COMMANDS, parse_arguments
from compute_jobs_cli.configuration import check_server_configuration
from compute_jobs_cli.kinds import CommandFailure, FailureKind
from compute_jobs_cli.sdk import SkyPilotSdk


def run() -> None:
    """Run ``compute-jobs`` with ``sys.argv`` and the process environment, then exit.

    This is the ``compute-jobs`` console script's entry point.
    """
    sys.exit(main(sys.argv[1:], os.environ))


def main(
    argv: Sequence[str],
    environment: Mapping[str, str],
    sdk: SkyPilotSdk | None = None,
) -> int:
    """Run one command and return the process exit code.

    On exit 1 or 2, stderr's first line is exactly ``kind=<kind>`` and the
    message follows on the next lines; exit 0 writes no ``kind=`` line. The
    server variables are checked before the command runs, so a command that
    needs the server and lacks them never calls SkyPilot.

    Args:
        argv: The arguments after the program name.
        environment: The variables to read, normally ``os.environ``.
        sdk: How commands call SkyPilot, or ``None`` until a command that calls
            SkyPilot is built.

    Returns:
        0 on success, 2 for ``not_configured``, and 1 for every other failure,
        including an unexpected exception (kind ``internal_error``, with its
        traceback after the message).
    """
    try:
        arguments = parse_arguments(argv)
        if arguments.command in SERVER_COMMANDS:
            check_server_configuration(environment)
        run_command(arguments, sdk)
    except CommandFailure as failure:
        return _report_failure(failure.kind, failure.message)
    except Exception as unexpected:  # noqa: BLE001 -- the top-level handler reports every error
        message = f"Unexpected error: {unexpected!r}\n{traceback.format_exc()}"
        return _report_failure(FailureKind.INTERNAL_ERROR, message)
    return 0


def run_command(arguments: argparse.Namespace, sdk: SkyPilotSdk | None) -> None:
    """Run the command that ``arguments`` names.

    Args:
        arguments: The parsed command line.
        sdk: How to call SkyPilot, for commands that do.

    Raises:
        NotImplementedError: Always, until the command is built.
    """
    raise NotImplementedError(
        f"compute-jobs {arguments.command} is not implemented yet"
    )


def _report_failure(kind: FailureKind, message: str) -> int:
    sys.stderr.write(f"kind={kind}\n{message.rstrip()}\n")
    return kind.exit_code
