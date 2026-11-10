# Frozen integration boundary: SEC provenance

Acceptance criteria, frozen 2026-11-09:

- Company research exposes issuer mapping changes and unverified SEC facts/filings;
  historical citations and lifecycle are bounded by known evidence times.
- Existing accepted financial state and provider/source truth remain unchanged.
- Incomplete Sheets publication remains unavailable at its shared external-write
  boundary regardless of configuration; read-only research and imports are unaffected.
- Relevant unit, integration, contract, security, desktop/mobile and migration
  compatibility checks pass with independent review. No migration is introduced.
- One PR records actual verification and release requirements. Production ingestion,
  deployment and financial decisions require separate owner authorization.

Deferred: refresh-job ownership and expanded Operations status, Sheets publication
recovery and direct ownership, new provider coverage, and production ingestion
activation. Their complete history remains on `codex/sec-coverage-readiness`.
Next product milestone: bounded historical prices/FX and useful source-backed
fundamentals in the live application.
