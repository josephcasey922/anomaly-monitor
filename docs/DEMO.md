# 5–10 minute employer demonstration (synthetic data only)

1. **Start:** `anomaly-monitor app`. Synthetic demo loads without a database.
2. **Show flexible import:** Open the column profiler. The synthetic source contains descriptive columns (`Region`, `DataSource`) that are ignored automatically when not selected.
3. **Choose metrics:** Select wash count, revenue, operating income, labor hours, opportunities and conversions. Show a derived operating margin and conversion rate computed from components.
4. **Run analysis:** Leave daily/weekly/monthly frequencies enabled, use short/long references, and enable CUSUM/EWMA. Interpret a point event versus a sustained-change episode.
5. **Statistical evidence:** Explain that predictive t, robust MAD and count/rate tests can disagree; p-values depend on models and are **not** the probability an anomaly is real. Emphasize data completeness.
6. **Zoom to a period:** In the investigation dashboard choose the recommended date range, a time preset, or Custom dates. For daily views try June 1–30, 2025. The event list follows the same range.
7. **Offline report:** Open `demo-run/outputs/dashboard.html` from `anomaly-monitor demo --directory demo-run`. Show the observed/reference chart and event table without the Python server.
7. **Excel:** Open `examples/Excel_Dashboard_Snapshot.xlsx` as an illustration; explain how the output CSVs can be linked to Power Query, refreshed independently of Python.
8. **Optional PostgreSQL:** With Docker installed, seed 80% of synthetic data, connect the app with the read-only account, then append the final 20% and rerun/poll. See [POSTGRES.md](POSTGRES.md).

## Questions worth asking colleagues

- Which reporting system/data warehouse provides stable daily or hourly exports?
- Are source rows transactions, stores per day, or accounting journal postings? What defines the date and a unique record?
- Which operational metrics are trustworthy, how are membership revenues attributed, and what are expected closures/posting delays?
- What is the accepted method for company-specific validation and handling suspected irregularities?
- Would an Excel/Power BI refresh of consolidated events be more useful than another dashboard?

Keep the conversation focused on **the synthetic learning project**. Do not connect to employer data until access, permissions and data handling have been approved.
