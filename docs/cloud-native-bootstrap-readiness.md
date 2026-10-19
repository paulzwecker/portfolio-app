# Cloud-native bootstrap readiness

## Decision

The operator has selected a **new canonical cloud baseline built from reproducible
authoritative inputs**. The historical local PostgreSQL database is not an input to
this workflow and will not be migrated. This is a new baseline, not a faithful copy
of the local database. Its canonical state must be explainable from versioned source
artifacts, exact identity mappings, recorded source/effective times, and pinned
calculation methods. Missing values stay distinct from explicit zero, and financial
values retain exact decimal semantics.

No local/source or Neon production database, workbook, provider, or cloud
credential was accessed for this review. A disposable PostgreSQL 18 test database
was used only to validate the counts-only SQL against the migrated empty schema.
The counts in the checked-in gap report are the aggregate counts supplied in the
request; the Neon baseline is also operator-reported and not independently audited.
The report contains counts only and must be replaced with read-only count snapshots
before it is used as an execution gate.

The planned route is a **gated, domain-by-domain cloud bootstrap**:

1. Reimport current authoritative snapshots where an existing importer has a
   reviewed mapping and a reconciliation report.
2. Re-fetch external facts only for exact reviewed identities and where provider
   terms permit storage and display.
3. Recompute only outputs whose complete canonical inputs and parity conditions
   are present.
4. Keep historical local-database-only state out of scope and record each omitted
   history class explicitly in the input manifest and recovery report.

There is no general restore, data reset, automatic scheduler, or complete bootstrap
orchestrator in this change. Task 4 adds a bounded first-stage canonical workbook
bootstrap over Task 3's approved snapshots. It reuses the validated identity,
portfolio, assessment, ranking, and research-priority import logic; requires the
shared target guard; and commits all stage rows and a content-keyed receipt in one
transaction. Later market, fundamentals, and model/analytics stages, plus a full
clean-rebuild rehearsal, remain separate work. The metadata-only manifest
validator remains available for source metadata, exact-value policies, history
decisions, and dependency order. The complete pipeline must coordinate later
provider operations with their distinct review, retry, and acceptance rules.
The current importer CLIs still select their database through `DATABASE_URL`, but
the shared SQLAlchemy engine now installs the verified database write-target guard.
Remote writes require Neon control-plane project/branch/endpoint identity checks and
environment-specific authorization; production bootstrap also requires an exact
interactive target confirmation. This guard does not make a general bootstrap
complete orchestrator or approve a production run. Every bootstrap stage must use
the shared engine factory, call its explicit preflight before source/provider work,
and retain the clean-schema, Alembic, domain reconciliation, and operator review
gates. See
[`database-write-targets.md`](database-write-targets.md) for the integration
contract and operator procedure. The metadata-only authoritative-input manifest
is validated separately through the procedure in
[`cloud-native-bootstrap-runbook.md`](cloud-native-bootstrap-runbook.md); it
does not apply inputs or authorize a write.

## Recovery classes

| Class | Meaning                                                                                                                                                  |
| ----- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A     | Reimportable from a current authoritative workbook or reviewed application contract. It may represent only a current snapshot, not old history.          |
| B     | Re-fetchable from a provider for reviewed identities. Retrieval times, provider payload versions, or the historical values once known may differ.        |
| C     | Deterministically recomputable from complete canonical inputs and the same versioned methodology. It is not recoverable when required inputs are absent. |
| D     | Historical, manually accepted, or audit state without a complete reproducible source. Preserve selectively or approve its omission explicitly.           |

## Recovery feasibility matrix

Counts below are from the task description unless otherwise stated. `Unknown` means
the request did not provide an aggregate count; it does not mean zero.

