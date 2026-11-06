"""Complete-period-aware aggregation of the finest available CSV observations."""
from __future__ import annotations
import numpy as np
import pandas as pd

PERIOD_ALIASES = {"h":"h", "D":"D", "W-SUN":"W-SUN", "MS":"M", "QS":"Q-DEC", "YS":"Y-DEC"}


def period_labels(timestamps: pd.Series, frequency: str) -> pd.Series:
    if frequency not in PERIOD_ALIASES:
        raise ValueError(f"Unsupported frequency {frequency}")
    return timestamps.dt.to_period(PERIOD_ALIASES[frequency]).dt.start_time


def _full_period_bounds(starts: pd.Series, frequency: str) -> tuple[pd.Series,pd.Series]:
    p = starts.dt.to_period(PERIOD_ALIASES[frequency])
    return p.dt.start_time, p.dt.end_time.dt.floor("D")


def _expected_counts(periods: pd.Series, cfg: dict, frequency: str) -> dict:
    """Expected number of source intervals in each complete target calendar period."""
    source = cfg["input"]["frequency"]
    if frequency == source:
        return {p: 1 for p in periods.unique()}
    starts = pd.Series(periods.unique())
    _, ends = _full_period_bounds(starts, frequency)
    weekdays = set(cfg["calendar"]["active_weekdays"])
    if source in ("D", "h"):
        multiplier = len(cfg["calendar"]["active_hours"]) if source == "h" else 1
        return {start: sum(d.day_of_week in weekdays for d in pd.date_range(start,end,freq="D"))*multiplier
                for start,end in zip(starts,ends)}
    from .ingest import FREQ
    # Calendar month/quarter/year inputs, never allocate weekly records across months.
    source_freq={"W-SUN":"W-MON"}.get(source,FREQ[source])
    return {start: len(pd.date_range(start,end,freq=source_freq)) for start,end in zip(starts,ends)}


def aggregate_complete_periods(regular: pd.DataFrame, cfg: dict, frequency: str) -> pd.DataFrame:
    """Aggregate valid source intervals and preserve denominator/calendar coverage.

    Incomplete periods have `value=NaN`; `partial_value` remains available for review.
    Ratio metrics are recomputed from complete additive component totals.
    """
    source = cfg["input"]["frequency"]
    legal = {
        "h": {"h","D","W-SUN","MS","QS","YS"},
        "D": {"D","W-SUN","MS","QS","YS"},
        "W-SUN": {"W-SUN"},  # calendar weeks cross month/quarter/year boundaries
        "MS": {"MS","QS","YS"},
        "QS": {"QS","YS"},
        "YS": {"YS"},
    }
    if frequency not in legal[source]:
        raise ValueError(f"Cannot safely aggregate {source} source to {frequency} periods")
    df = regular.copy()
    df["reporting_period"] = period_labels(df["period"], frequency)
    grouped = df.groupby(["location_id", "metric", "reporting_period"], sort=True, observed=True)
    agg = grouped.agg(
        observed_intervals=("value", "count"),
        partial_sum=("value", lambda x: x.sum(min_count=1)),
        partial_mean=("value", "mean"),
        partial_last=("value", lambda x: x.dropna().iloc[-1] if x.notna().any() else np.nan),
    ).reset_index().rename(columns={"reporting_period":"period"})
    counts = _expected_counts(agg["period"], cfg, frequency)
    agg["expected_intervals"] = agg["period"].map(counts).astype(int)
    agg["coverage_ratio"] = np.where(agg["expected_intervals"] > 0, agg["observed_intervals"]/agg["expected_intervals"], np.nan)
    agg["is_complete"] = (agg["observed_intervals"] == agg["expected_intervals"]) & (agg["expected_intervals"] > 0)
    agg["aggregation"] = agg["metric"].map({m:s["aggregation"] for m,s in cfg["metrics"].items()})
    agg["partial_value"] = np.select(
        [agg["aggregation"].eq("sum"), agg["aggregation"].eq("mean"), agg["aggregation"].eq("last")],
        [agg["partial_sum"], agg["partial_mean"], agg["partial_last"]], default=np.nan
    )
    agg["value"] = agg["partial_value"].where(agg["is_complete"])
    agg["quality_status"] = np.where(agg["is_complete"], "complete", "incomplete_period")
    core_cols = ["location_id","metric","period","value","partial_value","observed_intervals","expected_intervals","coverage_ratio","is_complete","quality_status","aggregation"]
    agg = agg[core_cols].copy()

    ratios = []
    for metric, spec in cfg["metrics"].items():
        if spec["aggregation"] != "ratio":
            continue
        numerator = agg.loc[agg["metric"] == spec["numerator"]].drop(columns=["metric", "aggregation"])
        denominator = agg.loc[agg["metric"] == spec["denominator"]].drop(columns=["metric", "aggregation"])
        joined = numerator.merge(denominator, on=["location_id", "period"], how="outer", suffixes=("_num", "_den"), validate="one_to_one")
        if joined.empty:
            continue
        complete = joined["is_complete_num"].fillna(False).astype(bool) & joined["is_complete_den"].fillna(False).astype(bool)
        denominator_valid = (joined["value_den"].notna() & joined["value_den"].ne(0))
        usable = complete & denominator_valid
        # Incomplete ratio components cannot be treated as a valid ratio.
        numerator_observed = joined["observed_intervals_num"].fillna(0)
        denominator_observed = joined["observed_intervals_den"].fillna(0)
        ratio = pd.DataFrame({
            "location_id": joined["location_id"],
            "metric": metric,
            "period": joined["period"],
            "value": (joined["value_num"] / joined["value_den"].where(joined["value_den"].ne(0)) * float(spec.get("multiplier", 1))).where(usable),
            "partial_value": np.nan,
            "observed_intervals": np.minimum(numerator_observed, denominator_observed),
            "expected_intervals": joined["expected_intervals_num"].fillna(joined["expected_intervals_den"]),
            "coverage_ratio": np.minimum(joined["coverage_ratio_num"], joined["coverage_ratio_den"]),
            "is_complete": complete,
            "quality_status": np.select([~complete, ~denominator_valid],["incomplete_component", "zero_denominator"], default="complete"),
            "aggregation": "ratio",
        })
        ratios.append(ratio[core_cols])
    if ratios:
        agg = pd.concat([agg] + ratios, ignore_index=True)
    return agg.sort_values(["location_id", "metric", "period"]).reset_index(drop=True)
