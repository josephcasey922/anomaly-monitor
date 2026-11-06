"""Portable, no-server interactive HTML dashboard with embedded Plotly.js."""
from __future__ import annotations
from pathlib import Path
import html
import json
import pandas as pd
from plotly.offline import get_plotlyjs


FIELDS = ["period", "observed", "expected", "scale", "score", "point_method",
          "point_alert", "direction", "cusum_alert", "cusum_direction", "cusum_up", "cusum_down", "scoring_status", "window"]


def _records(frame: pd.DataFrame) -> list[dict]:
    records = []
    for rec in frame[FIELDS].to_dict("records"):
        clean = {}
        for key, value in rec.items():
            if isinstance(value, pd.Timestamp):
                clean[key] = value.isoformat(timespec="minutes")
            elif pd.isna(value):
                clean[key] = None
            elif hasattr(value, "item"):
                clean[key] = value.item()
            else:
                clean[key] = value
        records.append(clean)
    return records


def create_dashboard(scored: pd.DataFrame, alerts: pd.DataFrame, issues: pd.DataFrame,
                     path: str | Path, max_points: int = 160, cusum_threshold: float = 5.) -> None:
    if max_points < 10:
        raise ValueError("dashboard_max_points must be at least 10")
    series: dict[str, list] = {}
    # The dashboard is compact; the CSV files retain the complete history.
    for (location,metric,freq,horizon), grp in scored.groupby(["location_id","metric","frequency","horizon"]):
        key = "|".join(map(str, (location,metric,freq,horizon)))
        series[key] = _records(grp.sort_values("period").tail(max_points))
    data_json = json.dumps(series, ensure_ascii=False, separators=(",",":"), allow_nan=False).replace("<", "\\u003c")
    # HTML escapes for the count only; model-generated chart labels are supplied as JSON.
    header = f"{len(alerts):,} recorded alert events · {len(issues):,} source-data quality issues"
    page = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Anomaly Monitor • Interactive Report</title>
