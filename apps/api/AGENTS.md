# API Agent Notes

Follow the root `AGENTS.md` and relevant domain documentation.

This file contains only API-specific guidance.

## Role

FastAPI owns validated domain behavior and deterministic calculations.

The API is responsible for:

- canonical domain operations
- financial-model calculations
- market/fundamental/estimate normalization
- portfolio analytics
- ranking/signal derivation
- revision/history workflows
- external-data ingestion and reconciliation

PostgreSQL is canonical for migrated domains.

## External data

Use the flow:

External provider → raw provider record → normalization → canonical observation → derived analytics.

Provider schemas must not become domain schemas.

Preserve provenance and point-in-time semantics.

Prefer multiple complementary provider adapters over dependence on one vendor.

Never silently blend conflicting observations.

Source precedence belongs to the relevant domain.

For consensus estimates, preserve provider continuity rather than synthesizing values across providers.

## Financial models

The application owns accepted canonical model state and revision history.

Google Sheets is a supported external editor through the canonical model contract.

Web and Sheets edits must use the same revision semantics.

Never silently overwrite a newer model revision.

Keep methodology-specific calculations separate where economics differ.

Standardize interfaces, not valuation methodology.

## Time and history

Where relevant distinguish:

- economic/reporting period
- effective/publication time
- observed/retrieved time
- recorded time

Historical queries must avoid look-ahead bias.

Never fabricate history.

## Implementation

Prefer explicit domain modules and deterministic services over generic frameworks.

Do not build:

- generic rule engines
- generic event sourcing
- provider-specific domain models

unless a demonstrated requirement justifies them.

Financial and portfolio calculations require deterministic tests and, where applicable, workbook/reference parity tests.