import numpy as np
import pandas as pd
from anomaly_monitor.quality import regularize_observations
from anomaly_monitor.aggregation import aggregate_complete_periods


def test_incomplete_first_week_missing_next_week(cfg):
    cfg['metrics']={'wash_count':cfg['metrics']['wash_count']}
    dates=[x for x in pd.date_range('2025-01-01','2025-01-19') if x !=pd.Timestamp('2025-01-08')]
    raw=pd.DataFrame({'period':dates,'location_id':'A','metric':'wash_count','value':10})
    regular,_=regularize_observations(raw,cfg)
    week=aggregate_complete_periods(regular,cfg,'W-SUN')
    assert week['period'].tolist()==list(pd.to_datetime(['2024-12-30','2025-01-06','2025-01-13']))
    assert week['expected_intervals'].tolist()==[7,7,7]
    assert week['observed_intervals'].tolist()==[5,6,7]
    assert week['is_complete'].tolist()==[False,False,True]
    assert pd.isna(week['value'].iloc[0]) and pd.isna(week['value'].iloc[1])
    assert week['value'].iloc[2]==70


def test_ratio_uses_sum_of_components_and_signed_income(cfg):
    raw=pd.DataFrame([
        ('2025-01-30','A','wash_count',2), ('2025-01-31','A','wash_count',8),
        ('2025-01-30','A','revenue',10), ('2025-01-31','A','revenue',90),
        ('2025-01-30','A','operating_income',-2), ('2025-01-31','A','operating_income',-5),
    ],columns=['period','location_id','metric','value'])
    cfg['calendar']['start']='2025-01-30';cfg['calendar']['end']='2025-01-31'
    regular,_=regularize_observations(raw,cfg)
    monthly=aggregate_complete_periods(regular,cfg,'MS')
    ratio=monthly.loc[monthly['metric']=='conversion_rate'].iloc[0]
    assert not ratio['is_complete']  # Jan 1-29 missing, so value must NOT be trusted
    assert pd.isna(ratio['value'])
    # At daily level, rate is computed from components and negative income is allowed.
    daily=aggregate_complete_periods(regular,cfg,'D')
    jan30=daily.loc[(daily['period']==pd.Timestamp('2025-01-30')) & (daily['metric']=='conversion_rate')].iloc[0]
    assert jan30['value']==20
    assert daily.loc[daily['metric']=='operating_income','value'].sum()==-7


def test_complete_month_ratio_weighted(cfg):
    dates=pd.date_range('2025-02-01','2025-02-28')
    rows=[]
    for i,d in enumerate(dates):
        rows.extend([(d,'A','wash_count',1 if i!=27 else 10),(d,'A','revenue',10 if i!=27 else 20),(d,'A','operating_income',-2)])
    regular,_=regularize_observations(pd.DataFrame(rows,columns=['period','location_id','metric','value']),cfg)
    month=aggregate_complete_periods(regular,cfg,'MS')
    ratio=month.loc[month['metric']=='conversion_rate'].iloc[0]
    assert ratio['is_complete']
    assert abs(ratio['value']-(37/290)*100)<1e-9


def test_hourly_incomplete_day(cfg):
    cfg['input']['frequency']='h'
    cfg['calendar']['active_hours']=[8,9,10]
    cfg['metrics']={'wash_count':cfg['metrics']['wash_count']}
    raw=pd.DataFrame({'period':pd.to_datetime(['2025-01-06 08:00','2025-01-06 10:00']), 'location_id':['A','A'],'metric':['wash_count']*2,'value':[7,8]})
    regular,_=regularize_observations(raw,cfg)
    assert len(regular)==3
    day=aggregate_complete_periods(regular,cfg,'D')
    assert day.iloc[0]['observed_intervals']==2
    assert day.iloc[0]['expected_intervals']==3
    assert pd.isna(day.iloc[0]['value'])


def test_zero_denominator_rate_is_not_zero(cfg):
    cfg['metrics']={
       'wash_count': {'aggregation':'sum','detector':'poisson'},
       'revenue': {'aggregation':'sum','detector':'zscore'},
       'rate': {'aggregation':'ratio','numerator':'wash_count','denominator':'revenue','multiplier':100,'detector':'zscore'}
    }
    raw=pd.DataFrame([('2025-01-01','A','wash_count',10),('2025-01-01','A','revenue',0)],columns=['period','location_id','metric','value'])
    regular,_=regularize_observations(raw,cfg)
    daily=aggregate_complete_periods(regular,cfg,'D')
    ratio=daily.loc[daily['metric']=='rate'].iloc[0]
    assert ratio['quality_status']=='zero_denominator'
    assert ratio['is_complete']
    assert pd.isna(ratio['value'])


def test_first_month_partial_is_explicit(cfg):
    cfg['metrics']={'wash_count':cfg['metrics']['wash_count']}
    dates=pd.date_range('2025-01-15','2025-01-31')
    raw=pd.DataFrame({'period':dates,'location_id':'A','metric':'wash_count','value':10})
    regular,_=regularize_observations(raw,cfg)
    monthly=aggregate_complete_periods(regular,cfg,'MS')
    assert len(monthly)==1
    row=monthly.iloc[0]
    assert row['observed_intervals']==17
    assert row['expected_intervals']==31
    assert abs(row['coverage_ratio']-17/31)<1e-9
    assert pd.isna(row['value'])
