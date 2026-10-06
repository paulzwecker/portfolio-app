# Estimate Momentum

## Ownership and availability

Estimate Momentum is a deterministic API read model derived from the selected,
provider-specific consensus history. It does not create or update consensus rows,
native model assumptions, rankings, company scores, price analytics, lifecycle, or
execution state. The calculation can be rerun for an `as_of` date and an optional
`known_at` cutoff; the underlying observations remain append-only and the result
is reproducible from those exact inputs.

The API only uses the source selected by the existing consensus continuity policy.
It does not blend providers or carry a previous provider's history into a newly
selected source. A source change therefore produces an explicit history gap until
the new source has enough repeated observations. Estimates without an absolute
fiscal period end, including the imported legacy FY+1/FY+2 baseline, do not enter
the calculation.

## Legacy methodology carried forward

The later formula set on `Estimate Momentum` (workbook rows 50–173 and summary
rows 177 onward) is the reference. The implementation reports the method version
`legacy-estimate-momentum-v2-partial-1`.

For each of Revenue/EPS and the nearest two future annual fiscal periods:

1. Compare the current estimate with the latest same-provider estimate observed
   on or before the 12M, 6M, or 3M reference date: `current / reference - 1`.
2. Scale each percentage revision by 5% and cap the component at `-2` to `+2`.
   If only some revision windows are supported, renormalize the 30% / 20% / 15%
   12M / 6M / 3M weights over the available windows.
3. Combine FY+1 and FY+2 at 60% / 40%. If only one period has a valid score,
   use that period's score without treating the missing period as zero.
4. Combine Revenue and EPS at 70% / 30%. If one metric has no valid score, use
   the other metric alone.
5. Calculate history coverage as the count of available components divided by 20
   possible components. Confidence is `min(1, history coverage × 2)`. The adjusted
   signal is raw score × confidence. The latest consensus analyst count is exposed
   separately on each period; it is not substituted for history coverage or used
   to weight the signal.

Direction uses the workbook's raw-score bands: Positive at `>= 0.35`, Mild
positive at `>= 0.12`, Neutral/mixed above `-0.12`, Mild negative above `-0.35`,
and Negative otherwise. A calculated score of exactly zero is a genuine
Neutral/mixed result; no observations or insufficient comparison history produce
no score and no direction. Below 35% confidence the direction is `DIRECTION_ONLY`;
at or above 35% it is `AVAILABLE`. This status does not trigger execution logic.

The workbook also assigns 20% to persistence and 15% to revision breadth. Those
inputs are not derived here. The consensus domain stores provider aggregate
estimates, not analyst-level upward/downward revision events, and the available
legacy snapshots do not establish how persistence was measured. The unavailable
components remain absent from the raw score; their absence is reflected in the
fixed 20-component coverage denominator. No proxy formula has been invented.

The legacy percentage formula needs a positive baseline. A zero or negative
reference is marked `INVALID_BASELINE` and excluded rather than assigned a new
denominator rule. A historical reference must be observed on or before its target
date and no more than 14 days before it; older references are shown as `STALE_REFERENCE`
and not scored. The 14-day window reuses the consensus freshness interval and is
an input-quality guard, not a score component. Current freshness is reported
separately from confidence and data quality.

## Point-in-time and data-quality rules

- Only annual Revenue and EPS observations with a resolved future `period_end` are
  eligible. Quarterly estimates are not mapped to the legacy annual signal.
- The two fiscal periods are selected by ascending future `period_end`; period
  labels and currency/unit must remain consistent within one source series.
- A snapshot after the requested `as_of` date or after `known_at` is excluded.
- Current or reference observations outside `PASS` quality are shown as data
  checks and are not used in a score.
- Freshness is `FRESH` through 14 days after the latest relevant annual snapshot,
  `STALE` after that, and `DATA_CHECK` when the latest relevant value is not
  passing. `NO_DATA` remains explicit.
- Currency changes, unit changes, zero/negative percentage baselines and ambiguous
  source precedence are not silently reconciled.
- Score, revision direction, analyst count, history coverage/confidence, data
  quality, freshness and signal availability remain separate fields. Price
  momentum, business Execution, valuation, model scenarios and expected returns
  are not inputs.

## API and product surface

- `GET /v1/companies/{company_id}/estimate-momentum` returns the selected source,
  method version, raw and confidence-adjusted scores, direction, availability,
  coverage/confidence, freshness/data quality, and the 12M/6M/3M comparisons by
  forward annual period. It accepts `as_of` and timezone-aware `known_at`.
- `GET /v1/universe/estimate-momentum-summary` returns the compact equivalent for
  each company and supports the existing lifecycle/search filters plus the same
  time cutoffs.
- Company Explorer shows signal coverage, source/freshness, each reference value
  date and revision, plus the formula limitations. Universe shows and sorts/filters
  the canonical API result; it does not recalculate the signal in TypeScript.

The signal is informational only. It does not alter Business Execution, target
weights, lifecycle, rankings, scenarios, or Execution Pace.

## Legacy workbook reconciliation

`docs/reconciliation/estimate-momentum-legacy-2026-10-05.json` records a selective
formula check for GOOGL. The cached sheet output is Positive with raw score
`1.838730796`, confidence `0.8`, and adjusted score `1.470984637`. The supported
12M/6M/3M revision arithmetic reproduces a Positive direction. Recomputing only
the six populated 6M/3M revision components gives raw score `1.92561542264`,
confidence `0.6`, and adjusted score `1.155369253584`; the difference is caused by
the two populated breadth components that this implementation intentionally
withholds. This is a partial formula reconciliation, not full signal parity.

The workbook's source notes use approximate crawl dates and do not establish
reliable per-estimate observation timestamps or consistent vendor identity. The
legacy values cannot be imported as point-in-time facts and are not used by the
application calculation. At the 2026-10-05 coverage audit, no FMP mappings were
configured and the single legacy estimate baseline had no absolute period ends;
therefore the real universe correctly remains without an available canonical
momentum signal until repeated primary-provider snapshots are captured.
