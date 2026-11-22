# Accepted native-model price onboarding — BKNG

## Why this exists

Booking Holdings now has an accepted native model (`P-BKNG`, revision 1), but
the accepted `financial_model_outputs` row correctly remains `PARTIAL`
because the canonical listing initially had no price observation.

The application already recalculates accepted revisions against current
canonical prices **read-only** via `current_native_model_calculation`.
Do not overwrite accepted model inputs, outputs, or revision metadata
when a market quote changes.

## Verified scope

- Accepted model: `94c15805-ee3a-48a2-9305-4a2d9fc466ed`
- Accepted revision: `a1ec141d-01d7-4900-950d-fc92e2dbf31c`
- Company: `c640fbf7-2fc3-5ea1-b175-2faede5c5a90`
- Valuation listing: `6f381626-22a1-5631-a992-c83125df183f`, `NASDAQ:BKNG`, USD
- Model method: `UFCF_ENTERPRISE_HMODEL_IRR`, not shareholder-distribution IRR
- Source workbook SHA-256: `27f1889a7185e8759486409490db4d52c694f0084d0a914b234a1e251ab78ce9`
- Model input digest: `a1ca8a851541e4813eeebcadcdc647f453bee425b142fd3cda82561451512157`

The verified Yahoo listing crosswalk maps `NASDAQ:BKNG` to `BKNG`,
`NasdaqGS`, USD common stock. A **source-only live lookup** on November
22, 2026 accepted nine daily bars (November 10–20) without quality warnings;
last completed close **USD 144.91 as of November 20, 2026**. That is a
provider preview, not evidence of an accepted canonical production price.

## Operator commands

Use the _reviewed exact commit_, valid Neon credentials in a private
operator environment, and a fresh recovery branch before any live write.
`NEON_API_KEY` must be genuine for the unmodified production write-target
guard, and `DATABASE_URL` must use the **direct** endpoint with
`sslmode=verify-full` and system CA validation. Never paste secrets into
chat, logs, Git, or reports.

The scoped command derives the **single** listing from the accepted model ID,
rejects multiple listings, forbids unrelated FX, and refuses corporate-action
writes. The selected model's current revision, listing, company, source
currency, and price quality are rechecked before applying. The requested
lookback is limited to 90 calendar days and must use a current UTC end date.
The output must be a fresh private file outside the checkout.

Read-only preview (example uses November 22, 2026):

```sh
uv run --locked --project apps/api python -m portfolio_api.market_data_ingestion \
  --accepted-model-id 94c15805-ee3a-48a2-9305-4a2d9fc466ed \
  --lookback-days 30 \
  --end-date 2026-11-22 \
  --report /private/bkng-price-preview-unique.json
```

Only after reviewing the actual current provider response, exact listing
identity, source quality, successful target-bound preview, recovery/rollback
plan and owner production-write authorization, use **a different private
receipt filename** and add `--apply`. Do not assume the sample calendar
date remains current on a later attempt.

```sh
uv run --locked --project apps/api python -m portfolio_api.market_data_ingestion \
  --accepted-model-id 94c15805-ee3a-48a2-9305-4a2d9fc466ed \
  --lookback-days 30 \
  --end-date 2026-11-22 \
  --apply \
  --report /private/bkng-price-apply-unique.json
```

The exact write operation `market_data_provider_accepted_model_price`
has a limited PostgreSQL privilege matrix, checked by the existing
write-target guard:

| Table                                                                                                                                                                             | Required privileges    |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| `companies`, `securities`, `listings`, `financial_models`, `financial_model_revisions`, `company_lifecycle_current`, `lifecycle_events`, `holding_snapshots`, `holding_positions` | SELECT                 |
| `price_observations`, `external_raw_payloads`                                                                                                                                     | SELECT, INSERT         |
| `market_data_batches`                                                                                                                                                             | SELECT, INSERT, UPDATE |

No blanket `DELETE`, FX insertion, corporate-action insertion, model
revision creation or schema change is permitted by this scope. Provision a
temporary least-privilege PostgreSQL role with those exact table grants;
do not choose Neon's broad default `read_write` role as a substitute.
A database guard verifies privileges but does not itself grant or revoke them.
Revoke the temporary role after operator readback.

## Independent verification after acceptance

Use an **independent read-only** connection to inspect:

1. Exactly the expected BKNG listing has new `price_observations` with
   `provider='YAHOO_FINANCE'`, valid raw payload provenance, USD currency,
   completed session dates, split-adjusted close, and `PASS` quality.
2. The canonical market-data batch and raw payload exist. No FX, corporate
   action or other listing was added by the scoped operation.
3. The accepted model ID, current revision ID, return methodology, fair
   values and original stored `PARTIAL` output are **unchanged**.
4. The company read-side `current_calculations` reports the exact quote
   identity/source/effective time and recalculated upside/enterprise-return
   diagnostics with appropriate freshness status. No shareholder-return
   inference is allowed.
5. Repeat the run only after comparing the new source digest and existing
   batch receipts; duplicate data must not produce duplicate revisions.

If provider fetch, source metadata, permissions, currency, freshness or
recovery fails any gate, stop. Do not fabricate observations, substitute an
unverified quote or issue direct SQL inserts outside the guarded importer.
