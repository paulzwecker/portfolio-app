# Model-only canonical identity bootstrap

## Scope

This path prepares canonical identity for the single supported
`financial-model-package-v1` source model `P-GOOGL`. It does not require or parse
the Portfolio workbook. The financial-model package remains an unaccepted
proposal; this operation does not create or accept a financial-model revision.

The explicit mapping is defined in
`apps/api/src/portfolio_api/model_identity_bootstrap.py`:

| Source model | Canonical company  | Security     | Exact listing  | Currency |
| ------------ | ------------------ | ------------ | -------------- | -------- |
| `P-GOOGL`    | Alphabet (`GOOGL`) | Common stock | `NASDAQ:GOOGL` | USD      |

The package contract is checked against every identity field in the mapping,
and the existing package schema, native calculation and parity validation must
pass before the database is inspected. Ticker/provider-symbol identity is not
used by itself to choose a company. No provider identifier is created by this
bootstrap.

## Canonical writes and stable identity

When absent, the operation creates exactly:

- one `Company` named Alphabet, with `reporting_currency` left unset;
- one `Security` associated with that company, with type `COMMON_STOCK` and no
  inferred share-class attribute;
- one `Listing` for `NASDAQ:GOOGL`, currency USD, linked to that security;
- one immutable `ModelIdentityBootstrapReceipt` containing the mapping and
  package digests, source identity/provenance, observed/recorded times and
  canonical IDs.

Company, security and listing IDs reuse the canonical workbook import's UUIDv5
keys (`company:GOOGL`, `security:GOOGL`, `listing:NASDAQ:GOOGL`). Existing rows
are reused only when their deterministic IDs and full identity fields match.
A same-name company or same venue/ticker under another ID is a conflict and
requires identity reconciliation; it is never silently merged. Concurrent
applications serialize on a transaction-scoped advisory lock. The receipt and
identity inserts share the caller's transaction, so rollback removes all of
them. Replaying the same package and mapping returns `ALREADY_APPLIED`.

The operation creates no lifecycle event/current lifecycle, portfolio,
holdings, cash, target, score, research record, ranking, provider mapping or
model revision. Model currency remains distinct from company reporting
currency. The listing is the exact basis used by the model package.

## Read-only preview and explicit apply

Inspect/validate the private package first with the existing package commands.
Use its exact run ID and payload hash; do not copy package contents into the
repository or task logs.

```powershell
$store = Join-Path $env:LOCALAPPDATA 'PortfolioResearch\workbook-snapshots'
$runId = '<private-package-run-id>'
$packageHash = '<64-character-package-sha256>'

npm run db:bootstrap-model-identity -- preview `
  --store $store `
  --run-id $runId `
  --payload-sha256 $packageHash `
  --target-environment production
```

Preview uses the shared read-only target guard with an explicit read scope of
`companies`, `securities` and `listings`. It checks the exact configured target,
Neon control-plane identity, TLS, role, read-only session and one of the exact
reviewed canonical schema heads: `6c2eaf0b8147`, `b16d4f8a2c91`,
`c17a0b9d4e62`, `3e5c8a1d7b42` or `9f2a6d4c81b7`. The final migration adds
the agent-proposal table and does not alter Company/Security/Listing identity
tables. The preview does not require unrelated later tables to preview identity.
If the receipt table is not present, the preview reports
`receipt_schema_available=false` and
`apply_available=false`; it still shows the planned receipt as a migration
dependency. No records are inserted during preview. A target, schema, or
identity preflight failure is a hard stop.

Apply is implemented for isolated test/rehearsal and later separately
authorized operations, but was not run as part of this milestone. It requires
the same stored hash twice, an explicit confirmation flag, the shared
write-target guard, and the guard's normal target-specific authorization. A
production apply additionally requires temporary production authorization and
the existing interactive target phrase:

```powershell
npm run db:bootstrap-model-identity -- apply `
  --store $store `
  --run-id $runId `
  --payload-sha256 $packageHash `
  --expected-payload-sha256 $packageHash `
  --approve-payload-sha256 $packageHash `
  --confirm-explicit-identity-bootstrap `
  --target-environment production
```

Do not set production authorization or execute this command without a separate
operator approval for the exact package hash and target. Database migrations
are also separate; this change adds migration
`3e5c8a1d7b42` after `c17a0b9d4e62` for the immutable receipt table. No
migration was run against Neon. Apply uses the normal full-schema preflight and
is unavailable until the receipt migration and all required application
migrations are deployed.

## Model-package association

The existing package preview remains responsible for checking the exact
company/security/listing chain and method identity before model acceptance.
After the identity bootstrap is applied, the package can be previewed through
the existing `db:financial-model-package preview` command. Its result is
`READY_FOR_EXPLICIT_ACCEPTANCE`; association alone does not accept it. The
accepted model and its revisions remain governed by the existing explicit
acceptance workflow.
