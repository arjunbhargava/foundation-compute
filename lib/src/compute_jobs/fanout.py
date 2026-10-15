"""Spread a search's evaluations over every node of a ``search`` job, and resume it after a restart.

In a ``search`` job the wrapper starts Ray on every node and runs the command
on rank 0. Each generation, ``map`` sends one Ray task per candidate and
``checkpoint`` saves the search's state. A preempted node restarts the whole
job, and ``restore`` and ``resume_generations`` continue after the last saved
generation. With ``COMPUTE_JOB_SMOKE=1``, as in dry-run, nothing uses Ray.

Example:
    Three generations of a search that keeps each generation's best fitness,
    run serially as dry-run's smoke test runs it:

    >>> import tempfile
    >>> from unittest import mock
    >>> from compute_jobs import fanout
    >>> checkpoint_dir = tempfile.mkdtemp()
    >>> with mock.patch.dict(
    ...     "os.environ", COMPUTE_JOB_SMOKE="1", COMPUTE_JOB_CHECKPOINT_DIR=checkpoint_dir
    ... ):
    ...     best_per_generation = fanout.restore(initial=[])
    ...     for generation in fanout.resume_generations(total=3):
    ...         candidates = [generation - 2, generation, generation + 1]
    ...         fitness = fanout.map(lambda x: -(x**2), candidates)
    ...         best_per_generation.append(max(fitness))
    ...         fanout.checkpoint(generation, best_per_generation)
    >>> best_per_generation
    [-1, 0, -1]
"""

import os
import pickle
import random
import sys
import traceback
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

# The user Ray cluster that the wrapper starts on every node of a search job.
# Never "auto": that can find SkyPilot's own Ray, on port 6380.
RAY_ADDRESS = "localhost:6379"


class Evaluations(list[Any]):
    """The results of one ``map`` call, in the candidates' order; a failed evaluation's is ``None``.

    Attributes:
        failed: How many evaluations raised an exception, or were lost with
            their Ray worker or node.
    """

    def __init__(self, results: Iterable[Any], failed: int) -> None:
        super().__init__(results)
        self.failed = failed


def map(
    evaluate: Callable[[Any], Any],
    candidates: Sequence[Any],
    *,
    gpus_per_evaluation: float = 0,
    cpus_per_evaluation: float = 1,
) -> Evaluations:
    """Evaluate every candidate, in parallel on the job's Ray cluster.

    Each evaluation is one Ray task, which Ray places on any node with the
    resources free. With ``COMPUTE_JOB_SMOKE=1`` the candidates are instead
    evaluated one after another in this process, without Ray. A failed
    evaluation doesn't stop the others: its result is ``None``, it is counted
    in ``failed``, and the first failure's traceback is printed to stderr,
    since Ray workers' own output isn't forwarded to the driver.

    Args:
        evaluate: Called once per candidate. Ray pickles it with cloudpickle
            and runs it in a worker process, so it must not depend on state
            the driver changes after the call.
        candidates: The inputs to evaluate.
        gpus_per_evaluation: GPUs each evaluation reserves, >= 0; a fraction,
            such as 0.25, shares a GPU.
        cpus_per_evaluation: CPUs each evaluation reserves, >= 0.

    Returns:
        One result per candidate, in the candidates' order.

    Raises:
        ValueError: ``gpus_per_evaluation`` or ``cpus_per_evaluation`` is
            negative, checked with ``COMPUTE_JOB_SMOKE=1`` too.
        RuntimeError: Ray isn't installed, or no Ray cluster answers at
            ``RAY_ADDRESS``, after Ray's retries (821 s with Ray 2.59.0).
            Neither applies with ``COMPUTE_JOB_SMOKE=1``.

    Example:
        >>> from unittest import mock
        >>> with mock.patch.dict("os.environ", {"COMPUTE_JOB_SMOKE": "1"}):
        ...     map(abs, [-2, 3, -1])
        [2, 3, 1]
    """
    if gpus_per_evaluation < 0 or cpus_per_evaluation < 0:
        raise ValueError(
            f"gpus_per_evaluation is {gpus_per_evaluation} and cpus_per_evaluation is "
            f"{cpus_per_evaluation}; each must be >= 0."
        )

    if os.environ.get("COMPUTE_JOB_SMOKE") == "1":
        results, errors = _evaluate_serially(evaluate, candidates)
    else:
        results, errors = _evaluate_on_ray(
            evaluate, candidates, gpus_per_evaluation, cpus_per_evaluation
        )

    if errors:
        first_failure = "".join(traceback.format_exception(errors[0]))
        print(
            f"{len(errors)} of {len(candidates)} evaluations failed; their results are "
            f"None. The first failure:\n{first_failure}",
            file=sys.stderr,
            flush=True,
        )
    return Evaluations(results, failed=len(errors))


def checkpoint(generation: int, state: object) -> None:
    """Save the search's state after a generation, replacing the last checkpoint.

    It saves Python's ``random`` module state too. It writes a temporary file
    and renames it, so a preemption mid-write leaves the last checkpoint whole.

    Args:
        generation: The generation just finished, from ``resume_generations``.
        state: Everything the search needs to continue, such as the
            optimizer and its population; it must pickle.

    Raises:
        RuntimeError: ``COMPUTE_JOB_CHECKPOINT_DIR`` isn't set.
        pickle.PicklingError: ``state`` can't be pickled.

    Example:
        >>> import tempfile
        >>> from unittest import mock
        >>> with mock.patch.dict("os.environ", COMPUTE_JOB_CHECKPOINT_DIR=tempfile.mkdtemp()):
        ...     checkpoint(4, {"population": [0.5, 0.7]})
        ...     list(resume_generations(total=6))
        [5, 6]
    """
    saved = {
        "generation": generation,
        "state": state,
        "random_state": random.getstate(),
    }
    path = _checkpoint_path()
    partial_path = path.with_name(path.name + ".partial")
    partial_path.write_bytes(pickle.dumps(saved))
    os.replace(partial_path, path)


