"""Validate source observations and build an explicit expected reporting calendar."""
from __future__ import annotations
from itertools import product
import numpy as np
import pandas as pd

COLUMNS = ("period", "location_id", "metric", "value")


def read_observations(cfg: dict) -> pd.DataFrame:
    inp = cfg["input"]
    df = pd.read_csv(inp["path"])
    mapping = inp.get("columns", {})
    rename = {mapping.get(col, col): col for col in COLUMNS}
    df = df.rename(columns=rename)
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing input columns: {sorted(missing)}")
    df = df[list(COLUMNS)].copy()
    if df.empty:
        raise ValueError("Input CSV has no observations")
    try:
        df["period"] = pd.to_datetime(df["period"], errors="raise")
    except Exception as exc:
        raise ValueError("Invalid period/date values") from exc
    if df["period"].dt.tz is not None:
        raise ValueError("v0.1 requires consistent timezone-naive timestamps; normalize upstream")
    if df[["period", "location_id", "metric"]].isna().any().any():
        raise ValueError("Period, location_id, and metric are mandatory")
    df["location_id"] = df["location_id"].astype(str)
    df["metric"] = df["metric"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="raise")
    if np.isinf(df["value"]).any():
        raise ValueError("Infinite values are invalid")
    if df.duplicated(["period", "location_id", "metric"]).any():
        dup = df.loc[df.duplicated(["period","location_id","metric"]),list(COLUMNS)].head(2)
        raise ValueError(f"Duplicate location/metric/time rows: {dup.to_dict('records')}")
    raw_metrics = {m for m,s in cfg["metrics"].items() if s["aggregation"] != "ratio"}
    unknown = set(df["metric"]) - raw_metrics
    if unknown:
        raise ValueError(f"Input contains unconfigured or derived metrics: {sorted(unknown)}")
    freq = cfg["input"]["frequency"]
    aligned = df["period"].dt.floor("h" if freq == "h" else "D")
    if not df["period"].eq(aligned).all():
        raise ValueError("Input intervals must start at exact hour or midnight, per input.frequency")
    for metric, spec in cfg["metrics"].items():
        if spec.get("detector") == "poisson" and metric in raw_metrics:
            values = df.loc[df["metric"] == metric, "value"].dropna()
            if ((values < 0) | (values % 1 != 0)).any():
                raise ValueError(f"Poisson count metric {metric} must be nonnegative integer-valued")
    return df.sort_values(["location_id","metric","period"]).reset_index(drop=True)


def expected_timestamps(cfg: dict, data: pd.DataFrame) -> pd.DatetimeIndex:
    """Expected source intervals, not fabricated numeric observations.

    An explicit calendar.start/end can extend beyond available rows. Weekly/monthly
    source dates must already be starts of their periods.
    """
    cal = cfg["calendar"]
    freq = cfg["input"]["frequency"]
    timestamps = pd.to_datetime(data["period"], errors="raise")
    earliest = pd.Timestamp(timestamps.min())
    latest = pd.Timestamp(timestamps.max())
    start = pd.Timestamp(cal.get("start") or earliest).normalize()
    end = pd.Timestamp(cal.get("end") or latest).normalize()
    if end < start:
        raise ValueError("calendar.end precedes calendar.start")
    if start > earliest or end < latest.normalize():
        raise ValueError("calendar range excludes observed data")
    if freq in ("D", "h"):
        days = pd.date_range(start, end, freq="D")
        days = days[days.day_of_week.isin(cal["active_weekdays"])]
        if freq == "D":
            expected = days
        else:
            hours = pd.to_timedelta(cal["active_hours"], unit="h")
            expected = pd.DatetimeIndex([d+h for d in days for h in hours])
    else:
        from .aggregation import period_labels
        from .ingest import FREQ
        begins = period_labels(pd.Series([start]), freq).iloc[0]
        expected = pd.date_range(begins, end, freq={"W-SUN":"W-MON"}.get(freq, FREQ[freq]))
    if len(expected) > 2_000_000:
        raise ValueError("Expected calendar exceeds 2 million source intervals")
    return pd.DatetimeIndex(expected, name="period")


def regularize_observations(data: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (complete expected source grid, source quality issues).

    Missing source rows and explicit NaN values remain NaN; never impute zero.
    Dates outside the configured operating schedule are reported and excluded.
    """
    data = data.copy()
    data["period"] = pd.to_datetime(data["period"], errors="raise")
    data["value"] = pd.to_numeric(data["value"], errors="raise")
    if data.duplicated(["period", "location_id", "metric"]).any():
        raise ValueError("Duplicate location/metric/time rows")
    expected = expected_timestamps(cfg, data)
    if not len(expected):
        raise ValueError("Calendar defines no expected reporting intervals")
    out_of_calendar = data.loc[~data["period"].isin(expected)].copy()
    out_of_calendar["quality_issue"] = "outside_reporting_calendar"
    valid = data.loc[data["period"].isin(expected)].copy()
    locations = sorted(data["location_id"].unique())
    metrics = [k for k, v in cfg["metrics"].items() if v["aggregation"] != "ratio"]
    n_expected = len(expected) * len(locations) * len(metrics)
    if n_expected > 3_000_000:
        raise ValueError("Expected input grid too large; narrow the calendar")
    grid = pd.MultiIndex.from_product(
        [locations, metrics, expected],
        names=["location_id", "metric", "period"]
    ).to_frame(index=False)
    merged = grid.merge(valid, on=["location_id","metric","period"], how="left", indicator=True, validate="one_to_one")
    merged["data_status"] = np.select(
        [merged["_merge"].eq("left_only"), merged["value"].isna()],
        ["missing_row", "missing_value"],
        default="observed"
    )
    issues = merged.loc[merged["data_status"] != "observed", list(COLUMNS) + ["data_status"]].copy()
    issues = issues.rename(columns={"data_status": "quality_issue"})
    if not out_of_calendar.empty:
        out_of_calendar = out_of_calendar[list(COLUMNS) + ["quality_issue"]]
        issues = pd.concat([issues, out_of_calendar], ignore_index=True)
    merged = merged.drop(columns="_merge")
    return merged.sort_values(["location_id","metric","period"]).reset_index(drop=True), issues
