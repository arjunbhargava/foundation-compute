from importlib.resources import files
from typing import Any

import pytest
import yaml
from compute_jobs_admin_policy.limits import (
    InvalidLimitsError,
    parse_limits,
    shipped_limits,
)

SHIPPED_YAML = files("compute_jobs_admin_policy").joinpath("limits.yaml").read_text()

# Each profile's maximum nodes and whether it is enabled, from the table in
# docs/compute-jobs.md, "Hardware profiles".
PROFILES_ON_THE_PAGE = {
    "cpu": (3, True),
    "gpu-small": (1, True),
    "gpu-sim": (2, True),
    "gpu-train": (2, True),
    "gpu-sim-large": (4, False),
    "gpu-train-large": (2, False),
}


def shipped_document() -> dict[str, Any]:
    return yaml.safe_load(SHIPPED_YAML)


def test_the_shipped_limits_validate_and_match_the_profiles_on_the_page() -> None:
    limits = shipped_limits()

    profiles = {
        name: (
            max(entry["max_nodes"] for entry in profile["entries"]),
            {entry["enabled"] for entry in profile["entries"]},
        )
        for name, profile in limits["profiles"].items()
    }
    assert profiles == {
        name: (max_nodes, {enabled})
        for name, (max_nodes, enabled) in PROFILES_ON_THE_PAGE.items()
    }
    assert limits["daily_cap_usd"] == 10000
    assert limits["quotas"] == {
        "standard_on_demand": 64,
        "g_vt_on_demand": 384,
        "g_vt_spot": 384,
        "p_on_demand": 0,
        "p_spot": 0,
    }


def edit_cpu_entry(field: str, value: object) -> str:
    document = shipped_document()
    document["profiles"]["cpu"]["entries"][0][field] = value
    return yaml.safe_dump(document)


def drop_cpu_entry_field(field: str) -> str:
    document = shipped_document()
    del document["profiles"]["cpu"]["entries"][0][field]
    return yaml.safe_dump(document)


def duplicate_gpu_small_entry() -> str:
    document = shipped_document()
    entries = document["profiles"]["gpu-small"]["entries"]
    entries.append(entries[0])
    return yaml.safe_dump(document)


@pytest.mark.parametrize(
    ("yaml_text", "message"),
    [
        ("profiles: [", "isn't valid YAML"),
        (edit_cpu_entry("enable", False), "('enable' was unexpected)"),
        (drop_cpu_entry_field("enabled"), "'enabled' is a required property"),
        (edit_cpu_entry("vcpus", True), "vcpus: True is not of type 'integer'"),
        (edit_cpu_entry("usd_per_hour", 0), "usd_per_hour: 0 is less than or equal to"),
        (
            edit_cpu_entry("gpus_per_node", 1),
            "gpu_memory_gb: None is not of type 'integer'",
        ),
        (
            edit_cpu_entry("spot_allowed", True),
            "spot_quota: None is not of type 'string'",
        ),
        (
            edit_cpu_entry("quota", "standard_spot"),
            "quota group standard_spot, which quotas lacks",
        ),
        (duplicate_gpu_small_entry(), "lists an instance type twice"),
    ],
)
def test_parse_limits_rejects_an_invalid_entry_naming_the_field(
    yaml_text: str, message: str
) -> None:
    with pytest.raises(InvalidLimitsError) as raised:
        parse_limits(yaml_text)

    assert message in str(raised.value)
