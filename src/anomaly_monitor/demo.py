"""Reproducible wide-format synthetic business data with intentionally unused columns."""
from __future__ import annotations
from tempfile import TemporaryDirectory
from pathlib import Path
import pandas as pd
from .sample_data import generate_sample


def generate_wide_demo(seed:int=42)->pd.DataFrame:
    with TemporaryDirectory() as directory:
        data=generate_sample(Path(directory)/"source.csv",seed=seed)
    wide=data.pivot(index=["period","location_id"],columns="metric",values="value").reset_index()
    wide.columns.name=None
    wide=wide.rename(columns={"period":"BusinessDate","location_id":"StoreID",
        "wash_count":"Washes","revenue":"NetRevenue","labor_hours":"LaborHours",
        "operating_income":"OperatingIncome","opportunities":"Opportunities",
        "conversions":"Conversions"})
    wide["Region"]=wide["StoreID"].map({"A":"West","B":"West","C":"East","D":"East"})
    wide["DataSource"]="synthetic_demo"
    return wide.sort_values(["BusinessDate","StoreID"]).reset_index(drop=True)
