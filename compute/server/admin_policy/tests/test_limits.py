from importlib.resources import files
from typing import Any

import pytest
import yaml
from compute_jobs_admin_policy.limits import (
    InvalidLimitsError,
    parse_limits,
    shipped_limits,
    spending_ceiling,
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


def enable(document: dict[str, Any], profile: str) -> None:
    for entry in document["profiles"][profile]["entries"]:
        entry["enabled"] = True


def ceiling_after(quotas: dict[str, int], enabled_profiles: list[str]) -> float:
    document = shipped_document()
    document["quotas"].update(quotas)
    for profile in enabled_profiles:
        enable(document, profile)
    return spending_ceiling(parse_limits(yaml.safe_dump(document))).usd_per_hour


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
    assert limits["spend"] == {"max_burn_usd_per_hour": 125, "daily_cap_usd": 3000}
    assert limits["quotas"] == {
        "standard_on_demand": 1152,
        "g_vt_on_demand": 768,
        "p_on_demand": 768,
        "standard_spot": 0,
        "g_vt_spot": 0,
        "p_spot": 0,
    }


def test_the_starting_burn_limit_fits_two_gpu_sim_jobs_a_gpu_small_and_a_cpu_job() -> (
    None
):
    limits = shipped_limits()

    def largest_job_usd_per_hour(profile: str) -> float:
        return max(
            entry["usd_per_hour"] * entry["max_nodes"]
            for entry in limits["profiles"][profile]["entries"]
        )

    burn_usd_per_hour = (
        2 * largest_job_usd_per_hour("gpu-sim")
        + largest_job_usd_per_hour("gpu-small")
        + largest_job_usd_per_hour("cpu")
    )

    assert round(burn_usd_per_hour, 2) == 124.80
    assert burn_usd_per_hour <= limits["spend"]["max_burn_usd_per_hour"]
    assert (
        limits["spend"]["daily_cap_usd"]
        == 24 * limits["spend"]["max_burn_usd_per_hour"]
    )


# Every row of the table under "Quota-based ceiling" in docs/compute-jobs.md.
# The ceiling is information: no row fails, whatever the spend limits say.
@pytest.mark.parametrize(
    ("quotas", "enabled_profiles", "usd_per_hour"),
    [
        ({}, [], 415.37),
        ({}, ["gpu-sim-large"], 415.37),
        ({}, ["gpu-train-large"], 635.53),
        ({"g_vt_spot": 768}, [], 772.68),
    ],
)
def test_the_quota_based_ceiling_matches_the_page(
    quotas: dict[str, int], enabled_profiles: list[str], usd_per_hour: float
) -> None:
    assert ceiling_after(quotas, enabled_profiles) == usd_per_hour


def test_the_ceiling_names_each_quota_group() -> None:
    document = shipped_document()
    enable(document, "gpu-train-large")

    ceiling = spending_ceiling(parse_limits(yaml.safe_dump(document)))

    assert ceiling.usd_per_hour_by_quota == {
        "standard_on_demand": 58.06,
        "g_vt_on_demand": 357.31,
        "p_on_demand": 220.16,
        "standard_spot": 0.0,
        "g_vt_spot": 0.0,
        "p_spot": 0.0,
    }


def edit_cpu_entry(field: str, value: object) -> str:
    document = shipped_document()
    document["profiles"]["cpu"]["entries"][0][field] = value
    return yaml.safe_dump(document)


def drop_cpu_entry_field(field: str) -> str:
    document = shipped_document()
    del document["profiles"]["cpu"]["entries"][0][field]
    return yaml.safe_dump(document)


def edit_spend(spend: dict[str, object]) -> str:
    document = shipped_document()
    document["spend"] = spend
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
            edit_cpu_entry("quota", "dl_on_demand"),
            "quota group dl_on_demand, which quotas lacks",
        ),
        (duplicate_gpu_small_entry(), "lists an instance type twice"),
        (
            edit_spend({"daily_cap_usd": 3000}),
            "'max_burn_usd_per_hour' is a required property",
        ),
        (
            edit_spend({"max_burn_usd_per_hour": 125, "daily_cap_usd": -1}),
            "spend.daily_cap_usd: -1 is less than or equal to",
        ),
        (
            edit_spend(
                {
                    "max_burn_usd_per_hour": 125,
                    "daily_cap_usd": 3000,
                    "monthly_cap_usd": 1,
                }
            ),
            "('monthly_cap_usd' was unexpected)",
        ),
    ],
)
def test_parse_limits_rejects_an_invalid_entry_naming_the_field(
    yaml_text: str, message: str
) -> None:
    with pytest.raises(InvalidLimitsError) as raised:
        parse_limits(yaml_text)

    assert message in str(raised.value)
