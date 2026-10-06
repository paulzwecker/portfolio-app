# Expected-return history

The Company Explorer composes historical investment state from the canonical
records that already own each fact. It does not persist a second copy of market,
estimate, model, or imported-output data, and it does not recalculate old model
revisions using today's inputs.

## Read operation and cutoffs

`GET /v1/companies/{company_id}/expected-return-history` accepts:

- `as_of` (optional date; defaults to today)
- `known_at` (optional timezone-aware timestamp)

`as_of` limits effective model/output state. When `known_at` is omitted, it is
the earlier of now and the end of the `as_of` date in UTC. An explicit `known_at`
lets a caller query the state of the record at a particular knowledge time. Native
revisions must be both effective and recorded by the requested cutoffs. Imported
output snapshots must have been recorded by `known_at`; dated snapshots must also
be effective by `as_of`. Undated imported records remain inspectable, marked
`EFFECTIVE_DATE_UNKNOWN`, and are excluded from dated charts.

Market prices and estimate context are evaluated at each model/output event time.
Their source observations and records must have been available by that event time;
later market or estimate observations are never attached to an earlier model
point. Estimate continuity follows the existing primary/fallback source policy
for that event time and does not blend providers. Unresolved fiscal periods remain
visible with their period metadata rather than being assigned an invented year.
If an estimate has only a snapshot date and no observation timestamp, it is not
joined to a same-day intraday model event because its availability within that day
cannot be established; it can be used for a later event when the snapshot date is
strictly earlier and it was already recorded.

## Source distinctions

Each history point identifies one of:

- `NATIVE_MODEL_REVISION`: the immutable accepted application revision and its
  stored deterministic calculation output. `is_current_at_cutoff` marks the
  latest eligible native revision for that model at the requested cutoffs.
- `IMPORTED_LEGACY_REVISION`: a retained legacy normalized-output snapshot.
- `IMPORTED_CURRENT_CONTRACT`: an imported current-contract snapshot.

Imported snapshots are not promoted to native model state. Native outputs use
`NATIVE_METHOD_OUTPUT` semantics. Imported output fields use
`LEGACY_NORMALIZED_FIELD` semantics: the source value is preserved, but this view
does not claim that a legacy Expected IRR used the canonical shareholder-cash-flow
IRR method. Model identity and methodology are shown where available. An imported
snapshot without a unique exact model-key-to-listing mapping has no inferred
listing or market-price join.
The history row also preserves the canonical actor and, for imported records, the
legacy source author, revision source, and revision type when the source supplied
them.

The fair-value, upside, IRR, hurdle, excess, and CAGR values shown at a model point
are the values stored with that output/revision. A later edit creates a later point;
it does not rewrite earlier output or hurdle state. The current accepted native
revision card is labelled separately from imported history.

## Price and estimate context

Prices use the exact valuation listing. The read model does not convert currencies
or substitute another listing. A native revision retains its own calculated
reference price and the linked raw quote context; a linked source quote that was
not observable and recorded by the revision is marked unavailable for that
point-in-time price context. Unknown observation timestamps, untrusted quality,
stale quotes, unknown currency, and currency mismatches remain explicit. Only
comparable dated prices are plotted against fair value.
The Company view groups selectable history series by both model identity and
model currency, so a historical currency change is never plotted on a shared
fair-value axis with another currency.

The estimate context shows the selected provider's latest eligible future-period
observations at the event cutoff, including snapshot, observed and recorded times,
coverage, currency, source, and quality. It is context only and does not replace
model assumptions or recalculate returns.

## Coverage and limits

Coverage is bounded by retained records: imported output snapshots with usable
effective dates, accepted native revisions, their linked exact-listing price
observations, and point-in-time consensus observations. No missing output, market
price, hurdle, estimate, currency, or date is reconstructed from current state.
Current calculated state means the latest accepted native revision as of the
query cutoff, not a live recalculation. Source snapshots and native outputs remain
separate. Expected IRR attribution is a separate comparison operation described
in [expected-return-attribution.md](expected-return-attribution.md); it does not
change this history response or calculate realized investment return, ranking,
or model quality.

Time coverage varies by company and by source. Imported rows with null effective
dates can be seen in the history list but do not extend chart time coverage.
Native model coverage begins with its first accepted revision; point-in-time
estimate and price detail is present only where their source timestamps permit a
defensible join.

In the configured development database checked on 2026-10-05, there are 5 native
model revisions, 344 imported output snapshots effective from 2026-09-02 through
2026-09-30, and 284,758 daily closes spanning 2016-10-07 through 2026-10-05. The
67 consensus observations are all dated 2026-09-12. None of the retained price or
consensus observations has a source `observed_at` timestamp. Those facts remain
available in their own market/consensus views, but source timing is incomplete:
the history read marks affected prices as `DATA_CHECK` and will not join date-only
same-day estimates to an intraday model revision. It does not backfill missing
observation times from ingestion or market dates.
