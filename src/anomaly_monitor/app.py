"""Local Streamlit import wizard and interactive investigation app.

Run: anomaly-monitor app
This is a local, trusted-user tool. It is not a multi-tenant production web server.
"""
from __future__ import annotations
from pathlib import Path
import io,os,re,time
import numpy as np
import pandas as pd
import yaml
import streamlit as st
import plotly.graph_objects as go
from anomaly_monitor.config import LEGAL,validate_config
from anomaly_monitor.database import make_engine,list_tables,fetch_table
from anomaly_monitor.ingest import profile_frame
from anomaly_monitor.pipeline import run_data_frame
from anomaly_monitor.sample_data import generate_sample
from anomaly_monitor.time_window import PRESET_CHOICES, default_preset, resolve_window, restrict_dates

st.set_page_config(page_title="Anomaly Monitor · Studio",page_icon="📊",layout="wide")
st.markdown("""<style>
.block-container{padding-top:1.5rem;max-width:1450px}.hero{padding:1.1rem 1.4rem;background:#113249;border-radius:12px;color:white;margin-bottom:17px}.hero h1{margin:0;font-size:2rem}.hero p{color:#cbdce6;margin:.4rem 0 0}
</style>""",unsafe_allow_html=True)
st.markdown('<div class="hero"><h1>Anomaly Monitor <span style="font-size:.8rem;color:#a4d8d4">v0.2.1</span></h1><p>Import data → define metrics → compare statistical evidence → review point anomalies and sustained shifts</p></div>',unsafe_allow_html=True)


def demo_frame()->pd.DataFrame:
    from anomaly_monitor.demo import generate_wide_demo
    return generate_wide_demo()


def _clean(name):
    return re.sub(r"[^a-z0-9]+","_",str(name).lower()).strip("_") or "metric"


def _suggest_tests(aggregation,metric_type):
    if metric_type=="count":return "predictive_t,robust_mad,poisson,neg_binomial"
    if metric_type=="proportion":return "predictive_t,robust_mad,binomial"
    return "predictive_t,robust_mad"


def _query_db(*,host,port,database,user,password,sslmode,schema,table,columns=None,time_col=None,start=None,end=None,max_rows=100000,preview=False):
    engine=make_engine(host=host,port=port,database=database,user=user,password=password,sslmode=sslmode)
    try:
        return fetch_table(engine,schema=schema,table=table,columns=columns,
                           timestamp_column=time_col,start=start,end=end,max_rows=max_rows,preview=preview)
    finally:engine.dispose()


