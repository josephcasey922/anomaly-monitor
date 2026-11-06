"""Lightweight, reproducible synthetic backtest with known injected point anomalies.

This is not a model validation on real company data. Run:
  python experiments/validate_detectors.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
from anomaly_monitor.baselines import estimate_reference
from anomaly_monitor.statistical import run_point_tests

RNG_SEEDS=range(40)
DAYS=240
METHODS=['zscore','predictive_t','robust_mad','poisson','neg_binomial']
results=[]
for seed in RNG_SEEDS:
    rng=np.random.default_rng(seed)
    dates=pd.date_range('2024-01-01',periods=DAYS)
    weekday_factor=np.array([.85,.92,.94,1.,1.05,1.25,1.1])
    mean=120*weekday_factor[dates.day_of_week]
    y=rng.poisson(mean).astype(float)
    # Known high/low anomalies on two late dates. Tests use only prior data.
    injected=np.zeros(DAYS,dtype=bool)
    injected[210]=injected[226]=True
    y[210]=int(round(2.2*mean[210]))
    y[226]=int(round(.20*mean[226]))
    frame=pd.DataFrame({'period':dates,'location_id':'A','metric':'wash_count',
                        'value':y,'is_complete':True,'quality_status':'complete'})
    reference=estimate_reference(frame,'D',window=12,min_history=12)
    points=run_point_tests(reference,frame,metric_spec={'aggregation':'sum','metric_type':'count','tests':METHODS},
        frequency='D',window=12,minimum=12,alpha=.01,z_threshold=3.)
    points['injected']=points['period'].isin(dates[injected])
    # Comparable evaluation window: last 80 days; mean/SD and MAD may remain noisy.
    points=points.loc[points.period>=dates[160]]
    for method,group in points.groupby('test'):
        evaluable=group.loc[group.scored]
        tp=int((evaluable.point_alert&evaluable.injected).sum())
        fp=int((evaluable.point_alert&~evaluable.injected).sum())
        pos=int(evaluable.injected.sum()); neg=int((~evaluable.injected).sum())
        results.append({'simulation':seed,'test':method,'TP':tp,'FP':fp,'positive_evaluable':pos,
                        'negative_evaluable':neg,'recall':tp/pos if pos else np.nan,
                        'false_positive_rate':fp/neg if neg else np.nan})
final=pd.DataFrame(results)
output=Path(__file__).resolve().parents[1]/'reports'
output.mkdir(exist_ok=True)
final.to_csv(output/'validation_details.csv',index=False)
summary=final.groupby('test').agg(tp=('TP','sum'),fp=('FP','sum'),
  positive=('positive_evaluable','sum'),negative=('negative_evaluable','sum')).reset_index()
summary['recall']=summary['tp']/summary['positive']
summary['false_positive_rate']=summary['fp']/summary['negative']
summary.to_csv(output/'validation_summary.csv',index=False)
print(summary.to_string(index=False,float_format=lambda v:f'{v:.4f}'))
print('\nSaved synthetic backtest reports to reports/. Thresholds are not calibrated for real business data.')
