# Ray's cluster_utils, ray.init, and ray.nodes are unannotated.
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false
import os
import random
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import ray
from compute_jobs import fanout
from ray.cluster_utils import Cluster


@pytest.fixture(scope="module")
def two_ray_nodes() -> Iterator[set[str]]:
    # fanout.map connects to the job's address only when Ray isn't connected
    # yet, so this cluster, on any free port, stands in for the job's.
    cluster = Cluster(initialize_head=True, head_node_args={"num_cpus": 1})
    cluster.add_node(num_cpus=1)
    ray.init(address=cluster.address)
    cluster.wait_for_nodes()
    yield {node["NodeID"] for node in ray.nodes() if node["Alive"]}
    ray.shutdown()
    cluster.shutdown()


@pytest.fixture
def checkpoint_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("COMPUTE_JOB_CHECKPOINT_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.xdist_group("two_ray_nodes")
def test_map_sends_evaluations_to_both_ray_nodes(two_ray_nodes: set[str]) -> None:
    # Each node has one CPU, so while one node's evaluation sleeps, Ray must
    # place the next on the other node.
    def node_id(_: int) -> str:
        time.sleep(0.5)
        return ray.get_runtime_context().get_node_id()

    evaluated_on = fanout.map(node_id, range(8))

    assert len(two_ray_nodes) == 2
    assert set(evaluated_on) == two_ray_nodes


@pytest.mark.xdist_group("two_ray_nodes")
def test_map_on_ray_keeps_the_candidates_order(two_ray_nodes: set[str]) -> None:
    def tenfold_after_a_shorter_sleep_for_later_candidates(candidate: int) -> int:
        time.sleep(0.1 * (5 - candidate))
        return 10 * candidate

    fitness = fanout.map(tenfold_after_a_shorter_sleep_for_later_candidates, range(6))

    assert fitness == [0, 10, 20, 30, 40, 50]


@pytest.mark.xdist_group("two_ray_nodes")
def test_map_on_ray_counts_failed_evaluations_and_gives_them_none(
    two_ray_nodes: set[str], capsys: pytest.CaptureFixture[str]
) -> None:
    def fail_on_odd(candidate: int) -> int:
        if candidate % 2:
            raise ValueError(f"odd candidate {candidate}")
        return candidate

    fitness = fanout.map(fail_on_odd, range(5))

    assert fitness == [0, None, 2, None, 4]
    assert fitness.failed == 2
    stderr = capsys.readouterr().err
    assert "2 of 5 evaluations failed" in stderr
    assert "odd candidate 1" in stderr


@pytest.mark.xdist_group("two_ray_nodes")
def test_map_on_ray_accepts_a_builtin_function(two_ray_nodes: set[str]) -> None:
    assert fanout.map(abs, [-2, 3]) == [2, 3]


def test_map_with_compute_job_smoke_rejects_negative_gpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPUTE_JOB_SMOKE", "1")

    with pytest.raises(ValueError, match=r"gpus_per_evaluation is -1"):
        fanout.map(abs, [1], gpus_per_evaluation=-1)


def test_map_connects_to_port_6379_without_forwarding_worker_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_arguments: dict[str, object] = {}

    def refuse_connection(**arguments: object) -> None:
        init_arguments.update(arguments)
        raise ConnectionError("nothing listens")

    monkeypatch.delenv("COMPUTE_JOB_SMOKE", raising=False)
    monkeypatch.setattr(ray, "is_initialized", lambda: False)
    monkeypatch.setattr(ray, "init", refuse_connection)

    with pytest.raises(RuntimeError, match="No Ray cluster answered"):
        fanout.map(abs, [1])
    assert init_arguments == {"address": "localhost:6379", "log_to_driver": False}


def test_map_with_compute_job_smoke_runs_serially_in_this_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    def record_call(candidate: int) -> int:
        calls.append((candidate, os.getpid()))
        return -candidate

    def fail_if_called(**_: object) -> None:
        pytest.fail("smoke mode called ray.init")

    monkeypatch.setenv("COMPUTE_JOB_SMOKE", "1")
    monkeypatch.setattr(ray, "init", fail_if_called)

    fitness = fanout.map(record_call, [3, 1, 2], gpus_per_evaluation=0.25)

    assert fitness == [-3, -1, -2]
    assert calls == [(3, os.getpid()), (1, os.getpid()), (2, os.getpid())]


def test_map_with_compute_job_smoke_counts_failed_evaluations(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("COMPUTE_JOB_SMOKE", "1")

    fitness = fanout.map(lambda candidate: 1 / candidate, [1, 0, 2])

    assert fitness == [1.0, None, 0.5]
    assert fitness.failed == 1
    stderr = capsys.readouterr().err
    assert "1 of 3 evaluations failed" in stderr
    assert "ZeroDivisionError" in stderr


def test_resume_generations_resumes_after_the_last_checkpoint(
    checkpoint_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert list(fanout.resume_generations(total=5)) == [1, 2, 3, 4, 5]
    fanout.checkpoint(1, "state after 1")
    fanout.checkpoint(2, "state after 2")

    assert list(fanout.resume_generations(total=5)) == [3, 4, 5]
    assert capsys.readouterr().err == "resuming after generation 2\n"
    assert len(list(checkpoint_dir.iterdir())) == 1


def test_restore_returns_the_last_checkpointed_state_and_random_state(
    checkpoint_dir: Path,
) -> None:
    random.seed(1234)
    fanout.checkpoint(2, {"population": [0.1, 0.2]})
    draw_after_checkpoint = random.random()
    random.seed(5678)

    state = fanout.restore(initial={"population": [0.0]})

    assert state == {"population": [0.1, 0.2]}
    assert random.random() == draw_after_checkpoint


def test_checkpoint_without_compute_job_checkpoint_dir_names_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COMPUTE_JOB_CHECKPOINT_DIR", raising=False)

    with pytest.raises(RuntimeError, match="COMPUTE_JOB_CHECKPOINT_DIR is not set"):
        fanout.checkpoint(1, "state")
