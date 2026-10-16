"""``limits.yaml``, the compute list, and the quota-based spending ceiling.

``limits.yaml`` names each hardware profile a job file may ask for, as an
ordered list of EC2 instance types, together with the spend limits the admin
policy enforces and the account's EC2 vCPU quotas. It is data: adding or
enabling an instance type is an edit to that file, which :func:`parse_limits`
validates against ``limits.v1.schema.json`` in this package.

The quotas limit nothing here: spend is limited in software, by
``spend`` (see "Spend limits" in docs/compute-jobs.md). :func:`spending_ceiling`
reports, for information, what the account could spend an hour with every
quota group full of its dearest enabled entry per vCPU.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from typing import TypedDict, cast

import yaml
from jsonschema import ValidationError, validate


class InstanceTypeEntry(TypedDict):
    """One EC2 instance type a profile may run on: what a node has and costs.

    Attributes:
        instance_type: The EC2 instance type, such as ``g6e.xlarge``.
        quota: The quota group that on-demand nodes of it count against.
        spot_quota: The quota group that spot nodes count against; None
            exactly when ``spot_allowed`` is false.
        accelerator: The GPU model, such as ``L40S``; None on a CPU type.
        gpus_per_node: GPUs on each node, >= 0.
        gpu_memory_gb: Memory of each GPU in GB; None on a CPU type.
        vcpus: vCPUs on each node, >= 1, which count against the quota.
        usd_per_hour: The on-demand list price of one node in USD per hour,
            > 0, and never below AWS's.
        max_nodes: The most nodes of it one job may use, >= 1.
        spot_allowed: Whether a job asking for spot may use it.
        enabled: Whether any job may use it.
    """

    instance_type: str
    quota: str
    spot_quota: str | None
    accelerator: str | None
    gpus_per_node: int
    gpu_memory_gb: int | None
    vcpus: int
    usd_per_hour: float
    max_nodes: int
    spot_allowed: bool
    enabled: bool


class Profile(TypedDict):
    """A hardware profile: the instance types a job naming it may use.

    Attributes:
        max_runtime_minutes: The longest ``max_runtime_minutes`` a job file
            may ask for, >= 1.
        entries: The instance types, in the order SkyPilot tries them.
    """

    max_runtime_minutes: int
    entries: list[InstanceTypeEntry]


class SpendLimits(TypedDict):
    """The default spend limits the admin policy enforces at launch.

    Both are in USD at on-demand list price and > 0, with
    ``daily_cap_usd`` >= ``max_burn_usd_per_hour``. The owner overrides
    either under ``plugins.compute_jobs`` in the server's config.

    Attributes:
        max_burn_usd_per_hour: The most the running jobs and the new one
            together may cost an hour.
        daily_cap_usd: The most the ceilings of the jobs launched in any 24
            hours, the new one included, may add up to.
    """

    max_burn_usd_per_hour: float
    daily_cap_usd: float


class Limits(TypedDict):
    """A parsed and validated ``limits.yaml``.

    Attributes:
        schema_version: 1, the only major this release reads.
        spend: The default spend limits.
        quotas: Each quota group's applied EC2 vCPU quota, by group name; 0
            where the quota isn't known yet.
        profiles: Each profile, by the name a job file uses.
    """

    schema_version: int
    spend: SpendLimits
    quotas: dict[str, int]
    profiles: dict[str, Profile]


class InvalidLimitsError(ValueError):
    """``limits.yaml`` isn't valid; the message says where, and why."""


def shipped_limits() -> Limits:
    """Return the ``limits.yaml`` this release ships, parsed and validated.

    Raises:
        InvalidLimitsError: The shipped file isn't valid, which a test
            prevents.

    Example:
        >>> shipped_limits()["profiles"]["cpu"]["entries"][0]["instance_type"]
        'm7i.4xlarge'
    """
    return parse_limits(
        files(__package__).joinpath("limits.yaml").read_text(encoding="utf-8")
    )