def render_report(result):
    """Explore a time slice of precomputed results, without rerunning detection."""
    frames = result["frames"]
    ref = frames["all_results"]
    point = frames["point_tests"]
    ev = frames["alerts"]
    sh = frames["shift_states"]
    st.divider()
    st.subheader("Investigation dashboard")

    a, b, c, d = st.columns(4)
    loc = a.selectbox("Location", sorted(ref["location_id"].unique()), key="view_loc")
    met = b.selectbox("Metric", sorted(ref.loc[ref.location_id == loc, "metric"].unique()), key="view_met")
    subset = ref.loc[(ref.location_id == loc) & (ref.metric == met)]
    frequencies = [f for f in ["h", "D", "W-SUN", "MS", "QS", "YS"] if f in subset.frequency.unique()]
    freq = c.selectbox("Period", frequencies, key="view_freq")
    subset = subset.loc[subset.frequency == freq]
    hor = d.selectbox("Reference", sorted(subset.horizon.unique()), key="view_hor")

    match = lambda frame: ((frame.location_id == loc) & (frame.metric == met) &
                           (frame.frequency == freq) & (frame.horizon == hor))
    full = ref.loc[match(ref)].sort_values("period")
    if full.empty:
        st.warning("There are no reporting periods for this combination.")
        return

    # Presets are relative to the selected series' latest *data* period.
    # A distinct key for each frequency preserves user preferences across views.
    preset = st.selectbox(
        "Visible time range",
        PRESET_CHOICES,
        index=PRESET_CHOICES.index(default_preset(freq)),
        key=f"view_range_{freq}",
        help="This only changes what you see; statistical tests always use full history."
    )
    start_date, end_date = pd.to_datetime(full.period).min().date(), pd.to_datetime(full.period).max().date()
    if preset == "Custom dates":
        lo_col, hi_col = st.columns(2)
        dates_key = f"{loc}_{met}_{freq}_{hor}"
        start_date = lo_col.date_input("From (inclusive)", value=start_date,
                                       min_value=start_date, max_value=end_date,
                                       key=f"view_start_{dates_key}")
        end_date = hi_col.date_input("Through (inclusive)", value=end_date,
                                     min_value=pd.to_datetime(full.period).min().date(),
                                     max_value=pd.to_datetime(full.period).max().date(),
                                     key=f"view_end_{dates_key}")
    try:
        lo, hi = resolve_window(full.period, preset, start=start_date, end=end_date)
    except ValueError as exc:
        st.warning(str(exc))
        return

    current = restrict_dates(full, lo, hi)
    findings = restrict_dates(point.loc[match(point) & point.point_alert], lo, hi)
    all_tests = restrict_dates(point.loc[match(point)], lo, hi)
    events = restrict_dates(ev.loc[match(ev)], lo, hi) if not ev.empty else ev
    shift_states = restrict_dates(sh.loc[match(sh)], lo, hi) if not sh.empty else sh
    if current.empty:
        st.info("No observations in this time range. Choose a different range.")
        return
    st.caption(
        f"Showing **{pd.Timestamp(lo):%b %d, %Y} – {pd.Timestamp(hi):%b %d, %Y}** "
        f"· **{len(current):,}** displayed periods / **{len(full):,}** available "
        f"· **{int(current.is_complete.sum()):,}** complete "
        f"· **{len(events):,}** consolidated events. "
        "Drag to zoom on either chart; double-click to reset the chart zoom."
    )

    # Scattergl supports denser hourly traces. Plotly zoom/range slider works
    # independently of the report's date range controls.
    trace_type = go.Scattergl if len(current) > 600 else go.Scatter
    g = go.Figure()
    g.add_trace(trace_type(x=current.period, y=current.observed, name="Observed",
                           mode="lines", line=dict(color="#8193a7", width=1.5), connectgaps=False))
    g.add_trace(trace_type(x=current.period, y=current.expected, name="Reference",
                           mode="lines", line=dict(color="#2576ab", width=2.5), connectgaps=False))

    # One visual marker per period/direction even when several tests agree.
    for direction, color, symbol in (("above", "#d08b30", "triangle-up"),
                                     ("below", "#c95162", "triangle-down")):
        flagged = findings.loc[findings.direction == direction]
        if not flagged.empty:
            marker_frame = (flagged.groupby("period", as_index=False)
                            .agg(observed=("observed", "first"),
                                 tests=("test", lambda x: ", ".join(sorted(set(x))))))
            g.add_trace(go.Scatter(x=marker_frame.period, y=marker_frame.observed,
                                   name=f"Point: {direction}", mode="markers",
                                   marker=dict(color=color, symbol=symbol, size=10),
                                   text=marker_frame.tests,
                                   hovertemplate="%{x}<br>Tests: %{text}<extra></extra>"))
    if not shift_states.empty:
        signals = shift_states.loc[shift_states.new_event]
        if not signals.empty:
            signals = signals.drop_duplicates(subset=["period", "direction"])
            marker_points = signals.merge(current[["period", "observed"]], on="period", how="left",
                                          suffixes=("", "_reference"))
            g.add_trace(go.Scatter(x=marker_points.period, y=marker_points.observed,
                                   name="New shift episode", mode="markers",
                                   marker=dict(color="#008d7d", symbol="diamond-open", size=14,
                                               line=dict(width=2))))
    g.update_layout(height=470, margin=dict(l=20, r=20, t=25, b=20),
                    legend=dict(orientation="h", y=1.13), hovermode="x unified",
                    xaxis_title="Reporting period", yaxis_title=met,
                    xaxis=dict(rangeslider=dict(visible=True, thickness=0.08), type="date"),
                    uirevision=f"{loc}/{met}/{freq}/{hor}/{preset}")
    st.plotly_chart(g, use_container_width=True)

    if not shift_states.empty:
        with st.expander("Sustained-change evidence (CUSUM / EWMA)", expanded=False):
            sg = go.Figure()
            for method in sorted(shift_states.method.dropna().unique()):
                for direction in ("upward", "downward"):
                    sliced = shift_states.loc[(shift_states.method == method) &
                                              (shift_states.direction == direction)]
                    if not sliced.empty:
                        sg.add_trace(go.Scatter(x=sliced.period, y=sliced.score, mode="lines",
                                                name=f"{method.upper()} {direction}"))
            sg.update_layout(height=270, margin=dict(l=20, r=20, t=10, b=30),
                             hovermode="x unified", xaxis_title="Reporting period")
            st.plotly_chart(sg, use_container_width=True)

    left, right = st.columns(2)
    with left:
        st.markdown("**Consolidated events in the visible range**")
        cols = ["period", "event_type", "direction", "tests", "observed", "expected",
                "min_p_value", "min_q_value"]
        st.dataframe(events[[x for x in cols if x in events]].iloc[::-1],
                     use_container_width=True, height=340, hide_index=True)
    with right:
        st.markdown("**Statistical findings in the visible range**")
        cols = ["period", "test", "score", "p_value", "q_value", "point_alert", "scoring_status"]
        st.dataframe(all_tests[[x for x in cols if x in all_tests]].iloc[::-1],
                     use_container_width=True, height=340, hide_index=True)
    st.info("**Interpretation:** Point tests flag individual observations. CUSUM/EWMA accumulate evidence of persistent changes. Test agreement is descriptive, and a p-value is not the probability that an anomaly is real.")
    st.markdown("**Export results / connect to Excel**")
    cols = st.columns(4)
    for i, key in enumerate(["alerts", "point_tests", "all_results", "period_quality"]):
        content = frames[key].to_csv(index=False).encode("utf-8")
        cols[i].download_button(key.replace("_", " ").title(), content,
                                file_name=f"{key}.csv", mime="text/csv", key=f"down_{key}")
    st.caption("Downloads retain the full analysis history (not only your visible date range). CSVs in the configured output folder retain stable names for Power Query refresh.")


