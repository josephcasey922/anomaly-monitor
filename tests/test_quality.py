import pandas as pd
import pytest
from anomaly_monitor.quality import regularize_observations, expected_timestamps


def test_missing_day_and_zero_distinct(cfg):
    cfg['metrics']={'wash_count':cfg['metrics']['wash_count']}
    data=pd.DataFrame({'period':pd.to_datetime(['2025-01-01','2025-01-03']), 'location_id':['A']*2, 'metric':['wash_count']*2, 'value':[0,12]})
    regular,issues=regularize_observations(data,cfg)
    assert regular['data_status'].tolist()==['observed','missing_row','observed']
    assert regular['value'].iloc[0]==0
    assert pd.isna(regular['value'].iloc[1])
    assert len(issues)==1


def test_outside_reporting_calendar(cfg):
    cfg['metrics']={'wash_count':cfg['metrics']['wash_count']}
    cfg['calendar']['active_weekdays']=[0,1,2,3,4]
    data=pd.DataFrame({'period':pd.to_datetime(['2025-01-03','2025-01-04','2025-01-06']), 'location_id':['A']*3, 'metric':['wash_count']*3, 'value':[2,4,3]})
    regular,issues=regularize_observations(data,cfg)
    assert regular['period'].dt.day_of_week.tolist()==[4,0]
    assert 'outside_reporting_calendar' in issues['quality_issue'].tolist()


def test_expected_date_range_includes_explicit_end(cfg):
    cfg['calendar']['start']='2025-01-01'
    cfg['calendar']['end']='2025-01-07'
    dummy=pd.DataFrame({'period':pd.to_datetime(['2025-01-03'])})
    assert len(expected_timestamps(cfg,dummy))==7


def test_calendar_excluding_observation_raises(cfg):
    cfg['calendar']['start']='2025-01-04'
    cfg['calendar']['end']='2025-01-05'
    dummy=pd.DataFrame({'period':pd.to_datetime(['2025-01-03'])})
    with pytest.raises(ValueError,match='excludes observed'):
        expected_timestamps(cfg,dummy)
