"""Leakage-free rolling reference distributions, aligned to comparable periods."""
from __future__ import annotations
import math
import numpy as np
import pandas as pd


def estimate_reference(data: pd.DataFrame, frequency: str, window: int, min_history: int | None = None) -> pd.DataFrame:
    """Use past comparable complete periods only, never the current value.

    For hourly: same weekday + hour in prior weeks.
    For daily: same weekday in prior weeks.
    For other resolutions: the previous complete calendar periods.
    Missing/incomplete periods remain in their correct positions.
    """
    if window < 2:
        raise ValueError("window must be at least 2")
    if min_history is None:
        min_history = window
    if not 2 <= min_history <= window:
        raise ValueError("Invalid min_history")
    result = data.copy()
    result["period"] = pd.to_datetime(result["period"])
    result = result.sort_values(["location_id", "metric", "period"]).reset_index(drop=True)
    result["observed"] = result["value"].where(result["is_complete"] & result["quality_status"].eq("complete"))
    grouping = ["location_id", "metric"]
    if frequency in ("D", "h"):
        result["weekday"] = result["period"].dt.day_of_week
        grouping.append("weekday")
    if frequency == "h":
        result["hour"] = result["period"].dt.hour
        grouping.append("hour")
    series = result.groupby(grouping, sort=False)["observed"]
    result["expected"] = series.transform(lambda x: x.shift(1).rolling(window, min_periods=min_history).mean())
    result["scale"] = series.transform(lambda x: x.shift(1).rolling(window, min_periods=min_history).std(ddof=1))
    result["history_count"] = series.transform(lambda x: x.shift(1).rolling(window, min_periods=1).count()).fillna(0).astype(int)
    return result.drop(columns=["weekday", "hour"], errors="ignore")
