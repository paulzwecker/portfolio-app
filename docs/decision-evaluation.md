# Scenario Calibration & Investment Decision Evaluation

## Purpose

This read-only evaluation layer uses accepted model revisions, imported output
snapshots, immutable Portfolio/Watchlist Rank runs, immutable Execution Pace runs,
and point-in-time canonical market and reported-fundamental observations. It does
not update model assumptions, scenario probabilities, rankings, targets, holdings,
or investment policy.

The evaluation keeps five questions distinct: business-forecast error, numeric
scenario-distribution quality, valuation context, subsequent security returns, and
portfolio implementation outcomes. Existing fiscal-period forecast errors remain
available through the Forecast Accuracy view and API. Research Rank is excluded
because it orders research work, not investment attractiveness.

## Scenario forecasts and valuation scenarios

The service groups accepted native model projections by exact revision, metric and
ordinal forecast year. It reports Bear/Base/Bull values and probabilities with the
revision methodology and knowledge timestamp. A continuous ranked probability score
(CRPS) is calculated only when all three scenarios are present, their probabilities
sum to one, the metric/currency/unit match, an explicit fiscal period exists, and a
later quality-passing reported actual was not known at the forecast time. CRPS is in
the forecast metric's units; lower is closer for that observation.

Model years currently remain ordinal and lack fiscal-period anchors, so their
reported-outcome scores remain unavailable. The score is not a stock-return measure.
Probability calibration is also explicitly unavailable until an economic rule defines
what observed outcome counts as Bear, Base or Bull. No such cutoff is inferred from
the scenario values.

Imported normalized outputs show scenario Fair Values, probabilities, currency,
source and revision timestamps as valuation context. Fair Value is not treated as a
fixed-date stock-price forecast, and no valuation-accuracy score is assigned to it.

## Subsequent security return

Portfolio Rank, Watchlist Rank and Execution Pace observations are read from their
historical run/entry snapshots. The signal's captured price-observation ID and exact
valuation listing define the baseline. The baseline must belong to that listing, have
an accepted quality state and source timestamp, be no more than seven calendar days
old at signal time, and have been observed/recorded by the signal run's recorded
time. The endpoint is selected from the same listing and must be known by the chosen
outcome cutoff, after the signal date, and within seven days before the requested
horizon.

Returns use `total_return_close` at both endpoints. They remain in listing currency;
no FX return is forecast or converted. A missing total-return value, a source time
that is absent, a stale baseline, an incomplete horizon, a currency mismatch or a
different listing remains unavailable. Provider-adjusted total-return values may
contain unverified dividend/corporate-action treatment; provider names and exact
observation IDs are returned for inspection. The API also reports a geometric
annualized return from actual elapsed days where the total return is available.

## Decision diagnostics

Each summary is one immutable run cross-section, one horizon, one listing currency,
and one exact signal/method group. The minimum is five distinct companies. Smaller
groups return `INSUFFICIENT_SAMPLE` without a statistic.

- Expected IRR versus realized return uses Spearman rank association only for an
  equity-perspective methodology with the same method/version and model currency as
  listing currency. Enterprise UFCF returns are not bridged to shareholder returns.
- Portfolio Rank and Watchlist Rank use their recorded position and same-run
  subsequent security returns. A positive coefficient is oriented to mean that
  better positions coincided with stronger outcomes.
- Execution Pace and fresh, quality-passing Estimate Momentum are grouped by their
  recorded state/direction. Their means and medians are descriptive only.

These are observational cross-sectional diagnostics, not causal estimates, skill
scores or investment recommendations. The implementation omits p-values and does
not pool across runs, methods or currencies. A change in model method/version starts
a separate cohort.

Portfolio implementation performance is unavailable: a holdings snapshot and
target history do not establish transaction dates, capital flows, cash movements or
realized portfolio weights over time. No portfolio result is inferred from current
holdings or rank/target state.

## API and Company Explorer

`GET /v1/companies/{company_id}/decision-evaluation` accepts an optional
timezone-aware `outcome_known_at` and one to three repeated `horizons_days` values
(1–3650). Defaults are 365 and 1095 days. The response includes scenario groups,
valuation-scenario context, the company's historical Portfolio/Watchlist/Execution
Pace snapshots, outcome states, run-level cross-sectional summaries, and explicit
portfolio implementation/data limitations.

The Company Explorer presents scenario distributions and score eligibility first,
then valuation references, historical decision states and cross-sectional samples.
Missing periods, prices, outcomes and insufficient samples remain visible. Forecast
Accuracy remains the source for the signed/absolute forecast error history; this
view does not duplicate it.

## Current local evidence

The PostgreSQL state reviewed on 2026-10-15 has 219 companies, 15 accepted native
model revisions, zero reported-fundamental observations, and 67 consensus rows with
no source observation timestamps or absolute fiscal-period ends. The daily close
history contains 285,242 rows across 99 listings, spanning 2016-10-07 through
2026-10-09; none of those daily-close rows has `observed_at`. There are 219,707
`total_return_close` values, but they lack that same source observation time. The
197 price rows with a source timestamp are current quotes, not a dated daily-close
series suitable for the historical horizon query.

The database has 16 ranking runs and 3,504 entries, but the captured daily price
history cannot currently pass the source-time requirement for a subsequent return.
Both stored Execution Pace runs contain no `AVAILABLE` decisions. There is one
holdings snapshot and no transaction ledger. Accordingly, the real database has
zero eligible scenario CRPS observations, zero eligible subsequent security-return
observations, zero eligible expected-return/rank/timing correlations, and zero
portfolio implementation observations. Scenario and signal history can still be
inspected with explicit reasons for those states.

The next useful data accumulation is prospective: retain source observation times
for daily closes and corporate-action-adjusted total-return observations; map model
forecast years to explicit fiscal periods within revisions; ingest dated reported
facts and consensus observations; and build transaction/cash-flow history before
evaluating portfolio implementation. Do not backfill source times or fiscal periods
from ingestion dates/current company state.
