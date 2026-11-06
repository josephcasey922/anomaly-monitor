"""Orchestrate adapter -> calendar -> aggregation -> tests -> reports.

No import step writes back to the source database. Results are local files.
"""
from __future__ import annotations
from pathlib import Path
import hashlib,json,math,os
import numpy as np
import pandas as pd
from .config import load_config, validate_config
from .ingest import normalize_source
from .quality import regularize_observations
from .aggregation import aggregate_complete_periods
from .baselines import estimate_reference
from .statistical import run_point_tests, add_fdr
from .shifts import detect_shifts


def _save_csv(frame:pd.DataFrame,path:Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        frame.to_csv(temp,index=False,na_rep="")
        os.replace(temp,path)
    except PermissionError as exc:
        raise PermissionError(f"Cannot update {path}; close open Excel CSV views") from exc
    finally:temp.unlink(missing_ok=True)


def _event_id(row,kind:str)->str:
    key="|".join(str(row[k]) for k in ("period","location_id","metric","frequency","horizon"))
    return hashlib.sha1(f"{kind}|{key}|{row.get('direction','')}".encode()).hexdigest()[:14]


def collapse_point_events(results:pd.DataFrame)->pd.DataFrame:
    """One event per location/metric/period/horizon/direction, with test agreement."""
    flagged=results.loc[results["point_alert"]].copy()
    output=[]
    for key,part in flagged.groupby(["period","location_id","metric","frequency","horizon","direction"],dropna=False):
        first=part.iloc[0]
        row=dict(zip(["period","location_id","metric","frequency","horizon","direction"],key))
        row.update({"event_type":"point","tests":", ".join(sorted(set(part["test"]))),
                    "test_count":int(part["test"].nunique()),"observed":first["observed"],
                    "expected":first["expected"],"deviation":first["observed"]-first["expected"],
                    "min_p_value":part["p_value"].min(skipna=True),
                    "min_q_value":part["q_value"].min(skipna=True),
                    "fdr_supported":bool(part["fdr_alert"].any()),
                    "description": "One unusually high/low period under the selected tests"})
        row["event_id"]=_event_id(row,"point")
        output.append(row)
    return pd.DataFrame(output)


def collapse_shift_events(shifts:pd.DataFrame)->pd.DataFrame:
    output=[]
    if shifts.empty:return pd.DataFrame()
    for key,part in shifts.loc[shifts["new_event"]].groupby(
        ["period","location_id","metric","frequency","horizon","direction"],dropna=False):
        first=part.iloc[0]
        row=dict(zip(["period","location_id","metric","frequency","horizon","direction"],key))
        row.update({"event_type":"sustained_change","tests":", ".join(sorted(set(part["method"]))),
                    "test_count":int(part["method"].nunique()),"observed":first["observed"],
                    "expected":first["expected"],"deviation":first["observed"]-first["expected"],
                    "min_p_value":np.nan,"min_q_value":np.nan,"fdr_supported":False,
                    "description":"New accumulated shift evidence; not another independent change each day"})
        row["event_id"]=_event_id(row,"shift")
        output.append(row)
    return pd.DataFrame(output)


def run_data_frame(frame:pd.DataFrame,cfg:dict,*,write_outputs:bool=True):
    cfg=validate_config(cfg) if not isinstance(cfg.get("output",{}).get("directory"),Path) else cfg
    raw=normalize_source(frame,cfg)
    regular,source_issues=regularize_observations(raw,cfg)
    metrics=cfg["metrics"]
    all_tests=[];all_base=[];period_issues=[]
    for frequency in cfg["analysis"]["frequencies"]:
        aggregated=aggregate_complete_periods(regular,cfg,frequency)
        bad=aggregated.loc[~aggregated["quality_status"].eq("complete"),
          ["period","location_id","metric","quality_status","observed_intervals","expected_intervals","coverage_ratio"]].copy()
        bad["frequency"]=frequency
        period_issues.append(bad)
        for horizon,window in cfg["analysis"]["windows"][frequency].items():
            minimum=max(2,math.ceil(window*cfg["analysis"].get("min_history_fraction",1.0)))
            baseline=estimate_reference(aggregated,frequency,window,minimum)
            baseline["frequency"]=frequency
            baseline["horizon"]=horizon
            baseline["window"]=window
            baseline["minimum_history"]=minimum
            baseline["reference_score"]=(baseline["observed"]-baseline["expected"])/baseline["scale"].where(baseline["scale"].gt(0))
            # Keep one baseline row per period, to avoid double-counting detector agreement.
            all_base.append(baseline)
            for metric, group in baseline.groupby("metric",sort=False):
                detected=run_point_tests(group,aggregated,metric_spec=metrics[metric],frequency=frequency,
                    window=window,minimum=minimum,alpha=float(cfg["analysis"].get("alpha",0.01)),
                    z_threshold=float(cfg["analysis"].get("z_threshold",3.0)),
                    stl_period=cfg["analysis"].get("stl_periods",{}).get(frequency))
                all_tests.append(detected)
    reference=pd.concat(all_base,ignore_index=True)
    point=add_fdr(pd.concat(all_tests,ignore_index=True),
                  alpha=float(cfg["analysis"].get("fdr_alpha",0.05)))
    shifts=detect_shifts(reference,cfg) if cfg["analysis"].get("shift_detectors",{}).get("enabled",False) else pd.DataFrame()
    all_events=[collapse_point_events(point),collapse_shift_events(shifts)]
    events=pd.concat([x for x in all_events if not x.empty],ignore_index=True) if any(not x.empty for x in all_events) else pd.DataFrame(columns=["event_id","period","location_id","metric","frequency","horizon","direction","event_type","tests","test_count","observed","expected","deviation","min_p_value","min_q_value","fdr_supported","description"])
    if not events.empty:
        events=events.sort_values(["period","location_id","metric","event_type"]).reset_index(drop=True)
    pquality=pd.concat(period_issues,ignore_index=True)
    quality=regular.groupby(["location_id","metric"],as_index=False).agg(
        observations=("value","size"),valid_values=("value","count"))
    quality["missing_values"]=quality["observations"]-quality["valid_values"]
    summary=reference.groupby(["location_id","metric","frequency","horizon"],as_index=False).agg(
        periods=("period","size"),scorable_reference=("reference_score","count"),
        complete=("is_complete","sum"))
    if not events.empty:
        ec=events.groupby(["location_id","metric","frequency","horizon","event_type"]).size().unstack(fill_value=0).reset_index()
        summary=summary.merge(ec,on=["location_id","metric","frequency","horizon"],how="left")
    frames={"all_results":reference,"point_tests":point,"shift_states":shifts,
            "alerts":events,"summary":summary,"source_quality":source_issues,
            "period_quality":pquality,"quality_summary":quality}
    paths={}
    if write_outputs:
        output=Path(cfg["output"]["directory"])
        output.mkdir(parents=True,exist_ok=True)
        for key,df in frames.items():
            path=output/f"{key}.csv"
            _save_csv(df,path)
            paths[key]=path
        if cfg["output"].get("interactive_html",True):
            from .viz02 import generate_dashboard
            path=output/"dashboard.html"
            generate_dashboard(reference,point,shifts,events,pquality,path)
            paths["dashboard"]=path
    return {"frames":frames,"paths":paths,"config":cfg}


def run_pipeline(config_path:str|Path):
    cfg=load_config(config_path)
    if cfg["input"].get("source","csv")=="csv":
        frame=pd.read_csv(cfg["input"]["path"])
    else:
        from .database import make_engine,fetch_table
        db=cfg["input"]["database"]
        env=db.get("password_env","ANOMALY_MONITOR_DB_PASSWORD")
        password=os.environ.get(env)
        if password is None:raise ValueError(f"Database password environment variable missing: {env}")
        engine=make_engine(host=db["host"],port=db["port"],database=db["database"],
                           user=db["username"],password=password,sslmode=db.get("sslmode","prefer"))
        try:
            frame=fetch_table(engine,schema=db["schema"],table=db["table"],
                 columns=db.get("columns"),timestamp_column=cfg.get("source_schema",{}).get("timestamp_column"),
                 start=db.get("start"),end=db.get("end"),max_rows=int(db.get("max_rows",100_000)))
        finally:engine.dispose()
    return run_data_frame(frame,cfg)["paths"]
