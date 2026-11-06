# Input semantics and calendar completeness

## Data shapes

The local Streamlit UI accepts **wide CSVs/SQL tables** (a date column, a location column, and selected numeric columns) and **long tables** (date, location, metric label, numeric value). Every metric must have an explicit aggregation meaning.

A saved `source_schema` maps actual source field names into internal IDs. Unselected columns are discarded. If a column's meaning is unclear (gross vs net revenue, payment date vs transaction date, membership attribution, inventory adjustments), the system cannot infer the correct accounting treatment.

**Row grain matters:**

- `period`: each row already summarizes one source period per location. Duplicate `period/location/metric` identifiers raise an error.
- `transaction`: multiple source rows per hour/day can be consolidated using `sum`, `mean`, `last`, or `count` per metric. The source timestamp is floored to the target input period. This is not deduplication of accidental repeated transactions; duplicate source identifiers must be handled upstream.
- When there are no transaction rows on an operating day, the current code considers that day **missing**, not zero; production counting needs an authoritative store-open calendar and a zero-activity policy.

Input timestamps must use a **consistent timezone-naive business calendar**. Time-zone conversions, DST transitions, and cross-location timezone differences need explicit source-system handling before comparisons. Native source resolutions are `h`, `D`, `W-SUN` (Monday-start weekly periods), `MS`, `QS`, and `YS`. Source periods must be labeled by their start dates.

## Which aggregations are safe?

- Hourly -> daily/weekly/monthly/quarterly/yearly.
- Daily -> weekly/monthly/quarterly/yearly.
- Calendar monthly -> quarterly/yearly.
- Calendar quarterly -> yearly.
- Weekly records **cannot** safely reconstruct calendar months/quarters/years: weeks may span boundaries, and splitting a weekly count across months would fabricate data.
- Finer frequencies cannot be recovered from coarser source data.

`sum` preserves signed amounts, `mean` is an equally weighted mean of complete source periods, and `last` retains the end quantity only when the target period is complete. Derived `ratio` values are reconstructed from **sum of numerator / sum of denominator** times multiplier; they are not summed or blindly averaged. A zero denominator gives an undefined metric, not zero.

## Missing data and incomplete periods

A reporting calendar lists expected days/hours, not just days with observed records. Period coverage = observed non-null source intervals / expected source intervals in the **full** calendar period. Partial opening weeks/months are incomplete even if the source has no apparent gaps. Incomplete source periods are retained for audit but **excluded** from anomaly scoring.

- `missing_row`: expected timestamp/location/metric not present.
- `missing_value`: timestamp exists but has null value.
- `outside_reporting_calendar`: observation falls outside configured working weekdays/hours.
- `incomplete_period`: not enough source intervals for the entire reporting period.
- `incomplete_component`: ratio's numerator or denominator is incomplete.
- `zero_denominator`: complete ratio inputs but zero denominator.
- `insufficient_history`: not enough earlier comparable observations.
- `model_inapplicable_or_zero_scale`: score impossible under chosen test.

**Limits:** Calendar settings are global, not location-specific; opening/closing dates, weather shutdowns, holidays, delayed posting, end-of-day closeouts and company-specific definitions need later business-specific configuration. When monitoring a current month, the current calendar month is marked incomplete until all expected intervals are present.

## Historical comparisons

- Hourly: same weekday and same hour in earlier weeks.
- Daily: same weekday in earlier weeks.
- Weekly/monthly/quarterly/yearly: preceding **complete calendar periods**, with missing periods preserved in their calendar position. No automatic yearly seasonality adjustment for monthly/quarterly groups.

No current observation contributes to its own reference distribution (`shift(1)` is used). Baselines may change after a late correction to earlier data, which can also change later CUSUM/EWMA states. Polling currently reruns the bounded source set rather than maintaining a transactional detector state.

## Practical limits

Source grids and database fetches have hard size limits to avoid silent truncation or accidental multi-million-row imports. The app is designed for **local prototype/demo use**, not unbounded warehouse analytics. In real systems, select an approved database view that already defines the correct business grain and meaningful aggregation, and enforce access controls independent of this code.
