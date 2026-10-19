# Canonical Portfolio Bootstrap (14B-R.4)

## Status and boundaries

The `portfolio_api.canonical_bootstrap` command imports one explicitly selected,
schema-approved Task 3 snapshot pair. It requires the current Alembic head and
the shared database write-target guard. It does not acquire sources, call Google,
call financial-data providers, migrate the historical local database, or run any
Task 5–7 ingestion or calculation stage.

Implementation is tested only with generated synthetic workbooks and a disposable
PostgreSQL 18 database. No real workbook snapshot, portfolio input, Neon branch,
Render service, or Vercel setting was accessed or changed for this task. A real
source rehearsal and every production write remain separately authorized actions.

| State       | Result                                                                                                                                                                                                          |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Implemented | Approved snapshot selection; exact source mapping; reviewed SEC CIK input; preview, apply, resume and reconcile; one-transaction import; private reports and immutable database receipts.                       |
| Tested      | Generated workbook fixtures, invalid and stale snapshot rejection, exact decimal and zero-target behavior, target guard, interrupted transaction recovery, rerun idempotency, and PostgreSQL 18 reconciliation. |
| Staged      | Operator may prepare private source snapshots and a reviewed identifier file, then run preview on an independently verified isolated target.                                                                    |
| Executed    | Synthetic fixture imports only. No canonical portfolio source import was executed.                                                                                                                              |

## Import scope and exact source mappings

The workbooks are read from their unchanged, hash-verified Task 3 blobs. Cached
OOXML values are consumed as supplied; formulas are not evaluated.

| Domain                       | Source mapping and policy                                                                                                                                                                                                                                                                                                                     |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Company identities           | `Portfolio_Watchlist.xlsx`, `Universe Registry`: exact ticker in A and company name in B. Duplicate normalized tickers, unsupported ticker syntax, and missing company names block apply.                                                                                                                                                     |
| Securities and listings      | `Market Data.xlsx`, `Listings`: exact canonical ticker A, name B, `venue:ticker` C, exchange D, quote currency E, instrument basis G, and READY status K. Venue conflicts, duplicate venue/ticker keys, non-READY rows and unsupported instruments block apply.                                                                               |
| Supported ADR                | The existing explicit `Price Feed` AUX mapping supports the documented `TSM-ADR` security linked to the `TSM` underlying. Other ADR rows without an explicit supported underlying mapping block apply; the tool never infers an ADR ratio.                                                                                                    |
| Reviewed provider identifier | Optional private JSON mapping for exact `SEC_CIK` company identifiers. Each row must map one exact canonical ticker to a ten-digit CIK string, provider issuer name, and an HTTPS `sec.gov` evidence URL containing that CIK. Ticker/name similarity is never used to assign a CIK.                                                           |
| Lifecycle                    | `Universe Registry` bucket C plus cached current and target weights D/F. Both weights must be present before any lifecycle is classified. A positive current or target amount only implies PORTFOLIO when both values are present. Explicit Watchlist, Candidate, and Drop buckets are retained.                                              |
| Holdings and cash            | `Current Holdings`: row type A, canonical ticker B, exact listing symbol D, quantity/balance E, native cash currency G, and portfolio base-currency label L4. A missing quantity or balance creates no position or cash row and marks the snapshot partial. It is never changed to zero.                                                      |
| Strategic targets            | `Target Architecture`: canonical ticker A and weight D, with P3 used as the source total check. Explicit zero company targets are imported and kept distinct from absent rows. A blank target blocks target import. A positive RESERVE is unsupported; a zero RESERVE is reported and is not a company allocation. No weights are normalized. |
| Scores and quality           | `10Y Durability` and `Compounder Quality` cached values G, rationales K, and source references L. Existing P/W/C detail tabs provide Execution and Risk values from B7/B8 when their labels are explicit in A7/A8. Invalid nonblank values are retained as INVALID/null assessments with a private diagnostic; missing rows remain absent.    |
| Research priority            | `Universe Registry` candidate bucket C plus `Candidate Ranking` seed A and exact ticker B. Conflicts and invalid values are preserved as DATA_CHECK inputs or exclusions; the documented missing-seed distinction is retained.                                                                                                                |
| Ranking snapshots            | Cached `Universe Registry` positions J (Research), L (Portfolio), and M (Watchlist). Positions are copied as observations; the application does not recalculate them. Duplicate/invalid ranks remain unavailable and are never reassigned.                                                                                                    |

