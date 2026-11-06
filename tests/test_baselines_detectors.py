import numpy as np
import pandas as pd
from anomaly_monitor.baselines import estimate_reference
from anomaly_monitor.detectors import point_detection, add_cusum
from anomaly_monitor.aggregation import period_labels


def test_same_weekday_and_missing_does_not_slide():
    dates=pd.date_range('2025-01-01','2025-03-31')
    raw=pd.DataFrame({'period':dates,'location_id':'A','metric':'wash_count','is_complete':True,'quality_status':'complete','value':[100 if d.day_of_week==0 else 20 for d in dates]})
    raw.loc[raw['period']==pd.Timestamp('2025-02-10'),'value']=np.nan
    raw.loc[raw['period']==pd.Timestamp('2025-02-10'),'is_complete']=False
    base=estimate_reference(raw,'D',window=4)
    feb=base.loc[base['period']==pd.Timestamp('2025-02-17')].iloc[0]
    mar=base.loc[base['period']==pd.Timestamp('2025-03-17')].iloc[0]
    assert pd.isna(feb['expected'])
    assert mar['expected']==100
    assert mar['history_count']==4


def test_hourly_same_weekday_and_hour():
    dates=pd.date_range('2025-01-06','2025-02-03',freq='h')
    dates=dates[(dates.day_of_week==0)&(dates.hour.isin([8,9]))]
    df=pd.DataFrame({'period':dates,'location_id':'A','metric':'wash_count','is_complete':True,'quality_status':'complete','value':[20 if d.hour==8 else 100 for d in dates]})
    base=estimate_reference(df,'h',window=2)
    row=base.loc[base['period']==pd.Timestamp('2025-01-20 08:00')].iloc[0]
    assert row['expected']==20
    assert row['history_count']==2


def test_poisson_and_zscore():
    df=pd.DataFrame({'period':pd.to_datetime(['2025-01-01','2025-01-02']),
    'observed':[100.,10.],'expected':[30.,10.], 'scale':[5.,0.], 'is_complete':[True,True], 'quality_status':['complete','complete']})
    z=point_detection(df,'zscore',3,.01)
    assert z['point_alert'].tolist()==[True,False]
    assert z['scoring_status'].tolist()==['scored','undefined_scale_or_model']
    poi=point_detection(df,'poisson',3,.01)
    assert bool(poi['point_alert'].iloc[0])
    assert not bool(poi['point_alert'].iloc[1])


def test_cusum_sustained_not_single_spike_and_reset():
    dates=pd.date_range('2025-01-01',periods=15)
    scores=[0]*4+[1.5]*6+[float('nan')]+[1.5]*4
    df=pd.DataFrame({'period':dates,'location_id':'A','metric':'revenue','frequency':'D','horizon':'long', 'score':scores, 'scoring_status':['scored' if np.isfinite(z) else 'undefined_scale_or_model' for z in scores]})
    out=add_cusum(df,enabled=True,horizon='long',k=.5,h=5,score_cap=2)
    assert int(out['cusum_alert'].sum())==1
    first=out.loc[out['cusum_alert'],'period'].iloc[0]
    assert first==pd.Timestamp('2025-01-09')
    assert out.loc[out['period']==pd.Timestamp('2025-01-12'),'cusum_up'].iloc[0]==1.0
    spike=df.iloc[:5].copy()
    spike['score']=[0,0,15,0,0]
    assert not add_cusum(spike,enabled=True,horizon='long',k=.5,h=5,score_cap=2)['cusum_alert'].any()


def test_calendar_month_start_label():
    ds=pd.Series(pd.to_datetime(['2025-01-31','2025-02-02','2025-12-31']))
    assert period_labels(ds,'MS').tolist()==list(pd.to_datetime(['2025-01-01','2025-02-01','2025-12-01']))
