"""Self-contained, offline Plotly explorer built from pipeline outputs."""
from __future__ import annotations
from pathlib import Path
import json
import pandas as pd
from plotly.offline import get_plotlyjs


def _json_rows(data:pd.DataFrame, keep:list, limit:int=150_000)->str:
    if data.empty:return "[]"
    frame=data[[c for c in keep if c in data.columns]].copy()
    if "period" in frame:
        frame["period"]=pd.to_datetime(frame["period"]).dt.strftime("%Y-%m-%d %H:%M").str.replace(" 00:00","",regex=False)
    # Explicit size limit avoids accidentally embedding tens of millions of records.
    if len(frame)>limit:frame=frame.tail(limit)
    return frame.to_json(orient="records").replace("</","<\\/")


def generate_dashboard(ref:pd.DataFrame,points:pd.DataFrame,shifts:pd.DataFrame,
                       events:pd.DataFrame,issues:pd.DataFrame,path:Path):
    r=_json_rows(ref,["period","location_id","metric","frequency","horizon","observed","expected","scale","reference_score","is_complete","history_count","window"])
    p=_json_rows(points.loc[points["point_alert"]],["period","location_id","metric","frequency","horizon","observed","test","score","p_value","q_value","direction"])
    s=_json_rows(shifts,["period","location_id","metric","frequency","horizon","method","direction","score","new_event","active"])
    e=_json_rows(events,["event_id","period","location_id","metric","frequency","horizon","event_type","direction","tests","test_count","observed","expected","min_p_value","min_q_value"])
    q=_json_rows(issues,["period","location_id","metric","frequency","quality_status","coverage_ratio"])
    html=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Anomaly Monitor • Investigation</title>
