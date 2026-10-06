# Canonical financial models

Milestone 3A began application-owned inputs and revision history with the 10-year
secular-growth-fade unlevered free-cash-flow DCF. Milestone 3D adds two materially
different workbook-proven methodologies: 10-year owner cash flow and 10-year
residual income. Each has its own relational inputs, projections and calculation
engine; the shared model/revision envelope and normalized output contract provide
the common interface. Google Sheets remains an optional authoring environment via
portable versioned contracts. Sheets is never required at runtime; there is no live
Sheets API connection.

## Relational model

`financial_models` identifies the company, supported model type, name, model
currency and exact valuation listing. Its `current_revision_id` is a pointer to the
latest accepted revision, not the only stored state.

Each `financial_model_revisions` row stores sequence number, parent/base revision,
optional external revision identity, actor, source, rationale, effective and
recorded timestamps. Portable imports also store a SHA-256 contract digest for safe
exact retries. Revision inputs and their calculated state are separate:

- `dcf_model_assumptions`: base-year operating values, net cash/debt and diluted
  shares;
- `dcf_scenario_assumptions`: exactly Bear, Base and Bull probabilities, terminal
  assumptions and scenario rationale;
- `dcf_year_assumptions`: editable operating drivers and discount rates for years
  1–5 of each scenario;
- `owner_cash_flow_assumptions`, `owner_cash_flow_scenarios`,
  `owner_cash_flow_year_assumptions` and `owner_cash_flow_projections`: separate
  base, scenario, ten-year annual drivers and method-derived projections;
- `residual_income_assumptions`, `residual_income_scenarios` and
  `residual_income_projections`: separate opening book-value/payout inputs,
  scenario return assumptions and the derived ten-year book-value/residual-income
  path;
- `dcf_projections`: deterministic derived rows for years 1–10, with detailed
  operating lines only for years 1–5;
- `financial_model_outputs`: normalized scenario fair values, weighted value,
  price-dependent return outputs, currency and availability/freshness state.

Amounts and ratios use exact decimal database/API values. The API accepts decimal
strings and rejects binary floating-point inputs. A revision request names the
current base revision. The transaction locks the model, rejects stale bases with
HTTP 409, calculates all projections and outputs, persists the entire accepted
revision and advances the current pointer atomically. The database/service layer
rejects updates or deletes to accepted revisions and their children. Corrections
are new revisions; previous values remain inspectable.

## Supported method and workbook reference

The currently implemented archetypes and representative workbook references are:

| Model type                 | Representative tab | Methodology                                                  | Fixture currency |
| -------------------------- | ------------------ | ------------------------------------------------------------ | ---------------- |
| `UFCF_DCF_10Y_FADE`        | `P-GOOGL`          | Unlevered free-cash-flow DCF with secular growth fade        | USD              |
| `OWNER_CASH_FLOW_10Y`      | `W-TOST`           | Owner cash flow, ten-year forecast and Gordon terminal value | USD              |
| `RESIDUAL_INCOME_10Y_FADE` | `W-HDFC`           | Book value plus residual income with mature-ROE fade         | INR              |

The real native-input population remains deliberately smaller than the set of
supported methods. `P-GOOGL` and `W-TOST` were accepted first; the reviewed Portfolio
DCF sub-batch then accepted `P-ASML`, `P-ISRG`, and `P-MA`. Their listing identities,
source mappings, revision provenance, idempotent import behavior and detailed
comparison results are in the [native model-input migration report](native-model-input-migration.md).
Other active workbook tabs remain output-only or blocked until their own input
mapping and parity review passes.

The DCF method is represented by the `P-GOOGL` tab in
`reference/workbook/Portfolio_Watchlist.xlsx` (workbook SHA-256
`27f1889a7185e8759486409490db4d52c694f0084d0a914b234a1e251ab78ce9`). Its published
methodology is "10-Year Secular Growth Fade UFCF DCF". The frozen test fixture is
[`apps/api/tests/fixtures/p_googl_ufcf_dcf_v1.json`](../apps/api/tests/fixtures/p_googl_ufcf_dcf_v1.json).
It is not a production seed. Accepted native model state is created through the
versioned importer documented in [native-model-input-migration.md](native-model-input-migration.md).

Revenue, D&A, capex, NWC and diluted shares follow the source model's billion-unit
inputs; fair values and market price are per share in the explicit model/listing
currency. For detailed years 1–5:

```text
revenue[t] = revenue[t-1] * (1 + scenario revenue growth[t])
EBIT[t] = revenue[t] * EBIT margin[t]
NOPAT[t] = EBIT[t] * (1 - tax rate[t])
change in NWC[t] = NWC[t] - NWC[t-1]
UFCF[t] = NOPAT[t] + D&A[t] - capex[t] - change in NWC[t]
```

