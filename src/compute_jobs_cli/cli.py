"""The ``compute-jobs`` executable: parse arguments, check configuration, run a command."""

import argparse
import sys
import traceback
from collections.abc import Sequence

from compute_jobs_cli.arguments import parse_arguments
from compute_jobs_cli.kinds import CommandFailure, FailureKind
from compute_jobs_cli.sdk import SkyPilotSdk


def run() -> None:
    """Run ``compute-jobs`` with ``sys.argv``, then exit.

    This is the ``compute-jobs`` console script's entry point.
    """
    sys.exit(main(sys.argv[1:]))


def main(argv: Sequence[str], sdk: SkyPilotSdk | None = None) -> int:
    """Run one command and return the process exit code.

    On exit 1 or 2, stderr's first line is exactly ``kind=<kind>`` and the
    message follows on the next lines; exit 0 writes no ``kind=`` line.

    Args:
        argv: The arguments after the program name.
        sdk: How commands call SkyPilot, or ``None`` until a command that calls
            SkyPilot is built.

    Returns:
        0 on success, otherwise the exit code of the failure's kind. An
        unexpected exception is kind ``internal_error``, with its traceback
        after the message.
    """
    try:
        arguments = parse_arguments(argv)
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