Yahoo listing symbols remain governed by the existing reviewed Yahoo crosswalk
used by market ingestion. They are not stored in `CompanyProviderIdentifier`,
which currently represents SEC CIK company identities. Task 5 consumes the
reviewed listing-provider crosswalk separately.

The import does not include price history, FX observations, corporate actions,
fundamental statements, licensed consensus, model outputs or assumptions,
investment theses, source-document bodies, accepted investment decisions, or
historical operational events. It does not invent those records.

The canonical columns have fixed PostgreSQL numeric scales. Targets must fit
`Numeric(18,12)`, holdings and cash `Numeric(28,10)`, and scores and research
priority seeds `Numeric(12,4)`. Values that do not fit exactly are rejected or
retained as an explicit data-quality gap; they are never silently rounded.

## Private reviewed CIK input

When reviewed SEC mappings are available, place this versioned JSON outside the
repository and pass its SHA-256 on every command. The following values are
fictional and are only a format example; do not use them for an actual baseline.

```json
{
  "format_version": 1,
  "reviewed_by": "synthetic-reviewer",
  "reviewed_at": "2026-10-18T12:00:00Z",
  "mappings": [
    {
      "canonical_ticker": "SYN",
      "identifier_type": "SEC_CIK",
      "identifier_value": "0000000001",
      "provider_company_name": "Synthetic Example Corporation",
      "evidence_source": "https://www.sec.gov/edgar/browse/?CIK=0000000001"
    }
  ]
}
```

The command accepts only the closed schema above. It rejects duplicate JSON keys,
duplicate tickers or CIKs, unknown canonical tickers, non-string CIKs, non-SEC
URLs, future review times, a provider-map file inside the repository, and a hash
that differs from the reviewed value. If no mappings are ready, omit both provider
map arguments. The report then records `NOT_SUPPLIED`; it does not infer CIKs.

## Operator procedure (Windows PowerShell 5.1 and 7)

All inputs and reports stay in a private directory outside the repository and
cloud-sync folders. Do not place workbook snapshots, CIK maps, generated reports,
database URLs, Neon API keys, or provider credentials in Git, CI, a PR, or chat.

### 1. Acquire and review the workbook snapshots

Use the Task 3 acquisition procedure. Acquisition alone never imports data. The
first snapshot for a source normally returns `ACQUIRED_REVIEW_REQUIRED`; inspect
its data-free manifest and approve the exact schema hash before using the review
run ID. An unchanged, previously accepted schema returns an `ACQUIRED` run ID.
Select the newest accepted run for each source.

```powershell
$snapshotStore = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
npm run source:workbook -- show '<portfolio-run-id>' --store $snapshotStore
npm run source:workbook -- show '<market-run-id>' --store $snapshotStore
```

The full workbook remains in the private snapshot store. Never copy it into the
repository or attach it to a PR. Do not acquire the actual workbook unless that
source action has been separately authorized.

### 2. Configure an isolated database target

The operator environment must provide `DATABASE_URL`,
`DATABASE_TARGET_ENVIRONMENT`, and `DATABASE_TARGET_DATABASE`. For a remote Neon
rehearsal it must also provide `NEON_API_KEY`, `NEON_PROJECT_ID`,
`NEON_BRANCH_ID`, `NEON_ENDPOINT_ID`, and the explicit rehearsal write
authorization. Use the direct endpoint rather than a pooled URL. The guard
resolves the live database identity on the same connection used by the writer and
checks Neon project, branch, and endpoint metadata. A user-entered branch label
alone is insufficient.

Load these values from the operator's protected environment or secret manager;
do not type or echo secret values in a command. `DATABASE_TARGET_ENVIRONMENT`
must match the command's `--target-environment`. The bootstrap command never
selects production by default, and production execution is outside this task.

The database must already be migrated to this checkout's exact Alembic head by
the separately reviewed database migration procedure. The bootstrap command
never runs migrations itself.