Years 6–10 contain only UFCF values. Their growth linearly fades from the implied
Year 5 UFCF growth rate to each scenario's Year 10 UFCF growth assumption. The Year
5 discount rate is held for years 6–10. The source terminal-value formula, including
its explicit 2.5 terminal-growth premium factor, is retained:

```text
spread = Year 5 discount rate - terminal growth
terminal value = Y10 UFCF * (1 + terminal growth) / spread
                 + Y10 UFCF * 2.5 * (Y10 UFCF growth - terminal growth) / spread
scenario FV/share = (PV of Y1–Y10 UFCF + PV of terminal value
                     + net cash/debt) / diluted shares
weighted FV = sum(scenario FV/share * scenario probability)
```

Bear/Base/Bull probabilities must sum exactly to 1; each terminal growth must be
below the Year 5 discount rate. `Hurdle` preserves this source model's probability-
weighted Year 5 discount rates. With a fresh positive price observation for the
exact valuation listing and a matching currency, `Weighted Upside` is weighted fair
value divided by price minus one. The API obtains the quote under the existing
listing-specific freshness and data-quality policy; an absent, stale, rejected or
currency-mismatched quote leaves upside, expected IRR and expected excess null with
an explicit reason. It never converts currencies or assumes an ADR ratio.

For this source model only, `Expected Cash-Flow IRR` is calculated from the
probability-weighted annual UFCF series, its probability-weighted terminal value in
year 10 and current implied enterprise cost (price times diluted shares less
net cash/debt). It is solved deterministically by bounded bisection after checking
for one conventional cash-flow sign change. It does not average scenario IRRs.
This preserves the source output, whose method is enterprise-value/UFCF based; it
does not establish that every future normalized expected-return model should use
UFCF rather than explicit shareholder cash flows. Dividend treatment is not modeled
by this DCF type. Resolve that interface distinction before adding other return
methodologies. `Forward Fundamental CAGR` remains null because this method does not
produce it.

## Parity results and limits

The test fixture pins the source inputs and cached outputs; tolerance is `1e-7`.
The deterministic implementation reconciles:

| Output                    | Workbook cached value | Application |
| ------------------------- | --------------------: | ----------: |
| Bear fair value/share     |           226.8117028 |  reconciled |
| Base fair value/share     |           443.5224326 |  reconciled |
| Bull fair value/share     |           633.5590147 |  reconciled |
| Weighted fair value/share |           462.6722601 |  reconciled |
| Weighted upside           |          0.3469352549 |  reconciled |
| Expected Cash-Flow IRR    |          0.1268953551 |  reconciled |
| Hurdle                    |         0.09024514219 |  reconciled |
| Expected excess           |         0.03665021294 |  reconciled |

Representative Bear Year 1, Base Year 5 and Bull Year 10 UFCF projections also
reconcile at the same tolerance. The end-to-end persistence test creates the initial
model, appends an assumption revision, reads the prior revision unchanged, verifies
all 30 scenario/year projections per revision and rejects a stale replay.

The owner-cash-flow fixture is [`apps/api/tests/fixtures/w_tost_owner_cash_flow_v1.json`](../apps/api/tests/fixtures/w_tost_owner_cash_flow_v1.json).
It grows revenue using ten scenario-specific annual growth assumptions. Annual
owner cash flow is revenue times the provided owner-cash-flow margin, which carries
the source methodology's owner-cash-flow treatment after its operating and
stock-compensation assumptions. Per-share cash flow is discounted at the scenario
required return. Terminal value uses Year 10 per-share owner cash flow and Gordon
growth; net cash per share is added separately. Expected IRR uses probability-
weighted annual per-share owner cash flows, weighted terminal value and net cash as
Year 10 proceeds. It does not average scenario IRRs.

The residual-income fixture is [`apps/api/tests/fixtures/w_hdfc_residual_income_v1.json`](../apps/api/tests/fixtures/w_hdfc_residual_income_v1.json).
Opening book value per share is the equity base. ROE holds at starting ROE through
Year 5 and fades linearly to mature ROE by Year 10. Dividends equal net income times
the explicit payout ratio; retained earnings roll into ending book value. Residual
income is `(ROE - cost of equity) × beginning book value`. Scenario fair value is
opening book value plus discounted annual residual income plus discounted terminal
residual income. Shareholder IRR includes scenario dividends and Year 10 ending
book value plus terminal residual income. Hurdle is the probability-weighted cost
of equity.

Both methods have isolated workbook parity fixtures covering all three scenario
values, Weighted Fair Value/Upside, Expected Cash-Flow IRR, Hurdle, Expected Excess
and a representative projection. Each reconciles against workbook cached published
outputs to `1e-7`. Persistence tests store 30 projections per revision, preserve
prior revisions and reject stale revision bases. These are representative parity
references, not production model imports. Other company tabs, SOTP, additional
financial-company variants and bespoke models remain unsupported; imported workbook
snapshots stay in the separate `model_output_snapshots` domain. No real model was
seeded from a fixture.

