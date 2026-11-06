from pathlib import Path
import re

import pandas as pd
from anomaly_monitor.time_window import default_preset, resolve_window, restrict_dates
from anomaly_monitor.viz02 import generate_dashboard


def test_default_time_presets():
    assert default_preset('h') == 'Last 7 days'
    assert default_preset('D') == 'Last 90 days'
    assert default_preset('YS') == 'All dates'


def test_preset_relative_to_data_not_today():
    periods=pd.date_range('2024-01-01', '2024-12-31', freq='D')
    lo,hi=resolve_window(periods,'Last 30 days')
    assert hi == pd.Timestamp('2024-12-31')
    assert lo == pd.Timestamp('2024-12-01')


def test_custom_end_includes_entire_day_and_filters():
    data=pd.DataFrame({'period':pd.to_datetime(['2025-06-01 09:00','2025-06-02 12:00','2025-06-03 14:00'])})
    lo,hi=resolve_window(data.period,'Custom dates',start='2025-06-02',end='2025-06-02')
    chosen=restrict_dates(data,lo,hi)
    assert len(chosen)==1
    assert chosen.period.iloc[0]==pd.Timestamp('2025-06-02 12:00')


def test_offline_html_includes_full_history_and_controls(tmp_path):
    n=260
    dates=pd.date_range('2025-01-01',periods=n,freq='D')
    reference=pd.DataFrame({'period':dates,'location_id':'A','metric':'revenue',
      'frequency':'D','horizon':'short','observed':range(n),'expected':range(n),
      'scale':2,'reference_score':0,'is_complete':True,'history_count':8,'window':8})
    points=pd.DataFrame(columns=['period','location_id','metric','frequency','horizon','observed','test','score','p_value','q_value','direction','point_alert'])
    shifts=pd.DataFrame(columns=['period','location_id','metric','frequency','horizon','method','direction','score','new_event','active'])
    events=pd.DataFrame(columns=['period','location_id','metric','frequency','horizon','event_type','direction','tests','test_count','observed','expected','min_p_value','min_q_value'])
    quality=pd.DataFrame(columns=['period','location_id','metric','frequency','quality_status','coverage_ratio'])
    target=tmp_path/'dashboard.html'
    generate_dashboard(reference,points,shifts,events,quality,target)
    doc=target.read_text(encoding='utf-8')
    assert 'id="timePreset"' in doc
    assert 'id="startDate"' in doc
    assert 'id="endDate"' in doc
    assert 'rangeslider:{visible:true' in doc
    # Early dates still exist; the old version discarded all but 180 per series.
    data_js=re.search(r'const R=(\[.*?\]),P=',doc,re.DOTALL)
    assert data_js is not None
    import json
    rows=json.loads(data_js.group(1))
    assert len(rows)==260
    assert rows[0]['period']=='2025-01-01'
    scripts=re.findall(r'<script>(.*?)</script>',doc,re.DOTALL)
    assert len(scripts)>=2
    (tmp_path/'dashboard.js').write_text(scripts[-1],encoding='utf-8')