### 3. Preview (read-only database checks)

```powershell
$portfolioRun = '<accepted portfolio snapshot run id>'
$marketRun = '<accepted market-data snapshot run id>'
npm run db:bootstrap-canonical -- preview --store $snapshotStore --portfolio-run $portfolioRun --market-run $marketRun --target-environment rehearsal
```

If a reviewed CIK file exists, include its path and a locally computed digest:

```powershell
$providerMap = 'D:\private-inputs\provider-identifiers.v1.json'
$providerMapHash = (Get-FileHash -LiteralPath $providerMap -Algorithm SHA256).Hash.ToLowerInvariant()
npm run db:bootstrap-canonical -- preview --store $snapshotStore --portfolio-run $portfolioRun --market-run $marketRun --provider-identifiers $providerMap --provider-identifiers-sha256 $providerMapHash --target-environment rehearsal
```

Preview checks the current Alembic head, target identity, write privileges,
source approval and hashes, source mappings, exact numeric scales, current
database state, and an in-memory Task 2 manifest contract. It writes no database
rows. It stores a mode-restricted report under `bootstrap-runs` inside the private
snapshot store. An ambiguous mapping, unresolved lifecycle, unsupported target,
or non-empty target without a matching receipt returns exit code 2. Review the
private report locally; it can contain tickers and source-cell references.

### 4. Apply or resume

After the preview report is reviewed and the operator has authorized this exact
isolated target, run `apply` with the same run IDs and provider-map hash:

```powershell
npm run db:bootstrap-canonical -- apply --store $snapshotStore --portfolio-run $portfolioRun --market-run $marketRun --provider-identifiers $providerMap --provider-identifiers-sha256 $providerMapHash --target-environment rehearsal
```

If no reviewed provider map is being imported, omit both provider-map options.
All canonical domains and the receipt are written in one transaction. A database
failure before commit rolls back the entire run and creates no success receipt.
After an interruption, rerun the same exact inputs with `resume`:

```powershell
npm run db:bootstrap-canonical -- resume --store $snapshotStore --portfolio-run $portfolioRun --market-run $marketRun --provider-identifiers $providerMap --provider-identifiers-sha256 $providerMapHash --target-environment rehearsal
```

`resume` is idempotent. A matching completed receipt triggers reconciliation
without inserting duplicate companies, listings, targets, holdings, research
priority records, provider identifiers, or ranking snapshots. It does not repair
drift automatically.

### 5. Reconcile the imported snapshot

```powershell
npm run db:bootstrap-canonical -- reconcile --store $snapshotStore --portfolio-run $portfolioRun --market-run $marketRun --provider-identifiers $providerMap --provider-identifiers-sha256 $providerMapHash --target-environment rehearsal
```

Reconciliation checks the frozen source projection against company/listing
identities, lifecycle, holdings/cash, targets, score assessments, priority inputs,
provider identifiers, and cached ranking runs. Exact decimal values are compared
as decimals. Differences are listed in the private report; no value is substituted
with zero and no write is performed by `reconcile`.

After a successful rehearsal, keep the report and source manifest local. A real
source rehearsal and any production bootstrap require the separate authorization
described in the cloud bootstrap runbook and Milestone 14B-R.9 plan.

## Recovery and known limits

- The import and `canonical_bootstrap_runs` receipt share one database
  transaction. A process stop before commit leaves no partial canonical import
  receipt; rerun `resume` with the same snapshots and hash-pinned CIK file.
- An existing `LegacyImportBatch` from the prior workbook importer can be used as
  a core-stage checkpoint. The canonical wrapper only adds missing reviewed CIK
  and research-priority stages, reconciles the result, and records its own
  receipt. Conflicts fail without overwriting existing mappings.
- The wrapper refuses to apply to a non-empty target unless it finds the matching
  content-keyed canonical or legacy receipt. It does not replace demo data.
- Unresolved or incomplete lifecycle inputs block apply. Missing holding quantity
  or native-cash balance produces no guessed row and leaves the holdings snapshot
  marked partial with a reportable gap.
- This stage does not import source-cell formulas as values, provider-market
  observations, financial statements, models, decisions, or historical event
  streams. Those require their later bootstrap stages.
