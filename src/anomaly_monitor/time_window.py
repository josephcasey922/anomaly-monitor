"""Presentation-only date windows; detections are always computed on full history."""
from __future__ import annotations

import pandas as pd

# Periods relative to the newest observation in the selected data, not wall time.
PRESET_DAYS = {
    "Last 24 hours": 1,
    "Last 7 days": 7,
    "Last 30 days": 30,
    "Last 90 days": 90,
    "Last 365 days": 365,
    "Last 2 years": 730,
}
PRESET_CHOICES = list(PRESET_DAYS) + ["All dates", "Custom dates"]


def default_preset(frequency: str) -> str:
    return {
        "h": "Last 7 days",
        "D": "Last 90 days",
        "W-SUN": "Last 365 days",
        "MS": "Last 2 years",
        "QS": "All dates",
        "YS": "All dates",
    }.get(frequency, "Last 90 days")


def resolve_window(periods, preset: str, *, start=None, end=None):
    """Inclusive timestamp boundaries, using the data's actual latest timestamp.

    On custom dates, end is inclusive as a calendar date. For presets,
    the right boundary is the latest available reporting period.
    """
    dates = pd.to_datetime(pd.Series(periods).dropna())
    if dates.empty:
        raise ValueError("Cannot select a range without observations")
    first, last = dates.min(), dates.max()
    if preset == "All dates":
        return first, last
    if preset == "Custom dates":
        if start is None or end is None:
            raise ValueError("Custom dates require both start and end")
        lo = pd.Timestamp(start).normalize()
        hi = pd.Timestamp(end).normalize() + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        if lo > hi:
            raise ValueError("Start date must not exceed end date")
        return lo, hi
    if preset not in PRESET_DAYS:
        raise ValueError(f"Unknown preset: {preset}")
    return max(first, last - pd.Timedelta(days=PRESET_DAYS[preset])), last


def restrict_dates(frame: pd.DataFrame, lo, hi, *, column="period") -> pd.DataFrame:
    if frame.empty or column not in frame:
        return frame.copy()
    periods = pd.to_datetime(frame[column])
    return frame.loc[periods.between(lo, hi)].copy()