| Domain                                                              | Class                                                                                      | Authoritative source and existing path                                                                                                      | Fidelity, dependency, and recovery limit                                                                                                                                                                                                                                                                                                                                                       |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Company identities                                                  | A                                                                                          | Current `Portfolio_Watchlist.xlsx` registry through `legacy_import.py`                                                                      | The stated local count is 219. A clean import can recreate mapped company identities; blank, conflicting, or unresolved source rows remain issues. Reimport must run before any company-linked data.                                                                                                                                                                                           |
| Securities and listings                                             | A                                                                                          | `Market Data.xlsx` exact `venue:ticker`, currency, instrument, and provider-symbol mappings through `legacy_import.py` and `market_data.py` | The stated count is 110 securities; the listing count was not supplied. A source file must map each held/listed security exactly. Ticker-only matching, guessed ADR ratios, and inferred currencies are rejected. Historical identity changes and local-only mappings are not recreated unless present in the authoritative mapping source.                                                    |
| Current holdings and cash                                           | A                                                                                          | `Current Holdings` workbook snapshot through `legacy_import.py`                                                                             | The stated count is 22 holdings. The importer creates a current snapshot; it does not recover older holdings snapshots, cost basis, historical cash flows, or source-effective time if the workbook never recorded it. The importer excludes the aggregate Cash row to avoid double counting.                                                                                                  |
| Current target allocations                                          | A                                                                                          | `Target Architecture` snapshot through `legacy_import.py`                                                                                   | The stated count is 16. Exact fractional weights and explicit zero are copied. Prior target revisions and acceptance decisions are not reconstructed from the current snapshot. An unrepresentable reserve row blocks apply.                                                                                                                                                                   |
| Lifecycle and accepted decisions                                    | A for current bucket; D for history                                                        | Explicit workbook bucket and `LifecycleEvent` domain                                                                                        | Current lifecycle may be mapped from the source rules, but old lifecycle transitions, authorship, rationale, effective time, and acceptance trail are historical state. Do not infer it from holdings, scores, models, ranks, or prices.                                                                                                                                                       |
| Provider identity and source mappings                               | A for reviewed current mappings; D for mapping history                                     | Checked-in Yahoo crosswalks plus operator-reviewed CIK/FMP mappings and evidence                                                            | Yahoo listing/pair mappings are versioned in source. CIK, provider symbol, currency, source precedence, evidence, and effective dates may be application data. Revalidate each mapping; do not guess from ticker/name or copy a current mapping into past periods.                                                                                                                             |
| Scores                                                              | A for source snapshot; D for full history                                                  | Workbook score tabs through `legacy_import.py`                                                                                              | The stated local count is 506 assessments. Current populated cells and source rationales may be imported. A workbook snapshot does not reproduce the sequence of accepted score revisions or the actual historical time each score became known. Blank values remain absent, not zero.                                                                                                         |
| Research priority inputs                                            | A for current imported snapshot; D for prior decisions                                     | Dedicated `research_priority_import.py` from the workbook's priority inputs                                                                 | A current priority seed can be imported separately. Prior priority changes, reviewer decisions, and agent queue acknowledgments are application history and are not reconstructed by re-running the current input import.                                                                                                                                                                      |
| Rankings and execution decisions                                    | A for cached source snapshot; C for a new run; D for old runs                              | Cached workbook rank positions, canonical ranking services, and append-only `RankingRun`/execution records                                  | A current rank run can be preserved as a workbook observation; new rankings can be recomputed only after all required scores, market values, models, targets, and definitions are present. Historical ranking runs, unavailable positions, and old execution decisions are not recreated by recalculation.                                                                                     |
| Prices and corporate actions                                        | B; A for a bounded workbook snapshot                                                       | `Market Data.xlsx` import and Yahoo chart ingestion                                                                                         | The stated local inventory is about 305,000 price observations. Provider ingestion uses exact reviewed listing crosswalks and a ten-year default lookback for a new listing. It cannot promise the same history, old listing coverage, source-quality labels, original observation times, or past provider adjustments. Yahoo corporate actions remain unverified until independently checked. |
| FX observations                                                     | B                                                                                          | Yahoo chart adapter with an explicit currency-pair allowlist                                                                                | The stated local inventory is about 26,000 observations. Only configured pairs are fetched; the adapter does not invent missing currencies or rates. Re-fetch creates new retrieval/provenance records and cannot restore the old application's historical knowledge time.                                                                                                                     |
| Reported fundamentals and filing metadata                           | B                                                                                          | SEC Company Facts and EDGAR submissions through reviewed CIK mappings                                                                       | The stated local inventory is about 27,000 observations. SEC access needs `SEC_USER_AGENT`; requests must stay under the SEC's published rate guidance. The standard concept allowlist is intentionally narrow, non-US coverage is incomplete, and the present SEC response cannot recreate what the application knew before ingestion. Filing bodies are not stored by the current adapter.   |
| Consensus estimates                                                 | A for limited legacy cells; B only with licensed provider access                           | Legacy estimate import or the FMP adapter                                                                                                   | The checked-in legacy baseline is a single `DATA_CHECK` snapshot without reliable provider, currency, analyst-count, or absolute-period semantics. FMP is disabled by default; a key alone does not authorize canonical storage/display. Current estimates cannot reconstruct past revisions.                                                                                                  |
| Published model-output snapshots                                    | A                                                                                          | `Model Output Contract` and `Model Revision History` through `model_outputs.py`                                                             | The stated local count is 344 snapshots. Exact cached decimals and available source-cell/revision provenance can be imported. The importer does not evaluate formulas, derive missing outputs, accept assumptions, or establish a new economic interpretation for legacy Expected IRR labels.                                                                                                  |
| Native financial-model inputs and revisions                         | A for the parity-backed source rows; D for local-only accepted history                     | `model_input_migration.py`, canonical revision services, and portable model contracts                                                       | Repository documentation records 10 parity-backed native models at its last coverage checkpoint, not a complete current local revision count. Import creates a new accepted revision time; it cannot claim the original acceptance time unless retained as source metadata. Most active workbook models remain output-only or blocked. Never bulk-recalculate them.                            |
| Research forecasts, assessments, thesis, evidence, and risk history | A only for complete reviewed portable contracts; D for accepted history without an archive | Sheets contract inboxes and append-only API revision operations                                                                             | The inbox is for current proposals and sync discovery; it is not a complete archive of all accepted historical revisions. Evidence foreign keys depend on canonical company, source-document, and fundamental records. Accepted decisions, rationale, authorship, supersession, and evidence links must be selectively preserved or explicitly omitted.                                        |
| Candidate-pipeline revisions and gate decisions                     | D                                                                                          | `candidate_pipeline_revisions`, gate assessments, evidence, and explicit review actions                                                     | This is application-owned screening/review history. Current inputs or a refreshed queue cannot recreate prior submission identities, gate outcomes, rationale, or evidence. Preserve through a reviewed source archive or explicitly approve omission.                                                                                                                                         |
| Source documents                                                    | B for current SEC metadata; D for historic retrieval/provenance                            | SEC submissions adapter and operator-registered HTTPS references                                                                            | Public metadata can be fetched again for reviewed CIKs, but new retrieval timestamps are not old timestamps. Non-US sources and document bodies are not covered. Historical mappings and application recording times are not recoverable from a current SEC response.                                                                                                                          |
| Raw payloads, import receipts, and operations history               | B for the latest fetch; D for prior runs and payload versions                              | Domain batch tables, `external_raw_payloads`, external and recurring operations ledgers                                                     | Reruns can re-use exact payloads or append a new correction, but they do not recreate previous run attempts, payload bytes, retry decisions, or the original source hash when those are only in the local database. Keep these as audit data if operational traceability matters.                                                                                                              |
| Sheets sync, agent delivery, and review receipts                    | A for current portable proposals; D for accepted and delivery history                      | Google Sheets inbox contracts, acknowledgement tabs, and application sync receipts                                                          | Current inbox contents can be rediscovered with a shared workbook and service account. Accepted/rejected candidates, work-feed deliveries, acknowledgments, and recorded sync times remain application history; discovery does not replay or accept them.                                                                                                                                      |
| Current derived analytics                                           | C                                                                                          | Existing portfolio/rank/valuation query services                                                                                            | Recompute only after all exact inputs, currency rules, source precedence, and methodology versions are present. A successful new result is a new current calculation, not evidence that an old result or old decision has been reproduced.                                                                                                                                                     |

