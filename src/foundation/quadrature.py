"""Numerical integration of uniformly sampled functions."""

from collections.abc import Sequence


def integrate_trapezoid(samples: Sequence[float], spacing: float) -> float:
    """Integrate uniformly spaced samples of a function with the trapezoid rule.

    For a function with a bounded second derivative the error is O(spacing²),
    so halving ``spacing`` divides the error by about 4.

    Args:
        samples: function values at equally spaced points, in order; at least
            2 values.
        spacing: distance between neighbouring points, in units of the
            integration variable; > 0.

    Returns:
        The integral over the sampled interval, in units of the samples times
        units of ``spacing``.

    Raises:
        ValueError: if ``samples`` has fewer than 2 values, or ``spacing`` is
            not > 0 (including NaN).

    Example:
        >>> integrate_trapezoid([0.0, 1.0, 2.0], spacing=0.5)
        1.0
    """
    if len(samples) < 2:
        raise ValueError(f"need at least 2 samples, got {len(samples)}")
    # `not >` rather than `<=`, so that NaN is rejected too.
    if not spacing > 0:
        raise ValueError(f"spacing must be > 0, got {spacing}")

    endpoint_mean = (samples[0] + samples[-1]) / 2
    return spacing * (endpoint_mean + sum(samples[1:-1]))
