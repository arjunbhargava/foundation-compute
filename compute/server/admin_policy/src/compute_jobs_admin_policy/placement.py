"""Placing a job on its profile: which of the profile's instance types it may use.

The admin policy never imports the library, so the caller passes only the job
file's fields that placement needs, as a :class:`JobRequest`.
"""

from dataclasses import dataclass
from typing import Literal

from compute_jobs_admin_policy.limits import InstanceTypeEntry, Limits


@dataclass(frozen=True)
class JobRequest:
    """The fields of a job file that decide which instance types it may use.

    Attributes:
        kind: ``single``, ``multi-node``, or ``search``.
        profile: The profile the job file names.
        nodes: Nodes the job asks for, >= 1; 1 for a ``single`` job.
        use_spot: Whether the job asks for spot machines.
    """

    kind: Literal["single", "multi-node", "search"]
    profile: str
    nodes: int
    use_spot: bool


@dataclass(frozen=True)
class PlacementRefusal:
    """Why a job can't be placed on its profile.

    Attributes:
        failure_kind: ``invalid_job_file`` for a profile ``limits.yaml``
            lacks or nodes on a ``single`` job, or ``refused_job_file`` for a
            limit in ``limits.yaml``; the client prints it as stderr's
            ``kind=`` line.
        message: One line saying what is wrong and the fix.
    """

    failure_kind: Literal["invalid_job_file", "refused_job_file"]
    message: str


def place_job(
    job: JobRequest, limits: Limits
) -> list[InstanceTypeEntry] | PlacementRefusal:
    """Return the profile's entries the job may use, in the profile's order.

    An entry is kept when it is enabled, allows the job's node count, and, if
    the job asks for spot, allows spot.

    Returns:
        The kept entries, never empty, or why the job is refused when none
        is kept.

    Example:
        >>> from compute_jobs_admin_policy.limits import shipped_limits
        >>> entries = place_job(JobRequest("single", "gpu-small", 1, False), shipped_limits())
        >>> [entry["instance_type"] for entry in entries]
        ['g6.xlarge', 'g6e.xlarge', 'g4dn.xlarge']
    """
    profile = limits["profiles"].get(job.profile)
    if profile is None:
        return PlacementRefusal(
            "invalid_job_file",
            f"profile {job.profile} isn't in limits.yaml; use one of {sorted(limits['profiles'])}",
        )
    if job.kind == "single" and job.nodes != 1:
        return PlacementRefusal(
            "invalid_job_file",
            f"a single job runs on 1 node, not {job.nodes}; use kind: multi-node",
        )

    enabled = [entry for entry in profile["entries"] if entry["enabled"]]
    if not enabled:
        return PlacementRefusal(
            "refused_job_file",
            f"profile {job.profile} has no enabled instance type; use another profile, "
            "or ask the owner to enable it",
        )
    max_nodes = max(entry["max_nodes"] for entry in enabled)
    if job.nodes > max_nodes:
        return PlacementRefusal(
            "refused_job_file",
            f"profile {job.profile} allows at most {max_nodes} nodes, not {job.nodes}; "
            "ask for fewer, or ask the owner to raise the limit",
        )

    kept = [
        entry
        for entry in enabled
        if job.nodes <= entry["max_nodes"]
        and (entry["spot_allowed"] or not job.use_spot)
    ]
    if not kept:
        return PlacementRefusal(
            "refused_job_file",
            f"no enabled instance type in profile {job.profile} allows spot on {job.nodes} "
            "nodes; set use_spot: false",
        )
    return kept
