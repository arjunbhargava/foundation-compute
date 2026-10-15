"""``limits.yaml``, the compute list, and the spending-ceiling check on it.

``limits.yaml`` names each hardware profile a job file may ask for, as an
ordered list of EC2 instance types, together with the EC2 vCPU quotas and the
daily spending cap. It is data: adding or enabling an instance type is an
edit to that file, which :func:`parse_limits` validates against
``limits.v1.schema.json`` in this package.

EC2's vCPU quotas cap what can run at once, so they also cap the hourly spend.
:func:`spending_ceiling` fills each quota group with its dearest enabled
entry per vCPU, and the result must stay within ``daily_cap_usd`` / 24.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from typing import TypedDict, cast

import yaml
from jsonschema import ValidationError, validate

HOURS_PER_DAY = 24


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


class Limits(TypedDict):
    """A parsed and validated ``limits.yaml``.

    Attributes:
        schema_version: 1, the only major this release reads.
        daily_cap_usd: The most all jobs together may spend in a day, in USD.
        quotas: Each quota group's EC2 vCPU quota, by group name.
        profiles: Each profile, by the name a job file uses.
    """

    schema_version: int
    daily_cap_usd: float
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
            or spot allowed without a spot quota group; names a quota group
            that ``quotas`` lacks; or lists an instance type twice in one
            profile.

    Example:
        >>> try:
        ...     parse_limits("{schema_version: 1, daily_cap_usd: 0, quotas: {}, profiles: {}}")
        ... except InvalidLimitsError as error:
        ...     print(error)
        limits.yaml at $.daily_cap_usd: 0 is less than or equal to the minimum of 0; see "Hardware profiles" in docs/compute-jobs.md
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
    """The most the enabled entries can cost an hour, with every quota full.

    Attributes:
        usd_per_hour_by_quota: Each quota group's ceiling in USD per hour:
            its vCPU quota times the dearest price per vCPU among the enabled
            entries that count against it, rounded to the cent; 0 for a
            group no enabled entry uses.
        usd_per_hour: The sum of the groups' ceilings.
        cap_usd_per_hour: ``daily_cap_usd`` / 24.
    """

    usd_per_hour_by_quota: Mapping[str, float]
    usd_per_hour: float
    cap_usd_per_hour: float

    def refusal(self) -> str | None:
        """Return why the ceiling exceeds the cap, or None if it is within it.

        Example:
            >>> print(spending_ceiling(shipped_limits()).refusal())
            None
        """
        if self.usd_per_hour <= self.cap_usd_per_hour:
            return None
        groups = ", ".join(
            f"{name} ${usd:.2f}" for name, usd in self.usd_per_hour_by_quota.items()
        )
        return (
            f"limits.yaml's spending ceiling is ${self.usd_per_hour:.2f} an hour ({groups}), "
            f"over daily_cap_usd / {HOURS_PER_DAY} = ${self.cap_usd_per_hour:.2f} an hour; "
            "lower a quota or disable an entry, or ask the owner to raise the daily cap"
        )


def spending_ceiling(limits: Limits) -> SpendingCeiling:
    """Return the hourly spend with every quota group full of its dearest entry.

    An enabled entry counts against its ``quota`` group and, when spot is
    allowed, its ``spot_quota`` group, at its on-demand price in both.

    Example:
        >>> spending_ceiling(shipped_limits()).usd_per_hour
        360.55
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
        cap_usd_per_hour=limits["daily_cap_usd"] / HOURS_PER_DAY,
    )