st.sidebar.header("1 · Data source")
source=st.sidebar.radio("Source",["Synthetic demo","CSV upload","PostgreSQL"],key="src_kind")
frame=None
connected=None
refresh_enabled=False
refresh_interval=30
if source=="Synthetic demo":
    frame=demo_frame()
    st.sidebar.success(f"Loaded {len(frame):,} synthetic store-day rows")
elif source=="CSV upload":
    upload=st.sidebar.file_uploader("Choose CSV",type=["csv"],help="Source remains local to this running app unless you deploy it yourself")
    if upload is not None:
        try:
            frame=pd.read_csv(upload)
            if len(frame)>500_000:st.error("Limit 500,000 rows in the UI. Filter or aggregate your export.");st.stop()
            st.sidebar.success(f"Loaded {len(frame):,} rows")
        except Exception as exc:st.error(f"CSV read failed: {exc}");st.stop()
else:
    st.sidebar.caption("Read-only SELECT; no SQL editor and no database writes. Run locally, not on an exposed public server.")
    host=st.sidebar.text_input("Host",value="localhost")
    port=st.sidebar.number_input("Port",min_value=1,max_value=65535,value=5433)
    database=st.sidebar.text_input("Database",value="anomaly_demo")
    username=st.sidebar.text_input("User",value="anomaly_reader")
    password=st.sidebar.text_input("Password",type="password")
    sslmode=st.sidebar.selectbox("SSL mode",["require","verify-full","prefer","disable"],index=2)
    opts=dict(host=host,port=int(port),database=database,user=username,password=password,sslmode=sslmode)
    if st.sidebar.button("Discover accessible tables"):
        try:
            engine=make_engine(**opts)
            try:st.session_state["db_tables"]=list_tables(engine)
            finally:engine.dispose()
        except Exception as exc:st.sidebar.error(f"Connection failed: {exc.__class__.__name__}: {str(exc)[:200]}")
    tables=st.session_state.get("db_tables",[])
    if tables:
        chosen=st.sidebar.selectbox("Schema.table",tables,format_func=lambda x:f"{x[0]}.{x[1]}")
        st.sidebar.caption("Preview reads at most 2,000 rows. Analysis reads the selected date range with a hard row limit.")
        if st.sidebar.button("Preview table"):
            try:
                frame=_query_db(**opts,schema=chosen[0],table=chosen[1],max_rows=2000,preview=True)
                st.session_state["db_preview"]=frame
            except ValueError as exc:
                # The preview can exceed cap: user must filter when running.
                st.sidebar.error(str(exc))
            except Exception as exc:st.sidebar.error(f"Preview failed: {exc.__class__.__name__}: {str(exc)[:180]}")
        frame=st.session_state.get("db_preview")
        connected=(opts,chosen)
    if not tables:st.info("Enter a database connection and choose **Discover accessible tables**, or switch to the included synthetic demo.")

