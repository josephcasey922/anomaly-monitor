# Excel and Power BI: stable CSV pipeline

## Quick setup (Microsoft 365 Excel for Windows)

1. In Python, run `anomaly-monitor run --config YOUR_CONFIG.yaml` or click **Run analysis** in Streamlit.
2. Excel: **Data → Get Data → From File → From Text/CSV**.
3. Import `outputs/alerts.csv` into a named Excel Table, e.g. `AnomalyEvents`.
4. Import `outputs/all_results.csv` as `ReferenceHistory` and, optionally, `outputs/point_tests.csv` as `TestEvidence`.
5. Choose **Close & Load To… → Table** (or connection/data model as appropriate). Set dates and numeric columns to suitable types in Power Query.
6. Create PivotTables or PivotCharts for location, metric, frequency, event type, direction, observed/expected and supporting tests. Use slicers for those categories.
7. In **Queries & Connections → Properties**, enable **Refresh data when opening the file**, optionally **Refresh every N minutes**. Test refresh with the workbook open and check for locked source files.
8. Generate a new Python report **at the same CSV paths**. Select **Data → Refresh All**. The connected Excel tables and visualizations should update.

This is a **pull** connection. Python does not push events to a running Excel session. The program's `watch` command or database polling updates the CSV; Excel refreshes independently.

## Recommended visuals

- Daily actual vs expected line chart, with separate above/below flags overlay.
- Flag count by week / location / metric (column chart), using `alerts.csv` rather than counting individual detector flags in `point_tests.csv`.
- Sustained shift episode table with start date, direction, metric and supporting method(s).
- A quality-summary page showing incomplete periods so a missing POS upload is not mistaken for genuine low demand.
- A detailed drillthrough tab linked by location/date/metric/frequency/horizon.

## Refresh caveats

- Data files are replaced atomically to reduce partially written output. Excel or antivirus may still temporarily lock files; close an actively edited CSV if replacement fails.
- The included `examples/Excel_Dashboard_Snapshot.xlsx` is a **STATIC** synthetic example, not a live Power Query workbook. Connecting its sheets to exported CSVs requires the steps above.
- Rows may increase on new data and after recalibration; load into *Excel Tables* (not fixed cell ranges).
- Microsoft Power BI can read the same CSVs via Power Query and perform scheduled refresh subject to its gateway and service configuration.
- A company environment should store outputs in an approved internal folder, use approved service credentials, and restrict access to sensitive reports.
