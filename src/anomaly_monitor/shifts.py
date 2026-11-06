"""CUSUM and EWMA event episodes on ordered standardized residuals.

These exploratory detectors are not calibrated evidence of causality. A signal
represents an episode, not independent daily proof of multiple shifts.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def _run_episode(group, *,method, k,h,cap,release, lam=0.2,L=3.0):
    up=down=0.0
    active_up=active_down=False
    n=0
    result=[]
    for idx,row in group.iterrows():
        score=row["reference_score"]
        if not np.isfinite(score):
            up=down=0.0
            active_up=active_down=False
            n=0
            result.append((idx,np.nan,np.nan,False,False,False,False))
            continue
        z=float(np.clip(score,-cap,cap))
        if method=="cusum":
            up=max(0.,up+z-k)
            down=max(0.,down-z-k)
            up_limit=down_limit=h
            recover=release
        elif method=="ewma":
            up=lam*z+(1-lam)*up
            down=-up
            n+=1
            limit=L*np.sqrt(lam/(2-lam)*(1-(1-lam)**(2*n)))
            up_limit=down_limit=limit
            recover=limit*release  # release in (0,1) for EWMA
        else:
            raise ValueError("Unknown shift method")
        if active_up and up<=recover:active_up=False
        if active_down and down<=recover:active_down=False
        new_up=bool(up>=up_limit and not active_up)
        new_down=bool(down>=down_limit and not active_down)
        if new_up:active_up=True
        if new_down:active_down=True
        result.append((idx,float(up),float(down),new_up,new_down,active_up,active_down))
    return result


def detect_shifts(reference_rows:pd.DataFrame, config:dict)->pd.DataFrame:
    """One reference row per (period, location, metric, frequency, horizon).

    Events are emitted only at a new episode start. Active state remains visible.
    Missing or unscorable records reset state (deliberately conservative).
    """
    if reference_rows.empty:
        return pd.DataFrame()
    df=reference_rows.copy().sort_values(["location_id","metric","frequency","horizon","period"]).reset_index(drop=True)
    shifts=config.get("analysis",{}).get("shift_detectors",{})
    refh=shifts.get("horizon","long")
    methods=shifts.get("methods",["cusum"])
    parts=[]
    for method in methods:
        if method not in ("cusum","ewma"):
            raise ValueError(f"Unknown shift detector: {method}")
        opts=shifts.get(method,{})
        k=float(opts.get("k",0.5));h=float(opts.get("h",5.0));cap=float(opts.get("score_cap",2.0))
        release=float(opts.get("release",1.0 if method=="cusum" else 0.5))
        lam=float(opts.get("lambda",0.2));L=float(opts.get("L",3.0))
        if (k<0 or h<=0 or cap<=0 or (method=="cusum" and not 0<=release<h)
            or (method=="ewma" and not 0<lam<=1) or L<=0
            or (method=="ewma" and not 0<release<1)):
            raise ValueError("Invalid shift detector configuration")
        subset=df.loc[df["horizon"].eq(refh)].copy()
        for _,g in subset.groupby(["location_id","metric","frequency","horizon"],sort=False):
            for idx,up,down,newup,newdown,activeup,activedown in _run_episode(
                g,method=method,k=k,h=h,cap=cap,release=release,lam=lam,L=L):
                r=df.loc[idx]
                for direction,is_new,is_active,stat in (("upward",newup,activeup,up),
                                                        ("downward",newdown,activedown,down)):
                    if not np.isfinite(stat) and not is_new:continue
                    parts.append({"period":r["period"],"location_id":r["location_id"],
                                  "metric":r["metric"],"frequency":r["frequency"],"horizon":r["horizon"],
                                  "method":method,"direction":direction,"score":stat,
                                  "new_event":bool(is_new),"active":bool(is_active),
                                  "observed":r["observed"],"expected":r["expected"],
                                  "reference_score":r["reference_score"]})
    return pd.DataFrame(parts,columns=["period","location_id","metric","frequency","horizon","method",
                                       "direction","score","new_event","active","observed","expected","reference_score"])