The counts-only baseline is in [`recovery-gap/known-local-inventory.json`](recovery-gap/known-local-inventory.json), the operator-reported target baseline is in [`recovery-gap/neon-reported-baseline.json`](recovery-gap/neon-reported-baseline.json), and the generated sanitized report is in [`recovery-gap/recovery-gap-report.json`](recovery-gap/recovery-gap-report.json). The JSON files contain no identities, row values, URLs, or credentials.

## Import and dependency order

The existing tools are domain importers, not one end-to-end bootstrap:

1. Apply and verify Alembic head `12a6f0d9c3e1` on a newly created, isolated
   PostgreSQL 18 database. Migration-seeded score/ranking/return definitions are
   schema bootstrap data. Do not run `npm run db:seed`; it adds fictional demo
   portfolio data and is not a production bootstrap.
2. Dry-run the workbook identity/state import. Review unresolved identities,
   lifecycle decisions, weights, scores, and rank rows. Only a clean empty
   universe/portfolio may be applied without the narrowly scoped demo replacement
   option. The apply is one transaction; do not use demo replacement for real data.
3. Apply the exact listing-aware market workbook import after identities exist.
   It does not populate FX and does not prove current provider coverage.
4. Dry-run and reconcile published output snapshots. Import native model inputs
   only after source-hash, company/listing identity, return semantics, and parity
   checks pass. Run `--parity-only` before an apply; inspect the per-model result.
