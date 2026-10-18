-- Aggregate-only inventory query. Run from a read-only PostgreSQL role.
-- It returns table names and row counts only; it never selects row values or IDs.
BEGIN TRANSACTION READ ONLY;

WITH counts AS (
    SELECT 'companies'::text AS domain, count(*)::bigint AS row_count FROM public.companies
    UNION ALL SELECT 'securities', count(*) FROM public.securities
    UNION ALL SELECT 'listings', count(*) FROM public.listings
    UNION ALL SELECT 'portfolios', count(*) FROM public.portfolios
    UNION ALL SELECT 'holding_snapshots', count(*) FROM public.holding_snapshots
    UNION ALL SELECT 'holding_positions', count(*) FROM public.holding_positions
    UNION ALL SELECT 'holding_cash_positions', count(*) FROM public.holding_cash_positions
    UNION ALL SELECT 'target_allocation_revisions', count(*) FROM public.target_allocation_revisions
    UNION ALL SELECT 'target_allocations', count(*) FROM public.target_allocations
    UNION ALL SELECT 'lifecycle_events', count(*) FROM public.lifecycle_events
    UNION ALL SELECT 'score_assessments', count(*) FROM public.score_assessments
    UNION ALL SELECT 'ranking_runs', count(*) FROM public.ranking_runs
    UNION ALL SELECT 'ranking_entries', count(*) FROM public.ranking_entries
    UNION ALL SELECT 'price_observations', count(*) FROM public.price_observations
    UNION ALL SELECT 'fx_observations', count(*) FROM public.fx_observations
    UNION ALL SELECT 'reported_fundamental_observations', count(*) FROM public.reported_fundamental_observations
    UNION ALL SELECT 'model_output_snapshots', count(*) FROM public.model_output_snapshots
    UNION ALL SELECT 'financial_models', count(*) FROM public.financial_models
    UNION ALL SELECT 'financial_model_revisions', count(*) FROM public.financial_model_revisions
    UNION ALL SELECT 'research_revisions', count(*) FROM public.research_revisions
    UNION ALL SELECT 'research_assessments', count(*) FROM public.research_assessments
    UNION ALL SELECT 'research_evidence', count(*) FROM public.research_evidence
    UNION ALL SELECT 'investment_thesis_revisions', count(*) FROM public.investment_thesis_revisions
    UNION ALL SELECT 'investment_thesis_evidence', count(*) FROM public.investment_thesis_evidence
    UNION ALL SELECT 'risk_assessment_revisions', count(*) FROM public.risk_assessment_revisions
    UNION ALL SELECT 'source_documents', count(*) FROM public.source_documents
    UNION ALL SELECT 'external_raw_payloads', count(*) FROM public.external_raw_payloads
    UNION ALL SELECT 'external_ingestion_runs', count(*) FROM public.external_ingestion_runs
    UNION ALL SELECT 'external_ingestion_attempts', count(*) FROM public.external_ingestion_attempts
    UNION ALL SELECT 'legacy_import_batches', count(*) FROM public.legacy_import_batches
    UNION ALL SELECT 'market_data_batches', count(*) FROM public.market_data_batches
    UNION ALL SELECT 'model_output_import_batches', count(*) FROM public.model_output_import_batches
)
SELECT domain, row_count FROM counts ORDER BY domain;

COMMIT;