if frame is None:
    st.stop()

with st.expander("Inspect source columns and preview",expanded=True):
    st.dataframe(profile_frame(frame),use_container_width=True,hide_index=True)
    st.dataframe(frame.head(12),use_container_width=True,hide_index=True)

st.subheader("2 · Map columns and define metrics")
column_names=list(frame.columns)
profile=profile_frame(frame)
def choose_default(role,fallback):
    sug=profile.loc[profile.suggested_role==role,"column"].tolist()
    return sug[0] if sug else (fallback if fallback in column_names else column_names[0])

one,two,three,four=st.columns(4)
mode=one.selectbox("CSV/table shape",["wide","long"],index=0 if source!="CSV upload" or "metric" not in frame else 1)
time_col=two.selectbox("Timestamp column",column_names,index=column_names.index(choose_default("timestamp","period")))
locations=["(single location)"]+column_names
loc_default=choose_default("location","location_id")
site_col=three.selectbox("Location column",locations,index=locations.index(loc_default) if loc_default in locations else 0)
freq=four.selectbox("Source frequency",["D","h","MS","W-SUN","QS","YS"],help="Most granular input period; transaction mode is for timestamped raw rows")
row_grain=st.radio("Rows represent",["period","transaction"] if freq in ("D","h") else ["period"],horizontal=True,help="Transaction mode groups many source rows into each period. Period mode requires one observation per location/metric/period.")

metrics={};mapping={};selected=[]
if mode=="wide":
    numeric=profile.loc[profile.suggested_role=="numeric","column"].tolist()
    numeric=[x for x in numeric if x not in (time_col,site_col)]
    defaults=[c for c in numeric if any(w in c.lower() for w in ("wash","revenue","income","hours","opportun","conversion","labor","expense"))]
    selected=st.multiselect("Select numeric columns to analyze (other columns are ignored)",numeric,default=defaults[:10] or numeric[:5])
    if not selected:st.warning("Select at least one numeric metric column");st.stop()
    if len(set(_clean(x) for x in selected)) != len(selected):
        st.error("Selected column names normalize to duplicate metric IDs; rename ambiguous columns before importing.");st.stop()
    mapping={_clean(x):x for x in selected}
    config_rows=[]
    for key,col in mapping.items():
        iscount=any(w in key for w in ("count","wash","conversion","opportun","visits","customers"))
        kind="count" if iscount else "amount"
        config_rows.append({"Metric":key,"Source column":col,"Aggregation":"sum","Type":kind,
                            "Tests":_suggest_tests("sum",kind),"Transaction reducer":"sum"})
    edited=st.data_editor(pd.DataFrame(config_rows),hide_index=True,use_container_width=True,num_rows="fixed",
                          disabled=["Metric","Source column"],key="metric_editor")
    for _,row in edited.iterrows():
        metric=row["Metric"]
        tests=[x.strip() for x in str(row["Tests"]).split(",") if x.strip()]
        metrics[metric]={"aggregation":row["Aggregation"],"metric_type":row["Type"],
                         "tests":tests,"input_reducer":row["Transaction reducer"]}
else:
    a,b=st.columns(2)
    metcol=a.selectbox("Metric-name column",column_names,index=column_names.index("metric") if "metric" in column_names else 0)
    valcol=b.selectbox("Numeric value column",column_names,index=column_names.index("value") if "value" in column_names else 0)
    labels=frame[metcol].dropna().astype(str).unique().tolist()
    selected=st.multiselect("Which metric names should be imported?",sorted(labels),default=sorted(labels)[:9])
    if not selected:st.stop()
    rows=[]
    for label in selected:
        key=_clean(label)
        if any(item["Metric"]==key for item in rows):st.error("Metric names would collide");st.stop()
        kind="count" if any(x in key for x in ("wash","count","conversion","opportun")) else "amount"
        rows.append({"Metric":key,"Source value":label,"Aggregation":"sum","Type":kind,"Tests":_suggest_tests("sum",kind)})
    edited=st.data_editor(pd.DataFrame(rows),hide_index=True,use_container_width=True,num_rows="fixed",disabled=["Metric","Source value"],key="long_metric_editor")
    for _,row in edited.iterrows():
        metrics[row["Metric"]]={"aggregation":row["Aggregation"],"metric_type":row["Type"],
                                "tests":[x.strip() for x in str(row["Tests"]).split(",") if x.strip()]}
    aliases={label:_clean(label) for label in selected}