5. Verify CIK/provider mappings and source terms. Ingest SEC documents/facts only
   for reviewed issuer identities. Add FMP only after written entitlement permits
   stored raw responses and application display.
6. Reconcile canonical facts, history coverage, currencies, and source quality.
   Compute current analytics/ranks only after their dependencies are complete.
7. Import accepted thesis/research/risk contracts only as explicit reviewed
   snapshots with valid canonical evidence references. Never auto-accept a Sheets
   proposal during bootstrap.

The principal existing commands are `db:import-workbook`, `db:import-market-data`,
`db:import-model-outputs`, `db:import-native-models`, `db:import-research-priority`,
`db:sync-market-data`, `db:sync-reported-fundamentals`, `db:sync-source-documents`,
and the explicit consensus commands. They require separate dry-run/reconcile
reviews. See the [workbook import](workbook-import.md),
[market data](market-data.md), [model-output import](model-output-ingestion.md),
[native model migration](native-model-input-migration.md),
[external-data architecture](external-data-architecture.md),
[external-data operations](external-data-operations.md),
[reported fundamentals](reported-fundamentals.md),
[source documents](source-documents.md),
[consensus estimates](consensus-estimates.md),
[financial models](financial-models.md), and
[Google Sheets sync](google-sheets-sync.md) runbooks before execution.

## Repeat behavior and failure recovery

| Operation                                | Repeat behavior                                                                                                                                                      | Interruption handling                                                                                                                                            |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Workbook identity/portfolio import       | Source workbook digests identify an import batch. An exact repeat returns its saved receipt. The apply is one database transaction.                                  | A failed transaction rolls back. Resolve reported source issues, then rerun the exact snapshot. A changed snapshot is a new source batch and needs a new review. |
| Market workbook and model-output imports | Content hashes and batch identities make an exact source replay idempotent. Output decimals are compared exactly; conflicting reuse of a revision identity aborts.   | Re-run the same dry-run before apply. Do not repair a report by changing canonical rows directly.                                                                |
| Native model input import                | It validates the checked-in inventory hash and parity; accepted inputs use explicit model/revision identity and are reported as already imported on exact replay.    | The database operation is transactional. Use parity-only output first; after a partial provider or database issue, inspect the per-model report before retry.    |
| Provider ingestion                       | Run/attempt ledgers, source hashes, and source business keys deduplicate exact repeats. A changed provider response may append a correction/superseding observation. | Domains may commit separately. `PARTIAL` does not mean no writes. Inspect run and batch receipts, then use the explicit replay/retry path for that domain.       |
| Sheets contract discovery                | Captured candidates are idempotent and preserve the source contract fingerprint. Discovery does not accept a proposal.                                               | Repeat discovery after configuration correction; keep reviewer acceptance as a separate action.                                                                  |
| Derived current analytics                | Recompute from the current canonical input set under the existing method and quality rules.                                                                          | A new result is not a replay of a prior decision. Preserve prior run rows where historical comparison matters.                                                   |

## Cloud readiness and limits

- `render.yaml` keeps `CLOUD_INGESTION_ENABLED=false`,
  `RECURRING_OPERATIONS_ENABLED=false`, and Sheets polling at `0`. No Cron service
  is configured. Keep those values unchanged during a bootstrap rehearsal.
- The task context says Vercel and Render are deployed. The current
  `cloud-deployment.md` introduction still describes them as unprovisioned, and
  this review did not query either provider. Reconcile that documentation state
  with the operator's service consoles before using deployment-specific steps;
  this assessment relies on checked-in defaults only.
