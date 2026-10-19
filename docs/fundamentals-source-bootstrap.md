# Financial statements and evidence bootstrap

Task 6 adds `portfolio_api.fundamentals_bootstrap`, a bounded operator command for
re-fetching SEC Company Facts and EDGAR filing metadata for existing reviewed CIK
mappings. It composes the existing importers; it does not discover companies or
identities, download filing bodies, read workbooks, import consensus, run models, or
schedule ingestion. No SEC source or production database was accessed while this
stage was implemented.

## Scope and guarantees

- The mapping must exist in `company_provider_identifiers` as one exact ten-digit
  SEC CIK per company, with the provider's issuer name and HTTPS evidence URL. An
  ambiguous mapping, duplicate CIK, invalid CIK, or post-prepare mapping change
  blocks provider calls. Unmapped active companies are listed in preview and are
  never guessed from tickers or names.
- Per company, the order is `SOURCE_DOCUMENTS`, then `REPORTED_FUNDAMENTALS`.
  Filing metadata and raw SEC responses are retained through the existing immutable
  batches. Filing bodies and exhibits remain on SEC.
- SEC-reported values preserve exact decimals, source units/currencies, accession,
  filing date, fiscal labels, and instant versus duration periods. A later filing
  appends a new observation and links superseded values; it never overwrites them.
  Missing facts remain missing and an actually reported zero remains zero.
- The report groups coverage by company, statement, economic period, and provider;
  it also shows filing types/periods, accession linkage, unsupported records,
  missing mappings, retry state, and exact batch reconciliation. It excludes
  canonical financial values. Private reports still include company/CIK identities,
  SEC accession IDs, hashes, and mapping evidence URLs; keep them outside the repo.
- SEC requests require `SEC_USER_AGENT` with a monitored contact address. Calls are
  spaced at least 0.15 seconds apart, at most five historical submissions files are
  downloaded per checkpoint page, and at most ten pages run per invocation.
  Checkpoints retain retry/backoff state and failure codes. SEC 401/403 and invalid
  responses block the checkpoint; transient network, 429, and 5xx failures are
  retryable within the configured attempt bound.
- Licensed consensus ingestion is explicitly excluded. This phase never reads
  workbook consensus cells, calls FMP, recalculates financial models, or creates
  accepted decisions.

`COMPLETE` means every mapped checkpoint completed without availability or review
flags. `PARTIAL` means data was fetched but there are unavailable checkpoints,
unsupported forms/concepts, or quality checks to review. A partial run is not a
coverage-complete result. `reconcile` separately reports whether every stored batch,
raw payload hash, and canonical fingerprint still matches; `MATCHED` does not waive
coverage review. `BLOCKED` and `FAILED` are hard stops. CLI exit code 2 indicates
preview/prepare did not reach readiness, run/status is not complete, or
reconciliation did not match; inspect the private report and run ledger before
continuing. Reconciliation can return exit code 0 with run status `PARTIAL` when
stored batches match but coverage still needs review. This verifies storage
integrity only.

## Operator procedure (Windows PowerShell 5.1 and 7)

Use a private local directory for reports. Do not put SEC contact details, database
URLs, Neon keys, source payloads, or reports in GitHub, CI, PR attachments, or the
repository. This procedure is for a verified isolated development/rehearsal target;
the command has no production mode. Every subcommand verifies the configured target
and authorization. `preview`, `status`, and `reconcile` do not write data;
`prepare` writes the run ledger, and `run`/`resume` import source data.

1. Review and apply the checked-in Alembic migration to the explicitly selected
   isolated target using the normal database-write-target procedure. The bootstrap
   command does not run migrations. Set the exact rehearsal target and authorization
   in the operator's secure process environment, following
   [database-write-targets.md](database-write-targets.md). For Neon, use the direct
   endpoint, exact project/branch/endpoint/database identifiers, TLS verification,
   and rehearsal authorization. Never use the primary branch.
2. Set the SEC contact. The value is shown here as a placeholder; use a monitored
   email address through the local environment, not a script edit:

   ```powershell
   $env:SEC_USER_AGENT = 'Portfolio Research Platform analyst@example.com'
   ```

