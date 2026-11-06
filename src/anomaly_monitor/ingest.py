"""Conservative schema adapter: unfamiliar columns are ignored, never guessed silently."""
from __future__ import annotations
import re
import numpy as np
import pandas as pd

FREQ = {"h":"h", "D":"D", "W-SUN":"W-SUN", "MS":"MS", "QS":"QS", "YS":"YS"}

def profile_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Provide UI suggestions, not authoritative semantic interpretations."""
    rows = []
    for col in df.columns:
        series = df[col]
        numeric = pd.to_numeric(series, errors="coerce")
        nonempty = series.notna().sum()
        name = str(col).lower()
        suggestion = ("timestamp" if any(x in name for x in ("date","time","timestamp")) else
                      "location" if any(x in name for x in ("location","store","site","branch")) else
                      "numeric" if nonempty and numeric.notna().sum()/nonempty > .90 else "ignore")
        rows.append({"column":str(col),"dtype":str(series.dtype),"nonnull":int(nonempty),
                     "unique":int(series.nunique(dropna=True)),"suggested_role":suggestion,
                     "example":str(series.dropna().iloc[0])[:60] if nonempty else ""})
    return pd.DataFrame(rows)


def normalize_source(frame: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Return period, location_id, metric, value at the configured *source* grain.

    source_schema.mode: wide or long. row_grain: period or transaction.
    source_schema.metrics maps internal metric names -> CSV/SQL column name in wide mode.
    When row_grain=transaction, multiple records are consolidated by each metric's
    input_reducer; period-grain duplicate keys are rejected, not silently summed.
    """
    if frame.empty:
        raise ValueError("Input data has no rows")
    inp=cfg["input"]
    spec=cfg.get("source_schema", {})
    mode=spec.get("mode","long")
    freq=inp.get("frequency","D")
    if freq not in FREQ:
        raise ValueError(f"Unsupported input frequency: {freq}")
    date_col=spec.get("timestamp_column", inp.get("columns",{}).get("period","period"))
    site_col=spec.get("location_column", inp.get("columns",{}).get("location_id","location_id"))
    if date_col not in frame:
        raise ValueError(f"Timestamp column '{date_col}' not found")
    dates=pd.to_datetime(frame[date_col], errors="coerce")
    if dates.isna().any():
        raise ValueError(f"Invalid/null timestamps: {int(dates.isna().sum())} rows")
    if dates.dt.tz is not None:
        raise ValueError("Normalize timezone-aware timestamps to one local calendar before import (DST policy required)")
    source=frame.copy()
    source["__period__"]=dates
    if site_col and site_col in source:
        if source[site_col].isna().any():
            raise ValueError("Null location identifiers")
        source["__location__"]=source[site_col].astype(str)
    elif not site_col or site_col=="(single location)":
        source["__location__"]=spec.get("default_location","All")
    else:
        raise ValueError(f"Location column '{site_col}' not found; select single-location mode if appropriate")
    if spec.get("row_grain","period") not in ("period","transaction"):
        raise ValueError("row_grain must be period or transaction")
    if spec.get("row_grain","period")=="transaction":
        if freq not in ("h","D"):
            raise ValueError("Transaction timestamps must be binned to hours or days")
        source["__period__"]=source["__period__"].dt.floor(freq)
    elif freq in ("h","D"):
        if not source["__period__"].eq(source["__period__"].dt.floor(freq)).all():
            raise ValueError("Period-grain rows must have aligned timestamps; select transaction mode to bin timestamps")
    else:
        from .aggregation import period_labels
        if not source["__period__"].eq(period_labels(source["__period__"],freq)).all():
            raise ValueError("Source periods must be labeled by their starts")
    if mode=="wide":
        metrics=spec.get("metrics",{})
        if not isinstance(metrics,dict) or not metrics:
            raise ValueError("Wide format requires source_schema.metrics mapping")
        columns=[]
        for metric,col in metrics.items():
            if metric not in cfg["metrics"]:
                raise ValueError(f"Unconfigured metric: {metric}")
            if cfg["metrics"][metric]["aggregation"]=="ratio":
                raise ValueError(f"Ratio metric {metric} must be derived from components, not directly imported")
            if col not in source:
                raise ValueError(f"Selected metric column '{col}' not found")
            columns.append(col)
        if len(set(columns)) != len(columns):
            raise ValueError("A source column cannot map to multiple metric definitions")
        chunks=[]
        for metric,col in metrics.items():
            one=source[["__period__","__location__",col]].copy()
            one.columns=["period","location_id","value"]
            one["metric"]=metric
            chunks.append(one)
        normalized=pd.concat(chunks,ignore_index=True)
    elif mode=="long":
        cols=inp.get("columns",{})
        metcol=spec.get("metric_column",cols.get("metric","metric"))
        valcol=spec.get("value_column",cols.get("value","value"))
        if metcol not in source or valcol not in source:
            raise ValueError("Long-format metric/value columns not found")
        normalized=source[["__period__","__location__",metcol,valcol]].copy()
        normalized.columns=["period","location_id","metric","value"]
        # Optional aliases allow import from unfamiliar metric labels.
        normalized["metric"]=normalized["metric"].astype(str).replace(spec.get("metric_aliases",{}))
        configured={m for m,s in cfg["metrics"].items() if s["aggregation"]!="ratio"}
        normalized=normalized.loc[normalized["metric"].isin(configured)].copy()
    else:
        raise ValueError("source_schema.mode must be wide or long")
    if normalized.empty:
        raise ValueError("No selected metric rows found")
    original=normalized["value"]
    normalized["value"]=pd.to_numeric(original,errors="coerce")
    bad=original.notna() & normalized["value"].isna()
    if bad.any() or np.isinf(normalized["value"]).any():
        raise ValueError(f"Non-numeric or infinite metric values in {int(bad.sum())} rows")
    dupcols=["period","location_id","metric"]
    if spec.get("row_grain","period")=="period":
        if normalized.duplicated(dupcols).any():
            raise ValueError("Duplicate period/location/metric rows: use transaction mode only if duplicate rows are legitimate")
    else:
        reducers={m:cfg["metrics"][m].get("input_reducer","sum") for m in normalized["metric"].unique()}
        invalid=set(reducers.values())-{"sum","mean","last","count"}
        if invalid:
            raise ValueError(f"Unsupported transaction reducers: {invalid}")
        pieces=[]
        for metric,group in normalized.groupby("metric",sort=False):
            reducer=reducers[metric]
            agg=group.groupby(dupcols,as_index=False)["value"].agg(
                (lambda x:x.sum(min_count=1)) if reducer=="sum" else reducer)
            pieces.append(agg)
        normalized=pd.concat(pieces,ignore_index=True)
    for metric, group in normalized.groupby("metric"):
        if cfg["metrics"].get(metric,{}).get("metric_type")=="count":
            values=group["value"].dropna()
            if ((values<0) | (values%1!=0)).any():
                raise ValueError(f"Count metric '{metric}' must contain nonnegative whole numbers; check the mapping and row grain")
    return normalized[["period","location_id","metric","value"]].sort_values(dupcols).reset_index(drop=True)
