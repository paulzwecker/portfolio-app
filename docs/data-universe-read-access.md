# Data & Universe Steward — scoped company-context read access

## Purpose

Allow one Data & Universe Steward to read accepted company operating evidence
without handing it the broad application proxy token, portfolio holdings/targets,
investment thesis/model content or SQL credentials.

This is a **code-only, disabled-by-default** capability on draft PR #42. It is
not connected to a live external agent and cannot initiate refresh, proposals,
model acceptance or production changes.

## Exact permission

- Method: `GET` only.
- Path: `/v1/companies/{company_id}/agent-context` only, exact route match.
- Company scope: an explicit allowlist of 1–25 canonical PostgreSQL company
  UUIDs, checked before any database access. An unlisted company returns 404.
- Allowed response: canonical company/security/listing identity; bounded KPI
  definitions and observations; issued management guidance; selected-provider
  consensus with original source/period/quality metadata.
- Excluded response: portfolio and target identifiers, holdings/market values,
  research/thesis details, accepted native models and imported model outputs.
  These sections return `UNSUPPORTED` and empty/null values; no expensive
  portfolio or model read is performed. General resource links are omitted.
- No other API route or method is reachable with this token. No generic company
  listing, arbitrary SQL or write access is added.

General application proxy consumers retain their existing full
`CompanyAgentContextV1` response. `X-Data-Universe-Read-Token` is evaluated
independently even in development; an invalid scoped header cannot fall back
to a concurrently supplied broad token.

## Operator configuration (do not enable automatically)

Set in a private, approved environment secret store:

```text
DATA_UNIVERSE_READ_ENABLED=true
DATA_UNIVERSE_READ_TOKEN=<unique 32+ character secret>
DATA_UNIVERSE_READ_COMPANY_IDS=<company-uuid-1>,<company-uuid-2>
```

The secret must be distinct from the API proxy and both model/observation
proposal agent/reviewer credentials. `DATA_UNIVERSE_READ_ENABLED` defaults
to `false`. Empty/invalid/duplicate/noncanonical UUIDs and missing token
configuration fail validation. No values are placed in tracked env files,
Sheets or agent prompts. Credential provision and hosted activation require
separate operator authorization; deploying code does not enable access.

Example (after an approved activation, without showing the secret):

```sh
curl -H "X-Data-Universe-Read-Token: $DATA_UNIVERSE_READ_TOKEN" \
  "https://<api-host>/v1/companies/<allowed-canonical-company-uuid>/agent-context"
```

The endpoint uses the existing read-only PostgreSQL session. Authenticated
responses are marked `Cache-Control: no-store`. Denials occur before the
database dependency. Disabled, invalid-token, outside-allowlist, write-method,
sibling-path and portfolio-query cases have focused tests.

## Shadow pilot

First read one manually approved company UUID and compare the returned
KPI/guidance source references to the public issuer disclosure. Existing
Uber Q3 2026 example values live only in an isolated fixture; they do not
establish an active agent or accepted real-company observations.

The next step is a real **read-only shadow agent** that identifies a supported
metric gap and prepares a typed proposal offline. Do not supply it an
observation-acceptance token or permit production publication. Only expand
read scopes (filings/financial statements) after demonstrating the need and
reviewing those resource boundaries.

## Operator-run shadow comparison

After an owner-approved company allowlist and token are configured, the
`data_universe_shadow` CLI can fetch this exact restricted context and compare
it with a separately reviewed primary-source evidence pack. It prepares local
typed drafts only; it does not make API proposal submissions or accepted writes.

See [data-universe-shadow-pilot](data-universe-shadow-pilot.md).
