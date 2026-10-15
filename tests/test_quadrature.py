import itertools
import math
import re
import sys

import pytest

from foundation.quadrature import integrate_trapezoid

# The trapezoid rule's error is C·spacing² + O(spacing⁴): second order.
TRAPEZOID_ORDER = 2

# Numbers of intervals over [0, 1]; each one halves the previous spacing. The
# smallest error, about 3.5e-5 at 64 intervals, is 9 orders of magnitude above
# the round-off in the sum.
INTERVAL_COUNTS = [16, 32, 64]

# For e^x on [0, 1], Euler–Maclaurin gives an error of
# (e - 1)(h²/12 - h⁴/720) + O(h⁶), so the observed order from h to h/2 falls
# short of 2 by about h²/(80 ln 2): 7.0e-5 at the coarsest spacing, h = 1/16.
# This tolerance is about 3 times that.
ORDER_TOLERANCE = 2e-4

# The trapezoid rule is exact for a linear function, so the result differs
# from the integral only by round-off. All terms are positive, so nothing
# cancels, and each term passes through at most 6 roundings in the rule and 3
# in the exact integral, each within half a machine epsilon relative: at most
# 4.5 epsilons in all. This tolerance is about twice that.
ROUND_OFF_TOLERANCE = 8 * sys.float_info.epsilon


def test_trapezoid_error_shrinks_fourfold_when_spacing_halves() -> None:
    # e^x is nonzero at both ends of [0, 1], so a wrong endpoint weight changes
    # the order. On a function that is zero at both ends, such as sin x on
    # [0, π], it wouldn't.
    def error(interval_count: int) -> float:
        spacing = 1 / interval_count
        samples = [math.exp(i * spacing) for i in range(interval_count + 1)]
        return abs(integrate_trapezoid(samples, spacing) - (math.e - 1))

    for coarse_count, fine_count in itertools.pairwise(INTERVAL_COUNTS):
        observed_order = math.log2(error(coarse_count) / error(fine_count))
        assert observed_order == pytest.approx(TRAPEZOID_ORDER, abs=ORDER_TOLERANCE), (
            f"observed order from {coarse_count} to {fine_count} intervals"
        )


def test_trapezoid_is_exact_for_a_linear_function() -> None:
    # 1 interval is 2 samples, the fewest the rule accepts.
    spacing = 0.1
    for interval_count in [1, 2, 4]:
        samples = [1 + 2 * (i * spacing) for i in range(interval_count + 1)]
        length = interval_count * spacing
        exact_integral = length + length**2
        # Without abs=0, approx also accepts its default absolute tolerance,
        # 1e-12, which here is about 1000 times looser.
        assert integrate_trapezoid(samples, spacing) == pytest.approx(
            exact_integral, rel=ROUND_OFF_TOLERANCE, abs=0
        ), f"{interval_count} intervals"


@pytest.mark.parametrize(
    ("samples", "spacing", "message"),
    [
        ([1.0], 1.0, "need at least 2 samples, got 1"),
        ([1.0, 2.0], 0.0, "spacing must be > 0, got 0.0"),
        ([1.0, 2.0], math.nan, "spacing must be > 0, got nan"),
    ],
    ids=["one sample", "zero spacing", "NaN spacing"],
)
def test_trapezoid_rejects_invalid_input_with_a_message_naming_the_value(
    samples: list[float], spacing: float, message: str
) -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        integrate_trapezoid(samples, spacing)
