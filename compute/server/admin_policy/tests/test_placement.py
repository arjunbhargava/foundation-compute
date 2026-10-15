from importlib.resources import files

import pytest
import yaml
from compute_jobs_admin_policy.limits import Limits, parse_limits, shipped_limits
from compute_jobs_admin_policy.placement import JobRequest, PlacementRefusal, place_job

INVALID = "invalid_job_file"
REFUSED = "refused_job_file"


def limits_with_gpu_sim_large_enabled_after_gpu_sim() -> Limits:
    shipped_yaml = (
        files("compute_jobs_admin_policy").joinpath("limits.yaml").read_text()
    )
    document = yaml.safe_load(shipped_yaml)
    for entry in document["profiles"]["gpu-sim-large"]["entries"]:
        entry["enabled"] = True
    document["profiles"]["gpu-sim-large"]["entries"].append(
        document["profiles"]["gpu-sim"]["entries"][1] | {"max_nodes": 2}
    )
    return parse_limits(yaml.safe_dump(document))


def test_placement_keeps_in_order_the_enabled_entries_that_allow_the_nodes_and_spot() -> (
    None
):
    limits = limits_with_gpu_sim_large_enabled_after_gpu_sim()

    def kept(nodes: int, use_spot: bool) -> list[str] | str:
        placement = place_job(
            JobRequest("search", "gpu-sim-large", nodes, use_spot), limits
        )
        if isinstance(placement, PlacementRefusal):
            return placement.message
        return [entry["instance_type"] for entry in placement]

    assert kept(2, False) == ["g6e.48xlarge", "g6e.12xlarge"]
    assert kept(4, False) == ["g6e.48xlarge"]
    assert kept(2, True) == ["g6e.12xlarge"]
    assert "allows spot on 4 nodes" in kept(4, True)


@pytest.mark.parametrize(
    ("job", "failure_kind", "message"),
    [
        (JobRequest("single", "gpu-huge", 1, False), INVALID, "isn't in limits.yaml"),
        (JobRequest("single", "cpu", 2, False), INVALID, "runs on 1 node, not 2"),
        (JobRequest("single", "gpu-train-large", 1, False), REFUSED, "no enabled"),
        (JobRequest("multi-node", "cpu", 4, False), REFUSED, "at most 3 nodes, not 4"),
        (JobRequest("single", "cpu", 1, True), REFUSED, "set use_spot: false"),
    ],
)
def test_placement_refuses_a_job_naming_why(
    job: JobRequest, failure_kind: str, message: str
) -> None:
    placement = place_job(job, shipped_limits())

    assert isinstance(placement, PlacementRefusal)
    assert (placement.failure_kind, message in placement.message) == (
        failure_kind,
        True,
    )
