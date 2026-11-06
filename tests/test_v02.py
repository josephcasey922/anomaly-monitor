import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from anomaly_monitor.config import validate_config
from anomaly_monitor.ingest import normalize_source,profile_frame
from anomaly_monitor.database import list_tables,list_columns,fetch_table
from anomaly_monitor.pipeline import run_data_frame
from anomaly_monitor.statistical import add_fdr,run_point_tests
from anomaly_monitor.shifts import detect_shifts
from anomaly_monitor.aggregation import aggregate_complete_periods
from anomaly_monitor.quality import regularize_observations


def cfg(tmp_path,mode='wide',grain='period',freq='D'):
    return {
       'input':{'source':'csv','path':'ignored.csv','frequency':freq},
       'source_schema':{'mode':mode,'row_grain':grain,'timestamp_column':'Date',
         'location_column':'Site','metrics':{'revenue':'Net','wash_count':'Cars','conversions':'Orders','opportunities':'Visits'}},
       'output':{'directory':str(tmp_path),'interactive_html':False},
       'calendar':{'active_weekdays':list(range(7)),'active_hours':list(range(24))},
       'metrics':{'revenue':{'aggregation':'sum','metric_type':'amount','tests':['predictive_t','robust_mad']},
                  'wash_count':{'aggregation':'sum','metric_type':'count','tests':['poisson','neg_binomial']},
                  'conversions':{'aggregation':'sum','metric_type':'count','tests':['poisson']},
                  'opportunities':{'aggregation':'sum','metric_type':'count','tests':['poisson']},
                  'conversion_rate':{'aggregation':'ratio','numerator':'conversions','denominator':'opportunities',
                                     'metric_type':'proportion','multiplier':100,'tests':['binomial']}},
       'analysis':{'frequencies':['D','W-SUN'],
                   'windows':{'D':{'short':2,'long':4},'W-SUN':{'short':2,'long':4}},
                   'shift_detectors':{'enabled':True,'horizon':'long','methods':['cusum','ewma']}}
    }


def fake_data(days=70):
    dates=pd.date_range('2025-01-01',periods=days)
    return pd.DataFrame({'Date':dates,'Site':'A','Cars':np.arange(days)%10+25,
                         'Net':100.+np.arange(days), 'Orders':10, 'Visits':50,
                         'Unused Department':'X'})


def test_ignore_unknown_columns_and_negative_amounts(tmp_path):
    data=fake_data();data.loc[0,'Net']=-100.
    out=normalize_source(data,cfg(tmp_path))
    assert len(out)==len(data)*4
    assert out.loc[(out.metric=='revenue') & (out.period=='2025-01-01'),'value'].iloc[0]==-100
    assert 'Unused Department' not in out
    assert 'Date' in profile_frame(data).column.values


def test_transaction_duplicate_modes(tmp_path):
    data=fake_data(3)
    duplicated=pd.concat([data,data.iloc[[0]]],ignore_index=True)
    with pytest.raises(ValueError,match='Duplicate'):
        normalize_source(duplicated,cfg(tmp_path))
    config=cfg(tmp_path,grain='transaction')
    result=normalize_source(duplicated,config)
    assert result.loc[(result.metric=="wash_count")&(result.period==pd.Timestamp("2025-01-01")),"value"].iloc[0]==50


def test_weighted_conversion_ratio(tmp_path):
    data=fake_data(35)
    data.loc[0,'Orders']=1;data.loc[0,'Visits']=2
    data.loc[1,'Orders']=1;data.loc[1,'Visits']=100
    config=validate_config(cfg(tmp_path))
    regular,_=regularize_observations(normalize_source(data,config),config)
    weekly=aggregate_complete_periods(regular,config,'W-SUN')
    # Jan 1-5 includes 1/2 and 1/100 plus three 10/50 observations
    expected=100*(1+1+30)/(2+100+150)
    row=weekly.loc[(weekly.metric=='conversion_rate')&(weekly.period==pd.Timestamp('2024-12-30'))].iloc[0]
    assert not row.is_complete  # partial opening week
    assert np.isnan(row.value)
    full=weekly.loc[(weekly.metric=="conversion_rate")&(weekly.period==pd.Timestamp("2025-01-06"))].iloc[0]
    assert full.value==pytest.approx(20.)


def test_fdr_and_statistical_methods(tmp_path):
    data=fake_data(85)
    data.loc[75,'Net']*=8
    result=run_data_frame(data,cfg(tmp_path),write_outputs=False)
    point=result['frames']['point_tests']
    assert {'poisson','neg_binomial','predictive_t','robust_mad','binomial'}<=set(point['test'])
    assert point['p_value'].notna().any()
    valid=point.dropna(subset=['p_value','q_value'])
    assert (valid['q_value']+1e-12>=valid['p_value']).all()
    assert 'event_type' in result['frames']['alerts'].columns


def test_cusum_episode_not_daily_repeat(tmp_path):
    df=pd.DataFrame({'period':pd.date_range('2025-01-01',periods=40),
       'location_id':'A','metric':'revenue','frequency':'D','horizon':'long',
       'reference_score':[0]*10+[1.4]*30,'observed':[100]*40,'expected':[80]*40})
    config=cfg(tmp_path)
    shifts=detect_shifts(df,config)
    c=shifts.query("method=='cusum' and direction=='upward'")
    assert c['new_event'].sum()==1
    assert c['active'].iloc[-1]
    assert c['score'].iloc[-1]>5


def test_monthly_input_preserves_months(tmp_path):
    config=cfg(tmp_path,freq='MS')
    config['source_schema']['metrics']={'revenue':'Net'}
    config['metrics']={'revenue':config['metrics']['revenue']}
    config['analysis']['frequencies']=['MS','QS']
    config['analysis']['windows']={'MS':{'short':2,'long':3},'QS':{'short':2,'long':3}}
    data=pd.DataFrame({'Date':['2025-01-01','2025-03-01','2025-04-01','2025-05-01'],
                       'Site':['A']*4,'Net':[100,300,400,500]})
    result=run_data_frame(data,config,write_outputs=False)
    issues=result['frames']['source_quality']
    assert (issues['period']==pd.Timestamp('2025-02-01')).any()
    assert (result['frames']['all_results']['frequency']=='MS').any()


def test_read_only_database_introspection_sqlite():
    engine=create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE metrics ("Date" TEXT, "Site" TEXT, "Net" REAL)'))
        conn.execute(text("INSERT INTO metrics VALUES ('2025-01-01','A',100),('2025-01-02','A',110)"))
    assert ('main','metrics') in list_tables(engine)
    assert 'Net' in list_columns(engine,'main','metrics')
    data=fetch_table(engine,schema='main',table='metrics',columns=['Date','Site','Net'],
                     timestamp_column=None,max_rows=100)
    assert len(data)==2
    with pytest.raises(ValueError,match='Unrecognized'):
        fetch_table(engine,schema='main',table='metrics',columns=['Net; DROP TABLE metrics;'])
    with pytest.raises(ValueError,match='row safety limit'):
        fetch_table(engine,schema='main',table='metrics',max_rows=1)
    engine.dispose()


def test_config_rejects_password_and_invalid_count_model(tmp_path):
    config=cfg(tmp_path)
    config['metrics']['revenue']['tests']=['poisson']
    with pytest.raises(ValueError,match='Count tests'):
        validate_config(config)
    c=cfg(tmp_path);c['input']={'source':'postgres','frequency':'D','database':{
        'host':'localhost','port':5432,'database':'demo','username':'demo','schema':'public','table':'metrics','password':'secret'}}
    with pytest.raises(ValueError,match='password'):
        validate_config(c)
