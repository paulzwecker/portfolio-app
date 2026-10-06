# Attention Center

The Attention Center is a read-only query over canonical immutable histories. It
does not persist a second event ledger, mutate upstream records, create ranks or
decisions, or run AI reasoning. Each entry carries the source domain and source
record ID, effective/event time when known, recorded time, and source reference.
Company links open the corresponding Company Explorer; source URLs open separately.

## Supported events

- Accepted native model revisions. When two adjacent revisions use the same
  model type and methodology and Expected Cash-Flow IRR changes by at least five
  percentage points, that same revision appears once as an Expected IRR change.
  Changes of ten percentage points receive high severity. Methodology changes
  remain model-revision entries without a misleading IRR comparison. A
  same-currency Weighted Fair Value change of at least ten percent is included
  in the revision explanation and values, without being treated as return.
- Recent imported normalized model-output snapshots, clearly labeled as imports.
- Same-provider Revenue/EPS estimate revisions for the same forward period,
  currency and unit, when a positive baseline changes by at least five percent.
  The selected consensus continuity source is used; providers are not blended.
- New recent filings or issuer documents. A document superseded by a later
  source record is omitted from the current feed.
- One-session split-adjusted price moves of at least ten percent for one exact
  listing, compared only across adjacent clean daily observations. Twenty
  percent or more is high severity. This is a conservative feed threshold, not
  a new market or investment signal.
- Portfolio, Watchlist and Research Rank changes when status changes or the
  position moves at least three places within the same ranking-definition
  version.
- Execution Pace state changes within the same methodology version.
- Current Portfolio/Watchlist market-quote gaps (no quote, stale beyond the
  documented five-day window, or non-passing quality) and absence of any
  complete native/current-contract model output.

Routine rank movements and consensus/price snapshots below the thresholds do
not generate items. A model revision is itself an accepted authored change and
is included; its Expected IRR movement is folded into that item to avoid a
second alert for the same revision. Feed IDs are derived from source-record
identity and results are de-duplicated before stable event-time ordering.

## Time and missing data

The feed retains each domain's effective time and recorded time separately.
Daily closes and date-only filing dates are marked with date precision; they do
not claim intraday timestamps. Current data-quality states have no synthetic
effective or recorded timestamp when none exists; the response-level `as_of`
indicates when the feed was evaluated. Historical model snapshots, price moves,
filings, ranks and decisions are filtered by their source event time so a recent
bulk backfill does not turn the entire archive into a series of fresh alerts.

Null values stay null. A missing model output or current quote is a Review item,
not zero, neutral return, failed gate or passing state. The feed always uses
company/listing/provider identity from canonical records, not ticker-only
matching. Consensus comparisons are omitted when the baseline is zero/negative,
the provider stream differs, data quality fails, or currency/unit differs.

## API and filters

`GET /v1/attention` accepts `company_id`, `event_type`, `lifecycle`, `severity`,
`status`, `lookback_days` (1–365, default 30), and `limit` (1–200, default 50).
The Next.js same-origin proxy exposes the same read operation at
`/api/research/attention`.

## Current limitations

The operational five-percent estimate, ten-percent daily-price, three-place
rank, and five/ten-percentage-point Expected IRR thresholds are feed materiality
choices. They do not alter the estimate-momentum, price-regime, ranking,
Execution Pace, valuation or hurdle methodologies. Price coverage is currently
summarized across a company's tracked listings; exact held-listing coverage can
be made more specific as a portfolio-aware feed filter is added.

Provider ingestion failures are not yet represented as durable canonical batch
failure records, so the feed cannot reliably surface failed ingestion attempts.
Existing accepted data-quality states are included. A future ingestion-status
domain can add failure entries while preserving provider, batch and retry
provenance. Event retention/export and user-specific dismissal are also not
implemented; this feed is a live composition of retained source histories.

The feed can support future research queues, review assignments, ingestion
operations, audit exports and automation triggers. Those workflows should link
to source records and keep recommendations/actions separate from this read-only
attention layer.
