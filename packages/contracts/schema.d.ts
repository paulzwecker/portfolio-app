export interface paths {
    "/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Liveness */
        get: operations["liveness_health_live_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Readiness */
        get: operations["readiness_health_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/canonical-financial-models/{model_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Extended Financial Model */
        get: operations["get_extended_financial_model_v1_canonical_financial_models__model_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/canonical-financial-models/{model_id}/contract": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Additional Model Contract */
        get: operations["get_additional_model_contract_v1_canonical_financial_models__model_id__contract_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/canonical-financial-models/{model_id}/contract/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Additional Model Contract Import */
        post: operations["post_additional_model_contract_import_v1_canonical_financial_models__model_id__contract_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/canonical-financial-models/{model_id}/contract/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Additional Model Contract Preview */
        post: operations["post_additional_model_contract_preview_v1_canonical_financial_models__model_id__contract_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/canonical-financial-models/{model_id}/owner-cash-flow/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Owner Cash Flow Revision */
        post: operations["post_owner_cash_flow_revision_v1_canonical_financial_models__model_id__owner_cash_flow_revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/canonical-financial-models/{model_id}/owner-cash-flow/revisions/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Owner Cash Flow Revision Preview */
        post: operations["post_owner_cash_flow_revision_preview_v1_canonical_financial_models__model_id__owner_cash_flow_revisions_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/canonical-financial-models/{model_id}/residual-income/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Residual Income Revision */
        post: operations["post_residual_income_revision_v1_canonical_financial_models__model_id__residual_income_revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/canonical-financial-models/{model_id}/residual-income/revisions/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Residual Income Revision Preview */
        post: operations["post_residual_income_revision_preview_v1_canonical_financial_models__model_id__residual_income_revisions_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/canonical-financial-models/{model_id}/revisions/{revision_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Extended Financial Model Revision */
        get: operations["get_extended_financial_model_revision_v1_canonical_financial_models__model_id__revisions__revision_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Company */
        post: operations["post_company_v1_companies_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company */
        get: operations["get_company_v1_companies__company_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/canonical-financial-models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company Extended Financial Models */
        get: operations["get_company_extended_financial_models_v1_companies__company_id__canonical_financial_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/canonical-financial-models/owner-cash-flow": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Owner Cash Flow Model */
        post: operations["post_owner_cash_flow_model_v1_companies__company_id__canonical_financial_models_owner_cash_flow_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/canonical-financial-models/owner-cash-flow/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Owner Cash Flow Initial Preview */
        post: operations["post_owner_cash_flow_initial_preview_v1_companies__company_id__canonical_financial_models_owner_cash_flow_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/canonical-financial-models/residual-income": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Residual Income Model */
        post: operations["post_residual_income_model_v1_companies__company_id__canonical_financial_models_residual_income_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/canonical-financial-models/residual-income/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Residual Income Initial Preview */
        post: operations["post_residual_income_initial_preview_v1_companies__company_id__canonical_financial_models_residual_income_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/consensus-estimates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company Consensus Estimates */
        get: operations["get_company_consensus_estimates_v1_companies__company_id__consensus_estimates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/financial-models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company Financial Models */
        get: operations["get_company_financial_models_v1_companies__company_id__financial_models_get"];
        put?: never;
        /** Post Company Financial Model */
        post: operations["post_company_financial_model_v1_companies__company_id__financial_models_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/financial-models/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Financial Model Initial Calculation Preview */
        post: operations["post_financial_model_initial_calculation_preview_v1_companies__company_id__financial_models_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/lifecycle-transitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Transition */
        post: operations["post_transition_v1_companies__company_id__lifecycle_transitions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/market-data": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company Market Data */
        get: operations["get_company_market_data_v1_companies__company_id__market_data_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/model-migration-status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company Model Migration Status */
        get: operations["get_company_model_migration_status_v1_companies__company_id__model_migration_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/model-outputs/current": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Current Model Outputs */
        get: operations["get_current_model_outputs_v1_companies__company_id__model_outputs_current_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/model-outputs/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Model Output History */
        get: operations["get_model_output_history_v1_companies__company_id__model_outputs_history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/rankings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company Rankings */
        get: operations["get_company_rankings_v1_companies__company_id__rankings_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/reported-fundamentals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company Reported Fundamentals */
        get: operations["get_company_reported_fundamentals_v1_companies__company_id__reported_fundamentals_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/score-assessments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Score Assessment */
        post: operations["post_score_assessment_v1_companies__company_id__score_assessments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/scores/current": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Current Scores */
        get: operations["get_current_scores_v1_companies__company_id__scores_current_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/scores/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Score History */
        get: operations["get_score_history_v1_companies__company_id__scores_history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/securities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Security */
        post: operations["post_security_v1_companies__company_id__securities_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/source-documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company Source Documents */
        get: operations["get_company_source_documents_v1_companies__company_id__source_documents_get"];
        put?: never;
        /** Post Company Source Document */
        post: operations["post_company_source_document_v1_companies__company_id__source_documents_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/financial-models/{model_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Financial Model */
        get: operations["get_financial_model_v1_financial_models__model_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/financial-models/{model_id}/contract": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Financial Model Contract */
        get: operations["get_financial_model_contract_v1_financial_models__model_id__contract_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/financial-models/{model_id}/contract/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Financial Model Contract Import */
        post: operations["post_financial_model_contract_import_v1_financial_models__model_id__contract_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/financial-models/{model_id}/contract/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Financial Model Contract Preview */
        post: operations["post_financial_model_contract_preview_v1_financial_models__model_id__contract_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/financial-models/{model_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Financial Model History */
        get: operations["get_financial_model_history_v1_financial_models__model_id__revisions_get"];
        put?: never;
        /** Post Financial Model Revision */
        post: operations["post_financial_model_revision_v1_financial_models__model_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/financial-models/{model_id}/revisions/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Financial Model Revision Calculation Preview */
        post: operations["post_financial_model_revision_calculation_preview_v1_financial_models__model_id__revisions_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/financial-models/{model_id}/revisions/{revision_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Financial Model Revision */
        get: operations["get_financial_model_revision_v1_financial_models__model_id__revisions__revision_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/fx-observations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Fx Observations */
        get: operations["get_fx_observations_v1_fx_observations_get"];
        put?: never;
        /** Post Fx Observation */
        post: operations["post_fx_observation_v1_fx_observations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/listings/{listing_id}/corporate-actions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Listing Corporate Actions */
        get: operations["get_listing_corporate_actions_v1_listings__listing_id__corporate_actions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/listings/{listing_id}/market-data": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Listing Market Data */
        get: operations["get_listing_market_data_v1_listings__listing_id__market_data_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/portfolios": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Portfolios */
        get: operations["get_portfolios_v1_portfolios_get"];
        put?: never;
        /** Post Portfolio */
        post: operations["post_portfolio_v1_portfolios_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/portfolios/{portfolio_id}/holding-snapshots": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Snapshots */
        get: operations["get_snapshots_v1_portfolios__portfolio_id__holding_snapshots_get"];
        put?: never;
        /** Post Snapshot */
        post: operations["post_snapshot_v1_portfolios__portfolio_id__holding_snapshots_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/portfolios/{portfolio_id}/overview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Overview */
        get: operations["get_overview_v1_portfolios__portfolio_id__overview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/portfolios/{portfolio_id}/target-revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Targets */
        get: operations["get_targets_v1_portfolios__portfolio_id__target_revisions_get"];
        put?: never;
        /** Post Targets */
        post: operations["post_targets_v1_portfolios__portfolio_id__target_revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/portfolios/{portfolio_id}/target-revisions/{revision_id}/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Accept */
        post: operations["post_accept_v1_portfolios__portfolio_id__target_revisions__revision_id__accept_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/ranking-definitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Ranking Definitions */
        get: operations["get_ranking_definitions_v1_ranking_definitions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/ranking-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Ranking Runs */
        get: operations["get_ranking_runs_v1_ranking_runs_get"];
        put?: never;
        /** Post Ranking Run */
        post: operations["post_ranking_run_v1_ranking_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/ranking-runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Ranking Run */
        get: operations["get_ranking_run_v1_ranking_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/reported-fundamental-definitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Reported Fundamental Definitions */
        get: operations["get_reported_fundamental_definitions_v1_reported_fundamental_definitions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/score-definitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Score Definitions */
        get: operations["get_score_definitions_v1_score_definitions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/securities/{security_id}/listings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Listing */
        post: operations["post_listing_v1_securities__security_id__listings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/universe": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Universe */
        get: operations["get_universe_v1_universe_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/universe/market-summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Universe Market Summary */
        get: operations["get_universe_market_summary_v1_universe_market_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/universe/model-output-summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Universe Model Output Summary */
        get: operations["get_universe_model_output_summary_v1_universe_model_output_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/universe/ranking-summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Universe Ranking Summary */
        get: operations["get_universe_ranking_summary_v1_universe_ranking_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/universe/score-summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Universe Score Summary */
        get: operations["get_universe_score_summary_v1_universe_score_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * Actor
         * @enum {string}
         */
        Actor: "LOCAL_USER" | "SYSTEM" | "IMPORT";
        /** AdditionalModelContractCandidate */
        "AdditionalModelContractCandidate-Input": {
            /**
             * Actor
             * @default IMPORT
             * @constant
             */
            actor: "IMPORT";
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            owner_cash_flow?: components["schemas"]["OwnerCashFlowInput-Input"] | null;
            /** Rationale */
            rationale?: string | null;
            residual_income?: components["schemas"]["ResidualIncomeInput-Input"] | null;
            /** Source */
            source?: string | null;
            /** Source Revision Id */
            source_revision_id: string;
        };
        /** AdditionalModelContractCandidate */
        "AdditionalModelContractCandidate-Output": {
            /**
             * Actor
             * @default IMPORT
             * @constant
             */
            actor: "IMPORT";
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            owner_cash_flow?: components["schemas"]["OwnerCashFlowInput-Output"] | null;
            /** Rationale */
            rationale?: string | null;
            residual_income?: components["schemas"]["ResidualIncomeInput-Output"] | null;
            /** Source */
            source?: string | null;
            /** Source Revision Id */
            source_revision_id: string;
        };
        /** AdditionalModelContractFieldChange */
        AdditionalModelContractFieldChange: {
            /** Path */
            path: string;
            /** Previous */
            previous: string | null;
            /** Proposed */
            proposed: string | null;
        };
        /** AdditionalModelContractImportRead */
        AdditionalModelContractImportRead: {
            model: components["schemas"]["ExtendedFinancialModelRead"];
            /** Revision */
            revision: components["schemas"]["OwnerCashFlowRevisionRead"] | components["schemas"]["ResidualIncomeRevisionRead"];
            /**
             * Status
             * @enum {string}
             */
            status: "IMPORTED" | "ALREADY_IMPORTED";
        };
        /** AdditionalModelContractPreviewRead */
        AdditionalModelContractPreviewRead: {
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            calculated_outputs: components["schemas"]["FinancialModelCalculationOutputsRead"] | null;
            /** Changes */
            changes: components["schemas"]["AdditionalModelContractFieldChange"][];
            current_outputs: components["schemas"]["FinancialModelCalculationOutputsRead"];
            /**
             * Current Revision Id
             * Format: uuid
             */
            current_revision_id: string;
            /** Current Revision Number */
            current_revision_number: number;
            /**
             * Model Id
             * Format: uuid
             */
            model_id: string;
            /** Output Changes */
            output_changes: components["schemas"]["AdditionalModelContractFieldChange"][];
            /** Reason */
            reason: string | null;
            /** Source Revision Id */
            source_revision_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "READY" | "NO_CHANGES" | "RATIONALE_REQUIRED" | "CONFLICT" | "ALREADY_IMPORTED";
        };
        /** AdditionalModelPortableContractV2 */
        "AdditionalModelPortableContractV2-Input": {
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            /** Base Revision Number */
            base_revision_number: number;
            candidate_revision: components["schemas"]["AdditionalModelContractCandidate-Input"];
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Contract Version
             * @default 2.0.0
             * @constant
             */
            contract_version: "2.0.0";
            /**
             * Exported At
             * Format: date-time
             */
            exported_at: string;
            /** Model Currency */
            model_currency: string;
            /**
             * Model Id
             * Format: uuid
             */
            model_id: string;
            /** Model Name */
            model_name: string;
            /**
             * Model Type
             * @enum {string}
             */
            model_type: "OWNER_CASH_FLOW_10Y" | "RESIDUAL_INCOME_10Y_FADE";
            /** Source Model Key */
            source_model_key: string | null;
            /**
             * Valuation Listing Id
             * Format: uuid
             */
            valuation_listing_id: string;
        };
        /** AdditionalModelPortableContractV2 */
        "AdditionalModelPortableContractV2-Output": {
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            /** Base Revision Number */
            base_revision_number: number;
            candidate_revision: components["schemas"]["AdditionalModelContractCandidate-Output"];
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Contract Version
             * @default 2.0.0
             * @constant
             */
            contract_version: "2.0.0";
            /**
             * Exported At
             * Format: date-time
             */
            exported_at: string;
            /** Model Currency */
            model_currency: string;
            /**
             * Model Id
             * Format: uuid
             */
            model_id: string;
            /** Model Name */
            model_name: string;
            /**
             * Model Type
             * @enum {string}
             */
            model_type: "OWNER_CASH_FLOW_10Y" | "RESIDUAL_INCOME_10Y_FADE";
            /** Source Model Key */
            source_model_key: string | null;
            /**
             * Valuation Listing Id
             * Format: uuid
             */
            valuation_listing_id: string;
        };
        /** AllocationInput */
        "AllocationInput-Input": {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Weight */
            weight: number | string;
        };
        /** AllocationInput */
        "AllocationInput-Output": {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Weight */
            weight: string;
        };
        /** CashInput */
        "CashInput-Input": {
            /** Balance */
            balance: (number | string) | null;
            /** Currency */
            currency: string;
        };
        /** CashInput */
        "CashInput-Output": {
            /** Balance */
            balance: string | null;
            /** Currency */
            currency: string;
        };
        /** CashValuation */
        CashValuation: {
            /** Balance */
            balance: string | null;
            /** Base Market Value */
            base_market_value: string | null;
            /** Currency */
            currency: string;
            /**
             * Valuation Status
             * @enum {string}
             */
            valuation_status: "VALUED" | "FX_UNAVAILABLE" | "BALANCE_UNAVAILABLE";
        };
        /** CompanyConsensusEstimatesRead */
        CompanyConsensusEstimatesRead: {
            /** As Of */
            as_of: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Continuity Status
             * @enum {string}
             */
            continuity_status: "PRIMARY_SELECTED" | "FALLBACK_SELECTED" | "PRIMARY_NO_DATA" | "NO_MAPPING" | "AMBIGUOUS_FALLBACK";
            /** Known At */
            known_at: string | null;
            /** Providers */
            providers: components["schemas"]["ConsensusEstimateProviderRead"][];
            /** Selected Provider Id */
            selected_provider_id: string | null;
        };
        /** CompanyCreate */
        CompanyCreate: {
            /** Name */
            name: string;
            /** Reporting Currency */
            reporting_currency?: string | null;
        };
        /** CompanyDetail */
        CompanyDetail: {
            company: components["schemas"]["CompanyRead"];
            holding_snapshot: components["schemas"]["SnapshotRead"] | null;
            /** Lifecycle History */
            lifecycle_history: components["schemas"]["LifecycleEventRead"][];
            /** Listings */
            listings: components["schemas"]["ListingRead"][];
            portfolio: components["schemas"]["PortfolioRead"] | null;
            portfolio_context: components["schemas"]["CompanyPortfolioContext"] | null;
            /** Positions */
            positions: components["schemas"]["HoldingContext"][];
            /** Securities */
            securities: components["schemas"]["SecurityRead"][];
            /** Target Revision Id */
            target_revision_id: string | null;
            /** Target Weight */
            target_weight: string | null;
        };
        /** CompanyFinancialModelMigrationItemRead */
        CompanyFinancialModelMigrationItemRead: {
            /** Blockers */
            blockers: string[];
            /** Canonical Ticker */
            canonical_ticker: string | null;
            /** Company Name */
            company_name: string;
            /**
             * Inventory Status
             * @enum {string}
             */
            inventory_status: "READY_FOR_NATIVE_IMPORT" | "NEEDS_MAPPING" | "UNSUPPORTED_METHOD" | "DATA_CHECK" | "LEGACY_ONLY";
            /** Legacy Return Semantics */
            legacy_return_semantics: string | null;
            /** Lifecycle */
            lifecycle: string;
            /** Methodology Family */
            methodology_family: string;
            /** Model Currency */
            model_currency: string | null;
            /** Model Key */
            model_key: string;
            /** Native Model Id */
            native_model_id: string | null;
            /** Native Revision Number */
            native_revision_number: number | null;
            /** Output Contract Status */
            output_contract_status: string;
            /** Output Snapshot Available */
            output_snapshot_available: boolean;
            /** Outputs Compared */
            outputs_compared: number | null;
            /** Outputs Passed */
            outputs_passed: number | null;
            /** Parity Status */
            parity_status: ("PARITY_PASS" | "PARTIAL_MAPPING" | "DATA_CHECK" | "BLOCKED") | null;
            /** Projections Compared */
            projections_compared: number | null;
            /** Projections Passed */
            projections_passed: number | null;
            /**
             * Representation Status
             * @enum {string}
             */
            representation_status: "NATIVE_EDITABLE" | "NATIVE_WITH_PARITY_ISSUE" | "IMPORTED_OUTPUT_ONLY" | "UNSUPPORTED_LEGACY" | "LEGACY_ONLY" | "NOT_IMPORTED";
        };
        /** CompanyFinancialModelMigrationRead */
        CompanyFinancialModelMigrationRead: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Inventory Available */
            inventory_available: boolean;
            /** Models */
            models: components["schemas"]["CompanyFinancialModelMigrationItemRead"][];
        };
        /** CompanyModelOutputsCurrentRead */
        CompanyModelOutputsCurrentRead: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** History Count */
            history_count: number;
            /** Models */
            models: components["schemas"]["ModelOutputCurrentModelRead"][];
            /**
             * Status
             * @enum {string}
             */
            status: "AVAILABLE" | "PARTIAL" | "NOT_MAPPED" | "NO_CONTRACT" | "DATA_CHECK" | "NO_MODEL";
        };
        /** CompanyPortfolioContext */
        CompanyPortfolioContext: {
            /** Allocation Gap */
            allocation_gap: string | null;
            /**
             * Allocation Status
             * @default PORTFOLIO_TOTAL_UNAVAILABLE
             * @enum {string}
             */
            allocation_status: "VALUED" | "PRICE_COVERAGE_INCOMPLETE" | "FX_UNAVAILABLE" | "PORTFOLIO_TOTAL_UNAVAILABLE";
            company: components["schemas"]["CompanyRead"];
            /** Current Market Currency */
            current_market_currency: string | null;
            /** Current Market Value */
            current_market_value: string | null;
            /** Current Weight */
            current_weight: string | null;
            /** Positions */
            positions: components["schemas"]["HoldingContext"][];
            /** Target Weight */
            target_weight: string | null;
        };
        /** CompanyRankingsRead */
        CompanyRankingsRead: {
            /** Current */
            current: components["schemas"]["RankingCurrentRead"][];
            /** History */
            history: components["schemas"]["RankingHistoryEntry"][];
        };
        /** CompanyRead */
        CompanyRead: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Demo */
            is_demo: boolean;
            lifecycle: components["schemas"]["Lifecycle"] | null;
            /** Lifecycle Event Id */
            lifecycle_event_id: string | null;
            /** Name */
            name: string;
            /** Reporting Currency */
            reporting_currency?: string | null;
        };
        /** CompanyReportedFundamentalsRead */
        CompanyReportedFundamentalsRead: {
            /** As Of */
            as_of: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Coverage */
            coverage: components["schemas"]["ReportedFundamentalCoverageRead"][];
            /** Known At */
            known_at: string | null;
            /** Latest Observed At */
            latest_observed_at: string | null;
            /** Periods */
            periods: components["schemas"]["ReportedFundamentalPeriodRead"][];
            /**
             * Provider Identity Status
             * @enum {string}
             */
            provider_identity_status: "MAPPED" | "UNMAPPED" | "AMBIGUOUS";
            /** Provider Ids */
            provider_ids: string[];
        };
        /** CompanySourceDocumentsRead */
        CompanySourceDocumentsRead: {
            /** As Of */
            as_of: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Documents */
            documents: components["schemas"]["SourceDocumentRead"][];
            /** Known At */
            known_at: string | null;
            /**
             * Sec Identity Status
             * @enum {string}
             */
            sec_identity_status: "MAPPED" | "UNMAPPED" | "AMBIGUOUS";
            /** Source Count */
            source_count: number;
        };
        /** ConsensusEstimateObservationRead */
        ConsensusEstimateObservationRead: {
            /** Analyst Count */
            analyst_count: number | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Currency */
            currency: string | null;
            /**
             * Data Quality
             * @enum {string}
             */
            data_quality: "PASS" | "DATA_CHECK" | "INVALID";
            /** Forecast Period */
            forecast_period: string;
            /** High Value */
            high_value: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Listing Id */
            listing_id: string | null;
            /** Low Value */
            low_value: string | null;
            /**
             * Metric
             * @enum {string}
             */
            metric: "REVENUE" | "EPS";
            /** Observed At */
            observed_at: string | null;
            /** Period End */
            period_end: string | null;
            /**
             * Period Type
             * @enum {string}
             */
            period_type: "ANNUAL" | "QUARTERLY";
            /** Provider Id */
            provider_id: string;
            /**
             * Provider Mapping Id
             * Format: uuid
             */
            provider_mapping_id: string;
            /** Quality Reason */
            quality_reason: string | null;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /**
             * Revision Context
             * @enum {string}
             */
            revision_context: "SNAPSHOT" | "REVISED" | "LEGACY_BASELINE";
            /**
             * Snapshot Date
             * Format: date
             */
            snapshot_date: string;
            /** Source Record Id */
            source_record_id: string;
            /** Source Ref */
            source_ref: string;
            /** Supersedes Observation Id */
            supersedes_observation_id: string | null;
            /** Unit */
            unit: string;
            /** Value */
            value: string;
        };
        /** ConsensusEstimatePeriodRead */
        ConsensusEstimatePeriodRead: {
            /** Currency */
            currency: string | null;
            current_observation: components["schemas"]["ConsensusEstimateObservationRead"] | null;
            /** Forecast Period */
            forecast_period: string;
            /** History */
            history: components["schemas"]["ConsensusEstimateObservationRead"][];
            /**
             * Metric
             * @enum {string}
             */
            metric: "REVENUE" | "EPS";
            /** Period End */
            period_end: string | null;
            /**
             * Period Type
             * @enum {string}
             */
            period_type: "ANNUAL" | "QUARTERLY";
            /** Unit */
            unit: string;
        };
        /** ConsensusEstimateProviderRead */
        ConsensusEstimateProviderRead: {
            /** Currency */
            currency: string | null;
            /** Currency Evidence Source */
            currency_evidence_source: string | null;
            /**
             * Effective From
             * Format: date-time
             */
            effective_from: string;
            /**
             * Freshness
             * @enum {string}
             */
            freshness: "FRESH" | "STALE" | "DATA_CHECK" | "NO_DATA";
            /** Identity Evidence Source */
            identity_evidence_source: string;
            /** Latest Observed At */
            latest_observed_at: string | null;
            /** Latest Snapshot Date */
            latest_snapshot_date: string | null;
            /**
             * Mapping Status
             * @enum {string}
             */
            mapping_status: "SELECTED" | "ALTERNATE" | "AMBIGUOUS";
            /** Missing Metrics */
            missing_metrics: ("REVENUE" | "EPS")[];
            /** Observation Count */
            observation_count: number;
            /** Periods */
            periods: components["schemas"]["ConsensusEstimatePeriodRead"][];
            /** Priority */
            priority: number;
            /** Provider Id */
            provider_id: string;
            /** Provider Symbol */
            provider_symbol: string;
            /**
             * Role
             * @enum {string}
             */
            role: "PRIMARY" | "FALLBACK";
            /** Selected */
            selected: boolean;
        };
        /** CorporateActionRead */
        CorporateActionRead: {
            /** Action Type */
            action_type: string;
            /** Cash Amount */
            cash_amount: string | null;
            /** Cash Currency */
            cash_currency: string | null;
            /**
             * Effective Date
             * Format: date-time
             */
            effective_date: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Listing Id
             * Format: uuid
             */
            listing_id: string;
            /** Notes */
            notes: string | null;
            /** Observed At */
            observed_at: string | null;
            /** Provider */
            provider: string;
            /** Provider Cash Amount */
            provider_cash_amount: string | null;
            /** Provider Cash Currency */
            provider_cash_currency: string | null;
            /** Ratio After */
            ratio_after: string | null;
            /** Ratio Before */
            ratio_before: string | null;
            /** Source Action Id */
            source_action_id: string;
            /** Source Url */
            source_url: string | null;
            /** Verified */
            verified: boolean;
        };
        /** DcfOperatingBase */
        "DcfOperatingBase-Input": {
            /** Base Capex To Revenue */
            base_capex_to_revenue: number | string;
            /** Base Da To Revenue */
            base_da_to_revenue: number | string;
            /** Base Ebit Margin */
            base_ebit_margin: number | string;
            /** Base Nwc To Revenue */
            base_nwc_to_revenue: number | string;
            /** Base Revenue */
            base_revenue: number | string;
            /** Base Tax Rate */
            base_tax_rate: number | string;
            /** Diluted Shares */
            diluted_shares: number | string;
            /** Net Cash Debt */
            net_cash_debt: number | string;
        };
        /** DcfOperatingBase */
        "DcfOperatingBase-Output": {
            /** Base Capex To Revenue */
            base_capex_to_revenue: string;
            /** Base Da To Revenue */
            base_da_to_revenue: string;
            /** Base Ebit Margin */
            base_ebit_margin: string;
            /** Base Nwc To Revenue */
            base_nwc_to_revenue: string;
            /** Base Revenue */
            base_revenue: string;
            /** Base Tax Rate */
            base_tax_rate: string;
            /** Diluted Shares */
            diluted_shares: string;
            /** Net Cash Debt */
            net_cash_debt: string;
        };
        /** DcfOperatingBaseRead */
        DcfOperatingBaseRead: {
            /** Base Capex To Revenue */
            base_capex_to_revenue: string;
            /** Base Da To Revenue */
            base_da_to_revenue: string;
            /** Base Ebit Margin */
            base_ebit_margin: string;
            /** Base Nwc To Revenue */
            base_nwc_to_revenue: string;
            /** Base Revenue */
            base_revenue: string;
            /** Base Tax Rate */
            base_tax_rate: string;
            /** Diluted Shares */
            diluted_shares: string;
            /** Net Cash Debt */
            net_cash_debt: string;
        };
        /** DcfProjectionCalculationPreviewRead */
        DcfProjectionCalculationPreviewRead: {
            /** Capex */
            capex: string | null;
            /** Change In Nwc */
            change_in_nwc: string | null;
            /** Depreciation Amortization */
            depreciation_amortization: string | null;
            /** Discount Factor */
            discount_factor: string;
            /** Discount Rate */
            discount_rate: string;
            /** Ebit */
            ebit: string | null;
            /** Forecast Year */
            forecast_year: number;
            /** Net Working Capital */
            net_working_capital: string | null;
            /** Nopat */
            nopat: string | null;
            /** Present Value Ufcf */
            present_value_ufcf: string;
            /** Revenue */
            revenue: string | null;
            /** Revenue Growth */
            revenue_growth: string;
            scenario: components["schemas"]["DcfScenario"];
            /** Terminal Value */
            terminal_value: string | null;
            /** Unlevered Free Cash Flow */
            unlevered_free_cash_flow: string;
        };
        /** DcfProjectionRead */
        "DcfProjectionRead-Input": {
            /** Capex */
            capex: (number | string) | null;
            /** Change In Nwc */
            change_in_nwc: (number | string) | null;
            /** Depreciation Amortization */
            depreciation_amortization: (number | string) | null;
            /** Discount Factor */
            discount_factor: number | string;
            /** Discount Rate */
            discount_rate: number | string;
            /** Ebit */
            ebit: (number | string) | null;
            /** Forecast Year */
            forecast_year: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Net Working Capital */
            net_working_capital: (number | string) | null;
            /** Nopat */
            nopat: (number | string) | null;
            /** Present Value Ufcf */
            present_value_ufcf: number | string;
            /** Revenue */
            revenue: (number | string) | null;
            /** Revenue Growth */
            revenue_growth: number | string;
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            /** Terminal Value */
            terminal_value: (number | string) | null;
            /** Unlevered Free Cash Flow */
            unlevered_free_cash_flow: number | string;
        };
        /** DcfProjectionRead */
        "DcfProjectionRead-Output": {
            /** Capex */
            capex: string | null;
            /** Change In Nwc */
            change_in_nwc: string | null;
            /** Depreciation Amortization */
            depreciation_amortization: string | null;
            /** Discount Factor */
            discount_factor: string;
            /** Discount Rate */
            discount_rate: string;
            /** Ebit */
            ebit: string | null;
            /** Forecast Year */
            forecast_year: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Net Working Capital */
            net_working_capital: string | null;
            /** Nopat */
            nopat: string | null;
            /** Present Value Ufcf */
            present_value_ufcf: string;
            /** Revenue */
            revenue: string | null;
            /** Revenue Growth */
            revenue_growth: string;
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            /** Terminal Value */
            terminal_value: string | null;
            /** Unlevered Free Cash Flow */
            unlevered_free_cash_flow: string;
        };
        /**
         * DcfScenario
         * @enum {string}
         */
        DcfScenario: "BEAR" | "BASE" | "BULL";
        /** DcfScenarioInput */
        "DcfScenarioInput-Input": {
            /** Probability */
            probability: number | string;
            /** Rationale */
            rationale: string;
            scenario: components["schemas"]["DcfScenario"];
            /** Terminal Growth */
            terminal_growth: number | string;
            /** Year10 Ufcf Growth */
            year10_ufcf_growth: number | string;
            /** Years */
            years: components["schemas"]["DcfYearAssumptionInput-Input"][];
        };
        /** DcfScenarioInput */
        "DcfScenarioInput-Output": {
            /** Probability */
            probability: string;
            /** Rationale */
            rationale: string;
            scenario: components["schemas"]["DcfScenario"];
            /** Terminal Growth */
            terminal_growth: string;
            /** Year10 Ufcf Growth */
            year10_ufcf_growth: string;
            /** Years */
            years: components["schemas"]["DcfYearAssumptionInput-Output"][];
        };
        /** DcfScenarioRead */
        DcfScenarioRead: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Probability */
            probability: string;
            /** Rationale */
            rationale: string;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            scenario: components["schemas"]["DcfScenario"];
            /** Terminal Growth */
            terminal_growth: string;
            /** Year10 Ufcf Growth */
            year10_ufcf_growth: string;
            /** Years */
            years: components["schemas"]["DcfYearAssumptionRead"][];
        };
        /** DcfYearAssumptionInput */
        "DcfYearAssumptionInput-Input": {
            /** Capex To Revenue */
            capex_to_revenue: number | string;
            /** Da To Revenue */
            da_to_revenue: number | string;
            /** Discount Rate */
            discount_rate: number | string;
            /** Ebit Margin */
            ebit_margin: number | string;
            /** Forecast Year */
            forecast_year: number;
            /** Nwc To Revenue */
            nwc_to_revenue: number | string;
            /** Revenue Growth */
            revenue_growth: number | string;
            /** Tax Rate */
            tax_rate: number | string;
        };
        /** DcfYearAssumptionInput */
        "DcfYearAssumptionInput-Output": {
            /** Capex To Revenue */
            capex_to_revenue: string;
            /** Da To Revenue */
            da_to_revenue: string;
            /** Discount Rate */
            discount_rate: string;
            /** Ebit Margin */
            ebit_margin: string;
            /** Forecast Year */
            forecast_year: number;
            /** Nwc To Revenue */
            nwc_to_revenue: string;
            /** Revenue Growth */
            revenue_growth: string;
            /** Tax Rate */
            tax_rate: string;
        };
        /** DcfYearAssumptionRead */
        DcfYearAssumptionRead: {
            /** Capex To Revenue */
            capex_to_revenue: string;
            /** Da To Revenue */
            da_to_revenue: string;
            /** Discount Rate */
            discount_rate: string;
            /** Ebit Margin */
            ebit_margin: string;
            /** Forecast Year */
            forecast_year: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Nwc To Revenue */
            nwc_to_revenue: string;
            /** Revenue Growth */
            revenue_growth: string;
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            /** Tax Rate */
            tax_rate: string;
        };
        /** ExtendedFinancialModelRead */
        ExtendedFinancialModelRead: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Current Revision */
            current_revision: components["schemas"]["OwnerCashFlowRevisionRead"] | components["schemas"]["ResidualIncomeRevisionRead"];
            /**
             * Current Revision Id
             * Format: uuid
             */
            current_revision_id: string;
            /** History */
            history: components["schemas"]["FinancialModelRevisionSummary"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Model Currency */
            model_currency: string;
            /** Model Name */
            model_name: string;
            /**
             * Model Type
             * @enum {string}
             */
            model_type: "OWNER_CASH_FLOW_10Y" | "RESIDUAL_INCOME_10Y_FADE";
            /** Source Model Key */
            source_model_key: string | null;
            valuation_listing: components["schemas"]["ListingRead"];
        };
        /** FinancialModelCalculationOutputsRead */
        FinancialModelCalculationOutputsRead: {
            /** Base Fv */
            base_fv: string;
            /** Base Probability */
            base_probability: string;
            /** Bear Fv */
            bear_fv: string;
            /** Bear Probability */
            bear_probability: string;
            /** Bull Fv */
            bull_fv: string;
            /** Bull Probability */
            bull_probability: string;
            /** Current Price */
            current_price: string | null;
            /** Expected Cash Flow Irr */
            expected_cash_flow_irr: string | null;
            /** Expected Excess */
            expected_excess: string | null;
            /** Forward Fundamental Cagr */
            forward_fundamental_cagr: string | null;
            /** Hurdle */
            hurdle: string;
            /** Irr Unavailable Reason */
            irr_unavailable_reason: string | null;
            /** Model Currency */
            model_currency: string;
            /** Price Effective At */
            price_effective_at: string | null;
            /** Price Observation Id */
            price_observation_id: string | null;
            /**
             * Price Status
             * @enum {string}
             */
            price_status: "FRESH" | "STALE" | "QUALITY_CHECK" | "NO_DATA" | "CURRENCY_MISMATCH" | "CURRENCY_UNKNOWN";
            /** Price Unavailable Reason */
            price_unavailable_reason: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "COMPLETE" | "PARTIAL";
            /** Weighted Fv */
            weighted_fv: string;
            /** Weighted Upside */
            weighted_upside: string | null;
        };
        /** FinancialModelCalculationPreviewRead */
        FinancialModelCalculationPreviewRead: {
            /** Base Revision Id */
            base_revision_id: string | null;
            /** Current Revision Id */
            current_revision_id: string | null;
            /** Current Revision Number */
            current_revision_number: number | null;
            /** Model Currency */
            model_currency: string;
            /** Model Id */
            model_id: string | null;
            outputs: components["schemas"]["FinancialModelCalculationOutputsRead"];
            /** Projections */
            projections: components["schemas"]["DcfProjectionCalculationPreviewRead"][];
        };
        /** FinancialModelContractBaseRevision */
        FinancialModelContractBaseRevision: {
            /**
             * Methodology Version
             * @constant
             */
            methodology_version: "ufcf-dcf-fade-v1";
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Revision Number */
            revision_number: number;
        };
        /** FinancialModelContractCalculation */
        "FinancialModelContractCalculation-Input": {
            outputs: components["schemas"]["FinancialModelOutputsRead-Input"];
            /** Projections */
            projections: components["schemas"]["DcfProjectionRead-Input"][];
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
        };
        /** FinancialModelContractCalculation */
        "FinancialModelContractCalculation-Output": {
            outputs: components["schemas"]["FinancialModelOutputsRead-Output"];
            /** Projections */
            projections: components["schemas"]["DcfProjectionRead-Output"][];
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
        };
        /** FinancialModelContractCandidateRevision */
        "FinancialModelContractCandidateRevision-Input": {
            /**
             * Actor
             * @default IMPORT
             * @constant
             */
            actor: "IMPORT";
            base: components["schemas"]["DcfOperatingBase-Input"];
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Rationale */
            rationale: string;
            /** Scenarios */
            scenarios: components["schemas"]["DcfScenarioInput-Input"][];
            /** Source */
            source?: string | null;
            /** Source Revision Id */
            source_revision_id: string;
        };
        /** FinancialModelContractCandidateRevision */
        "FinancialModelContractCandidateRevision-Output": {
            /**
             * Actor
             * @default IMPORT
             * @constant
             */
            actor: "IMPORT";
            base: components["schemas"]["DcfOperatingBase-Output"];
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Rationale */
            rationale: string;
            /** Scenarios */
            scenarios: components["schemas"]["DcfScenarioInput-Output"][];
            /** Source */
            source?: string | null;
            /** Source Revision Id */
            source_revision_id: string;
        };
        /** FinancialModelContractFieldChange */
        FinancialModelContractFieldChange: {
            /** Path */
            path: string;
            /** Previous */
            previous: string | null;
            /** Proposed */
            proposed: string | null;
        };
        /** FinancialModelContractIdentity */
        FinancialModelContractIdentity: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Model Currency */
            model_currency: string;
            /**
             * Model Id
             * Format: uuid
             */
            model_id: string;
            /** Model Name */
            model_name: string;
            model_type: components["schemas"]["FinancialModelType"];
            /** Source Model Key */
            source_model_key: string | null;
            valuation_listing: components["schemas"]["ListingRead"];
            /**
             * Valuation Listing Id
             * Format: uuid
             */
            valuation_listing_id: string;
        };
        /** FinancialModelContractImportRead */
        FinancialModelContractImportRead: {
            model: components["schemas"]["FinancialModelRead"];
            revision: components["schemas"]["FinancialModelRevisionRead"];
            /**
             * Status
             * @enum {string}
             */
            status: "IMPORTED" | "ALREADY_IMPORTED";
        };
        /** FinancialModelContractOutputSummary */
        FinancialModelContractOutputSummary: {
            /** Base Fv */
            base_fv: string;
            /** Bear Fv */
            bear_fv: string;
            /** Bull Fv */
            bull_fv: string;
            /** Current Price */
            current_price: string | null;
            /** Expected Cash Flow Irr */
            expected_cash_flow_irr: string | null;
            /** Expected Excess */
            expected_excess: string | null;
            /** Hurdle */
            hurdle: string;
            /** Irr Unavailable Reason */
            irr_unavailable_reason: string | null;
            /** Model Currency */
            model_currency: string;
            /** Price Effective At */
            price_effective_at: string | null;
            /**
             * Price Status
             * @enum {string}
             */
            price_status: "FRESH" | "STALE" | "QUALITY_CHECK" | "NO_DATA" | "CURRENCY_MISMATCH" | "CURRENCY_UNKNOWN";
            /** Price Unavailable Reason */
            price_unavailable_reason: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "COMPLETE" | "PARTIAL";
            /** Weighted Fv */
            weighted_fv: string;
            /** Weighted Upside */
            weighted_upside: string | null;
        };
        /** FinancialModelContractPreviewRead */
        FinancialModelContractPreviewRead: {
            /**
             * Actor
             * @default IMPORT
             * @constant
             */
            actor: "IMPORT";
            /** Already Imported Revision Id */
            already_imported_revision_id: string | null;
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            calculated_outputs: components["schemas"]["FinancialModelContractOutputSummary"] | null;
            /** Changes */
            changes: components["schemas"]["FinancialModelContractFieldChange"][];
            current_outputs: components["schemas"]["FinancialModelContractOutputSummary"];
            /**
             * Current Revision Id
             * Format: uuid
             */
            current_revision_id: string;
            /** Current Revision Number */
            current_revision_number: number;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /**
             * Model Id
             * Format: uuid
             */
            model_id: string;
            /** Output Changes */
            output_changes: components["schemas"]["FinancialModelContractFieldChange"][];
            /** Proposed Revision Number */
            proposed_revision_number: number | null;
            /** Reason */
            reason: string | null;
            /** Source */
            source?: string | null;
            /** Source Revision Id */
            source_revision_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "READY" | "NO_CHANGES" | "RATIONALE_REQUIRED" | "CONFLICT" | "INVALID_BASE_SNAPSHOT" | "ALREADY_IMPORTED";
        };
        /** FinancialModelContractV1 */
        "FinancialModelContractV1-Input": {
            base_calculation: components["schemas"]["FinancialModelContractCalculation-Input"];
            base_revision: components["schemas"]["FinancialModelContractBaseRevision"];
            candidate_revision: components["schemas"]["FinancialModelContractCandidateRevision-Input"];
            /**
             * Contract Version
             * @constant
             */
            contract_version: "1.0.0";
            /**
             * Exported At
             * Format: date-time
             */
            exported_at: string;
            model: components["schemas"]["FinancialModelContractIdentity"];
        };
        /** FinancialModelContractV1 */
        "FinancialModelContractV1-Output": {
            base_calculation: components["schemas"]["FinancialModelContractCalculation-Output"];
            base_revision: components["schemas"]["FinancialModelContractBaseRevision"];
            candidate_revision: components["schemas"]["FinancialModelContractCandidateRevision-Output"];
            /**
             * Contract Version
             * @constant
             */
            contract_version: "1.0.0";
            /**
             * Exported At
             * Format: date-time
             */
            exported_at: string;
            model: components["schemas"]["FinancialModelContractIdentity"];
        };
        /** FinancialModelCreate */
        FinancialModelCreate: {
            initial_revision: components["schemas"]["FinancialModelRevisionCreate"];
            /** Model Currency */
            model_currency: string;
            /** Model Name */
            model_name: string;
            /**
             * Model Type
             * @default UFCF_DCF_10Y_FADE
             * @constant
             */
            model_type: "UFCF_DCF_10Y_FADE";
            /** Source Model Key */
            source_model_key?: string | null;
            /**
             * Valuation Listing Id
             * Format: uuid
             */
            valuation_listing_id: string;
        };
        /** FinancialModelInitialCalculationPreviewCreate */
        FinancialModelInitialCalculationPreviewCreate: {
            base: components["schemas"]["DcfOperatingBase-Input"];
            /** Model Currency */
            model_currency: string;
            /** Scenarios */
            scenarios: components["schemas"]["DcfScenarioInput-Input"][];
            /**
             * Valuation Listing Id
             * Format: uuid
             */
            valuation_listing_id: string;
        };
        /** FinancialModelOutputsRead */
        "FinancialModelOutputsRead-Input": {
            /** Base Fv */
            base_fv: number | string;
            /** Base Probability */
            base_probability: number | string;
            /** Bear Fv */
            bear_fv: number | string;
            /** Bear Probability */
            bear_probability: number | string;
            /** Bull Fv */
            bull_fv: number | string;
            /** Bull Probability */
            bull_probability: number | string;
            /** Current Price */
            current_price: (number | string) | null;
            /** Expected Cash Flow Irr */
            expected_cash_flow_irr: (number | string) | null;
            /** Expected Excess */
            expected_excess: (number | string) | null;
            /** Forward Fundamental Cagr */
            forward_fundamental_cagr: (number | string) | null;
            /** Hurdle */
            hurdle: number | string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Irr Unavailable Reason */
            irr_unavailable_reason: string | null;
            /** Model Currency */
            model_currency: string;
            /** Price Effective At */
            price_effective_at: string | null;
            /** Price Observation Id */
            price_observation_id: string | null;
            /**
             * Price Status
             * @enum {string}
             */
            price_status: "FRESH" | "STALE" | "QUALITY_CHECK" | "NO_DATA" | "CURRENCY_MISMATCH" | "CURRENCY_UNKNOWN";
            /** Price Unavailable Reason */
            price_unavailable_reason: string | null;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "COMPLETE" | "PARTIAL";
            /** Weighted Fv */
            weighted_fv: number | string;
            /** Weighted Upside */
            weighted_upside: (number | string) | null;
        };
        /** FinancialModelOutputsRead */
        "FinancialModelOutputsRead-Output": {
            /** Base Fv */
            base_fv: string;
            /** Base Probability */
            base_probability: string;
            /** Bear Fv */
            bear_fv: string;
            /** Bear Probability */
            bear_probability: string;
            /** Bull Fv */
            bull_fv: string;
            /** Bull Probability */
            bull_probability: string;
            /** Current Price */
            current_price: string | null;
            /** Expected Cash Flow Irr */
            expected_cash_flow_irr: string | null;
            /** Expected Excess */
            expected_excess: string | null;
            /** Forward Fundamental Cagr */
            forward_fundamental_cagr: string | null;
            /** Hurdle */
            hurdle: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Irr Unavailable Reason */
            irr_unavailable_reason: string | null;
            /** Model Currency */
            model_currency: string;
            /** Price Effective At */
            price_effective_at: string | null;
            /** Price Observation Id */
            price_observation_id: string | null;
            /**
             * Price Status
             * @enum {string}
             */
            price_status: "FRESH" | "STALE" | "QUALITY_CHECK" | "NO_DATA" | "CURRENCY_MISMATCH" | "CURRENCY_UNKNOWN";
            /** Price Unavailable Reason */
            price_unavailable_reason: string | null;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "COMPLETE" | "PARTIAL";
            /** Weighted Fv */
            weighted_fv: string;
            /** Weighted Upside */
            weighted_upside: string | null;
        };
        /** FinancialModelRead */
        FinancialModelRead: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            current_revision: components["schemas"]["FinancialModelRevisionRead"];
            /**
             * Current Revision Id
             * Format: uuid
             */
            current_revision_id: string;
            /** History */
            history: components["schemas"]["FinancialModelRevisionSummary"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Model Currency */
            model_currency: string;
            /** Model Name */
            model_name: string;
            model_type: components["schemas"]["FinancialModelType"];
            /** Source Model Key */
            source_model_key: string | null;
            valuation_listing: components["schemas"]["ListingRead"];
        };
        /** FinancialModelRevisionCalculationPreviewCreate */
        FinancialModelRevisionCalculationPreviewCreate: {
            base: components["schemas"]["DcfOperatingBase-Input"];
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            /** Scenarios */
            scenarios: components["schemas"]["DcfScenarioInput-Input"][];
        };
        /** FinancialModelRevisionCreate */
        FinancialModelRevisionCreate: {
            actor: components["schemas"]["Actor"];
            base: components["schemas"]["DcfOperatingBase-Input"];
            /** Base Revision Id */
            base_revision_id: string | null;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Rationale */
            rationale: string;
            /** Scenarios */
            scenarios: components["schemas"]["DcfScenarioInput-Input"][];
            /** Source */
            source?: string | null;
            /** Source Revision Id */
            source_revision_id?: string | null;
        };
        /** FinancialModelRevisionRead */
        FinancialModelRevisionRead: {
            actor: components["schemas"]["Actor"];
            base: components["schemas"]["DcfOperatingBaseRead"];
            /** Base Revision Id */
            base_revision_id: string | null;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Methodology Version */
            methodology_version: string;
            /**
             * Model Id
             * Format: uuid
             */
            model_id: string;
            outputs: components["schemas"]["FinancialModelOutputsRead-Output"];
            /** Projections */
            projections: components["schemas"]["DcfProjectionRead-Output"][];
            /** Rationale */
            rationale: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Revision Number */
            revision_number: number;
            /** Scenarios */
            scenarios: components["schemas"]["DcfScenarioRead"][];
            /** Source */
            source: string | null;
            /** Source Revision Id */
            source_revision_id: string | null;
        };
        /** FinancialModelRevisionSummary */
        FinancialModelRevisionSummary: {
            actor: components["schemas"]["Actor"];
            /** Base Revision Id */
            base_revision_id: string | null;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Methodology Version */
            methodology_version: string;
            /**
             * Model Id
             * Format: uuid
             */
            model_id: string;
            outputs: components["schemas"]["FinancialModelOutputsRead-Output"];
            /** Rationale */
            rationale: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Revision Number */
            revision_number: number;
            /** Source */
            source: string | null;
            /** Source Revision Id */
            source_revision_id: string | null;
        };
        /**
         * FinancialModelType
         * @enum {string}
         */
        FinancialModelType: "UFCF_DCF_10Y_FADE" | "OWNER_CASH_FLOW_10Y" | "RESIDUAL_INCOME_10Y_FADE";
        /**
         * FundamentalDataQuality
         * @enum {string}
         */
        FundamentalDataQuality: "PASS" | "DATA_CHECK" | "INVALID";
        /**
         * FundamentalMetric
         * @enum {string}
         */
        FundamentalMetric: "REVENUE" | "GROSS_PROFIT" | "OPERATING_INCOME" | "NET_INCOME" | "CASH_AND_CASH_EQUIVALENTS" | "CURRENT_DEBT" | "NONCURRENT_DEBT" | "OPERATING_CASH_FLOW" | "CAPITAL_EXPENDITURES" | "DILUTED_WEIGHTED_AVERAGE_SHARES";
        /**
         * FundamentalPeriodType
         * @enum {string}
         */
        FundamentalPeriodType: "ANNUAL" | "QUARTERLY" | "INSTANT";
        /**
         * FundamentalRevisionContext
         * @enum {string}
         */
        FundamentalRevisionContext: "ORIGINAL" | "COMPARATIVE_REPORTED" | "POTENTIAL_RESTATEMENT" | "AMENDED_FILING";
        /**
         * FundamentalStatement
         * @enum {string}
         */
        FundamentalStatement: "INCOME_STATEMENT" | "BALANCE_SHEET" | "CASH_FLOW_STATEMENT";
        /** FxObservationCreate */
        FxObservationCreate: {
            actor: components["schemas"]["Actor"];
            /** Base Currency */
            base_currency: string;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Provider */
            provider: string;
            /** Quote Currency */
            quote_currency: string;
            /** Rate */
            rate: number | string;
            /** Reason */
            reason: string;
            /** Source */
            source: string;
        };
        /** FxObservationRead */
        FxObservationRead: {
            actor: components["schemas"]["Actor"];
            /** Base Currency */
            base_currency: string;
            /**
             * Data Quality
             * @enum {string}
             */
            data_quality: "PASS" | "DATA_CHECK" | "INVALID";
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Observed At */
            observed_at: string | null;
            /** Provider */
            provider: string;
            /** Quote Currency */
            quote_currency: string;
            /** Rate */
            rate: string;
            /** Reason */
            reason: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Source */
            source: string;
            /** Source Ref */
            source_ref: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HealthResponse */
        HealthResponse: {
            /**
             * Checked At
             * Format: date-time
             */
            checked_at: string;
            /**
             * Database
             * @enum {string}
             */
            database: "connected" | "unavailable";
            /**
             * Schema
             * @enum {string}
             */
            schema: "current" | "outdated" | "unavailable";
            /**
             * Status
             * @enum {string}
             */
            status: "ok" | "error";
        };
        /** HoldingContext */
        HoldingContext: {
            /** Base Market Value */
            base_market_value: string | null;
            /** Currency */
            currency: string | null;
            /** Latest Price */
            latest_price: string | null;
            /**
             * Listing Id
             * Format: uuid
             */
            listing_id: string;
            /** Native Market Value */
            native_market_value: string | null;
            /** Price Currency */
            price_currency: string | null;
            /** Price Date */
            price_date: string | null;
            /**
             * Price Freshness
             * @default NO_DATA
             * @enum {string}
             */
            price_freshness: "FRESH" | "STALE" | "QUALITY_CHECK" | "NO_DATA";
            /** Quantity */
            quantity: string | null;
            /**
             * Security Id
             * Format: uuid
             */
            security_id: string;
            /** Security Name */
            security_name: string;
            /** Ticker */
            ticker: string;
            /**
             * Valuation Status
             * @default PRICE_UNAVAILABLE
             * @enum {string}
             */
            valuation_status: "VALUED" | "PRICE_UNAVAILABLE" | "FX_UNAVAILABLE" | "QUANTITY_UNAVAILABLE";
            /** Venue */
            venue: string;
        };
        /**
         * Lifecycle
         * @enum {string}
         */
        Lifecycle: "PORTFOLIO" | "WATCHLIST" | "CANDIDATE" | "DROP";
        /** LifecycleChange */
        LifecycleChange: {
            actor: components["schemas"]["Actor"];
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Expected Event Id */
            expected_event_id: string | null;
            new_state: components["schemas"]["Lifecycle"];
            /** Reason */
            reason: string;
            /** Source */
            source?: string | null;
        };
        /** LifecycleEventRead */
        LifecycleEventRead: {
            actor: components["schemas"]["Actor"];
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            new_state: components["schemas"]["Lifecycle"];
            previous_state: components["schemas"]["Lifecycle"] | null;
            /** Reason */
            reason: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Sequence */
            sequence: number;
            /** Source */
            source?: string | null;
        };
        /** ListingCreate */
        ListingCreate: {
            /** Currency */
            currency?: string | null;
            /** Ticker */
            ticker: string;
            /** Venue */
            venue: string;
        };
        /** ListingMarketData */
        ListingMarketData: {
            /** Age Days */
            age_days: number | null;
            /**
             * Freshness
             * @enum {string}
             */
            freshness: "FRESH" | "STALE" | "QUALITY_CHECK" | "NO_DATA";
            /** History */
            history: components["schemas"]["PriceObservationRead"][];
            latest: components["schemas"]["PriceObservationRead"] | null;
            listing: components["schemas"]["ListingRead"];
            price_regime: components["schemas"]["PriceRegimeRead"] | null;
        };
        /** ListingRead */
        ListingRead: {
            /** Currency */
            currency?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Identity Source Ref */
            identity_source_ref: string | null;
            /** Is Demo */
            is_demo: boolean;
            /**
             * Security Id
             * Format: uuid
             */
            security_id: string;
            /** Ticker */
            ticker: string;
            /** Venue */
            venue: string;
        };
        /** LivenessResponse */
        LivenessResponse: {
            /**
             * Status
             * @default ok
             * @constant
             */
            status: "ok";
        };
        /** ModelOutputCurrentModelRead */
        ModelOutputCurrentModelRead: {
            /** Model Key */
            model_key: string;
            snapshot: components["schemas"]["ModelOutputSnapshotRead"];
            /**
             * Status
             * @enum {string}
             */
            status: "PUBLISHED" | "PARTIAL" | "NOT_MAPPED" | "NO_CONTRACT" | "DATA_CHECK";
        };
        /** ModelOutputSnapshotRead */
        ModelOutputSnapshotRead: {
            /**
             * Actor
             * @constant
             */
            actor: "IMPORT";
            /** Base Fv */
            base_fv: string | null;
            /** Base Probability */
            base_probability: string | null;
            /** Bear Fv */
            bear_fv: string | null;
            /** Bear Probability */
            bear_probability: string | null;
            /** Bull Fv */
            bull_fv: string | null;
            /** Bull Probability */
            bull_probability: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Contract Status
             * @enum {string}
             */
            contract_status: "PASS" | "NOT_MAPPED" | "NO_CONTRACT" | "DATA_CHECK" | "HISTORICAL_ONLY";
            /** Contract Version */
            contract_version: string | null;
            /** Currency Source Ref */
            currency_source_ref: string | null;
            /**
             * Currency Status
             * @enum {string}
             */
            currency_status: "DOCUMENTED" | "UNKNOWN";
            /** Effective At */
            effective_at: string | null;
            /** Evidence */
            evidence: string | null;
            /** Expected Cash Flow Irr */
            expected_cash_flow_irr: string | null;
            /** Expected Excess */
            expected_excess: string | null;
            /** Field Issues */
            field_issues: {
                [key: string]: string;
            }[];
            /** Forward Fundamental Cagr */
            forward_fundamental_cagr: string | null;
            /** Hurdle */
            hurdle: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Model Currency */
            model_currency: string | null;
            /** Model Key */
            model_key: string;
            /** Model Status */
            model_status: string | null;
            /** Notes */
            notes: string | null;
            /**
             * Output Quality
             * @enum {string}
             */
            output_quality: "COMPLETE" | "PARTIAL" | "DATA_CHECK" | "UNAVAILABLE";
            /** Rationale */
            rationale: string | null;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Revision Source */
            revision_source: string | null;
            /** Revision Type */
            revision_type: string | null;
            /** Snapshot Key */
            snapshot_key: string;
            /**
             * Snapshot Kind
             * @enum {string}
             */
            snapshot_kind: "CURRENT_CONTRACT" | "LEGACY_REVISION";
            /** Source */
            source: string;
            /** Source Actor */
            source_actor: string | null;
            /** Source Revision Id */
            source_revision_id: string | null;
            /** Weighted Fv */
            weighted_fv: string | null;
            /** Weighted Upside */
            weighted_upside: string | null;
        };
        /**
         * OwnerCashFlowBase
         * @description Owner-cash-flow method inputs. Amounts use source-model billions convention.
         */
        "OwnerCashFlowBase-Input": {
            /** Base Revenue */
            base_revenue: number | string;
            /** Diluted Shares */
            diluted_shares: number | string;
            /** Net Cash */
            net_cash: number | string;
        };
        /**
         * OwnerCashFlowBase
         * @description Owner-cash-flow method inputs. Amounts use source-model billions convention.
         */
        "OwnerCashFlowBase-Output": {
            /** Base Revenue */
            base_revenue: string;
            /** Diluted Shares */
            diluted_shares: string;
            /** Net Cash */
            net_cash: string;
        };
        /** OwnerCashFlowCalculationPreviewRead */
        OwnerCashFlowCalculationPreviewRead: {
            /** Base Revision Id */
            base_revision_id: string | null;
            /** Current Revision Id */
            current_revision_id: string | null;
            /** Current Revision Number */
            current_revision_number: number | null;
            /** Model Currency */
            model_currency: string;
            /** Model Id */
            model_id: string | null;
            outputs: components["schemas"]["FinancialModelCalculationOutputsRead"];
            /** Projections */
            projections: components["schemas"]["OwnerCashFlowProjectionRead"][];
        };
        /** OwnerCashFlowInitialPreviewCreate */
        OwnerCashFlowInitialPreviewCreate: {
            base: components["schemas"]["OwnerCashFlowBase-Input"];
            /** Model Currency */
            model_currency: string;
            /** Scenarios */
            scenarios: components["schemas"]["OwnerCashFlowScenarioInput-Input"][];
            /**
             * Valuation Listing Id
             * Format: uuid
             */
            valuation_listing_id: string;
        };
        /** OwnerCashFlowInput */
        "OwnerCashFlowInput-Input": {
            base: components["schemas"]["OwnerCashFlowBase-Input"];
            /** Scenarios */
            scenarios: components["schemas"]["OwnerCashFlowScenarioInput-Input"][];
        };
        /** OwnerCashFlowInput */
        "OwnerCashFlowInput-Output": {
            base: components["schemas"]["OwnerCashFlowBase-Output"];
            /** Scenarios */
            scenarios: components["schemas"]["OwnerCashFlowScenarioInput-Output"][];
        };
        /** OwnerCashFlowModelCreate */
        OwnerCashFlowModelCreate: {
            initial_revision: components["schemas"]["OwnerCashFlowRevisionCreate"];
            /** Model Currency */
            model_currency: string;
            /** Model Name */
            model_name: string;
            /** Source Model Key */
            source_model_key?: string | null;
            /**
             * Valuation Listing Id
             * Format: uuid
             */
            valuation_listing_id: string;
        };
        /** OwnerCashFlowProjectionRead */
        OwnerCashFlowProjectionRead: {
            /** Forecast Year */
            forecast_year: number;
            /** Owner Cash Flow */
            owner_cash_flow: string;
            /** Owner Cash Flow Per Share */
            owner_cash_flow_per_share: string;
            /** Present Value Per Share */
            present_value_per_share: string;
            /** Revenue */
            revenue: string;
            scenario: components["schemas"]["DcfScenario"];
            /** Terminal Value Per Share */
            terminal_value_per_share: string | null;
        };
        /** OwnerCashFlowRevisionCreate */
        OwnerCashFlowRevisionCreate: {
            actor: components["schemas"]["Actor"];
            base: components["schemas"]["OwnerCashFlowBase-Input"];
            /** Base Revision Id */
            base_revision_id: string | null;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Rationale */
            rationale: string;
            /** Scenarios */
            scenarios: components["schemas"]["OwnerCashFlowScenarioInput-Input"][];
            /** Source */
            source?: string | null;
            /** Source Revision Id */
            source_revision_id?: string | null;
        };
        /** OwnerCashFlowRevisionPreviewCreate */
        OwnerCashFlowRevisionPreviewCreate: {
            base: components["schemas"]["OwnerCashFlowBase-Input"];
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            /** Scenarios */
            scenarios: components["schemas"]["OwnerCashFlowScenarioInput-Input"][];
        };
        /** OwnerCashFlowRevisionRead */
        OwnerCashFlowRevisionRead: {
            actor: components["schemas"]["Actor"];
            base: components["schemas"]["OwnerCashFlowBase-Output"];
            /** Base Revision Id */
            base_revision_id: string | null;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Methodology Version */
            methodology_version: string;
            /**
             * Model Id
             * Format: uuid
             */
            model_id: string;
            outputs: components["schemas"]["FinancialModelOutputsRead-Output"];
            /** Projections */
            projections: components["schemas"]["OwnerCashFlowProjectionRead"][];
            /** Rationale */
            rationale: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Revision Number */
            revision_number: number;
            /** Scenarios */
            scenarios: components["schemas"]["OwnerCashFlowScenarioInput-Output"][];
            /** Source */
            source: string | null;
            /** Source Revision Id */
            source_revision_id: string | null;
        };
        /** OwnerCashFlowScenarioInput */
        "OwnerCashFlowScenarioInput-Input": {
            /** Probability */
            probability: number | string;
            /** Rationale */
            rationale: string;
            /** Required Return */
            required_return: number | string;
            scenario: components["schemas"]["DcfScenario"];
            /** Terminal Growth */
            terminal_growth: number | string;
            /** Years */
            years: components["schemas"]["OwnerCashFlowYearInput-Input"][];
        };
        /** OwnerCashFlowScenarioInput */
        "OwnerCashFlowScenarioInput-Output": {
            /** Probability */
            probability: string;
            /** Rationale */
            rationale: string;
            /** Required Return */
            required_return: string;
            scenario: components["schemas"]["DcfScenario"];
            /** Terminal Growth */
            terminal_growth: string;
            /** Years */
            years: components["schemas"]["OwnerCashFlowYearInput-Output"][];
        };
        /** OwnerCashFlowYearInput */
        "OwnerCashFlowYearInput-Input": {
            /** Forecast Year */
            forecast_year: number;
            /** Owner Cash Flow Margin */
            owner_cash_flow_margin: number | string;
            /** Revenue Growth */
            revenue_growth: number | string;
        };
        /** OwnerCashFlowYearInput */
        "OwnerCashFlowYearInput-Output": {
            /** Forecast Year */
            forecast_year: number;
            /** Owner Cash Flow Margin */
            owner_cash_flow_margin: string;
            /** Revenue Growth */
            revenue_growth: string;
        };
        /** PortfolioCreate */
        PortfolioCreate: {
            /** Base Currency */
            base_currency: string;
            /** Name */
            name: string;
        };
        /** PortfolioOverview */
        PortfolioOverview: {
            /** Base Market Value */
            base_market_value: string | null;
            /** Cash Valuations */
            cash_valuations: components["schemas"]["CashValuation"][];
            /** Companies */
            companies: components["schemas"]["CompanyPortfolioContext"][];
            portfolio: components["schemas"]["PortfolioRead"];
            snapshot: components["schemas"]["SnapshotRead"] | null;
            /** Standalone Positions */
            standalone_positions: components["schemas"]["HoldingContext"][];
            target_revision: components["schemas"]["TargetRead"] | null;
            /** Valuation Currency */
            valuation_currency: string;
            /** Valuation Gaps */
            valuation_gaps: components["schemas"]["ValuationGap"][];
            /**
             * Valuation Status
             * @default NO_HOLDING_SNAPSHOT
             * @enum {string}
             */
            valuation_status: "VALUED" | "NO_HOLDING_SNAPSHOT" | "INCOMPLETE_HOLDINGS" | "INCOMPLETE_PRICE_COVERAGE" | "INCOMPLETE_FX_COVERAGE";
        };
        /** PortfolioRead */
        PortfolioRead: {
            /** Base Currency */
            base_currency: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Demo */
            is_demo: boolean;
            /** Name */
            name: string;
        };
        /** PositionInput */
        "PositionInput-Input": {
            /**
             * Listing Id
             * Format: uuid
             */
            listing_id: string;
            /** Quantity */
            quantity: (number | string) | null;
        };
        /** PositionInput */
        "PositionInput-Output": {
            /**
             * Listing Id
             * Format: uuid
             */
            listing_id: string;
            /** Quantity */
            quantity: string | null;
        };
        /** PriceObservationRead */
        PriceObservationRead: {
            /** Adjustment Basis */
            adjustment_basis: string;
            /** Currency */
            currency: string;
            /**
             * Data Quality
             * @enum {string}
             */
            data_quality: "PASS" | "PASS_VERIFIED_FALLBACK" | "UNSPECIFIED" | "INVALID";
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Listing Id
             * Format: uuid
             */
            listing_id: string;
            /**
             * Market Date
             * Format: date-time
             */
            market_date: string;
            /** Observed At */
            observed_at: string | null;
            /**
             * Price Kind
             * @enum {string}
             */
            price_kind: "DAILY_CLOSE" | "CURRENT_QUOTE";
            /** Provider */
            provider: string;
            /** Provider Close */
            provider_close: string | null;
            /** Provider Currency */
            provider_currency: string | null;
            /** Provider Symbol */
            provider_symbol: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Source Price Multiplier */
            source_price_multiplier: string;
            /** Source Ref */
            source_ref: string;
            /** Split Adjusted Close */
            split_adjusted_close: string | null;
            /** Total Return Close */
            total_return_close: string | null;
            /** Volume */
            volume: string | null;
        };
        /** PriceRegimeRead */
        PriceRegimeRead: {
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Correction State */
            correction_state: string | null;
            /**
             * Data Quality
             * @enum {string}
             */
            data_quality: "PASS" | "DATA_CHECK" | "UNSPECIFIED";
            /** Dma 20 */
            dma_20: string | null;
            /** Dma 200 */
            dma_200: string | null;
            /** Dma 50 */
            dma_50: string | null;
            /** Drawdown 52W */
            drawdown_52w: string | null;
            /** High 52W */
            high_52w: string | null;
            /**
             * Listing Id
             * Format: uuid
             */
            listing_id: string;
            /** Methodology Version */
            methodology_version: string;
            /** Provider Close */
            provider_close: string | null;
            /** Quality Reason */
            quality_reason: string | null;
            /** Realized Vol 20D */
            realized_vol_20d: string | null;
            /** Regime */
            regime: string | null;
            /** Return 1M */
            return_1m: string | null;
            /** Return 3M */
            return_3m: string | null;
            /** Return 6M */
            return_6m: string | null;
            /** Source Ref */
            source_ref: string;
            /** Split Adjusted Close */
            split_adjusted_close: string | null;
            /** Trend State */
            trend_state: string | null;
            /** Vs Dma 20 */
            vs_dma_20: string | null;
            /** Vs Dma 200 */
            vs_dma_200: string | null;
            /** Vs Dma 50 */
            vs_dma_50: string | null;
        };
        /** RankingCurrentRead */
        RankingCurrentRead: {
            definition: components["schemas"]["RankingDefinitionRead"];
            entry: components["schemas"]["RankingEntryRead"] | null;
            run: components["schemas"]["RankingRunRead"] | null;
        };
        /** RankingDefinitionRead */
        RankingDefinitionRead: {
            /**
             * Effective From
             * Format: date-time
             */
            effective_from: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            implementation_status: components["schemas"]["RankingImplementationStatus"];
            /** Methodology */
            methodology: string;
            /** Population Rule */
            population_rule: string;
            ranking_type: components["schemas"]["RankingType"];
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Required Inputs */
            required_inputs: string;
            /** Source Reference */
            source_reference: string;
            status: components["schemas"]["RankingDefinitionStatus"];
            /** Title */
            title: string;
            /** Version */
            version: number;
        };
        /**
         * RankingDefinitionStatus
         * @enum {string}
         */
        RankingDefinitionStatus: "ACTIVE" | "RETIRED";
        /** RankingEntryRead */
        RankingEntryRead: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Position */
            position: number | null;
            /** Reason */
            reason: string;
            /**
             * Run Id
             * Format: uuid
             */
            run_id: string;
            status: components["schemas"]["RankingEntryStatus"];
        };
        /**
         * RankingEntryStatus
         * @enum {string}
         */
        RankingEntryStatus: "RANKED" | "INPUTS_UNAVAILABLE" | "NOT_ELIGIBLE" | "EXCLUDED" | "NOT_MIGRATED";
        /** RankingHistoryEntry */
        RankingHistoryEntry: {
            entry: components["schemas"]["RankingEntryRead"];
            run: components["schemas"]["RankingRunRead"];
        };
        /**
         * RankingImplementationStatus
         * @enum {string}
         */
        RankingImplementationStatus: "NOT_MIGRATED" | "PARTIAL" | "READY";
        /** RankingRunCreate */
        RankingRunCreate: {
            actor: components["schemas"]["Actor"];
            ranking_type: components["schemas"]["RankingType"];
            /** Reason */
            reason: string;
            /** Source */
            source?: string | null;
        };
        /** RankingRunDetailRead */
        RankingRunDetailRead: {
            /** Entries */
            entries: components["schemas"]["RankingRunEntryRead"][];
            run: components["schemas"]["RankingRunRead"];
        };
        /** RankingRunEntryRead */
        RankingRunEntryRead: {
            company: components["schemas"]["CompanyRead"];
            entry: components["schemas"]["RankingEntryRead"];
        };
        /** RankingRunRead */
        RankingRunRead: {
            actor: components["schemas"]["Actor"];
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Company Count */
            company_count: number;
            definition: components["schemas"]["RankingDefinitionRead"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Ranked Count */
            ranked_count: number;
            /** Reason */
            reason: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Source */
            source: string | null;
            status: components["schemas"]["RankingRunStatus"];
        };
        /**
         * RankingRunStatus
         * @enum {string}
         */
        RankingRunStatus: "COMPLETE" | "PARTIAL" | "UNAVAILABLE";
        /**
         * RankingType
         * @enum {string}
         */
        RankingType: "PORTFOLIO" | "WATCHLIST" | "RESEARCH";
        /** ReportedFundamentalCoverageRead */
        ReportedFundamentalCoverageRead: {
            /** Latest Period End */
            latest_period_end: string | null;
            metric: components["schemas"]["FundamentalMetric"];
            /** Observation Count */
            observation_count: number;
            statement: components["schemas"]["FundamentalStatement"];
            /**
             * Status
             * @enum {string}
             */
            status: "AVAILABLE" | "CONFLICT" | "DATA_CHECK" | "NOT_IMPORTED";
        };
        /** ReportedFundamentalDefinitionRead */
        ReportedFundamentalDefinitionRead: {
            /** Canonical Unit */
            canonical_unit: string;
            /** Description */
            description: string;
            /** Display Name */
            display_name: string;
            /**
             * Evidence Type
             * @enum {string}
             */
            evidence_type: "REPORTED_FACT" | "DERIVED_ANALYTIC";
            /** Metric */
            metric: string;
            statement: components["schemas"]["FundamentalStatement"] | null;
        };
        /** ReportedFundamentalObservationRead */
        ReportedFundamentalObservationRead: {
            /** Accession Number */
            accession_number: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Currency */
            currency: string | null;
            data_quality: components["schemas"]["FundamentalDataQuality"];
            /** Filed At */
            filed_at: string | null;
            /** Fiscal Period */
            fiscal_period: string | null;
            /** Fiscal Year */
            fiscal_year: number | null;
            /** Form */
            form: string | null;
            /** Frame */
            frame: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            metric: components["schemas"]["FundamentalMetric"];
            /**
             * Observed At
             * Format: date-time
             */
            observed_at: string;
            /**
             * Period End
             * Format: date-time
             */
            period_end: string;
            /** Period Start */
            period_start: string | null;
            period_type: components["schemas"]["FundamentalPeriodType"];
            /** Provider Entity Id */
            provider_entity_id: string;
            /** Provider Id */
            provider_id: string;
            /** Quality Reason */
            quality_reason: string | null;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            revision_context: components["schemas"]["FundamentalRevisionContext"];
            /** Security Id */
            security_id: string | null;
            /** Source Concept */
            source_concept: string;
            /** Source Priority */
            source_priority: number;
            /** Source Record Id */
            source_record_id: string;
            /** Source Ref */
            source_ref: string;
            /** Source Taxonomy */
            source_taxonomy: string;
            /** Source Unit */
            source_unit: string;
            /** Source Url */
            source_url: string;
            statement: components["schemas"]["FundamentalStatement"];
            /** Supersedes Observation Id */
            supersedes_observation_id: string | null;
            /** Unit */
            unit: string;
            /** Value */
            value: string;
        };
        /** ReportedFundamentalPeriodRead */
        ReportedFundamentalPeriodRead: {
            /** Currency */
            currency: string | null;
            /** Fiscal Period */
            fiscal_period: string | null;
            /** Fiscal Year */
            fiscal_year: number | null;
            metric: components["schemas"]["FundamentalMetric"];
            /** Observations */
            observations: components["schemas"]["ReportedFundamentalObservationRead"][];
            /**
             * Period End
             * Format: date-time
             */
            period_end: string;
            /** Period Start */
            period_start: string | null;
            period_type: components["schemas"]["FundamentalPeriodType"];
            selected_observation: components["schemas"]["ReportedFundamentalObservationRead"] | null;
            /**
             * Selection Status
             * @enum {string}
             */
            selection_status: "AVAILABLE" | "CONFLICT" | "DATA_CHECK";
            statement: components["schemas"]["FundamentalStatement"];
            /** Unit */
            unit: string;
            /** Value */
            value: string | null;
        };
        /** ResidualIncomeBase */
        "ResidualIncomeBase-Input": {
            /** Current Book Value Per Share */
            current_book_value_per_share: number | string;
            /** Payout Ratio */
            payout_ratio: number | string;
        };
        /** ResidualIncomeBase */
        "ResidualIncomeBase-Output": {
            /** Current Book Value Per Share */
            current_book_value_per_share: string;
            /** Payout Ratio */
            payout_ratio: string;
        };
        /** ResidualIncomeCalculationPreviewRead */
        ResidualIncomeCalculationPreviewRead: {
            /** Base Revision Id */
            base_revision_id: string | null;
            /** Current Revision Id */
            current_revision_id: string | null;
            /** Current Revision Number */
            current_revision_number: number | null;
            /** Model Currency */
            model_currency: string;
            /** Model Id */
            model_id: string | null;
            outputs: components["schemas"]["FinancialModelCalculationOutputsRead"];
            /** Projections */
            projections: components["schemas"]["ResidualIncomeProjectionRead"][];
        };
        /** ResidualIncomeInitialPreviewCreate */
        ResidualIncomeInitialPreviewCreate: {
            base: components["schemas"]["ResidualIncomeBase-Input"];
            /** Model Currency */
            model_currency: string;
            /** Scenarios */
            scenarios: components["schemas"]["ResidualIncomeScenarioInput-Input"][];
            /**
             * Valuation Listing Id
             * Format: uuid
             */
            valuation_listing_id: string;
        };
        /** ResidualIncomeInput */
        "ResidualIncomeInput-Input": {
            base: components["schemas"]["ResidualIncomeBase-Input"];
            /** Scenarios */
            scenarios: components["schemas"]["ResidualIncomeScenarioInput-Input"][];
        };
        /** ResidualIncomeInput */
        "ResidualIncomeInput-Output": {
            base: components["schemas"]["ResidualIncomeBase-Output"];
            /** Scenarios */
            scenarios: components["schemas"]["ResidualIncomeScenarioInput-Output"][];
        };
        /** ResidualIncomeModelCreate */
        ResidualIncomeModelCreate: {
            initial_revision: components["schemas"]["ResidualIncomeRevisionCreate"];
            /** Model Currency */
            model_currency: string;
            /** Model Name */
            model_name: string;
            /** Source Model Key */
            source_model_key?: string | null;
            /**
             * Valuation Listing Id
             * Format: uuid
             */
            valuation_listing_id: string;
        };
        /** ResidualIncomeProjectionRead */
        ResidualIncomeProjectionRead: {
            /** Beginning Book Value Per Share */
            beginning_book_value_per_share: string;
            /** Dividend Per Share */
            dividend_per_share: string;
            /** Ending Book Value Per Share */
            ending_book_value_per_share: string;
            /** Forecast Year */
            forecast_year: number;
            /** Net Income Per Share */
            net_income_per_share: string;
            /** Present Value Residual Income */
            present_value_residual_income: string;
            /** Residual Income Per Share */
            residual_income_per_share: string;
            /** Return On Equity */
            return_on_equity: string;
            scenario: components["schemas"]["DcfScenario"];
            /** Terminal Value Per Share */
            terminal_value_per_share: string | null;
        };
        /** ResidualIncomeRevisionCreate */
        ResidualIncomeRevisionCreate: {
            actor: components["schemas"]["Actor"];
            base: components["schemas"]["ResidualIncomeBase-Input"];
            /** Base Revision Id */
            base_revision_id: string | null;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Rationale */
            rationale: string;
            /** Scenarios */
            scenarios: components["schemas"]["ResidualIncomeScenarioInput-Input"][];
            /** Source */
            source?: string | null;
            /** Source Revision Id */
            source_revision_id?: string | null;
        };
        /** ResidualIncomeRevisionPreviewCreate */
        ResidualIncomeRevisionPreviewCreate: {
            base: components["schemas"]["ResidualIncomeBase-Input"];
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            /** Scenarios */
            scenarios: components["schemas"]["ResidualIncomeScenarioInput-Input"][];
        };
        /** ResidualIncomeRevisionRead */
        ResidualIncomeRevisionRead: {
            actor: components["schemas"]["Actor"];
            base: components["schemas"]["ResidualIncomeBase-Output"];
            /** Base Revision Id */
            base_revision_id: string | null;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Methodology Version */
            methodology_version: string;
            /**
             * Model Id
             * Format: uuid
             */
            model_id: string;
            outputs: components["schemas"]["FinancialModelOutputsRead-Output"];
            /** Projections */
            projections: components["schemas"]["ResidualIncomeProjectionRead"][];
            /** Rationale */
            rationale: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Revision Number */
            revision_number: number;
            /** Scenarios */
            scenarios: components["schemas"]["ResidualIncomeScenarioInput-Output"][];
            /** Source */
            source: string | null;
            /** Source Revision Id */
            source_revision_id: string | null;
        };
        /** ResidualIncomeScenarioInput */
        "ResidualIncomeScenarioInput-Input": {
            /** Cost Of Equity */
            cost_of_equity: number | string;
            /** Mature Roe */
            mature_roe: number | string;
            /** Probability */
            probability: number | string;
            /** Rationale */
            rationale: string;
            scenario: components["schemas"]["DcfScenario"];
            /** Starting Roe */
            starting_roe: number | string;
            /** Terminal Growth */
            terminal_growth: number | string;
        };
        /** ResidualIncomeScenarioInput */
        "ResidualIncomeScenarioInput-Output": {
            /** Cost Of Equity */
            cost_of_equity: string;
            /** Mature Roe */
            mature_roe: string;
            /** Probability */
            probability: string;
            /** Rationale */
            rationale: string;
            scenario: components["schemas"]["DcfScenario"];
            /** Starting Roe */
            starting_roe: string;
            /** Terminal Growth */
            terminal_growth: string;
        };
        /** ScoreAssessmentCreate */
        ScoreAssessmentCreate: {
            actor: components["schemas"]["Actor"];
            dimension: components["schemas"]["ScoreDimension"];
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Rationale */
            rationale: string;
            /** Score */
            score: (number | string) | null;
            /** Source */
            source?: string | null;
            status: components["schemas"]["ScoreAssessmentStatus"];
            /** Superseded Assessment Id */
            superseded_assessment_id?: string | null;
        };
        /** ScoreAssessmentRead */
        ScoreAssessmentRead: {
            actor: components["schemas"]["Actor"];
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Rationale */
            rationale: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Score */
            score: string | null;
            /**
             * Score Definition Id
             * Format: uuid
             */
            score_definition_id: string;
            /** Source */
            source: string | null;
            status: components["schemas"]["ScoreAssessmentStatus"];
            /** Superseded Assessment Id */
            superseded_assessment_id: string | null;
        };
        /**
         * ScoreAssessmentStatus
         * @enum {string}
         */
        ScoreAssessmentStatus: "ASSESSED" | "MISSING" | "UNAVAILABLE" | "INVALID";
        /** ScoreCurrentRead */
        ScoreCurrentRead: {
            assessment: components["schemas"]["ScoreAssessmentRead"] | null;
            definition: components["schemas"]["ScoreDefinitionRead"];
        };
        /** ScoreDefinitionRead */
        ScoreDefinitionRead: {
            dimension: components["schemas"]["ScoreDimension"];
            directionality: components["schemas"]["ScoreDirectionality"];
            /**
             * Effective From
             * Format: date-time
             */
            effective_from: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Maximum Score */
            maximum_score: string;
            /** Methodology */
            methodology: string;
            /** Minimum Score */
            minimum_score: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            status: components["schemas"]["ScoreDefinitionStatus"];
            /** Units */
            units: string;
            /** Version */
            version: number;
        };
        /**
         * ScoreDefinitionStatus
         * @enum {string}
         */
        ScoreDefinitionStatus: "ACTIVE" | "RETIRED";
        /**
         * ScoreDimension
         * @enum {string}
         */
        ScoreDimension: "DURABILITY_10Y" | "COMPOUNDER_QUALITY" | "EXECUTION" | "RISK";
        /**
         * ScoreDirectionality
         * @enum {string}
         */
        ScoreDirectionality: "HIGHER_IS_BETTER" | "HIGHER_IS_RISK";
        /** ScoreHistoryEntry */
        ScoreHistoryEntry: {
            assessment: components["schemas"]["ScoreAssessmentRead"];
            definition: components["schemas"]["ScoreDefinitionRead"];
        };
        /** SecurityCreate */
        SecurityCreate: {
            /** Name */
            name: string;
            /**
             * Security Type
             * @enum {string}
             */
            security_type: "COMMON_STOCK" | "ADR" | "PREFERRED";
            /** Share Class */
            share_class?: string | null;
            /** Underlying Security Id */
            underlying_security_id?: string | null;
        };
        /** SecurityRead */
        SecurityRead: {
            /** Company Id */
            company_id: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Demo */
            is_demo: boolean;
            /** Name */
            name: string;
            /**
             * Security Type
             * @enum {string}
             */
            security_type: "COMMON_STOCK" | "ADR" | "PREFERRED" | "ETF";
            /** Share Class */
            share_class: string | null;
            /** Underlying Security Id */
            underlying_security_id: string | null;
        };
        /** SnapshotCreate */
        SnapshotCreate: {
            actor: components["schemas"]["Actor"];
            /** Cash Positions */
            cash_positions?: components["schemas"]["CashInput-Input"][];
            /**
             * Completeness
             * @enum {string}
             */
            completeness: "COMPLETE" | "PARTIAL" | "UNAVAILABLE";
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Positions */
            positions: components["schemas"]["PositionInput-Input"][];
            /** Reason */
            reason: string;
            /** Source */
            source?: string | null;
        };
        /** SnapshotRead */
        SnapshotRead: {
            actor: components["schemas"]["Actor"];
            /** Cash Positions */
            cash_positions: components["schemas"]["CashInput-Output"][];
            /**
             * Completeness
             * @enum {string}
             */
            completeness: "COMPLETE" | "PARTIAL" | "UNAVAILABLE";
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Portfolio Id
             * Format: uuid
             */
            portfolio_id: string;
            /** Positions */
            positions: components["schemas"]["PositionInput-Output"][];
            /** Reason */
            reason: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Source */
            source?: string | null;
        };
        /**
         * SourceDocumentCreate
         * @description Register an issuer-published source reference without uploading its content.
         */
        SourceDocumentCreate: {
            /** @default LOCAL_USER */
            actor: components["schemas"]["Actor"];
            /** Amends Document Id */
            amends_document_id?: string | null;
            /**
             * Canonical Url
             * Format: uri
             */
            canonical_url: string;
            /** @default PASS */
            data_quality: components["schemas"]["SourceDocumentQuality"];
            document_type: components["schemas"]["SourceDocumentType"];
            /** External Identifier */
            external_identifier: string;
            /** Fiscal Period */
            fiscal_period?: string | null;
            /** Fiscal Year */
            fiscal_year?: number | null;
            /**
             * Is Amendment
             * @default false
             */
            is_amendment: boolean;
            /** Period End */
            period_end?: string | null;
            /**
             * Provider Id
             * @default company_source
             * @constant
             */
            provider_id: "company_source";
            /** Published At */
            published_at?: string | null;
            /** Quality Reason */
            quality_reason?: string | null;
            /** Reporting Period */
            reporting_period?: string | null;
            /** Security Id */
            security_id?: string | null;
            /** Source Jurisdiction */
            source_jurisdiction?: string | null;
            /** Source Name */
            source_name: string;
            /** Supersedes Document Id */
            supersedes_document_id?: string | null;
            /** Title */
            title: string;
        };
        /**
         * SourceDocumentQuality
         * @enum {string}
         */
        SourceDocumentQuality: "PASS" | "DATA_CHECK";
        /** SourceDocumentRead */
        SourceDocumentRead: {
            actor: components["schemas"]["Actor"];
            /** Amends Document Id */
            amends_document_id: string | null;
            /** Batch Id */
            batch_id: string | null;
            /**
             * Canonical Url
             * Format: uri
             */
            canonical_url: string;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            data_quality: components["schemas"]["SourceDocumentQuality"];
            document_type: components["schemas"]["SourceDocumentType"];
            /** External Identifier */
            external_identifier: string;
            /** Filed At */
            filed_at: string | null;
            /** Fiscal Period */
            fiscal_period: string | null;
            /** Fiscal Year */
            fiscal_year: number | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Amendment */
            is_amendment: boolean;
            /** Period End */
            period_end: string | null;
            /** Provider Id */
            provider_id: string;
            /** Published At */
            published_at: string | null;
            /** Quality Reason */
            quality_reason: string | null;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Reporting Period */
            reporting_period: string | null;
            /** Retrieved At */
            retrieved_at: string | null;
            /** Security Id */
            security_id: string | null;
            /** Source Form */
            source_form: string | null;
            /** Source Jurisdiction */
            source_jurisdiction: string | null;
            /** Source Name */
            source_name: string;
            /** Supersedes Document Id */
            supersedes_document_id: string | null;
            /** Title */
            title: string;
        };
        /**
         * SourceDocumentType
         * @enum {string}
         */
        SourceDocumentType: "10-K" | "10-Q" | "8-K" | "20-F" | "6-K" | "ANNUAL_REPORT" | "EARNINGS_RELEASE" | "OTHER";
        /** TargetCreate */
        TargetCreate: {
            actor: components["schemas"]["Actor"];
            /** Allocations */
            allocations: components["schemas"]["AllocationInput-Input"][];
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Reason */
            reason: string;
            /** Source */
            source?: string | null;
        };
        /** TargetRead */
        TargetRead: {
            /** Accepted At */
            accepted_at: string | null;
            actor: components["schemas"]["Actor"];
            /** Allocations */
            allocations: components["schemas"]["AllocationInput-Output"][];
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Invested Weight */
            invested_weight: string;
            /**
             * Portfolio Id
             * Format: uuid
             */
            portfolio_id: string;
            /** Reason */
            reason: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Source */
            source?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "DRAFT" | "ACCEPTED";
            /** Strategic Cash Weight */
            strategic_cash_weight: string;
        };
        /** UniverseMarketSummary */
        UniverseMarketSummary: {
            company: components["schemas"]["CompanyRead"];
            /** Market Data */
            market_data: components["schemas"]["ListingMarketData"][];
        };
        /** UniverseModelOutputSummary */
        UniverseModelOutputSummary: {
            company: components["schemas"]["CompanyRead"];
            outputs: components["schemas"]["CompanyModelOutputsCurrentRead"];
        };
        /** UniverseRankingSummary */
        UniverseRankingSummary: {
            company: components["schemas"]["CompanyRead"];
            /** Rankings */
            rankings: components["schemas"]["RankingCurrentRead"][];
        };
        /** UniverseScoreSummary */
        UniverseScoreSummary: {
            company: components["schemas"]["CompanyRead"];
            /** Scores */
            scores: components["schemas"]["ScoreCurrentRead"][];
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** ValuationGap */
        ValuationGap: {
            /** Identity */
            identity: string;
            /** Reason */
            reason: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    liveness_health_live_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LivenessResponse"];
                };
            };
        };
    };
    readiness_health_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
            /** @description Database or schema not ready */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    get_extended_financial_model_v1_canonical_financial_models__model_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExtendedFinancialModelRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_additional_model_contract_v1_canonical_financial_models__model_id__contract_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdditionalModelPortableContractV2-Output"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_additional_model_contract_import_v1_canonical_financial_models__model_id__contract_import_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AdditionalModelPortableContractV2-Input"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdditionalModelContractImportRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_additional_model_contract_preview_v1_canonical_financial_models__model_id__contract_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AdditionalModelPortableContractV2-Input"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdditionalModelContractPreviewRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_owner_cash_flow_revision_v1_canonical_financial_models__model_id__owner_cash_flow_revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OwnerCashFlowRevisionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OwnerCashFlowRevisionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_owner_cash_flow_revision_preview_v1_canonical_financial_models__model_id__owner_cash_flow_revisions_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OwnerCashFlowRevisionPreviewCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OwnerCashFlowCalculationPreviewRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_residual_income_revision_v1_canonical_financial_models__model_id__residual_income_revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResidualIncomeRevisionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResidualIncomeRevisionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_residual_income_revision_preview_v1_canonical_financial_models__model_id__residual_income_revisions_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResidualIncomeRevisionPreviewCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResidualIncomeCalculationPreviewRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_extended_financial_model_revision_v1_canonical_financial_models__model_id__revisions__revision_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
                revision_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OwnerCashFlowRevisionRead"] | components["schemas"]["ResidualIncomeRevisionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_company_v1_companies_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CompanyCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_company_v1_companies__company_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_company_extended_financial_models_v1_companies__company_id__canonical_financial_models_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExtendedFinancialModelRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_owner_cash_flow_model_v1_companies__company_id__canonical_financial_models_owner_cash_flow_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OwnerCashFlowModelCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExtendedFinancialModelRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_owner_cash_flow_initial_preview_v1_companies__company_id__canonical_financial_models_owner_cash_flow_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OwnerCashFlowInitialPreviewCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OwnerCashFlowCalculationPreviewRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_residual_income_model_v1_companies__company_id__canonical_financial_models_residual_income_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResidualIncomeModelCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExtendedFinancialModelRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_residual_income_initial_preview_v1_companies__company_id__canonical_financial_models_residual_income_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResidualIncomeInitialPreviewCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResidualIncomeCalculationPreviewRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_company_consensus_estimates_v1_companies__company_id__consensus_estimates_get: {
        parameters: {
            query?: {
                as_of?: string | null;
                known_at?: string | null;
            };
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyConsensusEstimatesRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_company_financial_models_v1_companies__company_id__financial_models_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_company_financial_model_v1_companies__company_id__financial_models_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FinancialModelCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_financial_model_initial_calculation_preview_v1_companies__company_id__financial_models_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FinancialModelInitialCalculationPreviewCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelCalculationPreviewRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_transition_v1_companies__company_id__lifecycle_transitions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LifecycleChange"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LifecycleEventRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_company_market_data_v1_companies__company_id__market_data_get: {
        parameters: {
            query?: {
                history_limit?: number;
                as_of?: string | null;
                known_at?: string | null;
            };
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListingMarketData"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_company_model_migration_status_v1_companies__company_id__model_migration_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyFinancialModelMigrationRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_current_model_outputs_v1_companies__company_id__model_outputs_current_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyModelOutputsCurrentRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_model_output_history_v1_companies__company_id__model_outputs_history_get: {
        parameters: {
            query?: {
                model_key?: string | null;
            };
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ModelOutputSnapshotRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_company_rankings_v1_companies__company_id__rankings_get: {
        parameters: {
            query?: {
                ranking_type?: components["schemas"]["RankingType"] | null;
            };
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyRankingsRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_company_reported_fundamentals_v1_companies__company_id__reported_fundamentals_get: {
        parameters: {
            query?: {
                period_type?: components["schemas"]["FundamentalPeriodType"] | null;
                as_of?: string | null;
                known_at?: string | null;
            };
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyReportedFundamentalsRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_score_assessment_v1_companies__company_id__score_assessments_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScoreAssessmentCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScoreHistoryEntry"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_current_scores_v1_companies__company_id__scores_current_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScoreCurrentRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_score_history_v1_companies__company_id__scores_history_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScoreHistoryEntry"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_security_v1_companies__company_id__securities_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SecurityCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SecurityRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_company_source_documents_v1_companies__company_id__source_documents_get: {
        parameters: {
            query?: {
                document_type?: components["schemas"]["SourceDocumentType"] | null;
                as_of?: string | null;
                known_at?: string | null;
                limit?: number;
            };
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanySourceDocumentsRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_company_source_document_v1_companies__company_id__source_documents_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SourceDocumentCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceDocumentRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_financial_model_v1_financial_models__model_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_financial_model_contract_v1_financial_models__model_id__contract_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelContractV1-Output"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_financial_model_contract_import_v1_financial_models__model_id__contract_import_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FinancialModelContractV1-Input"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelContractImportRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_financial_model_contract_preview_v1_financial_models__model_id__contract_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FinancialModelContractV1-Input"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelContractPreviewRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_financial_model_history_v1_financial_models__model_id__revisions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelRevisionSummary"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_financial_model_revision_v1_financial_models__model_id__revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FinancialModelRevisionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelRevisionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_financial_model_revision_calculation_preview_v1_financial_models__model_id__revisions_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FinancialModelRevisionCalculationPreviewCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelCalculationPreviewRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_financial_model_revision_v1_financial_models__model_id__revisions__revision_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                model_id: string;
                revision_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FinancialModelRevisionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_fx_observations_v1_fx_observations_get: {
        parameters: {
            query?: {
                base_currency?: string | null;
                quote_currency?: string | null;
                as_of?: string | null;
                known_at?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FxObservationRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_fx_observation_v1_fx_observations_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FxObservationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FxObservationRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_listing_corporate_actions_v1_listings__listing_id__corporate_actions_get: {
        parameters: {
            query?: {
                as_of?: string | null;
                known_at?: string | null;
                limit?: number;
            };
            header?: never;
            path: {
                listing_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CorporateActionRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_listing_market_data_v1_listings__listing_id__market_data_get: {
        parameters: {
            query?: {
                history_limit?: number;
                as_of?: string | null;
                known_at?: string | null;
            };
            header?: never;
            path: {
                listing_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListingMarketData"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_portfolios_v1_portfolios_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PortfolioRead"][];
                };
            };
        };
    };
    post_portfolio_v1_portfolios_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PortfolioCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PortfolioRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_snapshots_v1_portfolios__portfolio_id__holding_snapshots_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                portfolio_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_snapshot_v1_portfolios__portfolio_id__holding_snapshots_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                portfolio_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SnapshotCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_overview_v1_portfolios__portfolio_id__overview_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                portfolio_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PortfolioOverview"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_targets_v1_portfolios__portfolio_id__target_revisions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                portfolio_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TargetRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_targets_v1_portfolios__portfolio_id__target_revisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                portfolio_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TargetCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TargetRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_accept_v1_portfolios__portfolio_id__target_revisions__revision_id__accept_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                portfolio_id: string;
                revision_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TargetRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_ranking_definitions_v1_ranking_definitions_get: {
        parameters: {
            query?: {
                ranking_type?: components["schemas"]["RankingType"] | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RankingDefinitionRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_ranking_runs_v1_ranking_runs_get: {
        parameters: {
            query?: {
                ranking_type?: components["schemas"]["RankingType"] | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RankingRunRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_ranking_run_v1_ranking_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RankingRunCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RankingRunRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_ranking_run_v1_ranking_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RankingRunDetailRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_reported_fundamental_definitions_v1_reported_fundamental_definitions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportedFundamentalDefinitionRead"][];
                };
            };
        };
    };
    get_score_definitions_v1_score_definitions_get: {
        parameters: {
            query?: {
                dimension?: components["schemas"]["ScoreDimension"] | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScoreDefinitionRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_listing_v1_securities__security_id__listings_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                security_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ListingCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListingRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_universe_v1_universe_get: {
        parameters: {
            query?: {
                lifecycle?: components["schemas"]["Lifecycle"] | null;
                search?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_universe_market_summary_v1_universe_market_summary_get: {
        parameters: {
            query?: {
                lifecycle?: components["schemas"]["Lifecycle"] | null;
                search?: string | null;
                as_of?: string | null;
                known_at?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UniverseMarketSummary"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_universe_model_output_summary_v1_universe_model_output_summary_get: {
        parameters: {
            query?: {
                lifecycle?: components["schemas"]["Lifecycle"] | null;
                search?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UniverseModelOutputSummary"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_universe_ranking_summary_v1_universe_ranking_summary_get: {
        parameters: {
            query?: {
                lifecycle?: components["schemas"]["Lifecycle"] | null;
                search?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UniverseRankingSummary"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_universe_score_summary_v1_universe_score_summary_get: {
        parameters: {
            query?: {
                lifecycle?: components["schemas"]["Lifecycle"] | null;
                search?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UniverseScoreSummary"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
