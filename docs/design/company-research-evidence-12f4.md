# Company Research & Evidence workspace (12F.4)

## Purpose

The Research & Evidence view answers: **what evidence has emerged, what does it
mean, and what should be reviewed next?** It is a company-level investigation
workspace. It does not author or accept research, risk, model or investment
decisions.

## Information hierarchy

1. **Research & evidence** — a compact summary of the latest primary source,
   accepted research revisions, accepted qualitative risk findings and open
   review work.
2. **What changed** — a deterministic, recency-filtered activity stream. It
   combines filing metadata, accepted research revisions, accepted risk
   findings and captured evidence triggers, sorted by effective time and then
   recorded time. The stream shows the ten most recent matching records; the
   underlying source sections remain available below.
3. **Filings & source documents** — the eight most recent source records with
   exact filing/publication dates, amendment relationships, source links,
   retrieval time and quality state. Metadata inspection uses a drawer; the
   original link opens in a new tab.
4. **Research interpretations & source evidence** — accepted research revision
   history, author/source context, forecasts and linked evidence. Source
   evidence is explicitly labelled as evidence used by an interpretation; it
   is not presented as consensus or an accepted model assumption.
5. **Accepted qualitative risk assessments** — accepted findings, severity,
   confidence, direction, reviewer and portfolio baseline. Stale or incomplete
   baselines stay visible and are never converted to numeric Risk scores,
   target changes or trades.
6. **Research next** — open queue tasks, open deterministic triggers and
   unresolved thesis questions. The existing Research Queue and Model Sync
   review flows remain the actions for completion or proposal acceptance.
7. **Thesis and model context** — claim-level supporting/contradicting/context
   evidence with links to Thesis, Financials and Valuation views.

## Shared interaction patterns

- Evidence category (`Reported sources`, `Research interpretations`, `Accepted
risks`, `Evidence triggers`) and recency (`30`/`90` days) controls filter the
  prioritized activity stream. Undated records remain visible in the all-dates
  view and are excluded from a bounded recency window rather than being given
  an invented date.
- `Inspect evidence` opens a keyboard-accessible detail drawer. Drawers retain
  source IDs, timestamps, contract/revision identity, baseline status and
  original URLs.
- Empty, loading and error states are shown per evidence stream. A missing
  source, thesis, risk assessment or queue is never represented as zero or as
  a completed research conclusion.
- Accepted qualitative risk assessments and pending proposals are separated.
  The page links to Model Sync for proposal review; it has no acceptance
  action.
- Company context is preserved in links to the existing Research Queue, Thesis,
  Financials and Valuation views.

## Implementation boundaries

`CompanyResearchEvidenceWorkspace` is a thin orchestration component. It uses
the existing typed `/v1` contracts and `useResearch` data access for:

- source documents and SEC identity status;
- research revisions and source evidence;
- accepted company risk assessments;
- captured research triggers;
- the derived research queue; and
- the accepted thesis stream and claim evidence.

The former standalone `SourceDocuments` and `CompanyRiskAssessments` views
were removed after their consumers were migrated into this workspace. Their
typed contracts and backend routes remain unchanged.

Filtering and ordering are presentation-only. The backend remains responsible
for event materiality, point-in-time selection, risk baseline validation,
queue fingerprints and immutable revision history. The workspace replaces the
old isolated `SourceDocuments` + `CompanyRiskAssessments` composition on the
Research & Evidence tab.

## Verification

- Unit tests cover category filtering, deterministic newest-first ordering,
  undated source behavior and the separation of four activity categories.
- The Company Explorer browser test covers complete filing/risk fixtures,
  category filtering, evidence drawer inspection and the existing thesis
  workflow at desktop and mobile widths.
- A live local database inspection was performed at desktop width using
  Alphabet. The populated state showed 54 source records, explicit source
  provenance, open model/research review work and explicit no-thesis/no-risk
  states. Mobile layout and horizontal-overflow behavior are covered by the
  corresponding Playwright project.
- Visual captures: [desktop](screenshots/company-research-12f4-desktop.png) ·
  [mobile](screenshots/company-research-12f4-mobile.png).

## Known limitations

- Source document bodies are not stored or summarized; the catalog provides
  stable metadata and links only.
- Pending Google Sheets risk candidates are reviewed on Model Sync and are not
  duplicated in Company Explorer. The Company page surfaces the pending review
  path and accepted history separately.
- Activity records are intentionally compact. Full document, revision, risk
  and trigger context is available through the drawers and linked domain views.
- The first version does not infer thesis significance from a filing and does
  not generate recommendations. Deterministic triggers and analyst review
  remain separate.
