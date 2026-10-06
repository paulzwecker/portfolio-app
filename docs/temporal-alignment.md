# Temporal forecast and outcome alignment

The Company Explorer's **Forecast vs. outcome** section selects a native model
revision and displays the selected consensus series, a later reported fact, and
listing prices for one annual fiscal year where their periods can be aligned. Native
ordinal projections remain explicitly unmapped until the model revision stores a
fiscal-year anchor. This is an inspection/query layer over canonical records; it does
not calculate forecast error, ranking, model-quality scores, or investment decisions.

## Query

`GET /v1/companies/{company_id}/temporal-alignment` accepts:

- `fiscal_year` (required)
- `as_of` (required forecast date)
- `known_at` (optional timezone-aware forecast knowledge cutoff)
- `outcome_known_at` (optional timezone-aware outcome knowledge cutoff)
- `horizon_days` (optional calendar-day horizon, 1–3650; defaults to 365)

When `known_at` is omitted, the cutoff is the end of `as_of` in UTC. An explicit
`known_at` must be timezone-aware and no later than that UTC day end. Effective
time is capped at the same instant as knowledge time; a record effective later
that day cannot leak into an earlier intraday view even if it was recorded early.
The response returns both forecast and outcome cutoffs.

`outcome_known_at` is independent of forecast knowledge. It defaults to the current
UTC time. Reported facts and subsequent prices are included only if their source
observation and application record were known by that cutoff. For a true historical
evaluation, supply an outcome cutoff that is late enough for the relevant filing and
market horizon. A reported figure is not exposed as forecast-time knowledge.

## Alignment rules

- **Model revision:** select the latest immutable revision whose effective and
  recorded timestamps are both at or before the forecast cutoff. Current models
  store only ordinal projection years and do not record the fiscal year of year 1.
  The selected revision remains visible, but its requested-FY value is null with
  `FISCAL_YEAR_MAPPING_UNAVAILABLE`; effective/recorded revision dates are not used
  to invent a forecast period. Residual-income models also lack a Revenue
  projection and remain `UNSUPPORTED_METHOD_FOR_REVENUE`.
- **Model fiscal year:** add an explicit forecast-period anchor to the canonical
  revision contract before joining a model projection to a fiscal-year outcome.
  This is especially important for imported workbook revisions: the source does
  not carry a trustworthy model effective date, and the application acceptance time
  is provenance, not the model's projection base year.
- **Consensus:** use the same forecast `as_of` and `known_at`; provider mapping
  effective time, observation snapshot date, source observation time and recorded
  time are bounded. Only the existing primary/fallback continuity selection is
  used; provider series are not blended. Annual Revenue is matched by the calendar
  year of `period_end`. Periods without an absolute end date, including legacy
  `FY+1` values, remain unavailable for fiscal-year alignment.
- **Actual:** annual canonical Revenue facts are selected using the existing
  source precedence/conflict resolver. Period end and filing/publication time must
  be no later than `outcome_known_at`, and observed and recorded timestamps must
  also meet that cutoff. A filing/restatement later on the same date is excluded
  from an earlier intraday outcome cutoff.
- **Price at forecast:** use a daily close for the model's exact valuation listing;
  current quotes and economically different listings are excluded. Market/effective
  date, observed time and recorded time are bounded by the forecast cutoff. A close
  older than seven calendar days, an unknown source observation time, untrusted
  quality, or missing split-adjusted value is explicit and is not treated as a
  usable baseline.
- **Subsequent return:** use the same listing's total-return-close series at the
  forecast and horizon endpoints. The endpoint is the latest eligible daily close
  on or before `as_of + horizon_days`, known by `outcome_known_at`, and no more
  than seven calendar days before the target date. Both points need accepted data
  quality, a total-return value, and the same currency. The API reports an observed
  total return, not an annualized return or valuation return. Missing, stale,
  untrusted, not-yet-reached, and mixed-currency outcomes stay unavailable.
- **Comparability:** the top-level state is `COMPARABLE` only if model Revenue,
  selected consensus Revenue, and a resolved actual Revenue are all available and
  have the same currency and unit. Partial coverage is surfaced as status and null;
  it is never filled with zero.

## Current coverage and gaps

The reusable query is presently Revenue-only. Native DCF and owner-cash-flow models
have Revenue projections, but those ordinal years cannot yet be aligned to a fiscal
year; residual-income Revenue, EPS forecasts/actuals, quarterly comparisons, model
revision fiscal calendars, and alternate fiscal-year conventions are not supported.
Consensus contributes only when a selected provider has an
annual Revenue period with a known end date. Actual coverage depends on canonical
reported fundamentals and source conflicts. Price/return coverage depends on exact
listing history and `total_return_close` availability. Each response includes the
individual data states so sparse coverage is visible rather than hidden.

The development-database snapshot checked on 2026-10-05 contains 219 companies (21
Portfolio and 71 Watchlist), two native models with 15 stored Base Revenue projection
years in total, and 67 legacy consensus observations. None of those consensus rows
has an absolute fiscal period end, so none can yet be joined to a requested FY. No
reported-fundamental observations are present. Daily closes cover 99 of 100 listings
and total-return closes cover 84, but the current price rows have no source
`observed_at`; temporal price values therefore surface as `DATA_CHECK` and returns
remain unavailable under the strict source-time rule. Consequently, the local data
currently supports inspecting selected revisions, market history and the explicit
missing-state behavior, but not a complete three-way forecast/consensus/actual
comparison or a validated return study.

No additional market, fundamental, consensus, or model facts are created by this
feature. It adds no ranking or model-quality metric. Future expansion should first
add explicit model fiscal periods and source coverage for comparable annual/quarterly
facts, then introduce other metrics with representative edge-case tests.