with st.expander("Add a derived ratio / percentage (optional)"):
    st.caption("Choose additive numerator and denominator components. Monthly/weekly ratios are recalculated from their aggregated totals—not averaged daily rates.")
    raw_keys=[k for k,s in metrics.items() if s["aggregation"]=="sum"]
    if len(raw_keys)>1:
        x,y,z,w=st.columns([2,2,2,1])
        newname=x.text_input("Metric name",value="operating_margin")
        num=y.selectbox("Numerator",raw_keys)
        den=z.selectbox("Denominator",raw_keys,index=min(1,len(raw_keys)-1))
        multiplier=w.selectbox("Multiplier",[1,100],index=1)
        prop=st.checkbox("Proportion: numerator is count of successes and denominator is number of trials",value=False)
        if st.button("Add derived metric"):
            if _clean(newname) in metrics:st.error("That metric already exists")
            else:
                st.session_state.setdefault("ratios",{})[_clean(newname)]={
                    "aggregation":"ratio","numerator":num,"denominator":den,"multiplier":multiplier,
                    "metric_type":"proportion" if prop else "ratio",
                    "tests":["predictive_t","robust_mad","binomial"] if prop else ["predictive_t","robust_mad"]}
    for name in list(st.session_state.get("ratios",{})):
        r=st.session_state["ratios"][name]
        if r["numerator"] in metrics and r["denominator"] in metrics and name not in metrics:
            metrics[name]=r
    if st.session_state.get("ratios"):
        st.dataframe(pd.DataFrame([{"Metric":k,**v} for k,v in st.session_state["ratios"].items()]),use_container_width=True,hide_index=True)
        if st.button("Clear derived metrics"):
            st.session_state["ratios"]={};st.rerun()

st.subheader("3 · Analysis settings")
legal=[x for x in ["h","D","W-SUN","MS","QS","YS"] if x in LEGAL[freq]]
default_freq=[x for x in ["D","W-SUN","MS"] if x in legal] or [legal[0]]
frequencies=st.multiselect("Periods to analyze",legal,default=default_freq)
if not frequencies:st.stop()
windows={}
with st.expander("Historical reference windows",expanded=False):
    st.caption("For daily: 8 means previous 8 comparable weekdays. Monthly: 8 means previous 8 calendar months. Shorter windows adapt faster.")
    for f in frequencies:
        c1,c2=st.columns(2)
        default_short=8 if f in ("h","D") else 6 if f=="W-SUN" else 4
        default_long=24 if f in ("h","D") else 12 if f in ("W-SUN","MS") else 8
        windows[f]={"short":c1.number_input(f"{f}: short window",min_value=2,max_value=100,value=default_short,key=f"short_{f}"),
                    "long":c2.number_input(f"{f}: long window",min_value=2,max_value=200,value=default_long,key=f"long_{f}")}
cc1,cc2,cc3=st.columns(3)
alpha=cc1.number_input("Unadjusted test alpha",min_value=.001,max_value=.20,value=.01,step=.005,format="%.3f")
fdr=cc2.number_input("FDR target q",min_value=.001,max_value=.20,value=.05,step=.01,format="%.3f")
z_threshold=cc3.number_input("Heuristic score threshold",min_value=1.,max_value=10.,value=3.,step=.5)
with st.expander("Reporting calendar & sustained-change detection"):
    days=st.multiselect("Expected weekdays (Mon=0)",list(range(7)),default=list(range(7)))
    hours=st.multiselect("Expected hours (hourly input only)",list(range(24)),default=list(range(8,19)))
    shifts_enabled=st.checkbox("Enable sustained-change methods",value=True)
    shifts_methods=st.multiselect("Sustained-change detectors",["cusum","ewma"],default=["cusum","ewma"])
    sh_c1,sh_c2,sh_c3=st.columns(3)
    cusum_h=sh_c1.number_input("CUSUM threshold h",min_value=.5,max_value=50.,value=5.)
    ewma_lam=sh_c2.number_input("EWMA smoothing λ",min_value=.05,max_value=1.,value=.2,step=.05)
    shift_ref=sh_c3.selectbox("Shift reference",["long","short"],index=0)

schema={"mode":mode,"timestamp_column":time_col,"location_column":site_col,
        "row_grain":row_grain}
