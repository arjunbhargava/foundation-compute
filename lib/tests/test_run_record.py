import json
from dataclasses import replace

import jsonschema
import pytest
from compute_jobs.run_record import RunRecord, final_state
from compute_jobs.schemas import load_schema

RUNNING = RunRecord(
    job_name="pr81-search-3f9a2c1d",
    kind="search",
    machine_id="AROAEXAMPLE:i-0abc",
    node_rank=0,
    nodes=2,
    state="running",
    started_at="2026-10-15T03:26:00Z",
    command="python -m myproject.search",
)


def test_a_running_record_validates_against_the_run_record_schema() -> None:
    jsonschema.validate(RUNNING.to_dict(), load_schema("run-record", 1))


def test_a_finished_record_validates_and_keeps_every_field_it_has() -> None:
    finished = replace(
        RUNNING,
        state="timed_out",
        exit_code=124,
        finished_at="2026-10-15T06:26:00Z",
        seed=1234,
        driver_cuda_version="12.8",
    )
    document = json.loads(json.dumps(finished.to_dict()))
    jsonschema.validate(document, load_schema("run-record", 1))
    assert document["schema_version"] == 1
    assert document["exit_code"] == 124
    assert document["seed"] == 1234
    assert "failure" not in document


@pytest.mark.parametrize(
    ("exit_code", "state"),
    [(0, "succeeded"), (1, "failed"), (124, "timed_out"), (137, "failed")],
)
def test_the_final_state_follows_the_exit_code(exit_code: int, state: str) -> None:
    assert final_state(exit_code) == state