## Legacy population and expected-return semantics

The per-tab population, identity/lifecycle checks, currency evidence, output
contract state and migration batches are maintained in the
[model migration inventory](model-migration-inventory.md) and its checked-in
[JSON artifact](reconciliation/model-migration-inventory-2026-10-05.json). The
workbook's normalized output label `Expected Cash-Flow IRR` is not a guarantee that
the underlying method computes the canonical shareholder-cash-flow IRR.

The project definition uses probability-weighted explicit shareholder cash flows;
it does not average scenario IRRs, dividends are represented explicitly and
terminal proceeds are separate. The legacy `P-GOOGL` reference solves IRR from
probability-weighted enterprise UFCF and terminal value against an implied
enterprise cost. That preserves its workbook parity, but it is not the same cash
flow boundary as shareholder distributions. Owner-cash tabs use their own
owner-cash-flow convention, while residual-income and other financial-company tabs
may solve implied equity return from dividends and terminal equity value. Do not
recompute or relabel historical legacy outputs. A method-specific bridge and
regression fixture are required before treating any legacy field as canonical
shareholder-cash-flow IRR.

The inventory distinguishes published outputs from safe assumption mapping.
Ninety-six normalized contracts are publishable after source identity/layout checks.
Five active tabs have tab-specific parity evidence: four Portfolio DCFs (`P-GOOGL`,
`P-ASML`, `P-ISRG`, `P-MA`) and Watchlist owner-cash model `W-TOST`. Those five
company input sets are accepted as native revisions. `W-HDFC` has residual-income
parity but is currently Drop and remains outside active migration priority.

## API and Company flow

- `GET /v1/companies/{company_id}/financial-models` lists the company's accepted
  canonical models.
- `POST /v1/companies/{company_id}/financial-models` creates a supported model and
  its first complete revision.
- `POST /v1/companies/{company_id}/financial-models/preview` calculates the first
  revision draft without storing it.
- `GET /v1/financial-models/{model_id}` reads current model state and history.
- `GET /v1/financial-models/{model_id}/revisions` lists immutable revision
  summaries; `GET .../revisions/{revision_id}` returns that revision's full inputs,
  projections and outputs.
- `POST /v1/financial-models/{model_id}/revisions` appends a recalculated revision
  against its current base.
- `POST /v1/financial-models/{model_id}/revisions/preview` recalculates a draft
  against the named current revision without creating history. A stale base returns
  HTTP 409, and the response includes all scenario projections plus normalized
  outputs and explicit price/IRR availability state.
- `GET /v1/companies/{company_id}/canonical-financial-models` lists accepted
  owner-cash-flow and residual-income models; method-specific `POST` operations
  create their initial revision, with sibling `/preview` operations for drafts.
- `GET /v1/canonical-financial-models/{model_id}` and
  `/revisions/{revision_id}` read current or historical method-specific state.
  `POST /{method}/revisions` appends against the current base and the matching
  `/preview` route calculates without storing.
- `GET /v1/canonical-financial-models/{model_id}/contract` exports v2 state;
  `POST .../contract/preview` validates and compares a candidate, and
  `POST .../contract/import` appends it through the same revision operation.

The Company Explorer's canonical-model sections display accepted assumptions,
scenarios, method-specific projections, normalized outputs, quote freshness,
source, rationale and revision history. The DCF editor previews all scenarios and
its selectable forecast. Owner-cash-flow and residual-income forms expose their
own editable assumptions and a base-case projection preview. The API owns all
deterministic calculations. Acceptance is enabled only after a valid preview;
source references and rationale are recorded with each new revision.

Acceptance still uses the same atomic append operation as portable-contract imports:
the editor supplies the revision it was based on, and a base that changed while the
draft was open is rejected. The user can reload the latest revision and begin again;
the editor does not silently merge concurrent Sheets and web edits. Preview is
read-only and returns decimals rounded to the database's 18 fractional-place model
precision so the displayed accepted-versus-draft values reconcile with persistence.
Revision history can expand into an assumption and normalized-output comparison
against the current revision. Imported legacy output snapshots remain in their
separate read-only history section.

## Google Sheets interoperability

The portable boundaries are `FinancialModelContractV1` (`1.0.0`) for DCF and
`AdditionalModelPortableContractV2` (`2.0.0`) for owner cash flow and residual
income. `GET /v1/financial-models/{model_id}/contract` exports model identity,
listing/currency, base revision identity, methodology, editable candidate
assumptions and provenance. The v1 DCF contract also includes a read-only snapshot
of stored outputs and projections so the API can detect an altered export; that
snapshot is never an import source for calculated values.

