# Booking Q3 2026 — evidence-to-decision (read-only pilot)

## Outcome

A reviewed SEC quarterly filing becomes a sourced, reproducible investor
brief. This pilot does not recommend trades, publish research, write canonical
data, change accepted models, or activate recurring source jobs.

The source is Booking Holdings' November 3, 2026 Q3 Form 10-Q:
https://www.sec.gov/Archives/edgar/data/1075531/000107553126000045/bkng-20260930.htm

| SEC operating metric | 2026 Q3 (millions) | 2025 Q3 (millions) | Issuer-reported YoY |
| --- | ---: | ---: | ---: |
| Room nights | 345 | 323 | +6.7% |
| Flight tickets | 21 | 17 | +19.4% |
| Gross bookings, USD | 54,461 | 49,668 | +9.6% |

The displayed quarterly values are rounded to millions, so the brief uses
the issuer's reported year-on-year percentages, not ratios calculated from
rounded values. SEC quarters and nine-month periods are never interchanged.
It rejects changed source values, implausible growth, reversed periods,
unverified SEC CIK, ambiguous source rows and incomplete scoped context.

## Private operator workflow

Run the standalone module `portfolio_api.booking_evidence_decision`
with the reviewed source pack, explicit canonical Booking UUID and scoped
read-only access. A live run needs the operator-configured SEC contact
`SEC_USER_AGENT` and the Booking-allowlisted `DATA_UNIVERSE_READ_TOKEN`.

```sh
uv run --locked --project apps/api python -m portfolio_api.booking_evidence_decision \
  --api-base-url https://portfolio-api-gisk.onrender.com \
  --company-id '<operator-reviewed-booking-uuid>' \
  --source-pack apps/api/tests/fixtures/data_universe_bkng_q3_2026.json \
  --output /private/booking-evidence-decision.json
```

The operator must supply real credentials through an approved private
environment; never commit or print them. Source verification takes one bounded
(no redirect, max 2 MB) fixed SEC GET before fetching scoped canonical
company context. The resulting JSON is mode 0600, outside the public repository,
and never overwrites an existing report.

For isolated tests, substitute both `--context-file` and `--source-html`
for `--api-base-url`. This is an offline fixture proof, not a live SEC
verification or production activation.

## Canonical decision boundary

The existing reviewer handoff controls proposal eligibility.

- First definitions: `REVIEW_METRIC_DEFINITIONS`, KPI batch deferred.
- After definitions are accepted: `REVIEW_KPI_OBSERVATIONS`.
- No differences: `ALREADY_MATCHED`, no new proposal.
- Conflicts or truncated canonical history: `RESOLVE_CONFLICT` or
  `CONTEXT_INCOMPLETE`, no eligible proposal.

The brief contains exact source hash, data period, unit, comparison values,
canonical findings, eligible batch ID/type and three review questions about
demand monetization, flight economics and cash conversion. It **does not**
submit that batch. The established candidate API, human preview, acceptance,
production write gate and revision history remain separate.

`fair_value_change` and `expected_irr_change` remain null. Gross bookings,
revenue, margin and FCF are different economic measures. No model sensitivity
can be quantified from these three operating metrics alone.

## Validation and gates

Focused tests are in `test_booking_evidence_decision.py` and the existing
Booking source and Data Universe shadow suites. Passing tests prove offline
contract behavior, not live SEC access or reviewer acceptance.

The next gate is a separately approved, operator-configured **read-only live
SEC/source-context proof**. Subsequent review proposals, human acceptance,
model sensitivity and cloud deployment remain independently authorized.
