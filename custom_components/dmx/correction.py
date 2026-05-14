"""Output correction curves for DMX intensity channels."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

type CurveFunction = Callable[[float], float]

# Each entry is (forward, inverse) — both map [0, 1] → [0, 1]
AVAILABLE_CURVES: dict[str, tuple[CurveFunction, CurveFunction]] = {
    "linear": (lambda x: x, lambda x: x),
    "quadratic": (lambda x: x * x, math.sqrt),
    "cubic": (lambda x: x**3, lambda x: x ** (1 / 3)),
    "quartic": (lambda x: x**4, lambda x: x**0.25),
    "sine": (lambda x: 1 - math.cos(x * math.pi / 2), lambda x: math.acos(1 - x) * 2 / math.pi),
}


@dataclass
class OutputCorrection:
    curve_name: str = "linear"
    min_value: float = 0.0  # DMX floor when ON (fraction 0–1)
    max_value: float = 1.0  # DMX ceiling (fraction 0–1)

    def apply(self, t: float) -> float:
        """Map intended intensity t ∈ [0,1] to corrected DMX fraction.

        Zero always returns zero so the light turns fully off.
        """
        if t == 0.0:
            return 0.0
        forward, _ = AVAILABLE_CURVES[self.curve_name]
        return self.min_value + forward(t) * (self.max_value - self.min_value)

    def invert(self, corrected_t: float) -> float:
        """Map a corrected DMX fraction back to the intended intensity in [0,1].

        Zero returns zero. Values below min_value (but non-zero) map to the
        smallest representable on-value so the light is not silently shown as off.
        """
        if corrected_t <= 0.0:
            return 0.0
        _, inverse = AVAILABLE_CURVES[self.curve_name]
        y = (corrected_t - self.min_value) / (self.max_value - self.min_value)
        if y <= 0.0:
            # Below the floor but non-zero — light is physically on at minimum.
            return 1.0 / 255.0
        return min(1.0, inverse(min(1.0, y)))


def parse_output_correction(config: str | dict | None) -> OutputCorrection | None:
    """Parse output_correction from YAML config (string shorthand or full dict)."""
    if config is None:
        return None
    if isinstance(config, str):
        return OutputCorrection(curve_name=config)
    curve_name = config.get("curve", "linear")
    return OutputCorrection(
        curve_name=curve_name,
        min_value=float(config.get("min", 0.0)),
        max_value=float(config.get("max", 1.0)),
    )
