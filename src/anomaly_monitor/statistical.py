"""Multiple point tests; explicit assumptions and no future-data leakage.

p-values condition on estimated baseline parameters; unless calibrated via
out-of-sample simulation, nominal alpha is NOT a guaranteed false-alarm rate.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd
from scipy.stats import poisson, nbinom, t as student_t, binom
from statsmodels.stats.multitest import multipletests

TESTS = {
    "zscore": "Heuristic 3-SD style screening (no p-value)",
    "predictive_t": "Normal iid next-value predictive t approximation",
    "robust_mad": "Median/MAD heuristic (no p-value)",
    "poisson": "Poisson count test, plug-in estimated rate",
    "neg_binomial": "Negative-binomial count test, moment estimated dispersion",
    "binomial": "Binomial successes/trials test, plug-in estimated rate",
    "stl_residual": "Trailing STL forecast residual heuristic; expensive, no p-value",
}

def _grouping(frequency):
    if frequency in ("D","h"):
        return ["location_id","metric","weekday"] + (["hour"] if frequency=="h" else [])
    return ["location_id","metric"]


def _rolling_prior(series,window,min_history,func):
    return series.transform(lambda x: x.shift(1).rolling(window,min_periods=min_history).apply(func,raw=True))


def add_robust_reference(baseline:pd.DataFrame, frequency:str, window:int, minimum:int)->pd.DataFrame:
    df=baseline.copy()
    df["weekday"]=pd.to_datetime(df["period"]).dt.day_of_week
    df["hour"]=pd.to_datetime(df["period"]).dt.hour
    g=df.groupby(_grouping(frequency),sort=False)["observed"]
    df["robust_expected"]=_rolling_prior(g,window,minimum,lambda x:np.nanmedian(x))
    def mad(a):
        med=np.nanmedian(a)
        return 1.4826*np.nanmedian(np.abs(a-med))
    df["robust_scale"]=_rolling_prior(g,window,minimum,mad)
    return df.drop(columns=["weekday","hour"])


def attach_binomial_context(baseline:pd.DataFrame, aggregated:pd.DataFrame,
                            spec:dict,frequency:str,window:int,minimum:int)->pd.DataFrame:
    """Historical rate = sum of earlier successes / sum of earlier opportunities.

    Unlike averaging historical percentages, this weights by observed exposures.
    """
    df=baseline.copy()
    keys=["location_id","period"]
    for metric, newname in ((spec["numerator"],"successes"),(spec["denominator"],"trials")):
        part=aggregated.loc[aggregated["metric"]==metric,keys+["value"]].rename(columns={"value":newname})
        df=df.merge(part,on=keys,how="left",validate="many_to_one")
    df["weekday"]=df["period"].dt.day_of_week
    df["hour"]=df["period"].dt.hour
    gkeys=_grouping(frequency)
    for col in ("successes","trials"):
        df[f"history_{col}"]=df.groupby(gkeys,sort=False)[col].transform(
            lambda x:x.shift(1).rolling(window,min_periods=minimum).sum())
    df["reference_probability"]=df["history_successes"]/df["history_trials"].where(df["history_trials"].gt(0))
    return df.drop(columns=["weekday","hour"])


def _stl_rolling_scores(df:pd.DataFrame,frequency:str,period:int,window:int)->pd.DataFrame:
    """Return prequential STL forecast and standardized residual using *past* data.

    May be slow on long/many series; no p-value and no guaranteed calibration.
    """
    from statsmodels.tsa.seasonal import STL
    output=pd.DataFrame(index=df.index,data={"score":np.nan,"forecast":np.nan})
    if frequency not in ("D","W-SUN","MS","QS") or period<2:
        return output
    for _,group in df.groupby(["location_id","metric"],sort=False):
        y=group["observed"].to_numpy(dtype=float)
        lookback=max(3*period,window)
        for i in range(lookback,len(y)):
            history=y[max(0,i-lookback):i]
            if len(history)<3*period or not np.isfinite(history).all() or not np.isfinite(y[i]):
                continue
            fit=STL(history,period=period,robust=True).fit()
            pred=fit.trend[-1]+fit.seasonal[-period]
            spread=np.std(fit.resid,ddof=1)
            if spread>0 and np.isfinite(spread):
                output.at[group.index[i],"score"]=(y[i]-pred)/spread
                output.at[group.index[i],"forecast"]=pred
    return output


def run_point_tests(baseline:pd.DataFrame,aggregated:pd.DataFrame,*,metric_spec:dict,
                    frequency:str,window:int,minimum:int,alpha:float=0.01,
                    z_threshold:float=3.0,stl_period:int|None=None)->pd.DataFrame:
    methods=metric_spec.get("tests") or [metric_spec.get("detector","zscore")]
    methods=list(dict.fromkeys(methods))
    if any(m not in TESTS for m in methods):
        raise ValueError(f"Unknown tests: {set(methods)-set(TESTS)}")
    ratio=metric_spec.get("aggregation")=="ratio"
    if "binomial" in methods and not ratio:
        raise ValueError("Binomial test requires ratio metric with success/total components")
    if any(m in methods for m in ("poisson","neg_binomial")) and metric_spec.get("aggregation")!="sum":
        raise ValueError("Count models require additive count metrics")
    source=baseline.copy()
    if "robust_mad" in methods:
        source=add_robust_reference(source,frequency,window,minimum)
    if "binomial" in methods:
        source=attach_binomial_context(source,aggregated,metric_spec,frequency,window,minimum)
    observed=source["observed"].to_numpy(dtype=float)
    mean=source["expected"].to_numpy(dtype=float)
    sd=source["scale"].to_numpy(dtype=float)
    n=source["history_count"].to_numpy(dtype=float)
    frames=[]
    for method in methods:
        df=source.copy()
        df["test"]=method
        df["test_description"]=TESTS[method]
        df["score"]=np.nan
        df["p_value"]=np.nan
        valid=np.isfinite(observed)&np.isfinite(mean)
        if method=="zscore":
            valid &= np.isfinite(sd)&(sd>0)
            df.loc[valid,"score"]=(observed[valid]-mean[valid])/sd[valid]
        elif method=="predictive_t":
            valid &= np.isfinite(sd)&(sd>0)&(n>=2)
            stat=(observed[valid]-mean[valid])/(sd[valid]*np.sqrt(1+1/n[valid]))
            df.loc[valid,"score"]=stat
            df.loc[valid,"p_value"]=2*student_t.sf(np.abs(stat),df=n[valid]-1)
        elif method=="robust_mad":
            rm=df["robust_expected"].to_numpy(dtype=float)
            rs=df["robust_scale"].to_numpy(dtype=float)
            valid=np.isfinite(observed)&np.isfinite(rm)&np.isfinite(rs)&(rs>0)
            df.loc[valid,"score"]=(observed[valid]-rm[valid])/rs[valid]
            df["test_expected"]=df["robust_expected"]
        elif method in ("poisson","neg_binomial"):
            valid &= (observed>=0)&(np.mod(observed,1)==0)&(mean>0)
            if method=="neg_binomial":
                variance=sd**2
                valid &= np.isfinite(variance)&(variance>mean)
            if valid.any():
                y=observed[valid]
                mu=mean[valid]
                if method=="poisson":
                    p=np.minimum(1.,2*np.minimum(poisson.cdf(y,mu),poisson.sf(y-1,mu)))
                    score=(y-mu)/np.sqrt(mu)
                else:
                    variance=sd[valid]**2
                    size=mu**2/(variance-mu)
                    prob=size/(size+mu)
                    p=np.minimum(1.,2*np.minimum(nbinom.cdf(y,size,prob),nbinom.sf(y-1,size,prob)))
                    score=(y-mu)/np.sqrt(variance)
                df.loc[valid,"p_value"]=p
                df.loc[valid,"score"]=score
        elif method=="binomial":
            s=df["successes"].to_numpy(dtype=float)
            trials=df["trials"].to_numpy(dtype=float)
            p0=df["reference_probability"].to_numpy(dtype=float)
            valid=np.isfinite(s)&np.isfinite(trials)&np.isfinite(p0)&(trials>0)&(s>=0)&(s<=trials)&(np.mod(s,1)==0)&(np.mod(trials,1)==0)&(p0>=0)&(p0<=1)
            if valid.any():
                # SciPy binom.cdf is inclusive; subtract one for upper-tail survival.
                p=np.minimum(1.,2*np.minimum(binom.cdf(s[valid],trials[valid],p0[valid]),
                                              binom.sf(s[valid]-1,trials[valid],p0[valid])))
                variance=trials[valid]*p0[valid]*(1-p0[valid])
                signed=np.sign(s[valid]-trials[valid]*p0[valid])
                score=signed*np.sqrt(np.where(variance>0,(s[valid]-trials[valid]*p0[valid])**2/variance,np.nan))
                df.loc[valid,"p_value"]=p
                df.loc[valid,"score"]=score
            df["test_expected"]=df["reference_probability"]*float(metric_spec.get("multiplier",1))
        elif method=="stl_residual":
            seasonal=int(stl_period or {"D":7,"W-SUN":52,"MS":12,"QS":4}.get(frequency,0))
            stl=_stl_rolling_scores(df,frequency,seasonal,window)
            df["score"]=stl["score"]
            df["test_expected"]=stl["forecast"]
        df["test_expected"]=df.get("test_expected",df["expected"])
        df["scored"]=(df["p_value"].notna() if method in ("predictive_t","poisson","neg_binomial","binomial") else (df["score"].notna() & np.isfinite(df["score"])))
        df["point_alert"]=False
        if method in ("zscore","robust_mad","stl_residual"):
            df.loc[df["scored"],"point_alert"]=df.loc[df["scored"],"score"].abs()>=z_threshold
            df["evidence_type"]="heuristic threshold"
        else:
            df.loc[df["p_value"].notna(),"point_alert"]=df.loc[df["p_value"].notna(),"p_value"]<=alpha
            df["evidence_type"]="plug-in model p-value"
        df["deviation"]=df["observed"]-df["test_expected"]
        df["direction"]=np.where(df["point_alert"],np.where(df["deviation"]>0,"above","below"),"none")
        df["deviation_pct"]=100*df["deviation"]/df["test_expected"].where(df["test_expected"].ne(0))
        df["scoring_status"]=np.select(
            [~df["is_complete"],df["observed"].isna(),df["expected"].isna(),~df["scored"]],
            ["incomplete_period","undefined_metric","insufficient_history","model_inapplicable_or_zero_scale"],
            default="scored")
        frames.append(df)
    return pd.concat(frames,ignore_index=True)


def add_fdr(point_results:pd.DataFrame, *,alpha:float=0.05)->pd.DataFrame:
    """BH across locations/metrics for each period/frequency/horizon/test family.

    Correlated tests and temporal dependence limit exact error-control claims.
    Never treat adjusted p-values as the probability a result is anomalous.
    """
    df=point_results.copy()
    df["q_value"]=np.nan
    df["fdr_alert"]=False
    cols=["period","frequency","horizon","test"]
    for _,group in df.loc[df["p_value"].notna()].groupby(cols,sort=False):
        rejected,q,*_=multipletests(group["p_value"].to_numpy(),alpha=alpha,method="fdr_bh")
        df.loc[group.index,"q_value"]=q
        df.loc[group.index,"fdr_alert"]=rejected
    return df
