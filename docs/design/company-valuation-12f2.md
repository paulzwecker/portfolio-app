# Company Valuation & Modeling UX — Milestone 12F.2

## Purpose

The Valuation view is now a single research workspace answering: **what is this
company worth, which assumptions drive that value, and how would a change affect
expected return?** The page consumes the existing deterministic model and
market-data APIs. It does not calculate valuation, IRR, probabilities or
comparability in the browser.

## Information hierarchy

1. **Accepted valuation** — the selected model's revision, methodology,
   currency, exact listing, fair-value range, weighted fair value, canonical
   weighted upside, return fields and price/data state.
2. **Scenario range** — Bear/Base/Bull values and probabilities. Selecting a
   case reveals the corresponding retained assumptions where the native model
   stores them.
3. **Method and evidence** — return perspective, comparability group,
   methodology limitation, revision timestamp, source and rationale.
4. **Model family** — UFCF DCF, owner cash flow and residual income remain
   separate. A method must be selected before its editor is mounted.
5. **Draft assumptions & deterministic preview** — existing method-specific
   editors are disclosed only after an explicit action. Preview is calculated by
   FastAPI; acceptance remains an explicit, immutable revision operation.
6. **Revision history & migration diagnostics** — imported output snapshots and
   migration status are available in a progressive disclosure panel rather than
   competing with the current valuation conclusion.

## Implementation

- `CompanyValuationWorkspace` owns model-family selection, normalized summary
  presentation, scenario interaction and progressive disclosure.
- `CanonicalDcfExplorer` remains the UFCF DCF editor and Sheets contract
  workflow. `CanonicalArchetypeExplorer` remains the owner-cash-flow and
  residual-income adapter; it can now be focused on one selected method.
- `ModelMigrationStatus` and `CompanyModelOutputHistory` remain audit/reference
  views and are mounted only when the user opens the audit disclosure.
- Current native quote calculations are read from
  `expected-return-history.current_calculations`, so current prices are not
  taken from accepted reference prices. Imported output-only snapshots remain
  explicitly read-only and do not receive an invented listing or price basis.
- Displayed percentage precision is intentionally rounded for readability;
  API decimal precision is unchanged.

## Interaction and integrity rules

- The page never blends enterprise UFCF and equity-return methods into one
  comparison. Method perspective, comparability group and limitations remain
  visible.
- Missing price, IRR, output, listing and provenance values render as
  unavailable or data-state text, never zero.
- Scenario selection changes the displayed retained assumptions only; it does
  not recalculate a scenario or create a revision.
- Editing follows accepted model → draft → deterministic preview → compare →
  evidence/rationale → explicit acceptance. Existing stale-base and revision
  safeguards remain in the method-specific editors.

## Visual review

The live local application was inspected with the canonical Alphabet UFCF DCF
and Axon owner-cash-flow examples at desktop and 390px mobile widths. The
review covered the accepted summary, current exact-listing quote, scenario
selection, assumption disclosure, method selection and residual-income
unsupported/new-model state. The mobile view was checked for stacked metric
cards, scenario controls, readable percentage precision and absence of page
overflow. The editor was opened and closed without changing canonical state.

Remaining limitation: the repository's migrated live population does not
currently contain an accepted residual-income model, so that method's editor is
verified through the deterministic new-model workflow and fixtures rather than
an accepted production revision. The current normalized output contracts also do
not expose a canonical sensitivity matrix; the workspace keeps that state
explicit and uses the method-specific deterministic draft preview for what-if
analysis instead of calculating sensitivities in React.