- Render Free API instances sleep after 15 minutes idle. The API process does not
  run workers. A bootstrap spanning provider calls is not a reliable request or
  web-service operation. The optional Render Cron path is a separately billed
  service (the repository's current estimate is at least $1/month); do not create
  it for this task.
- Neon Free is documented as 1 GB storage and 100 CU-hours per project/month.
  Prior deployment notes measured the existing local database at about 289 MB
  and the schema-only Neon branch at about 31.7 MB. These older measurements do
  not certify the size of the latest source snapshot, retained provider payloads,
  or a reconstructed branch. A first planning estimate is approximately the old
  289 MB database footprint before new raw-payload growth; treat that only as a
  sizing reference. Measure a disposable rehearsal after import and require
  substantial headroom below the 1 GB project limit; do not purchase capacity
  automatically.
- Approximate runtime for an end-to-end rebuild has not been measured. It spans
  operator review, up to a ten-year market backfill, SEC calls, importer
  transactions, partial-result diagnosis, and reconciliation. Plan for several
  hours across review and execution windows; do not schedule a one-shot job on
  Render Free.
- Expected marginal infrastructure cost is `$0` if the existing Neon and Render
  Free allowances cover the rehearsal and no paid provider entitlement is added.
  A Render Cron service is a separate paid resource, currently estimated in the
  deployment notes at a minimum of `$1/month` plus execution; it is not part of
  this plan. FMP pricing is not estimated because no approved plan or agreement
  was supplied.
- SEC does not require an API key but requires a descriptive `SEC_USER_AGENT`;
  keep requests within the SEC's published limit. Yahoo uses the repository's
  exact listing/pair allowlists and bounded retries, but availability and
  redistribution terms must be reviewed for the intended deployment. FMP requires
  both a key and a contractual storage/display entitlement. Google Sheets requires
  a spreadsheet ID plus a service-account file shared to the relevant workbook;
  read and write permissions differ. Do not place credentials in the repo, report,
  browser, or Codex Cloud.
- External providers have bounded retries and record `BLOCKED`, `PARTIAL`, and
  `FAILED` outcomes. A partial domain may commit valid independent observations;
  it does not roll back the other provider/domain transactions. Reconcile each
  result and use the domain's explicit replay or retry workflow rather than
  treating a nonzero exit as no writes.

## Exact read-only count check

This procedure produces only table names and aggregate counts. It does not read a
row value into a report. Run it only from the operator's trusted workstation with
a read-only database role. The task did not authorize connecting to Neon
production, so no such connection was made here.

PowerShell, after the operator has separately approved and obtained the correct
read-only endpoint and role:

```powershell
$ErrorActionPreference = 'Stop'
$countFile = Join-Path $env:TEMP 'portfolio-source-counts.csv'
try {
    $env:PGHOST = '<direct-hostname>'
    $env:PGPORT = '5432'
    $env:PGDATABASE = '<database-name>'
    $env:PGUSER = '<read-only-role>'
    $env:PGSSLMODE = 'require'
    psql -q -W -X -v ON_ERROR_STOP=1 --csv -f docs/recovery-gap/recovery-gap-counts.sql > $countFile
    if ($LASTEXITCODE -ne 0) { throw 'The read-only count query failed.' }
} finally {
    Remove-Item Env:PGHOST, Env:PGPORT, Env:PGDATABASE, Env:PGUSER, Env:PGSSLMODE -ErrorAction SilentlyContinue
}
```

`psql -W` prompts for the password rather than putting it in the command line or
report. Repeat separately for the isolated target and save the second output under
a different local filename. Keep both CSV files outside Git and do not upload them
to Codex or attach them to a PR. Check only the CSV header and count values. Update
the counts-only JSON snapshots in local copies on the trusted workstation. Set
`verified` to `true` only after the complete count set is confirmed, then run:

```powershell
$sourceInventory = Join-Path $env:TEMP 'portfolio-source-inventory.json'
$targetInventory = Join-Path $env:TEMP 'portfolio-target-inventory.json'
Copy-Item docs/recovery-gap/known-local-inventory.json $sourceInventory
Copy-Item docs/recovery-gap/neon-reported-baseline.json $targetInventory
# Update aggregate counts in these local copies from the two count-only CSV files.
& .\.tools\venv\Scripts\python.exe -m portfolio_api.bootstrap_gap_report `
  --source $sourceInventory `
  --target $targetInventory `
  --output (Join-Path $env:TEMP 'portfolio-bootstrap-gap-report.json')
```

On Linux or macOS, use `.tools/venv/bin/python` with the same module arguments.
The report utility uses only the supplied aggregate JSON snapshots and does not
load `.env` or connect to a database.

The committed target file is explicitly provisional. Before a real apply, every
required count must be independently verified from the live target and all D-class
source counts must be inventoried. Store the generated operator report locally;
only commit an aggregate report after removing private notes and confirming it
contains counts alone. A read-only count comparison is not an import approval.

## Data fidelity and recommendation

A fresh cloud rebuild can restore an operational **current-state** starting point
from the mapped workbook snapshots, supported model outputs, and provider facts.
It cannot by itself preserve the full canonical history. In particular, a rebuild
without a separate archive or selective preservation plan loses or changes:

- prior accepted financial-model revisions, scenario inputs, acceptance times,
  authorship, and evidence references that are not in the import workbook;
- historical holdings, target, lifecycle, score, ranking, execution, and research
  decisions beyond the snapshots available in authoritative source files;
- the application's original `recorded_at`/`known_at` state for prices, FX,
  fundamentals, consensus, source documents, and provider corrections;
- old provider payload bytes, import/ingestion receipts, retry attempts, and
  original operational provenance;
- manually authored thesis, research, risk, and evidence history that is not
  available as a complete accepted-contract archive.

The current decision is to create a new cloud baseline, not to reproduce or replace
the historical database. D-class histories that have no authoritative portable
archive are outside this baseline; they must be listed as omitted, never inferred
from current snapshots. The operator's instruction rules out using the historical
database as an input. Keep that local database untouched. The old aggregate counts
in this readiness audit are context only, not import expectations or acceptance
criteria for the new baseline. Do not proceed until the authoritative input files,
versions, exact identity-map hashes, source times, decimal/null policies, and domain
decisions are assembled in the metadata manifest on the trusted operator machine.

## Safe rehearsal and production activation sequence

1. Complete the input manifest locally using the template and procedure in
   [`cloud-native-bootstrap-runbook.md`](cloud-native-bootstrap-runbook.md). Keep
   source artifacts, manifests with private paths, and detailed reports on the
   trusted operator machine. CI receives only synthetic fixtures.
2. Validate the metadata manifest with the no-database command in that runbook.
   This checks dependency order and blocks ambiguous history, identity, decimal,
   missing-value, or approval metadata.
3. Use Task 4 `preview` only after the exact source snapshots and isolated target
   are separately authorized. Task 4's apply/resume path is tested only against
   synthetic inputs and a disposable PostgreSQL 18 target. Do not apply real
   portfolio snapshots or run provider jobs against Neon until a real-source
   rehearsal has been separately authorized and reviewed. Later tasks must add
   and test the remaining domains before claiming end-to-end readiness.
4. Do not enable Cron, Sheets polling, `CLOUD_INGESTION_ENABLED`, Render jobs, or
   Vercel/Render configuration changes as part of this baseline preparation.
5. A separate future milestone must define recovery reports and financial/domain
   reconciliation for exact identities, decimal values, null/zero distinctions,
   accepted outputs, provenance, and approved history omissions.
6. Production activation requires a separately authorized change, a verified
   production target, reviewer sign-off, and an explicit operational rollback plan.
   Never reset, truncate, or replace the existing production branch as a shortcut.

## Known limits

- The report baseline is provisional until read-only counts are collected by the
  operator. The reported aggregate counts do not resolve table-level count
  differences or the older workbook inventory's differing snapshot counts.
- The latest prompt reports 110 securities. Older workbook documentation records
  a different securities/listings snapshot. Resolve the exact source artifact and
  mapping inventory before using either count as an import expectation.
- This change intentionally does not import workbook data, connect to Neon, fetch
  provider data, enable a worker, or add an end-to-end bootstrap command. CI uses
  synthetic PostgreSQL fixtures only.
  Existing importer tests cover individual transactions and repeat behavior;
  they do not prove that a complete current dataset can be recovered from
  external sources.
- No approved source archive for the complete set of accepted research and native
  model histories was available in this review. Those counts and exact recovery
  paths remain open operator decisions.