def restore(initial: Any) -> Any:
    """Return the state the last checkpoint saved, or ``initial`` if there is none.

    It also restores Python's ``random`` module state from the checkpoint.

    Args:
        initial: The state a search starts from.

    Returns:
        The checkpointed state, unpickled, or ``initial``.

    Raises:
        RuntimeError: ``COMPUTE_JOB_CHECKPOINT_DIR`` isn't set.

    Unpickling runs code, so ``$COMPUTE_JOB_CHECKPOINT_DIR`` must hold only
    what this job's own ``checkpoint`` calls wrote.

    Example:
        >>> import tempfile
        >>> from unittest import mock
        >>> with mock.patch.dict("os.environ", COMPUTE_JOB_CHECKPOINT_DIR=tempfile.mkdtemp()):
        ...     before = restore(initial="new search")
        ...     checkpoint(1, "after generation 1")
        ...     after = restore(initial="new search")
        >>> before, after
        ('new search', 'after generation 1')
    """
    saved = _load_checkpoint()
    if saved is None:
        return initial

    random.setstate(saved["random_state"])
    return saved["state"]


def resume_generations(total: int) -> range:
    """Return the generations still to run, after the last checkpointed one.

    Without a checkpoint they are 1 to ``total``. After one, they start at the
    next generation, and ``resuming after generation <n>`` is printed to
    stderr.

    Args:
        total: The search's number of generations, >= 0.

    Returns:
        The generation numbers to run, in order; empty if the last
        checkpoint is at or past ``total``.

    Raises:
        RuntimeError: ``COMPUTE_JOB_CHECKPOINT_DIR`` isn't set.

    Example:
        >>> import tempfile
        >>> from unittest import mock
        >>> with mock.patch.dict("os.environ", COMPUTE_JOB_CHECKPOINT_DIR=tempfile.mkdtemp()):
        ...     list(resume_generations(total=3))
        [1, 2, 3]
    """
    saved = _load_checkpoint()
    if saved is None:
        return range(1, total + 1)

    last_generation: int = saved["generation"]
    print(f"resuming after generation {last_generation}", file=sys.stderr, flush=True)
    return range(last_generation + 1, total + 1)


def _evaluate_serially(
    evaluate: Callable[[Any], Any], candidates: Sequence[Any]
) -> tuple[list[Any], list[BaseException]]:
    results: list[Any] = []
    errors: list[BaseException] = []
    for candidate in candidates:
        try:
            results.append(evaluate(candidate))
        except Exception as error:  # noqa: BLE001 -- Ray fails a task on any exception, too
            results.append(None)
            errors.append(error)
    return results, errors


def _evaluate_on_ray(
    evaluate: Callable[[Any], Any],
    candidates: Sequence[Any],
    gpus_per_evaluation: float,
    cpus_per_evaluation: float,
) -> tuple[list[Any], list[BaseException]]:
    try:
        import ray
        from ray.exceptions import RayError
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Ray isn't installed; add \"compute-jobs[fanout]\" to the project's dependencies, "
            "or set COMPUTE_JOB_SMOKE=1 to run the evaluations serially."
        ) from error

    if not ray.is_initialized():
        try:
            # ray.init's **kwargs are unannotated.
            ray.init(address=RAY_ADDRESS, log_to_driver=False)  # pyright: ignore[reportUnknownMemberType]
        except ConnectionError as error:
            raise RuntimeError(
                f"No Ray cluster answered at {RAY_ADDRESS}. In a search job the wrapper "
                "starts one on every node; elsewhere, set COMPUTE_JOB_SMOKE=1 to run "
                "the evaluations serially."
            ) from error

    # ray.remote takes only a function defined in Python, not a builtin such
    # as abs or a functools.partial, so it gets this wrapper.
    def evaluate_one(candidate: Any) -> Any:
        return evaluate(candidate)

    remote_evaluate = ray.remote(
        num_gpus=gpus_per_evaluation, num_cpus=cpus_per_evaluation
    )(evaluate_one)
    pending = [remote_evaluate.remote(candidate) for candidate in candidates]

    results: list[Any] = []
    errors: list[BaseException] = []
    for reference in pending:
        try:
            results.append(ray.get(reference))
        except RayError as error:
            results.append(None)
            errors.append(error)
    return results, errors


def _load_checkpoint() -> dict[str, Any] | None:
    path = _checkpoint_path()
    if not path.exists():
        return None
    return pickle.loads(path.read_bytes())


def _checkpoint_path() -> Path:
    directory = os.environ.get("COMPUTE_JOB_CHECKPOINT_DIR")
    if not directory:
        raise RuntimeError(
            "COMPUTE_JOB_CHECKPOINT_DIR is not set, so fanout has nowhere to keep its "
            "checkpoint. A job's wrapper sets it; to run elsewhere, set it to a directory."
        )
    return Path(directory) / "fanout-checkpoint.pickle"
