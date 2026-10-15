"""Failure kinds: the names the client gives each way a command can exit 1 or 2.

The kinds are part of contract v0.1 ("Failure kinds" in the compute jobs
plan). The template's skill and wrapper branch on the ``kind=<kind>`` line
that the client writes first on stderr, so renaming or removing a kind, or
changing its exit code, needs the template's agreement.
"""

from enum import StrEnum

NOT_CONFIGURED_EXIT_CODE = 2
FAILURE_EXIT_CODE = 1


class FailureKind(StrEnum):
    """Why a command exited 1 or 2; the value is the text after ``kind=``.

    Every value matches ``[a-z][a-z0-9_]*``. The kinds mean:

    - ``not_configured``, exit 2: a server variable is unset, or the endpoint
      isn't ``https://`` or points at this machine.
    - ``argument_error``: an unknown command or option, or a missing or
      malformed argument.
    - ``invalid_job_file``: the file isn't a valid job file.
    - ``refused_job_file``: a valid job file that this release refuses, such
      as one over a limit.
    - ``smoke_failed``: the dry run's smoke test exited nonzero or ran out of
      time.
    - ``rejected``: the server or its admin policy refused the request.
    - ``unknown_job``: no job has the given name.
    - ``server_unreachable``: the server didn't answer in time.
    - ``branch_not_ready``: uncommitted or unpushed changes, or no open pull
      request to name the job by.
    - ``unauthorized``: the server refused the token.
    - ``internal_error``: an unexpected error in the client.

    Every kind other than ``not_configured`` exits 1.
    """

    NOT_CONFIGURED = "not_configured"
    ARGUMENT_ERROR = "argument_error"
    INVALID_JOB_FILE = "invalid_job_file"
    REFUSED_JOB_FILE = "refused_job_file"
    SMOKE_FAILED = "smoke_failed"
    REJECTED = "rejected"
    UNKNOWN_JOB = "unknown_job"
    SERVER_UNREACHABLE = "server_unreachable"
    BRANCH_NOT_READY = "branch_not_ready"
    UNAUTHORIZED = "unauthorized"
    INTERNAL_ERROR = "internal_error"

    @property
    def exit_code(self) -> int:
        """Return the process exit code, which is 2 for ``not_configured`` and 1 otherwise.

        Example:
            >>> FailureKind.NOT_CONFIGURED.exit_code
            2
            >>> FailureKind.UNKNOWN_JOB.exit_code
            1
        """
        if self is FailureKind.NOT_CONFIGURED:
            return NOT_CONFIGURED_EXIT_CODE
        return FAILURE_EXIT_CODE


class CommandFailure(Exception):
    """A command's expected failure, which ends the process with its kind's exit code.

    Attributes:
        kind: Which failure this is.
        message: What happened and what to do next, for the person or agent
            reading stderr.
    """

    def __init__(self, kind: FailureKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
