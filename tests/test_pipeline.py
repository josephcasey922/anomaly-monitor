from pathlib import Path
import pandas as pd
import yaml
from anomaly_monitor.pipeline import run_pipeline
from anomaly_monitor.demo import generate_wide_demo


def test_pipeline_integration(tmp_path):
    frame=generate_wide_demo(seed=7)
    src=tmp_path/'input.csv';frame.to_csv(src,index=False)
    root=Path(__file__).resolve().parents[1]
    cfg=yaml.safe_load((root/'examples/config.yaml').read_text())
    cfg['input']['path']=str(src)
    cfg['output']['directory']=str(tmp_path/'out')
    cfg['output']['interactive_html']=False
    cfg_path=tmp_path/'config.yaml';cfg_path.write_text(yaml.safe_dump(cfg))
    paths=run_pipeline(cfg_path)
    assert {'alerts','summary','source_quality','period_quality','all_results','point_tests','shift_states'}<=paths.keys()
    assert all(p.exists() for p in paths.values())
    quality=pd.read_csv(paths['source_quality'])
    assert 'missing_row' in quality['quality_issue'].values
    all_results=pd.read_csv(paths['all_results'])
    assert set(['D','W-SUN','MS','QS','YS'])==set(all_results['frequency'])
    assert 'operating_margin' in all_results['metric'].values
    point=pd.read_csv(paths['point_tests'])
    assert point.loc[point['scoring_status']=='incomplete_period','point_alert'].sum()==0
    assert {'predictive_t','robust_mad','poisson','neg_binomial','binomial'}<=set(point['test'])
    assert 'sustained_change' in pd.read_csv(paths['alerts'])['event_type'].values


def test_hourly_csv_pipeline(tmp_path):
    periods=pd.date_range('2025-01-06','2025-02-17',freq='D')
    periods=[d+pd.Timedelta(hours=h) for d in periods for h in [8,9]]
    raw=pd.DataFrame({'period':periods,'location_id':'A','metric':'wash_count','value':[5]*len(periods)})
    raw=raw.loc[raw['period'] != pd.Timestamp('2025-01-15 09:00')]
    src=tmp_path/'hours.csv';raw.to_csv(src,index=False)
    cfg={
      'input':{'source':'csv','path':str(src),'frequency':'h'},
      'source_schema':{'mode':'long','row_grain':'period','timestamp_column':'period','location_column':'location_id',
                       'metric_column':'metric','value_column':'value'},
      'calendar':{'active_weekdays':list(range(7)),'active_hours':[8,9]},
      'metrics':{'wash_count':{'aggregation':'sum','metric_type':'count','tests':['poisson']}},
      'analysis':{'frequencies':['h','D','W-SUN'],
          'windows':{'h':{'short':2,'long':3},'D':{'short':2,'long':3},'W-SUN':{'short':2,'long':3}},
          'shift_detectors':{'enabled':False}},
      'output':{'directory':str(tmp_path/'out'),'interactive_html':False}
    }
    yaml_path=tmp_path/'config.yaml';yaml_path.write_text(yaml.safe_dump(cfg))
    paths=run_pipeline(yaml_path)
    result=pd.read_csv(paths['all_results'])
    assert 'h' in result['frequency'].unique()
    incomplete=result.loc[(result['frequency']=='D') & (result['period']=='2025-01-15')]
    assert incomplete['is_complete'].eq(False).all()
    quality=pd.read_csv(paths['source_quality'])
    assert 'missing_row' in quality['quality_issue'].values