<style>
:root{--navy:#14253d;--teal:#008b85;--muted:#65738a;--line:#dfe5ed;--bg:#f5f7fa;--paper:#fff;--amber:#be812d;--red:#c44857}
*{box-sizing:border-box}body{font-family:Inter,ui-sans-serif,system-ui,Segoe UI,Arial;margin:0;background:var(--bg);color:var(--navy)}main{max-width:1450px;padding:28px 26px 70px;margin:auto}
header{display:flex;justify-content:space-between;gap:20px;align-items:center;padding-bottom:22px;border-bottom:1px solid var(--line)}h1{margin:3px 0 4px;font-size:30px;letter-spacing:-.6px}h2{font-size:17px;margin:0 0 10px}h3{font-size:13px;margin:0}p{line-height:1.55}small,.muted{color:var(--muted)}.eyebrow{color:var(--teal);font-size:12px;letter-spacing:2px;font-weight:800}.panel{padding:21px;border-radius:12px;background:var(--paper);border:1px solid var(--line);box-shadow:0 2px 14px #172d4506;margin:16px 0}.controls{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:14px}.date-controls{grid-template-columns:repeat(3,minmax(150px,1fr));align-items:end;margin-top:12px}.date-controls[hidden]{display:none}input[type=date]{display:block;width:100%;padding:10px;margin-top:7px;border:1px solid var(--line);border-radius:7px;color:var(--navy);font:inherit}#timeNotice{margin:12px 0 0;font-size:12px;color:var(--muted)}label{font-size:12px;color:#52617a;font-weight:700}select{display:block;width:100%;padding:11px;margin-top:7px;border:1px solid var(--line);background:white;border-radius:7px;color:var(--navy);font:inherit}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.kpi{background:#f8fafb;border:1px solid var(--line);border-radius:10px;padding:16px}.kpi b{font-size:28px;display:block}.kpi span{font-size:12px;color:var(--muted)}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.desc{font-size:13px;color:var(--muted);margin-top:0}#metricChart{height:450px}#shiftChart{height:310px}.scroll{max-height:450px;overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px}th{text-align:left;position:sticky;top:0;background:#eef3f6;color:#43546f;padding:10px}td{padding:10px;border-bottom:1px solid var(--line)}.tag{display:inline-block;padding:4px 8px;border:1px solid #c4dcd8;background:#eff8f7;border-radius:99px;font-weight:700;color:#21746e;font-size:11px}.pill{display:inline-block;background:#f4e9d6;color:#946a26;padding:3px 8px;border-radius:6px}ul{line-height:1.65;font-size:13px;color:#495972}footer{font-size:12px;color:#65738a;margin-top:24px;line-height:1.5}@media(max-width:850px){.controls,.kpis,.two{grid-template-columns:1fr 1fr}}@media(max-width:530px){.controls,.kpis,.two{grid-template-columns:1fr}main{padding:18px}}
</style></head><body><main><header><div><div class="eyebrow">ANOMALY MONITOR · VERSION 0.2</div><h1>Investigation overview</h1><small>Local, offline exploratory report · no company data is sent anywhere</small></div><span class="tag">REPORT SNAPSHOT</span></header>
<div class="panel"><div class="controls"><label>Location<select id="loc"></select></label><label>Metric<select id="met"></select></label><label>Reporting period<select id="freq"></select></label><label>Reference window<select id="horizon"></select></label></div></div>
<div class="panel"><div class="controls date-controls"><label>Visible time range<select id="timePreset"><option>Recommended</option><option>Last 24 hours</option><option>Last 7 days</option><option>Last 30 days</option><option>Last 90 days</option><option>Last 365 days</option><option>Last 2 years</option><option>All dates</option><option>Custom dates</option></select></label><div id="customRange" class="controls date-controls" style="grid-column:span 2;margin:0;grid-template-columns:1fr 1fr" hidden><label>From<input type="date" id="startDate"></label><label>Through<input type="date" id="endDate"></label></div></div><p id="timeNotice"></p></div>
<div id="kpis" class="kpis"></div>
<div class="panel"><h2>Observed values versus historical reference</h2><p class="desc">Use the time range above to narrow the entire report, and the navigator below the chart to zoom further. Triangles show unusual individual periods; diamonds mark the beginning of a sustained shift episode.</p><div id="metricChart"></div></div>
<div class="two"><div class="panel"><h2>Accumulated shift evidence</h2><p class="desc">CUSUM and EWMA follow runs of small deviations. A crossing creates a shift episode; a point flag concerns one observation.</p><div id="shiftChart"></div></div>
<div class="panel"><h2>Detector findings in this view</h2><p class="desc">Tests are not independent votes. P-values are conditional on model assumptions—not probabilities of a real anomaly.</p><div class="scroll"><table><thead><tr><th>Date</th><th>Test</th><th>Score</th><th>p</th><th>q (BH)</th></tr></thead><tbody id="testRows"></tbody></table></div></div></div>
<div class="panel"><h2>Consolidated events</h2><p class="desc">Multiple test flags on the same period appear as one point event. New sustained-change episodes appear separately.</p><div class="scroll"><table><thead><tr><th>Period</th><th>Type</th><th>Direction</th><th>Observed</th><th>Tests supporting finding</th><th>Agreement</th></tr></thead><tbody id="eventRows"></tbody></table></div></div>
<div class="two"><div class="panel"><h2>How to read the methods</h2><ul><li><b>Short/long reference:</b> fewer/more earlier comparable observations. Long references adapt more slowly; neither proves a true change.</li><li><b>Point tests:</b> estimate how unusual this one period is. A robust MAD score can disagree with a normal-model predictive test because assumptions differ.</li><li><b>CUSUM/EWMA:</b> accumulated evidence of a persistent shift. One episode is not proof of business causality.</li><li><b>p-value:</b> under the test model, the probability of data as extreme or more extreme; <b>not</b> the probability that an anomaly is real.</li><li><b>q-value:</b> BH-adjusted p-value within the date, resolution, reference, and test family; dependence and parameter estimation affect guarantees.</li></ul></div><div class="panel"><h2>Data quality and caveats</h2><p class="desc">Incomplete periods are excluded from tests; missing is not zero. Ratio metrics are reconstructed from component totals.</p><div id="qualitySummary" class="kpi"></div><p class="desc" style="margin-top:15px">The current view can have incomplete historical windows or unsupported models. Inspect <b>point_tests.csv</b>, <b>period_quality.csv</b>, and <b>source_quality.csv</b> for detailed diagnostics.</p></div></div>
<footer>This static HTML is an exploratory snapshot. Update it by rerunning the analysis; use the Streamlit app to import fresh CSVs or query PostgreSQL. Anomaly results do not establish causation, accounting errors, or appropriate business actions.</footer></main>
<script>__PLOTLY__</script><script>
const R=__REFERENCE__,P=__POINT__,S=__SHIFT__,E=__EVENT__,Q=__QUALITY__,SNAPSHOT_CAPPED=__CAP__;
const fields=['loc','met','freq','horizon'];
const uniq=xs=>[...new Set(xs)].filter(x=>x!=null).sort();
const pretty=x=>x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:3});
const keyOf=r=>[r.location_id,r.metric,r.frequency,r.horizon].join('\u0001');
function choices(id,arr){let el=document.getElementById(id),keep=el.value;el.replaceChildren();for(let v of arr){let x=document.createElement('option');x.textContent=v;x.value=v;el.append(x)}el.value=arr.includes(keep)?keep:(arr[0]??'')}
function selected(){return fields.map(id=>document.getElementById(id).value)}
function matching(o,tuple){return keyOf(o)===tuple.join('\u0001')}
function updateChoices(){
  choices('loc',uniq(R.map(x=>x.location_id)));let [loc]=selected();
  choices('met',uniq(R.filter(x=>x.location_id===loc).map(x=>x.metric)));
  let met=document.getElementById('met').value;
  const order=['h','D','W-SUN','MS','QS','YS'];
  choices('freq',uniq(R.filter(x=>x.location_id===loc&&x.metric===met).map(x=>x.frequency)).sort((a,b)=>order.indexOf(a)-order.indexOf(b)));
  let freq=document.getElementById('freq').value;
  choices('horizon',uniq(R.filter(x=>x.location_id===loc&&x.metric===met&&x.frequency===freq).map(x=>x.horizon)))
}
const ranges={h:7,D:90,'W-SUN':365,MS:730,QS:null,YS:null};
function parseStamp(v){return Date.parse(String(v).replace(' ','T'))}
function currentRange(all){
  if(!all.length)return {rows:[],min:'',max:'',start:'',end:'',name:''};
  const sorted=[...all].sort((a,b)=>parseStamp(a.period)-parseStamp(b.period));
  const earliest=sorted[0].period.slice(0,10), latest=sorted.at(-1).period.slice(0,10);
  const preset=document.getElementById('timePreset').value;
  const from=document.getElementById('startDate'),to=document.getElementById('endDate');
  for(const el of [from,to]){el.min=earliest;el.max=latest;}
  const freq=document.getElementById('freq').value;
  let days=preset==='Recommended'?ranges[freq]:({ 'Last 24 hours':1,'Last 7 days':7,'Last 30 days':30,'Last 90 days':90,'Last 365 days':365,'Last 2 years':730,'All dates':null }[preset]);
  let rows,start,end,name;
  const isCustom=preset==='Custom dates';
  document.getElementById('customRange').hidden=!isCustom;
  if(isCustom){
    if(!from.value || from.value<earliest || from.value>latest)from.value=earliest;
    if(!to.value || to.value<earliest || to.value>latest)to.value=latest;
    if(from.value>to.value){document.getElementById('timeNotice').textContent='Start date is after end date; adjust your selection.';return {rows:[],min:earliest,max:latest,start:from.value,end:to.value,name:'Invalid dates'};}
    start=from.value;end=to.value;name='Custom dates';
    rows=sorted.filter(x=>x.period.slice(0,10)>=start&&x.period.slice(0,10)<=end);
  }else if(days==null){
    rows=sorted;start=earliest;end=latest;name='All available dates';
    from.value=start;to.value=end;
  }else{
    const threshold=parseStamp(sorted.at(-1).period)-days*86400000;
    rows=sorted.filter(x=>parseStamp(x.period)>=threshold);
    start=rows.length?rows[0].period.slice(0,10):latest;
    end=latest;name=preset==='Recommended'?`Recommended for ${freq}`:preset;
    from.value=start;to.value=end;
  }
  document.getElementById('timeNotice').textContent=`${name}: ${start} through ${end} · ${rows.length.toLocaleString()} visible of ${all.length.toLocaleString()} available periods.${SNAPSHOT_CAPPED?' HTML snapshot reached its row limit; use Streamlit or CSVs for the full history.':''}`;
  return {rows,min:earliest,max:latest,start,end,name};
}
function inRange(x,sel){
  if(!sel.rows.length)return false;
  if(document.getElementById('timePreset').value==='Custom dates' || document.getElementById('timePreset').value==='All dates' || (document.getElementById('timePreset').value==='Recommended' && ranges[document.getElementById('freq').value]==null)){
    return x.period.slice(0,10)>=sel.start&&x.period.slice(0,10)<=sel.end;
  }
  const first=sel.rows[0].period,last=sel.rows.at(-1).period;
  return parseStamp(x.period)>=parseStamp(first)&&parseStamp(x.period)<=parseStamp(last);
}
function deDupDots(data){
  const m=new Map();for(const p of data){let key=p.period+'|'+p.direction;
    if(!m.has(key))m.set(key,{period:p.period,direction:p.direction,observed:p.observed,tests:new Set()});
    m.get(key).tests.add(p.test);}
  return [...m.values()].map(x=>({...x,tests:[...x.tests].sort().join(', ')}));
}
function fill(id,records,mapper){
  let table=document.getElementById(id);table.replaceChildren();
  for(let rec of records.slice(0,200)){let tr=document.createElement('tr');for(let val of mapper(rec)){let td=document.createElement('td');td.textContent=val??'—';tr.append(td)}table.append(tr)}
  if(!records.length){let tr=document.createElement('tr'),td=document.createElement('td');td.textContent='No records in the selected date range';tr.append(td);table.append(tr)}
}
function draw(){
  updateChoices();let tuple=selected(),full=R.filter(x=>matching(x,tuple));
  let sel=currentRange(full),r=sel.rows;
  let p=P.filter(x=>matching(x,tuple)&&inRange(x,sel)),
      s=S.filter(x=>matching(x,tuple)&&inRange(x,sel)),
      ev=E.filter(x=>matching(x,tuple)&&inRange(x,sel)),
      q=Q.filter(x=>x.location_id===tuple[0]&&x.metric===tuple[1]&&x.frequency===tuple[2]&&inRange(x,sel));
  let dots=deDupDots(p.filter(x=>x.direction==='above'||x.direction==='below'));
  let above=dots.filter(x=>x.direction==='above'),below=dots.filter(x=>x.direction==='below');
  let shifted=s.filter(x=>x.new_event);let seen=new Set();shifted=shifted.filter(x=>{const key=x.period+'|'+x.direction;if(seen.has(key))return false;seen.add(key);return true});
  const seriesType=r.length>1500?'scattergl':'scatter';
  const pl=[
    {x:r.map(x=>x.period),y:r.map(x=>x.observed),name:'Observed',type:seriesType,mode:'lines',line:{color:'#718297',width:1.5},connectgaps:false},
    {x:r.map(x=>x.period),y:r.map(x=>x.expected),name:'Historical reference',type:seriesType,mode:'lines',line:{color:'#126fba',width:2.4},connectgaps:false},
    {x:above.map(x=>x.period),y:above.map(x=>x.observed),name:'Above expected',mode:'markers',type:'scatter',marker:{color:'#d79a38',size:9,symbol:'triangle-up'},text:above.map(x=>x.tests),hovertemplate:'%{x}<br>Tests: %{text}<extra></extra>'},
    {x:below.map(x=>x.period),y:below.map(x=>x.observed),name:'Below expected',mode:'markers',type:'scatter',marker:{color:'#c94852',size:9,symbol:'triangle-down'},text:below.map(x=>x.tests),hovertemplate:'%{x}<br>Tests: %{text}<extra></extra>'},
    {x:shifted.map(x=>x.period),y:shifted.map(x=>r.find(o=>o.period===x.period)?.observed??null),name:'New shift episode',mode:'markers',type:'scatter',marker:{color:'#008b85',size:14,symbol:'diamond-open',line:{width:2}}}
  ];
  const layout={margin:{l:60,r:20,t:24,b:60},paper_bgcolor:'#fff',plot_bgcolor:'#fff',hovermode:'x unified',
    xaxis:{title:'Reporting period',gridcolor:'#edf1f6',rangeslider:{visible:true,thickness:.085},type:'date'},
    yaxis:{title:tuple[1],gridcolor:'#edf1f6'},legend:{orientation:'h',y:1.18},font:{family:'system-ui',color:'#243249'}};
  Plotly.react('metricChart',pl,layout,{responsive:true,displaylogo:false,scrollZoom:true});
  const methods=uniq(s.map(x=>x.method)),colors={cusum:'#007d78',ewma:'#d2893c'};
  let sp=[];
  for(let m of methods)for(let dir of ['upward','downward']){
    let sub=s.filter(x=>x.method===m&&x.direction===dir);
    if(sub.length)sp.push({x:sub.map(x=>x.period),y:sub.map(x=>x.score),name:m.toUpperCase()+' '+dir,type:sub.length>1500?'scattergl':'scatter',mode:'lines',line:{color:colors[m]||'#7c3aed',dash:dir==='downward'?'dot':'solid'}});
  }
  Plotly.react('shiftChart',sp,{...layout,margin:{l:50,r:12,t:12,b:55},legend:{orientation:'h',y:1.27},yaxis:{title:'Evidence statistic'}},{responsive:true,displaylogo:false});
  const items=[['Periods visible',r.length],['Complete',r.filter(x=>x.is_complete).length],['Point events',ev.filter(x=>x.event_type==='point').length],['New shifts',ev.filter(x=>x.event_type==='sustained_change').length]];
  document.getElementById('kpis').innerHTML=items.map(x=>`<div class="kpi"><b>${x[1]}</b><span>${x[0]}</span></div>`).join('');
  fill('testRows',[...p].reverse(),x=>[x.period,x.test,pretty(x.score),pretty(x.p_value),pretty(x.q_value)]);
  fill('eventRows',[...ev].reverse(),x=>[x.period,x.event_type,x.direction,pretty(x.observed),x.tests,x.test_count]);
  document.getElementById('qualitySummary').textContent=`${q.length} incomplete/undefined reporting periods in this date range`;
}
for(let id of fields)document.getElementById(id).addEventListener('change',draw);
for(let id of ['timePreset','startDate','endDate'])document.getElementById(id).addEventListener('change',()=>{
  if(id!=='timePreset')document.getElementById('timePreset').value='Custom dates';
  draw();
});
draw();
</script></body></html>'''
    for name,value in (("PLOTLY",get_plotlyjs()),("REFERENCE",r),("POINT",p),("SHIFT",s),("EVENT",e),("QUALITY",q),("CAP",str(len(ref)>150000).lower())):
        html=html.replace("__"+name+"__",value)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.partial');temp.write_text(html,encoding="utf-8");temp.replace(path)
