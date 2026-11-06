# Changelog

## v0.2.1 — Investigation dashboard date controls

- Added visible date ranges to both the Streamlit investigation page and offline HTML explorer.
- Added frequency-aware recommended windows, presets, inclusive custom dates and Plotly zoom/range navigation.
- Filter charts, evidence tables, event tables, and view summaries together; retain full history in CSV exports.
- Removed the previous 180-reference-point per-series snapshot truncation. The offline file maintains a 150,000-row safety cap and warns if reached.
- Deduplicated plotted point-anomaly markers for tests agreeing on the same date and direction.
- Added time-window regression tests and validated generated JavaScript syntax.
- **Validation boundary:** Streamlit is not installed in the release environment and the automated browser is restricted from loading local/loopback pages. Browser UI should be smoke-tested on a local machine.

## v0.2.0 — Import Studio, multiple statistical tests, PostgreSQL connector

- New Streamlit local browser app with CSV profiling, selected-column mapping, ratio metric definitions, per-metric method configuration, source-frequency/window controls, event exploration, and downloadable YAML profiles.
- Read-only reflected PostgreSQL table connector with bound date filters, schema/table/column allowlisting, row cap, ephemeral browser-entered password, and optional periodic refresh.
- Preserve data-quality and calendar semantics for daily/hourly and native monthly input; reject mathematically unsafe weekly-to-monthly summing.
- Added plug-in predictive t, robust MAD, Poisson, negative binomial and binomial point tests, with separate optional STL residual diagnostic.
- Added BH q-values across date + method-family batches; no posterior anomaly probabilities are claimed.
- Added EWMA plus CUSUM episode-state tracking with new vs active signals.
- Consolidate multiple test flags from the same period into single point events, with supporting test names and counts.
- Added an offline HTML explorer, new CSV evidence exports, synthetic PostgreSQL update demo, static Excel dashboard snapshot and Power Query instructions.
- Added v0.2 regression tests and implementation/limitations documentation.

**Validation boundary:** Automated Python/SQL query tests and synthetic end-to-end analysis pass. The local build runtime lacks Streamlit and a running PostgreSQL server, so the browser app and live PostgreSQL connection require smoke-testing on a machine with these optional components installed. Test thresholds are exploratory.

## v0.1.0 — Initial CSV-first monitor

- CSV-source normalizer, expected reporting calendar, calendar-aware aggregation, historical references, z-score/Poisson screening, clipped CUSUM, offline Plotly report, and CSV exports.
