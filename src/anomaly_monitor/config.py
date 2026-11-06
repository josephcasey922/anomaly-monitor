"""Config validation. Secrets never belong in exported YAML profiles."""
from __future__ import annotations
from pathlib import Path
import copy, math
import yaml

VALID_FREQUENCIES=("h","D","W-SUN","MS","QS","YS")
LEGAL={"h":{"h","D","W-SUN","MS","QS","YS"},"D":{"D","W-SUN","MS","QS","YS"},
       "W-SUN":{"W-SUN"},"MS":{"MS","QS","YS"},"QS":{"QS","YS"},"YS":{"YS"}}

def validate_config(raw:dict, base:Path|None=None)->dict:
    from .statistical import TESTS
    cfg=copy.deepcopy(raw)
    if not isinstance(cfg,dict):raise ValueError("Configuration must be YAML mapping")
    for name in ("input","output","calendar","metrics","analysis"):
        if not isinstance(cfg.get(name),dict):raise ValueError(f"Missing mapping: {name}")
    inp=cfg["input"]
    inp.setdefault("source","csv")
    if inp["source"] not in ("csv","postgres"):
        raise ValueError("input.source must be csv or postgres")
    freq=inp.get("frequency","D")
    if freq not in VALID_FREQUENCIES:raise ValueError("Invalid input.frequency")
    if inp["source"]=="csv":
        if not inp.get("path"):raise ValueError("input.path required for CSV")
        inp["path"]=(base / inp["path"]).resolve() if base else Path(inp["path"]).resolve()
    else:
        db=inp.get("database",{})
        if "password" in db:raise ValueError("Do not store passwords in YAML. Use password_env")
        for required in ("host","port","database","username","schema","table"):
            if not db.get(required):raise ValueError(f"Missing input.database.{required}")
    out=cfg["output"]
    out["directory"]=(base / out.get("directory","outputs")).resolve() if base else Path(out.get("directory","outputs")).resolve()
    cal=cfg["calendar"]
    for key,lim,default in (("active_weekdays",7,list(range(7))),("active_hours",24,list(range(24)))):
        vals=cal.get(key,default)
        if not isinstance(vals,list) or not vals or any(not isinstance(x,int) or x not in range(lim) for x in vals):
            raise ValueError(f"calendar.{key} must be nonempty integer list")
        cal[key]=sorted(set(vals))
    metrics=cfg["metrics"]
    if not metrics:raise ValueError("Configure at least one metric")
    for name,spec in metrics.items():
        agg=spec.get("aggregation")
        if agg not in ("sum","mean","last","ratio"):
            raise ValueError(f"Invalid aggregation for {name}: {agg}")
        methods=spec.get("tests",[spec.get("detector","zscore")])
        if not isinstance(methods,list) or not methods or any(m not in TESTS for m in methods):
            raise ValueError(f"Invalid statistical methods for {name}: {methods}")
        if agg=="ratio":
            if any(spec.get(x) not in metrics or metrics[spec[x]].get("aggregation")!="sum" for x in ("numerator","denominator")):
                raise ValueError(f"Ratio {name} needs two additive component metrics")
            if "binomial" in methods and spec.get("metric_type")!="proportion":
                raise ValueError("Binomial test requires metric_type: proportion")
        elif "binomial" in methods:
            raise ValueError(f"Binomial requires derived ratio: {name}")
        if any(m in ("poisson","neg_binomial") for m in methods):
            if agg!="sum" or spec.get("metric_type")!="count":
                raise ValueError(f"Count tests require sum and metric_type: count: {name}")
    s=cfg.get("source_schema",{})
    if not isinstance(s,dict):raise ValueError("source_schema must be a mapping")
    if s.get("mode","long") not in ("long","wide"):
        raise ValueError("source_schema.mode must be wide or long")
    if s.get("mode")=="wide" and not s.get("metrics"):
        raise ValueError("Wide CSV requires source_schema.metrics")
    a=cfg["analysis"]
    freqs=a.get("frequencies",[freq])
    if any(f not in LEGAL[freq] for f in freqs) or not freqs:
        raise ValueError(f"Incompatible analysis frequencies for {freq}: {freqs}")
    for f in freqs:
        windows=a.get("windows",{}).get(f,{})
        if not windows or any(type(v)!=int or v<2 for v in windows.values()):
            raise ValueError(f"Invalid windows for {f}")
    frac=a.get("min_history_fraction",1.0)
    if not isinstance(frac,(float,int)) or not 0<frac<=1:
        raise ValueError("Invalid min_history_fraction")
    alpha=a.get("alpha",0.01)
    fdr=a.get("fdr_alpha",0.05)
    if not (0<alpha<1 and 0<fdr<1):raise ValueError("Invalid alpha/FDR alpha")
    sh=a.get("shift_detectors",{})
    if sh.get("enabled",False):
        horizon=sh.get("horizon","long")
        if any(horizon not in a["windows"][f] for f in freqs):
            raise ValueError(f"Shift horizon {horizon} unavailable in some frequencies")
        if not set(sh.get("methods",["cusum"])).issubset({"cusum","ewma"}):
            raise ValueError("Only CUSUM and EWMA shift methods are supported")
    return cfg


def load_config(config_path:str|Path)->dict:
    path=Path(config_path).resolve()
    with path.open(encoding="utf-8") as file: raw=yaml.safe_load(file)
    return validate_config(raw,path.parent)