if mode=="wide":schema["metrics"]=mapping
else:schema.update({"metric_column":metcol,"value_column":valcol,"metric_aliases":aliases})
cfg={"input":{"source":"csv","path":"REPLACE_WITH_INPUT.csv","frequency":freq},
     "source_schema":schema,"output":{"directory":str((Path.cwd()/"monitor_outputs").resolve()),"interactive_html":True},
     "calendar":{"active_weekdays":days,"active_hours":hours},"metrics":metrics,
     "analysis":{"frequencies":frequencies,"windows":windows,"min_history_fraction":1.0,"alpha":float(alpha),
                 "fdr_alpha":float(fdr),"z_threshold":float(z_threshold),
                 "shift_detectors":{"enabled":shifts_enabled,"horizon":shift_ref,"methods":shifts_methods,
                   "cusum":{"k":0.5,"h":float(cusum_h),"score_cap":2.0,"release":1.0},
                   "ewma":{"lambda":float(ewma_lam),"L":3.0,"score_cap":2.0,"release":0.5}}}}
if source=="PostgreSQL" and connected:
    dbopts,table=connected
    cfg["input"]["source"]="postgres"
    cfg["input"]["database"]={"host":dbopts["host"],"port":dbopts["port"],"database":dbopts["database"],
                              "username":dbopts["user"],"schema":table[0],"table":table[1],
                              "sslmode":dbopts["sslmode"],"password_env":"ANOMALY_MONITOR_DB_PASSWORD","max_rows":100000}
    cfg["input"].pop("path",None)

try:
    checked=validate_config(cfg)
except Exception as exc:
    st.error(f"Review your metric configuration: {exc}")
    st.stop()

st.download_button("Save reusable YAML profile (no credentials)",yaml.safe_dump(cfg,sort_keys=False),file_name="monitor_profile.yaml",mime="text/yaml",help="For CSV, change the input path; for PostgreSQL set the password in an environment variable. No credentials are saved.")

if source=="PostgreSQL" and connected:
    with st.expander("PostgreSQL query bounds and polling"):
        all_dates=frame[time_col] if time_col in frame else None
        start=st.text_input("Start timestamp inclusive (optional)",value="")
        end=st.text_input("End timestamp exclusive (optional)",value="")
        limit=st.number_input("Hard maximum rows",1000,500000,100000,step=1000)
        refresh_enabled=st.checkbox("Automatically poll PostgreSQL and regenerate the report",value=False)
        refresh_interval=st.number_input("Polling interval (seconds)",min_value=10,max_value=3600,value=60,step=10)

st.caption("A point test may find an isolated extreme. CUSUM/EWMA track sustained evidence. Detector agreement is descriptive, not independent confirmation or a calibrated posterior probability.")
run=st.button("Run analysis",type="primary",use_container_width=True)


def run_and_show(fetched):
    try:
        with st.spinner("Validating calendar, calculating references and running tests…"):
            output=run_data_frame(fetched,checked)
        st.session_state["last_result"]=output
        st.success(f"Analysis complete. {len(output['frames']['alerts'])} consolidated events; outputs written to {checked['output']['directory']}")
    except Exception as exc:
        st.error(f"Analysis failed: {exc.__class__.__name__}: {str(exc)[:500]}")
        return
    render_report(output)

if refresh_enabled and connected:
    st.warning("Polling re-queries a bounded table and recomputes the analysis. It is not CDC or sub-second real-time streaming. Disable it when finished.")
    # Use a fragment so each refresh re-queries rather than serving stale cached data.
    @st.fragment(run_every=f"{int(refresh_interval)}s")
    def live_query():
        try:
            fetched=_query_db(**connected[0],schema=connected[1][0],table=connected[1][1],
                  time_col=time_col,start=start or None,end=end or None,max_rows=int(limit))
            run_and_show(fetched)
        except Exception as exc:st.error(f"Polling query failed: {exc.__class__.__name__}: {str(exc)[:250]}")
    live_query()
elif run:
    if source=="PostgreSQL" and connected:
        try:
            fetched=_query_db(**connected[0],schema=connected[1][0],table=connected[1][1],
                  time_col=time_col,start=start or None,end=end or None,max_rows=int(limit))
            run_and_show(fetched)
        except Exception as exc:st.error(f"Database fetch failed: {exc.__class__.__name__}: {str(exc)[:250]}")
    else:run_and_show(frame)
elif "last_result" in st.session_state:
    render_report(st.session_state["last_result"])
