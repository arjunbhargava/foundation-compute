"""The arguments of the four ``compute-jobs`` commands."""

import argparse
from collections.abc import Sequence
from typing import NoReturn

from compute_jobs_cli.kinds import CommandFailure, FailureKind

COMMANDS = ("dry-run", "launch", "observe", "cancel")
SERVER_COMMANDS = ("launch", "observe", "cancel")


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    """Parse the command line that follows ``compute-jobs``.

    The result's ``command`` is one of ``COMMANDS``. The other attributes are
    ``job_file`` (dry-run, launch), ``job_name`` (observe, where it may be
    ``None``, and cancel), and ``pr``, ``lines``, and ``json`` (observe).

    Args:
        argv: The arguments after the program name.

    Raises:
        CommandFailure: With kind ``argument_error`` for an unknown command or
            option, or a missing or malformed argument. ``argparse`` would exit
            2, which contract v0 reserves for "not configured".
        SystemExit: With status 0 after printing help for ``-h`` or ``--help``.

    Example:
        >>> parse_arguments(["observe", "--pr", "81"]).pr
        81
    """
    parser = _ContractArgumentParser(prog="compute-jobs", allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    for command in ("dry-run", "launch"):
        subparser = commands.add_parser(command, allow_abbrev=False)
        subparser.add_argument("job_file", help="path of the job file")

    observe = commands.add_parser("observe", allow_abbrev=False)
    observe.add_argument("job_name", nargs="?", help="job to show; omit to list jobs")
    observe.add_argument(
        "--pr", type=_positive_integer, help="list the jobs of this PR"
    )
    observe.add_argument(
        "--lines", type=_positive_integer, help="lines of log tail to show"
    )
    observe.add_argument("--json", action="store_true", help="print one JSON object")

    cancel = commands.add_parser("cancel", allow_abbrev=False)
    cancel.add_argument("job_name", help="job to cancel")

    return parser.parse_args(argv)


class _ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise CommandFailure(
            FailureKind.ARGUMENT_ERROR, f"{self.format_usage()}{message}"
        )


def _positive_integer(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} isn't an integer") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"{value} isn't at least 1")
    return value
