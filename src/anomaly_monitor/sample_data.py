"""Reproducible public synthetic operational data; no real company information."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd


def generate_sample(output: str | Path, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.date_range("2024-01-01", "2025-12-31", freq="D")
    base = {"A": 120, "B": 85, "C": 155, "D": 200}
    multiplier = {0:.8, 1:.85, 2:.9, 3:1., 4:1.1, 5:1.4, 6:1.1}
    rows = []
    for loc, rate in base.items():
        for day in days:
            # A sustained traffic shift, individual spikes, missing source records.
            factor = 1.25 if loc == "A" and day >= pd.Timestamp("2025-09-01") else 1.0
            traffic = rng.poisson(rate * multiplier[day.day_of_week] * factor)
            opps = rng.poisson(rate * 1.9 * multiplier[day.day_of_week])
            conversions = rng.binomial(opps, .18 if loc != "C" else .14)
            revenue = traffic * max(4, rng.normal(12, 1.5))
            labor = max(0, 14 + .13 * traffic + rng.normal(0, 2))
            expense = 450 + labor*16 + traffic*2.2 + rng.normal(0, 40)
            income = revenue - expense
            if loc == "A" and day == pd.Timestamp("2025-11-17"):
                revenue *= .2
                income = revenue - expense
            if loc == "B" and day == pd.Timestamp("2025-07-08"):
                labor *= 2.5
            for metric, value in (
                ("wash_count", traffic), ("revenue", round(revenue, 2)),
                ("labor_hours", round(labor, 2)), ("operating_income", round(income, 2)),
                ("opportunities", opps), ("conversions", conversions)
            ):
                if loc == "C" and day == pd.Timestamp("2025-04-13"):
                    continue  # genuine missing source rows
                if loc == "D" and day == pd.Timestamp("2024-01-01"):
                    continue  # irregular store series start
                rows.append((day,loc,metric,value))
    df = pd.DataFrame(rows, columns=["period","location_id","metric","value"])
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)
    return df