def parse_limits(yaml_text: str) -> Limits:
    """Parse the text of a ``limits.yaml`` and validate it.

    Args:
        yaml_text: The file's contents.

    Raises:
        InvalidLimitsError: The text isn't YAML; doesn't match the schema,
            such as a missing or unknown field, GPUs without an accelerator,
            or spot allowed without a spot quota group; sets a daily cap
            below the hourly burn limit; names a quota group that ``quotas``
            lacks; or lists an instance type twice in one profile.

    Example:
        >>> try:
        ...     parse_limits(
        ...         "{schema_version: 1, spend: {max_burn_usd_per_hour: 0, daily_cap_usd: 1},"
        ...         " quotas: {}, profiles: {}}"
        ...     )
        ... except InvalidLimitsError as error:
        ...     print(error)
        limits.yaml at $.spend.max_burn_usd_per_hour: 0 is less than or equal to the minimum of 0; see "Hardware profiles" in docs/compute-jobs.md
    """
    try:
        document: object = yaml.safe_load(yaml_text)
    except yaml.YAMLError as error:
        raise InvalidLimitsError(f"limits.yaml isn't valid YAML: {error}") from error

    schema = json.loads(
        files(__package__).joinpath("limits.v1.schema.json").read_text(encoding="utf-8")
    )
    try:
        validate(document, schema)
    except ValidationError as error:
        raise InvalidLimitsError(
            f"limits.yaml at {error.json_path}: {error.message}; "
            'see "Hardware profiles" in docs/compute-jobs.md'
        ) from error

    limits = cast(Limits, document)
    spend = limits["spend"]
    if spend["daily_cap_usd"] < spend["max_burn_usd_per_hour"]:
        raise InvalidLimitsError(
            f"limits.yaml's spend.daily_cap_usd {spend['daily_cap_usd']} is below "
            f"spend.max_burn_usd_per_hour {spend['max_burn_usd_per_hour']}; "
            "make the daily cap at least the hourly burn limit"
        )
    for profile_name, profile in limits["profiles"].items():
        instance_types = [entry["instance_type"] for entry in profile["entries"]]
        if len(set(instance_types)) < len(instance_types):
            raise InvalidLimitsError(
                f"limits.yaml's profile {profile_name} lists an instance type twice: "
                f"{instance_types}"
            )
        for entry in profile["entries"]:
            for group in (entry["quota"], entry["spot_quota"]):
                if group is not None and group not in limits["quotas"]:
                    raise InvalidLimitsError(
                        f"limits.yaml's profile {profile_name} puts {entry['instance_type']} "
                        f"in the quota group {group}, which quotas lacks; use one of "
                        f"{sorted(limits['quotas'])}"
                    )
    return limits


@dataclass(frozen=True)
class SpendingCeiling:
    """The most the enabled entries could cost an hour, with every quota full.

    This is information for ``compute-server:status``, not a limit: it is
    what the account could spend if launches bypassed the spend limits.

    Attributes:
        usd_per_hour_by_quota: Each quota group's ceiling in USD per hour:
            its vCPU quota times the dearest price per vCPU among the enabled
            entries that count against it, rounded to the cent; 0 for a
            group no enabled entry uses.
        usd_per_hour: The sum of the groups' ceilings.
    """

    usd_per_hour_by_quota: Mapping[str, float]
    usd_per_hour: float


def spending_ceiling(limits: Limits) -> SpendingCeiling:
    """Return the hourly spend with every quota group full of its dearest entry.

    An enabled entry counts against its ``quota`` group and, when spot is
    allowed, its ``spot_quota`` group, at its on-demand price in both.

    Example:
        >>> spending_ceiling(shipped_limits()).usd_per_hour
        415.37
    """
    usd_per_vcpu_hour = dict.fromkeys(limits["quotas"], 0.0)
    for profile in limits["profiles"].values():
        for entry in profile["entries"]:
            if not entry["enabled"]:
                continue
            entry_usd_per_vcpu_hour = entry["usd_per_hour"] / entry["vcpus"]
            for group in (entry["quota"], entry["spot_quota"]):
                if group is not None:
                    usd_per_vcpu_hour[group] = max(
                        usd_per_vcpu_hour[group], entry_usd_per_vcpu_hour
                    )

    # ponytail: rounding each group to the nearest cent, as the table in
    # docs/compute-jobs.md does, can understate the total by $0.005 a group.
    by_quota = {
        group: round(vcpus * usd_per_vcpu_hour[group], 2)
        for group, vcpus in limits["quotas"].items()
    }
    return SpendingCeiling(
        usd_per_hour_by_quota=by_quota,
        usd_per_hour=round(sum(by_quota.values()), 2),
    )
