# Statistical methods, assumptions, and validation

**Core principle:** A model score is evidence *under a set of assumptions*, not a diagnosis and not the probability an anomaly is genuine. The program intentionally keeps every per-method result separate in `point_tests.csv`, and aggregates same-period flags into a single event in `alerts.csv`.

## Reference distributions

For each location/metric/time-resolution, a rolling window of earlier **comparable** complete observations estimates the mean and sample SD. Daily values compare the same weekday; hourly values compare the same weekday and hour. A `short` baseline adapts faster; a `long` baseline is slower and often more stable. A baseline reference is not itself a trend-change test.

Data gaps are not filled with zero. A missing observation remains in its calendar position and may make a baseline unscorable. Small reference samples can severely inflate false-positive rates.

## Point tests

| Name in YAML | Statistic / test | Appropriate use / caveat |
|---|---|---|
| `zscore` | `(y-mean)/SD`, flag if absolute value >= threshold | General numeric heuristic; **no p-value** |
| `predictive_t` | `(y-mean)/(s sqrt(1+1/n))`, compared to t with `n-1` df | Next-observation prediction assuming iid normal references; p-value ignores weekday-level drift and nonnormality |
| `robust_mad` | `(y-median)/(1.4826 × MAD)` | Robust center/scale, normal-consistency factor; heuristic, unstable with tiny history/zero MAD; **no p-value** |
| `poisson` | Two-sided discrete tail from `Poisson(estimated mean)` | Counts with variance roughly equal to mean; estimate uncertainty makes nominal p-values approximate |
| `neg_binomial` | Discrete negative-binomial tail, with variance estimated from reference SD | Overdispersed counts (`sample variance > mean`); moments estimates can be unstable; otherwise test unavailable |
| `binomial` | Two-sided discrete tail for observed successes/trials using historical weighted success rate | Only if numerator/denominator are actual integer successes/trials; the historical probability is estimated and not fixed |
| `stl_residual` | Fit robust STL to a **trailing window only**, forecast next period with last trend and previous seasonal cycle, compare residual to fitted residual SD | Optional, slow and exploratory; no p-value; needs >=3 complete seasonal cycles and equal spacing; not recommended as primary detector |

**Discrete p-values:** `min(1, 2 × min(lower-tail CDF, upper-tail survival))` is a conservative-style two-tail construction when the model parameters are known, but the reference parameters here are *estimated*. This does **not** guarantee advertised false-alarm probabilities. A binary rate from 5 trials must not be evaluated as though it has the precision of a rate from 50,000 trials.

`point_alert` uses an unadjusted alpha for methods with p-values and a configurable absolute score threshold for heuristic methods. The report also provides a Benjamini–Hochberg `q_value` and `fdr_alert` for the set of tests at one date / frequency / reference / method family. BH assumptions can fail under correlated tests, time-series autocorrelation, or estimated baselines; interpret adjusted p-values cautiously. Changing alpha across many metric/window choices also creates selection effects.

**Detector agreement is descriptive.** A predictive t test and a robust MAD test use the same historical measurements, so their signals are correlated. A report showing `3 tests` is not a probability, a posterior, nor three independent confirmations.

## Persistent-shift detectors

Both methods use the signed standardized residual relative to the selected reference, with contributions capped to reduce the influence of one extreme point. Missing scores reset the state.

**CUSUM** maintains two recursive quantities:

```
up[t]   = max(0, up[t-1] + clip(z[t],-c,c) - k)
down[t] = max(0, down[t-1] - clip(z[t],-c,c) - k)
```

A fresh crossing of `h` emits `new_event=true`. The direction stays active until accumulated evidence has recovered below a configured release level. Unlike v0.1, a brief dip just under `h` does not immediately create another independent event if the episode has not recovered.

**EWMA** recursively smooths clipped residuals:

```
ewma[t] = lambda * clip(z[t],-c,c) + (1-lambda)*ewma[t-1]
```

The exploratory limit is `L × sqrt(lambda/(2-lambda) × [1-(1-lambda)^(2t)])`, based on the **iid unit-variance** reference assumption. We detect positive and negative crossing episodes separately. This is not a calibrated company-specific guarantee and becomes less trustworthy with serial correlation and adaptive rolling baselines.

CUSUM and EWMA are *change evidence*, not point-anomaly tests or automated root-cause analyses. In an increasing process, a short rolling baseline can adapt so rapidly that residuals diminish; a longer reference may preserve evidence for longer. Both may detect drift, variance changes, or incorrectly modeled seasonality rather than a true step change.

## Validation checklist before production use

1. Audit the source grain, sign convention, revenue definition, closures, posting delays and whether all observations are complete.
2. Plot the raw series and comparable-period references, including holidays and special events.
3. Simulate stable data and measure false-alarm rate **per metric and frequency**, not only a total across thousands of tests.
4. Inject labeled isolated spikes, persistent shifts, variance changes and missing periods; measure detection sensitivity and detection latency at matched false-alarm budgets.
5. Check model assumptions: count overdispersion, zero inflation, autocorrelation, seasonal patterns, unequal exposures, long-term trends, and mixture distributions.
6. Calibrate p-values using appropriate predictive methods or held-out data; use historical backtesting to choose thresholds for a specific use case.
7. Track tests and software versions with each report; rerun or retract downstream alerts after corrected historical records.
8. Obtain approval for confidential data and keep all company datasets/output reports in approved internal systems.

No method or combination in this release establishes that a data point is erroneous or that an automated accounting correction is justified.
