"""The boundary between the client and SkyPilot's SDK.

Commands reach SkyPilot only through a ``SkyPilotSdk``, so tests pass a fake
that records its calls and never open a network connection.
"""

from collections.abc import Mapping, Sequence
from typing import Protocol


class SkyPilotSdk(Protocol):
    """The SkyPilot managed-job calls that launch, observe, and cancel make.

    Every method sends a request to the shared API server. The commands that
    call them, and the real implementation, arrive with PRs 5 and 6 of the
    compute jobs plan, which may widen these signatures.
    """

    def launch(self, job_name: str, task_yaml: str) -> None:
        """Submit a managed job named ``job_name`` described by ``task_yaml``."""
        ...

    def queue(self) -> Sequence[Mapping[str, object]]:
        """Return a record for each managed job the server knows."""
        ...

    def cancel(self, job_name: str) -> None:
        """Cancel the managed job named ``job_name``."""
        ...
