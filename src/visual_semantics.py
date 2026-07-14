"""Shared action-oriented color semantics for dashboard and report figures.

The thresholds are relative within each displayed comparison.  They identify
where to investigate first; they are not business targets or causal effects.
"""
from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


IMPROVE = "优先改进"
WATCH = "需要关注"
GOOD = "表现较好"
DESCRIPTIVE = "描述性"

IMPROVE_RED = "#DC2626"
WATCH_AMBER = "#F59E0B"
GOOD_GREEN = "#16A34A"
NEUTRAL_BLUE = "#2563EB"
MUTED_GRAY = "#94A3B8"

STATUS_ORDER = [IMPROVE, WATCH, GOOD]
STATUS_COLORS = {
    IMPROVE: IMPROVE_RED,
    WATCH: WATCH_AMBER,
    GOOD: GOOD_GREEN,
    DESCRIPTIVE: NEUTRAL_BLUE,
}


def classify_relative(values: Iterable[float], direction: str = "higher") -> list[str]:
    """Classify values into relative action tiers.

    ``direction`` describes which direction is operationally preferable:
    ``higher`` for conversion, coverage, and score; ``lower`` for delay,
    complaint, conflict, and action-priority measures.
    """
    if direction not in {"higher", "lower"}:
        raise ValueError("direction must be 'higher' or 'lower'")
    series = pd.to_numeric(pd.Series(list(values)), errors="coerce")
    valid = series.dropna()
    if valid.empty:
        return [DESCRIPTIVE] * len(series)
    low = float(valid.quantile(1 / 3))
    high = float(valid.quantile(2 / 3))
    if np.isclose(low, high):
        return [WATCH if pd.notna(value) else DESCRIPTIVE for value in series]

    labels: list[str] = []
    for value in series:
        if pd.isna(value):
            labels.append(DESCRIPTIVE)
        elif direction == "higher":
            labels.append(IMPROVE if value <= low else GOOD if value >= high else WATCH)
        else:
            labels.append(IMPROVE if value >= high else GOOD if value <= low else WATCH)
    return labels


def colors_for(values: Iterable[float], direction: str = "higher") -> list[str]:
    return [STATUS_COLORS[label] for label in classify_relative(values, direction)]


def semantic_colorscale(direction: str = "higher") -> list[list[object]]:
    if direction == "higher":
        return [[0.0, IMPROVE_RED], [0.5, WATCH_AMBER], [1.0, GOOD_GREEN]]
    if direction == "lower":
        return [[0.0, GOOD_GREEN], [0.5, WATCH_AMBER], [1.0, IMPROVE_RED]]
    raise ValueError("direction must be 'higher' or 'lower'")
