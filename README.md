# Anomaly Monitor v0.2.1

**Explore unusual observations and persistent changes in operational or financial data.**

An installable, local-first Python package with a Streamlit CSV/PostgreSQL import wizard, calendar-aware aggregation, multiple statistical tests, clear point-vs-shift events, an offline interactive HTML report, and Excel-ready exports. The included demonstration data are **entirely synthetic**.

> **Research / demonstration status.** This is not a validated financial control, a causality engine, a guaranteed real-time service, or a production-hardened multi-user web application. Results require domain-specific validation before being used for decisions. See [scientific limitations](docs/STATISTICS.md) and [data requirements](docs/DATA_CONTRACT.md).

## Five-minute demonstration (Windows PowerShell)

From the extracted repository directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[app,dev]"
.\.venv\Scripts\anomaly-monitor.exe app
```

The browser opens a **local** dashboard. It loads the built-in synthetic example without needing a CSV, PostgreSQL, or company credentials. Select a metric, adjust the detectors and historical windows, click **Run analysis**, and examine the plot, consolidated events, and individual statistical findings. Export CSV reports from the page.

For a fully offline, command-line demonstration that does **not** require Streamlit:

```powershell
.\.venv\Scripts\anomaly-monitor.exe demo --directory demo-run
```

Open `demo-run/outputs/dashboard.html`. The command creates a synthetic wide-format CSV, a reusable YAML profile, and the report files.

On macOS/Linux, replace `.\.venv\Scripts\` with `./.venv/bin/` and use `python3 -m venv .venv`. Python 3.11+ is required.

## Explore specific dates without crowding the chart

**New in v0.2.1:** Both the Streamlit app and generated offline `dashboard.html`
let you narrow the visible period without recomputing historical statistics:

- **Recommended** initial ranges: hourly = last 7 days, daily = last 90 days,
  weekly = last year, monthly = last 2 years, quarterly/yearly = full history.
- Choose **Last 24 hours**, **Last 7/30/90/365 days**, **Last 2 years**, **All dates**,
  or **Custom dates**. These are relative to the **last observation**, not today's date.
- The actual/reference plot and event/evidence tables show the same date range.
  Drag over the Plotly chart to zoom to individual days or hours; double-click to reset.
  An x-axis navigator is included on the main chart.
- The full history remains in the CSV exports. Date filtering is a **display choice**;
  every statistical test still uses its configured historical reference window.
- The offline HTML snapshot embeds up to 150,000 reference rows to keep file sizes bounded.
  If that cap is reached, it displays a warning. Use the Streamlit app and full CSV
  outputs to explore large histories beyond the HTML cap.

**Examples:** Select `D → Recommended` to view recent daily results, or select
`Custom dates → 2025-06-01 through 2025-06-30` to investigate June. For hourly
records, select the last 7 days and drag to zoom into a few hours.

## What changed from v0.1?

| Capability | v0.2.1 |
|---|---|
| CSV imports | Wide or long format; identify date/location/metrics in an interactive interface; unrelated columns ignored |
| Row grain | Already-aggregated periods **or** many timestamped transaction rows (explicit choice) |
| PostgreSQL | Discover permitted schemas/tables/columns; read-only, bounded SQLAlchemy queries; no user-entered SQL |
| Source frequencies | Hourly, daily, weekly, monthly, quarterly, yearly (only mathematically safe aggregation paths) |
| Metric definitions | Additive amounts/counts; measured means; ending balances; calculated numerator/denominator ratios |
| Point tests | Z score, predictive t approximation, median/MAD, Poisson, negative binomial, binomial, optional trailing STL residual |
| Shift methods | Clipped two-sided CUSUM **and** EWMA with new-event / active-episode separation |
| Multiple-test evidence | Individual results, conditional model p-values, per-date/test-family BH q-values, consolidated events showing test agreement |
| Reports | Offline HTML explorer, Streamlit interactive views, CSVs, polished example Excel snapshot |
| Refresh | CLI CSV watcher; periodic PostgreSQL re-query via Streamlit or CLI poll; reports overwritten at stable paths |
| Tests | Source adaptation, completeness, weighted ratios, source calendar, shift episodes, database query boundaries, end-to-end pipeline |

## Import CSVs without preprocessing every column

The **Import** panel profiles columns and suggests date, location and numeric fields. Choose the useful columns only; the rest are ignored. Save a YAML mapping from the UI to reuse the same schema for future exports.

For *wide* source data:

```csv
BusinessDate,StoreID,Washes,NetRevenue,LaborHours,OperatingIncome,Region,UnusedNotes
2025-01-01,A,110,1420.12,27.5,-80.33,West,example
2025-01-02,A,125,1642.30,29.1,42.90,West,example
```

Select `BusinessDate` as timestamp, `StoreID` as location, and only the metrics that matter. **Choose the correct row grain**: if rows are already daily totals, use `period`; if each row is a transaction, use `transaction` and specify how transaction rows aggregate. Duplicate period-grain identifiers raise errors instead of quietly double-counting.

For *long* data, select the timestamp, location, metric name, and value columns; optional aliases map unfamiliar metric names. The engine internally standardizes all supported sources into `period, location_id, metric, value`.

**Critical:** A column named “revenue” could be gross, net, attributed membership revenue, or another definition. The wizard offers suggestions, not guarantees. Confirm financial meaning and grain before running. There is no automatic inference of missing values as zero.

## Different metrics require different mathematical treatment

- `sum`: wash counts, amounts, labor hours, revenues and **signed** operating income.
- `mean`: average of per-interval measures (unweighted); do **not** use it to aggregate financial ratios unless that average is the intended definition.
- `last`: ending quantity at each interval, only for complete source periods.
- `ratio`: derive `numerator / denominator × multiplier` **after aggregating the two components**. Examples: operating margin, conversion rate, average revenue per wash.
- `binomial`: available for a proportion where numerator and denominator are genuine nonnegative integer successes/trials and success count does not exceed trials.
- `poisson` and `neg_binomial`: only for additive nonnegative integer count metrics. Overdispersion and estimation uncertainty affect their calibration.

## Interpret the statistics correctly

A **point event** concerns one unusually high or low observation relative to a historical reference. Several point tests may support one event, but their results are correlated—not independent votes.

A **sustained-change episode** concerns an accumulation of evidence in CUSUM or EWMA. A new shift signal marks the **start** of a detected episode; its `active` state continues on later observations rather than creating a new event each day. A sustained shift may be real, or it may arise from a misspecified historical baseline.

A **p-value is not the probability that an anomaly is genuine**. Some methods have no defensible p-value and display only heuristic scores. BH-adjusted q-values are computed per period, resolution, baseline, and test family across the locations/metrics under evaluation; dependence and estimated parameters limit formal guarantees.

The previous observation never enters its own historical baseline. Daily references compare comparable weekdays; hourly references compare the same weekday and hour. Monthly, quarterly and yearly references compare consecutive complete calendar periods. Incomplete periods and unscorable methods remain visible in the CSVs.

[Methods and assumptions](docs/STATISTICS.md) · [Data contract](docs/DATA_CONTRACT.md)

## Reusable YAML + command line

The template at `examples/config.yaml` maps a synthetic wide CSV. Customize it and run:

```powershell
.\.venv\Scripts\anomaly-monitor.exe run --config examples/config.yaml
```

The app also downloads a source-specific YAML profile containing **no database password**. Use its `input.path` for a CSV or its PostgreSQL connection information with the password supplied through an environment variable.

## PostgreSQL via the browser

Choose **PostgreSQL** in the local app, enter host/port/database, username and a session-only password, then click **Discover accessible tables**. Choose a table and preview it, map columns, set analysis options, then run the query. An optional **auto-poll** control rereads the bounded table and regenerates outputs on an interval.

The app only constructs reflection-validated **SELECT** statements, never lets users type arbitrary SQL, and requests a read-only transaction on PostgreSQL. We strongly recommend an actual **read-only PostgreSQL role**. Passwords are not saved into exported YAML profiles.

**This is polling, not change-data capture (CDC), event-driven updates, or sub-second real-time analysis.** Re-reading large datasets is expensive and corrections to older periods may change later baselines. Queries have configurable row limits and optional date filters. The local tool does not securely authenticate multiple remote users, so do not expose it directly to the internet or use it against sensitive systems without security review.

The included [PostgreSQL demo](docs/POSTGRES.md) uses Docker and *synthetic* rows. Seed the first 80% of records, run analysis, append the remaining 20%, and re-run or enable polling to watch results update. The runtime used to build this package did **not** include a PostgreSQL server; the SQL layer has been tested with an in-memory database, while live PostgreSQL integration still needs to be exercised on your machine.

## Excel / Power BI integration

Every run writes stable filenames to the configured output folder:

| File | Contents |
|---|---|
| `all_results.csv` | Reference distributions, completeness, comparable history and scores |
| `point_tests.csv` | Every test, scores, p-values, q-values, flags and inapplicability reasons |
| `shift_states.csv` | CUSUM/EWMA upward/downward state at each reporting period |
| `alerts.csv` | **One consolidated event** per direction/period or new shift episode; supporting methods listed |
| `summary.csv` | Store/metric/frequency/horizon overview |
| `source_quality.csv` | Missing/null/off-calendar source observations |
| `period_quality.csv` | Incomplete or invalid aggregated reporting periods |
| `quality_summary.csv` | Source coverage summary |
| `dashboard.html` | Standalone interactive Plotly explorer with date-range presets, custom dates and zooming |

`examples/Excel_Dashboard_Snapshot.xlsx` illustrates layout with cards, formulas, an actual/reference trend chart, and an alerts table. It is a **static example**; it does not include a preconfigured live Power Query connection. To refresh data automatically within Excel, use **Data → Get Data → From Text/CSV** on the stable output files, load to Excel tables, and configure refresh intervals / refresh on opening. Python and Excel refresh on separate schedules. See [Excel guide](docs/EXCEL.md).

## Local PostgreSQL refresh testing

See [docs/POSTGRES.md](docs/POSTGRES.md) for Docker Compose and synthetic data `seed` / `append` steps. CLI polling works for PostgreSQL-backed YAML profiles, with the password in `ANOMALY_MONITOR_DB_PASSWORD`:

```powershell
.\.venv\Scripts\anomaly-monitor.exe watch --config examples/postgres_config.yaml --interval 60
```

The polling process runs only while its terminal/process remains active. No persistent cloud worker is created.

## Verification

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The release was tested with synthetic samples and an in-memory SQL database. The built-in test suite does not certify low false-alarm rates in real company data. The optional STL diagnostic is computationally expensive, exploratory, and should be validated separately before use. See [docs/STATISTICS.md](docs/STATISTICS.md).

## Scope and security

- Public repository: synthetic data, code, example report; **no employer information or credentials**.
- Actual employer records: use only with approval, follow security/data retention policies, and keep proprietary data and output outside the public repository.
- No automated modifications to accounting records or business operations.
- No automatic investigation or corrective-action recommendations.
- Local source/table/schema mapping is reusable; business semantics and thresholds still require human confirmation.

MIT-licensed example package. [Changelog](CHANGELOG.md) · [Running the demo](docs/DEMO.md) · [GitHub publishing](docs/GITHUB.md).