<style>
:root{--navy:#0e1b32;--blue:#2168a6;--teal:#21867a;--muted:#65738a;--line:#e2e8f0;--bg:#f4f7fb;--red:#c13d4c;--amber:#d28422}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--navy);font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif}
header{background:var(--navy);color:white;padding:26px max(calc((100vw - 1250px)/2),24px)}header h1{font-size:27px;margin:0 0 7px}header p{color:#cbd5e1;margin:0}
main{max-width:1250px;margin:26px auto;padding:0 18px} .panel{background:white;border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:18px;box-shadow:0 3px 14px rgba(27,42,70,.035)}
.controls{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:12px} label{font-size:12px;font-weight:700;color:var(--muted);display:block;margin-bottom:6px}select{width:100%;border:1px solid #d0d9e5;border-radius:8px;padding:11px;background:white;color:var(--navy);font-size:14px}
h2{font-size:18px;margin:0 0 4px} .subtitle{color:var(--muted);font-size:13px;margin:4px 0 16px}.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:13px;margin-top:8px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}.above{background:var(--amber)}.below{background:var(--red)}.shift{background:var(--teal)}
.cardrow{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.stat{padding:14px;background:#f5f8fc;border-radius:10px}.stat b{display:block;font-size:22px}.stat span{color:var(--muted);font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px;border-bottom:1px solid var(--line);text-align:left}th{color:#53657f;background:#f8fafc} .scroll{overflow:auto;max-height:360px}
footer{padding:0 5px 30px;color:#66758b;font-size:12px} #chart{min-height:420px}#cusumChart{min-height:240px}
@media(max-width:680px){.controls{grid-template-columns:repeat(2,minmax(0,1fr))}.cardrow{grid-template-columns:1fr}}
</style></head><body>
<header><h1>ANOMALY MONITOR <span style="color:#8fc9d4;font-size:14px">v0.1</span></h1><p>Explore unusual observations and evidence of sustained shifts. All data are embedded in this report.</p></header>
<main>
<div class="panel"><div class="controls">
<div><label for="loc">Location</label><select id="loc"></select></div>
<div><label for="metric">Metric</label><select id="metric"></select></div>
<div><label for="freq">Time period</label><select id="freq"></select></div>
<div><label for="horizon">Reference baseline</label><select id="horizon"></select></div>
</div><div class="legend" style="margin-top:16px"><span><i class="dot above"></i> Above expected (not necessarily good)</span><span><i class="dot below"></i> Below expected (not necessarily bad)</span><span><i class="dot shift"></i> CUSUM shift signal</span></div></div>
<div class="panel"><div class="cardrow" id="stats"></div></div>
<div class="panel"><h2>Observed versus historical reference</h2><p class="subtitle" id="chartNote"></p><div id="chart"></div></div>
<div class="panel"><h2>Cumulative evidence of a shift (CUSUM)</h2><p class="subtitle">CUSUM accumulates smaller deviations over time. It is different from an isolated point anomaly; a signal suggests a persistent change, not proof of a business cause.</p><div id="cusumChart"></div></div>
<div class="panel"><h2>Selected series — recent alerts</h2><p class="subtitle">A point flag identifies one unusually high or low period. A CUSUM flag identifies a new crossing of an accumulation threshold.</p><div class="scroll"><table><thead><tr><th>Period</th><th>Kind</th><th>Direction</th><th>Observed</th><th>Expected</th></tr></thead><tbody id="alertTable"></tbody></table></div></div>
<div class="panel"><h2>How to interpret the results</h2><p><b>Reference baseline:</b> Short uses fewer past comparable periods and adapts faster; long uses more history and can be slower to adapt. For daily data, only the same weekday is compared; for hourly, the same weekday and hour. No current observation is used to estimate its own baseline.</p><p><b>Point anomaly:</b> An observation unusually far from the estimated reference, based on a heuristic z-score or a two-sided Poisson test for counts.</p><p><b>CUSUM:</b> An exploratory cumulative-shift signal, computed on the configured long baseline. Scores are clipped so a lone spike has reduced influence. Thresholds have not been calibrated to guarantee a false-alarm rate.</p><p><b>Data completeness:</b> Incomplete periods are excluded from scoring; missing/invalid periods remain in the exported CSV. Ratios are derived from their component totals instead of being summed.</p></div>
<footer>This report is exploratory and not a substitute for source-data validation or domain review. Dashboard series show the most recent configured observations; complete history lives in all_results.csv. Excel/Power Query can refresh from the companion CSV reports.</footer>
</main>
<script>__PLOTLY__</script>
<script>
const SERIES=__SERIES__;
const CUSUM_H=__CUSUM__;
const HEADER=__HEADER__;
const orderFreq=['h','D','W-SUN','MS','QS','YS'];
const keys=Object.keys(SERIES);
const selectIds=['loc','metric','freq','horizon'];
const components=keys.map(k=>k.split('|'));
const unique=(arr)=>[...new Set(arr)];
const opts=(id,values,preferred)=>{const el=document.getElementById(id);const selected=values.includes(el.value)?el.value:(values.includes(preferred)?preferred:values[0]);el.innerHTML='';for(const v of values){const o=document.createElement('option');o.value=v;o.textContent=v;el.append(o);}el.value=selected;};
function refreshOptions(){
  let loc=document.getElementById('loc').value;
  opts('loc',unique(components.map(a=>a[0])).sort(),'A');loc=document.getElementById('loc').value;
  opts('metric',unique(components.filter(a=>a[0]===loc).map(a=>a[1])).sort(),'revenue');
  let met=document.getElementById('metric').value;
  opts('freq',unique(components.filter(a=>a[0]===loc&&a[1]===met).map(a=>a[2])).sort((a,b)=>orderFreq.indexOf(a)-orderFreq.indexOf(b)),'D');
  const freq=document.getElementById('freq').value;
  opts('horizon',unique(components.filter(a=>a[0]===loc&&a[1]===met&&a[2]===freq).map(a=>a[3])).sort(),'long');
}
const format=v=>v==null?'—':Number(v).toLocaleString(undefined,{maximumFractionDigits:2});
const trace=(rows,name,y,color,extra={})=>({x:rows.map(r=>r.period),y:rows.map(r=>r[y]),name,mode:'lines',type:'scatter',line:{color,width:name==='Observed'?1.5:2.5},connectgaps:false,...extra});
function render(){
  refreshOptions();
  const key=selectIds.map(id=>document.getElementById(id).value).join('|');
  const rows=SERIES[key]||[];
  const point=rows.filter(r=>r.point_alert),up=point.filter(r=>r.direction==='above'),down=point.filter(r=>r.direction==='below'),shift=rows.filter(r=>r.cusum_alert);
  const d1={x:up.map(r=>r.period),y:up.map(r=>r.observed),mode:'markers',type:'scatter',name:'Above expected',marker:{color:'#d28422',symbol:'triangle-up',size:11}};
  const d2={x:down.map(r=>r.period),y:down.map(r=>r.observed),mode:'markers',type:'scatter',name:'Below expected',marker:{color:'#c13d4c',symbol:'triangle-down',size:11}};
  const d3={x:shift.map(r=>r.period),y:shift.map(r=>r.observed),mode:'markers',type:'scatter',name:'CUSUM shift',marker:{color:'#21867a',symbol:'diamond-open',size:14,line:{width:2}}};
  const traces=[trace(rows,'Observed','observed','#73859f'),trace(rows,'Expected baseline','expected','#2168a6'),d1,d2,d3];
  const layout={margin:{l:65,r:25,t:20,b:60},paper_bgcolor:'#fff',plot_bgcolor:'#fff',hovermode:'x unified',xaxis:{title:'Period',gridcolor:'#edf1f6'},yaxis:{title:document.getElementById('metric').value,gridcolor:'#edf1f6'},legend:{orientation:'h',y:1.13},font:{family:'system-ui,Arial',color:'#0e1b32'}};
  Plotly.react('chart',traces,layout,{responsive:true,displaylogo:false});
  const crows=rows.filter(r=>r.cusum_up!=null||r.cusum_down!=null);
  const ct=[trace(crows,'Upward evidence','cusum_up','#21867a'),trace(crows,'Downward evidence','cusum_down','#c13d4c'),{x:crows.map(r=>r.period),y:crows.map(()=>CUSUM_H),name:'Threshold',mode:'lines',line:{dash:'dash',color:'#8793a6'},type:'scatter'}];
  Plotly.react('cusumChart',ct,{margin:{l:65,r:25,t:20,b:55},paper_bgcolor:'#fff',plot_bgcolor:'#fff',xaxis:{title:'Period',gridcolor:'#edf1f6'},yaxis:{title:'Accumulated score',gridcolor:'#edf1f6'},legend:{orientation:'h',y:1.18},font:{family:'system-ui,Arial',color:'#0e1b32'}},{responsive:true,displaylogo:false});
  const scored=rows.filter(r=>r.score!=null).length;
  document.getElementById('stats').innerHTML=`<div class="stat"><b>${scored}</b><span>Scored periods in view</span></div><div class="stat"><b>${point.length}</b><span>Point anomalies in view</span></div><div class="stat"><b>${shift.length}</b><span>New CUSUM signals in view</span></div>`;
  document.getElementById('chartNote').textContent=`${document.getElementById('horizon').value} reference • ${rows[0]?.window??'—'} historical comparison periods • ${rows.length} plotted observations`;
  const events=[];
  for(const r of rows){if(r.point_alert)events.push({date:r.period,kind:'Point',direction:r.direction,observed:r.observed,expected:r.expected});if(r.cusum_alert)events.push({date:r.period,kind:'CUSUM',direction:r.cusum_direction,observed:r.observed,expected:r.expected});}
  events.reverse();
  const tbody=document.getElementById('alertTable');tbody.innerHTML='';
  for(const e of events.slice(0,60)){const tr=document.createElement('tr');for(const val of [e.date,e.kind,e.direction,format(e.observed),format(e.expected)]){const td=document.createElement('td');td.textContent=val;tr.append(td);}tbody.append(tr);}
  if(!events.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=5;td.textContent='No flagged events in this view.';tr.append(td);tbody.append(tr);}
}
for(const id of selectIds) document.getElementById(id).addEventListener('change',render);
render();
</script></body></html>'''
    page = page.replace("__PLOTLY__", get_plotlyjs()).replace("__SERIES__", data_json)
    page = page.replace("__CUSUM__", json.dumps(cusum_threshold)).replace("__HEADER__",json.dumps(header))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.partial')
    temp.write_text(page, encoding="utf-8")
    temp.replace(path)
