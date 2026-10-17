# Agent-assisted research-to-model workflow

This workflow connects published research to a proposed assumption change while
keeping factual or qualitative research, agent interpretation, model assumptions
and accepted model revisions as separate records. It uses the existing Sheets
model inbox and deterministic financial-model engines; it adds no new valuation
methodology or automatic acceptance behavior.

## Sequence

1. Publish source-linked forecasts through `ResearchRevisionContractV1` or a
   thesis snapshot through `InvestmentThesisContractV1`. When the work came from a
   Thesis Watch trigger, use contract version `1.1.0` and include its canonical
   trigger ID, classification and rationale in `trigger_references`. The
   application records
   those revisions immutably and returns canonical IDs. Read them later through
   `GET /v1/companies/{company_id}/research` and
   `GET /v1/companies/{company_id}/thesis`.
2. Export the current model contract, edit only supported method-specific
   assumptions in Sheets, and fill the proposal provenance and evidence references.
3. Publish the complete contract to the existing `Application Model Sync Inbox`.
4. `/model-sync` captures the contract, verifies model/listing/currency/method
   identity and the current base revision, resolves each cited record, and runs the
   deterministic model engine to produce assumption, projection and output diffs.
5. A named reviewer previews the contract, records a decision note and explicitly
   accepts or rejects it. Acceptance appends a new canonical model revision.

The same model inbox and review states serve this workflow. Research records are
never copied into the model input tables, and suggested assumptions remain a
proposal until accepted. The application does not change portfolio transactions,
holdings or targets.

## Contract versions and evidence

`FinancialModelContractV1` version `1.2.0` is used for UFCF DCF. The versioned
`AdditionalModelPortableContractV2` version `2.1.0` covers owner cash flow and
residual income. These versions add a top-level `proposal` object and
`supporting_evidence` array. Earlier `1.0.0`, `1.1.0` and `2.0.0` contracts remain
readable for compatibility with prior inbox records; new evidence-linked proposals
must use the latest version for their model family.

The proposal metadata contains `author_id`, timezone-aware `authored_at`, and an
HTTPS `source_reference`. The existing model candidate continues to contain the
revision rationale, effective time, source identity and external revision ID.
Supporting evidence uses typed canonical references:

- `RESEARCH_REVISION` and `RESEARCH_FORECAST`
- `THESIS_REVISION` and `THESIS_CLAIM`

Each reference carries its canonical UUID, a relationship (`SUPPORTS`,
`CONTRADICTS` or `CONTEXT`) and an optional note. At least one published research
or thesis reference is required. Referenced rows must exist, belong to the model's
company, and, when security-scoped, match the exact security used by the model's
valuation listing. Unavailable or data-check forecasts remain labeled with their
source status for the reviewer. The system does not score evidence quality or
decide whether it economically justifies a proposed assumption.

Example proposal envelope:

```json
{
  "contract_version": "1.2.0",
  "proposal": {
    "author_id": "research-agent",
    "authored_at": "2026-10-15T09:00:00Z",
    "source_reference": "https://docs.google.com/spreadsheets/d/<id>/edit#gid=<tab>"
  },
  "supporting_evidence": [
    {
      "evidence_type": "RESEARCH_FORECAST",
      "reference_id": "<published-research-forecast-uuid>",
      "relationship": "SUPPORTS",
      "note": "Revenue outlook informs the proposed forecast path."
    },
    {
      "evidence_type": "THESIS_CLAIM",
      "reference_id": "<published-thesis-claim-uuid>",
      "relationship": "CONTEXT",
      "note": "The change is consistent with the reviewed growth-driver claim."
    }
  ]
}
```

These fields sit beside the existing `candidate_revision` object. Its assumptions,
model rationale and external revision identity describe the proposed model state;
the proposal block identifies the author and work source; evidence references point
to separately published research state.

## Validation, acceptance and history

The API rejects missing proposal metadata, missing evidence, unsupported methods,
unknown evidence IDs, withdrawn research/thesis revisions, company/security
mismatches, duplicate references and stale model bases. Exact contract replays stay
idempotent. Reusing an external revision ID for changed content conflicts. At
acceptance, the application recalculates again and verifies that the canonical base
has not advanced. A changed preview must be reviewed again before acceptance.

Accepted model revisions retain proposal author, authored time, source reference and
relational links to each cited research or thesis record. Accepted research/thesis
revisions retain their trigger ID, trigger classification and rationale, and model
proposal evidence resolves that lineage for review. Research and thesis rows remain
immutable and are not duplicated. The existing Sheets candidate retains the
reviewer, decision note, source workbook row, publication fingerprint and final
decision. Model history displays the proposal and linked sources. Downstream
Expected Return History, attribution, rankings and Attention Center continue to
consume the accepted canonical model revision through their existing interfaces;
research records alone do not change those calculations.

The workflow creates no scheduled agent watcher and performs no automatic
acceptance. A human still judges whether evidence supports the assumption change.
See [Google Sheets synchronization](google-sheets-sync.md),
[canonical research forecasts](research-forecasts.md),
[investment thesis and evidence](investment-thesis.md), and
[financial models](financial-models.md) for the underlying contracts and domain
rules.