3. From the repository root, preview the exact reviewed mapping set. This is
   read-only and makes no SEC requests:

   ```powershell
   $reportDir = Join-Path $env:USERPROFILE 'Documents\portfolio-fundamentals-bootstrap'
   New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
   $preview = Join-Path $reportDir ('preview-' + [guid]::NewGuid().ToString('N') + '.json')
   npm run db:bootstrap-fundamentals -- preview `
     --target-environment rehearsal `
     --report $preview
   $previewResult = Get-Content -Raw $preview | ConvertFrom-Json
   $previewResult | Select-Object status, mapped_company_count, active_company_without_reviewed_cik_count
   ```

   Expect `READY` when at least one valid mapping exists. Review every listed
   mapping and every active unmapped company. `BLOCKED` or a mapping discrepancy
   means stop and correct the reviewed identity through the existing mapping
   workflow; do not infer a CIK.

4. Prepare the immutable run manifest and checkpoints. This writes only the
   operational run ledger and makes no SEC requests:

   ```powershell
   $prepared = Join-Path $reportDir ('prepared-' + [guid]::NewGuid().ToString('N') + '.json')
   npm run db:bootstrap-fundamentals -- prepare `
     --target-environment rehearsal `
     --report $prepared
   $run = Get-Content -Raw $prepared | ConvertFrom-Json
   $run.run_id
   $run.total_checkpoints
   ```

   Save the displayed `run_id` in the private operator record. The prepared scope
   freezes the mapping-set hash and importer/provider versions. If a mapping changes,
   the run is blocked and a new preview and run are required.

5. Run in bounded resumable invocations. Choose a fresh report path each time because
   report files are create-only:

   ```powershell
   $runId = '<run-id-from-prepare>'
   $runReport = Join-Path $reportDir ('run-' + [guid]::NewGuid().ToString('N') + '.json')
   npm run db:bootstrap-fundamentals -- run `
     --run-id $runId `
     --target-environment rehearsal `
     --max-checkpoints 5 `
     --report $runReport
   $runExit = $LASTEXITCODE
   $runResult = Get-Content -Raw $runReport | ConvertFrom-Json
   $runResult | Select-Object status, pending_checkpoints, retryable_checkpoints, failed_checkpoints
   ```

   If `pending_checkpoints` is positive, invoke `resume` with the same run ID and a
   new report path. Respect `next_attempt_at` for retryable failures. A CLI exit code
   of 2 requires review; do not treat `PARTIAL` as a successful complete bootstrap.
   A worker interruption leaves the checkpoint resumable and records
   `WORKER_INTERRUPTED` in its failure history. Each canonical importer receipt and
   checkpoint commit together, so a retry cannot leave a half-imported checkpoint.

6. Inspect and reconcile after work finishes:

   ```powershell
   $statusReport = Join-Path $reportDir ('status-' + [guid]::NewGuid().ToString('N') + '.json')
   npm run db:bootstrap-fundamentals -- status `
     --run-id $runId `
     --target-environment rehearsal `
     --report $statusReport
   $reconcileReport = Join-Path $reportDir ('reconcile-' + [guid]::NewGuid().ToString('N') + '.json')
   npm run db:bootstrap-fundamentals -- reconcile `
     --run-id $runId `
     --target-environment rehearsal `
     --report $reconcileReport
   $reconciliation = Get-Content -Raw $reconcileReport | ConvertFrom-Json
   $reconciliation.reconciliation.status
   $reconciliation.coverage.fundamental_statement_coverage
   $reconciliation.coverage.fundamental_period_coverage
   $reconciliation.coverage.accession_reference_coverage
   ```

   Require `MATCHED` for stored batches and review all coverage flags, unavailable
   checkpoints, unmapped companies, zero counts, unsupported forms/concepts, and
   amendment links. `MATCHED` is an integrity result; it is not approval to activate
   the dataset or evidence that every expected issuer/period is covered.

7. Clear the SEC contact from the current shell when finished:

   ```powershell
   Remove-Item Env:\SEC_USER_AGENT
   ```

The PowerShell syntax above uses features available in Windows PowerShell 5.1 and
PowerShell 7. It has not been executed on Windows in this development environment.
Never copy environment values or report contents into issue comments or chat.

## Recovery and known limits

Use `resume` for retryable failures or interrupted pending work. Do not retry
`BLOCKED` mapping/schema/authorization errors until the cause is corrected and a
fresh preview is reviewed. Once attempts are exhausted, prepare a new run after
review. SEC Company Facts is a current historical response: its retrieval and
recording timestamps describe this import and cannot recreate earlier application
knowledge times. SEC's filing index may return unsupported forms and comparative
facts; those are surfaced in review counts rather than silently treated as complete.
The currently supported standard concept allowlist is intentionally narrow and
non-US/regulator coverage is incomplete. Provider availability is not inferred from
zero rows. No run should trigger scheduled ingestion or model recalculation.
