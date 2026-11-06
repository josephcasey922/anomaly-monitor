"""Two-sided point detection, and an exploratory clipped two-sided CUSUM."""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import poisson


def point_detection(data: pd.DataFrame, method: str, z_threshold: float, poisson_alpha: float) -> pd.DataFrame:
    df = data.copy()
    df["point_method"] = method
    df["score"] = np.nan
    df["p_value"] = np.nan
    df["point_alert"] = False
    if method == "zscore":
        good = df["observed"].notna() & df["expected"].notna() & df["scale"].gt(0) & np.isfinite(df["scale"])
        df.loc[good, "score"] = (df.loc[good, "observed"] - df.loc[good, "expected"]) / df.loc[good, "scale"]
        df.loc[good, "point_alert"] = df.loc[good, "score"].abs().ge(z_threshold)
    elif method == "poisson":
        good = df["observed"].notna() & df["expected"].gt(0) & np.isfinite(df["expected"]) & df["observed"].ge(0) & df["observed"].mod(1).eq(0)
        y = df.loc[good, "observed"].to_numpy()
        mu = df.loc[good, "expected"].to_numpy()
        p = np.minimum(1.0, 2 * np.minimum(poisson.cdf(y, mu), poisson.sf(y - 1, mu)))
        df.loc[good, "p_value"] = p
        df.loc[good, "score"] = (y - mu) / np.sqrt(mu)
        df.loc[good, "point_alert"] = p <= poisson_alpha
    else:
        raise ValueError("Unknown point detector")
    df["direction"] = np.select(
        [df["point_alert"] & df["score"].gt(0), df["point_alert"] & df["score"].lt(0)],
        ["above", "below"], default="none"
    )
    df["deviation"] = df["observed"] - df["expected"]
    df["deviation_pct"] = 100 * df["deviation"] / df["expected"].where(df["expected"].ne(0))
    df["scoring_status"] = np.select(
        [~df["is_complete"], df["observed"].isna(), df["expected"].isna(), df["score"].isna()],
        ["incomplete_period", "undefined_metric", "insufficient_history", "undefined_scale_or_model"],
        default="scored"
    )
    return df


def add_cusum(data: pd.DataFrame, *, enabled: bool, horizon: str, k: float, h: float, score_cap: float) -> pd.DataFrame:
    df = data.copy().sort_values(["location_id", "metric", "frequency", "horizon", "period"]).reset_index(drop=True)
    df["cusum_up"] = np.nan
    df["cusum_down"] = np.nan
    df["cusum_alert"] = False
    df["cusum_direction"] = "none"
    if not enabled:
        return df
    groups = df.groupby(["location_id", "metric", "frequency", "horizon"], sort=False)
    for (_, _, _, current_horizon), group in groups:
        if current_horizon != horizon:
            continue
        up = down = 0.0
        was_up = was_down = False
        for idx in group.index:
            z = df.at[idx, "score"]
            if not np.isfinite(z) or df.at[idx, "scoring_status"] != "scored":
                up = down = 0.0
                was_up = was_down = False
                continue
            clipped = float(np.clip(z, -score_cap, score_cap))
            up = max(0.0, up + clipped - k)
            down = max(0.0, down - clipped - k)
            df.at[idx, "cusum_up"] = up
            df.at[idx, "cusum_down"] = down
            now_up, now_down = up >= h, down >= h
            new_up, new_down = now_up and not was_up, now_down and not was_down
            if new_up or new_down:
                df.at[idx, "cusum_alert"] = True
                df.at[idx, "cusum_direction"] = "both" if new_up and new_down else "upward_shift" if new_up else "downward_shift"
            was_up, was_down = now_up, now_down
    return df
