"""Deterministic parsers for forecast answer contracts."""
from __future__ import annotations

import re

_FINAL_PROBABILITY_RE = re.compile(
    r"Probability\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*%",
    re.IGNORECASE,
)


def extract_last_probability(text: str) -> float:
    """Extract the last explicit ``Probability: N%`` and clamp for Metaculus."""
    matches = _FINAL_PROBABILITY_RE.findall(text)
    if not matches:
        raise ValueError("final Probability: N% answer was not found")
    percentage = float(matches[-1])
    if not 0 <= percentage <= 100:
        raise ValueError("final probability must be between 0 and 100 percent")
    return max(0.01, min(0.99, percentage / 100))