The Company Explorer can download this JSON contract, preview an edited JSON file,
show assumption and recalculation differences, and accept a ready candidate as a
new revision. For a Sheets authoring pass, use
[`tools/google-sheets/README.md`](../tools/google-sheets/README.md) and the Apps
Script adapter in the same directory. The adapter creates editable method-specific
base, scenario, year-input (owner cash flow only) and revision tabs, then writes
edits back into contract JSON for review and upload. It does not call the API or
calculate model outputs. Exact decimal strings are kept as text; the application
validates ranges, probabilities, scenario structure and terminal-spread constraints,
then recalculates with the selected canonical implementation.

The v1 DCF API operations are:

- `GET /v1/financial-models/{model_id}/contract` exports a v1.0.0 contract with a
  fresh external revision identifier.
- `POST /v1/financial-models/{model_id}/contract/preview` validates identity and the
  saved base snapshot, then returns a non-mutating status and field/output diff.
- `POST /v1/financial-models/{model_id}/contract/import` repeats those checks while
  locking the model and appends through the same immutable revision operation used by
  native edits. It records actor `IMPORT`, source, rationale, effective time, base
  revision and external revision identity.

A candidate based on an older revision returns preview status `CONFLICT`; import
returns HTTP 409 and preserves current state. A contract with an invalid base
calculation is marked `INVALID_BASE_SNAPSHOT`. Changing model inputs without changing
the revision rationale returns `RATIONALE_REQUIRED`; unchanged assumptions and
rationale return `NO_CHANGES`. A duplicate external revision identity with changed
content is a conflict. The exact accepted contract can be retried safely: a canonical
SHA-256 digest stored on the accepted revision returns `ALREADY_IMPORTED` without
adding a duplicate. Export again before making a subsequent external edit so the
candidate gets a new identity and current base.

Owner-cash-flow and residual-income v2 contracts use the parallel endpoints under
`/v1/canonical-financial-models/{model_id}/contract` for export, preview and import.
Their envelope carries model type, base revision identity/number and exactly one
method-specific input block. External acceptance uses the same immutable revision
history and optimistic base check as an application edit. Integration tests verify
a v2 round trip, idempotent exact retry and stale-base conflict.

Preview recalculation is advisory. Import recalculates at acceptance and captures the
then-current listing quote under the existing freshness/currency rules. Outputs in
the portable base snapshot cannot overwrite calculations, market observations,
assumptions, model identity, or revision history. Unknown contract versions are
rejected by validation. This development transport is a file handoff; OAuth, live
Sheets API sync, concurrent cell-level merge, further model methodologies and
authentication are not included.

The API integration test demonstrates the full round trip: export revision 2, change
Base-case Year 1 revenue growth from `0.21` to `0.22` in the portable candidate,
preview the changed assumptions and recalculated outputs, accept it as revision 3,
and verify the original history is unchanged. A retry is idempotent; a second
contract authored from the older base is rejected after a later in-app revision is
accepted.

## Lessons for more model types

The migration inventory lists 116 model tabs and the workbook registry contains
219 companies. Six tabs have native formula parity fixtures: `P-GOOGL`, `P-ASML`,
`P-ISRG`, `P-MA`, `W-TOST`, and dropped `W-HDFC`. Five active companies now have
accepted native input revisions (4 Portfolio and 1 Watchlist). This is a controlled
5-of-92 active model-tab migration, not workbook-wide issuer coverage.

Keep the shared envelope small: company/model identity, methodology discriminator,
currency/listing, revision chain, rationale/provenance, timestamps and a normalized
output interface. Add inputs and derived projections in methodology-specific tables
and calculation modules only when a supported source methodology and fixture exist.
Do not turn assumptions into arbitrary JSON or build a formula/rules engine merely
to make unlike models look uniform. Define the return/currency semantics and
availability rules for each method, then test the adapter to the normalized output
contract. In particular, reconcile per-share basis, security conversion and
shareholder-versus-enterprise cash flows before claiming cross-method comparability.

The shared envelope held up for model/listing identity, revision ancestry,
provenance, currency and normalized scenario outputs. It did not justify a shared
formula or projection schema: the owner-cash-flow method needs explicit annual
revenue/margin drivers and per-share cash flows, while residual income needs a book
value roll-forward, dividends and annual residual income. The web forms and Sheets
v2 contract preserve those differences while sharing the revision workflow.

The inventory recommends accepting only the parity-backed active pair first,
validating the active Portfolio DCF cohort in small batches, then handling active
Portfolio owner-cash variants and the exact-identity `P-SPGI` SOTP before bulk
Watchlist work. Financial, acquisition-reinvestment and other bespoke methods need
their own representative designs. Resolve exact component identity for
`P-MELI-SOTP` and `P-SPGI-CIQ`; do not migrate the remaining universe in bulk.
