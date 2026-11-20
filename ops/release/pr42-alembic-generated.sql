BEGIN;

-- Running upgrade b59f16c8a203 -> c6d8e4f1a290

CREATE TABLE company_metric_definitions (
    id UUID NOT NULL, 
    metric_key VARCHAR(160) NOT NULL, 
    company_id UUID, 
    display_name VARCHAR(200) NOT NULL, 
    category VARCHAR(32) NOT NULL, 
    value_kind VARCHAR(16) NOT NULL, 
    canonical_unit VARCHAR(64) NOT NULL, 
    canonical_scale NUMERIC(38, 12) NOT NULL, 
    currency_policy VARCHAR(16) NOT NULL, 
    aggregation_semantics VARCHAR(40) NOT NULL, 
    default_period_type VARCHAR(16) NOT NULL, 
    default_basis VARCHAR(120), 
    scope_dimensions JSON NOT NULL, 
    actuals_allowed BOOLEAN NOT NULL, 
    guidance_allowed BOOLEAN NOT NULL, 
    consensus_allowed BOOLEAN NOT NULL, 
    model_driver_allowed BOOLEAN NOT NULL, 
    active BOOLEAN NOT NULL, 
    description TEXT NOT NULL, 
    source_reference VARCHAR(2000), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    deprecated_at TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_company_metric_definitions PRIMARY KEY (id), 
    CONSTRAINT ck_company_metric_definitions_metric_key CHECK (length(metric_key) > 0), 
    CONSTRAINT ck_company_metric_definitions_category CHECK (category IN ('FINANCIAL','CAPITAL_STRUCTURE','OPERATING','CUSTOMER','CAPACITY','PRODUCT','MARKET_SHARE','MARKET_EXPOSURE','SEGMENT','BACKLOG','QUALITY','OTHER')), 
    CONSTRAINT ck_company_metric_definitions_value_kind CHECK (value_kind IN ('CURRENCY','PERCENT','COUNT','RATIO','TEXT')), 
    CONSTRAINT ck_company_metric_definitions_canonical_scale CHECK (canonical_scale > 0), 
    CONSTRAINT ck_company_metric_definitions_currency_policy CHECK (currency_policy IN ('NONE','OPTIONAL','REQUIRED')), 
    CONSTRAINT ck_company_metric_definitions_default_period_type CHECK (default_period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')), 
    CONSTRAINT fk_company_metric_definitions_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_company_metric_definition_key UNIQUE (metric_key)
);

CREATE INDEX ix_company_metric_definitions_company_active ON company_metric_definitions (company_id, active);

CREATE INDEX ix_company_metric_definitions_company_id ON company_metric_definitions (company_id);

CREATE TABLE company_metric_observations (
    id UUID NOT NULL, 
    external_observation_id VARCHAR(200) NOT NULL, 
    company_id UUID NOT NULL, 
    metric_definition_id UUID NOT NULL, 
    period_type VARCHAR(16) NOT NULL, 
    period_start DATE NOT NULL, 
    period_end DATE NOT NULL, 
    fiscal_year INTEGER, 
    fiscal_quarter INTEGER, 
    value NUMERIC(38, 12) NOT NULL, 
    value_qualifier VARCHAR(16) NOT NULL, 
    unit VARCHAR(64) NOT NULL, 
    scale NUMERIC(38, 12) NOT NULL, 
    currency VARCHAR(3), 
    basis VARCHAR(120) NOT NULL, 
    scope_json JSON NOT NULL, 
    reported_at TIMESTAMP WITH TIME ZONE, 
    source_type VARCHAR(80) NOT NULL, 
    source_reference VARCHAR(2000) NOT NULL, 
    quality_status VARCHAR(16) NOT NULL, 
    quality_reason VARCHAR(1000), 
    supersedes_observation_id UUID, 
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_company_metric_observations PRIMARY KEY (id), 
    CONSTRAINT ck_company_metric_observations_period_type CHECK (period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')), 
    CONSTRAINT ck_company_metric_observations_period_dates CHECK (period_start <= period_end), 
    CONSTRAINT ck_company_metric_observations_fiscal_quarter CHECK (fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4), 
    CONSTRAINT ck_company_metric_observations_value_qualifier CHECK (value_qualifier IN ('EQ','APPROX','GT','GTE','LT','LTE')), 
    CONSTRAINT ck_company_metric_observations_scale CHECK (scale > 0), 
    CONSTRAINT ck_company_metric_observations_currency CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$'), 
    CONSTRAINT ck_company_metric_observations_quality_status CHECK (quality_status IN ('VERIFIED','PROVISIONAL','CONFLICTED','RESTATED')), 
    CONSTRAINT fk_company_metric_observations_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_company_metric_observations_metric_definition_id_com_4341 FOREIGN KEY(metric_definition_id) REFERENCES company_metric_definitions (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_company_metric_observation_supersession FOREIGN KEY(company_id, metric_definition_id, supersedes_observation_id) REFERENCES company_metric_observations (company_id, metric_definition_id, id) ON DELETE RESTRICT, 
    CONSTRAINT uq_company_metric_observation_identity UNIQUE (company_id, metric_definition_id, id), 
    CONSTRAINT uq_company_metric_observation_external_id UNIQUE (external_observation_id), 
    CONSTRAINT uq_company_metric_observations_supersedes_observation_id UNIQUE (supersedes_observation_id)
);

CREATE INDEX ix_company_metric_observations_company_metric_period ON company_metric_observations (company_id, metric_definition_id, period_end);

CREATE INDEX ix_company_metric_observations_company_recorded ON company_metric_observations (company_id, recorded_at);

CREATE INDEX ix_company_metric_observations_company_id ON company_metric_observations (company_id);

CREATE INDEX ix_company_metric_observations_metric_definition_id ON company_metric_observations (metric_definition_id);

CREATE TABLE company_guidance_observations (
    id UUID NOT NULL, 
    external_guidance_id VARCHAR(200) NOT NULL, 
    company_id UUID NOT NULL, 
    metric_definition_id UUID NOT NULL, 
    period_type VARCHAR(16) NOT NULL, 
    period_start DATE NOT NULL, 
    period_end DATE NOT NULL, 
    fiscal_year INTEGER, 
    fiscal_quarter INTEGER, 
    lower_value NUMERIC(38, 12), 
    midpoint_value NUMERIC(38, 12), 
    upper_value NUMERIC(38, 12), 
    value_qualifier VARCHAR(16) NOT NULL, 
    unit VARCHAR(64) NOT NULL, 
    scale NUMERIC(38, 12) NOT NULL, 
    currency VARCHAR(3), 
    basis VARCHAR(120) NOT NULL, 
    scope_json JSON NOT NULL, 
    issued_at TIMESTAMP WITH TIME ZONE, 
    source_type VARCHAR(80) NOT NULL, 
    source_reference VARCHAR(2000) NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    supersedes_guidance_id UUID, 
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_company_guidance_observations PRIMARY KEY (id), 
    CONSTRAINT ck_company_guidance_observations_period_type CHECK (period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')), 
    CONSTRAINT ck_company_guidance_observations_period_dates CHECK (period_start <= period_end), 
    CONSTRAINT ck_company_guidance_observations_fiscal_quarter CHECK (fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4), 
    CONSTRAINT ck_company_guidance_observations_value_qualifier CHECK (value_qualifier IN ('EQ','APPROX','GT','GTE','LT','LTE','RANGE')), 
    CONSTRAINT ck_company_guidance_observations_status CHECK (status IN ('ACTIVE','SUPERSEDED','WITHDRAWN','ACHIEVED')), 
    CONSTRAINT ck_company_guidance_observations_value_or_withdrawn CHECK (status = 'WITHDRAWN' OR lower_value IS NOT NULL OR midpoint_value IS NOT NULL OR upper_value IS NOT NULL), 
    CONSTRAINT ck_company_guidance_observations_range_order CHECK (lower_value IS NULL OR upper_value IS NULL OR lower_value <= upper_value), 
    CONSTRAINT ck_company_guidance_observations_scale CHECK (scale > 0), 
    CONSTRAINT ck_company_guidance_observations_currency CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$'), 
    CONSTRAINT fk_company_guidance_observations_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_company_guidance_observations_metric_definition_id_c_5ddc FOREIGN KEY(metric_definition_id) REFERENCES company_metric_definitions (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_company_guidance_supersession FOREIGN KEY(company_id, metric_definition_id, supersedes_guidance_id) REFERENCES company_guidance_observations (company_id, metric_definition_id, id) ON DELETE RESTRICT, 
    CONSTRAINT uq_company_guidance_identity UNIQUE (company_id, metric_definition_id, id), 
    CONSTRAINT uq_company_guidance_external_id UNIQUE (external_guidance_id), 
    CONSTRAINT uq_company_guidance_observations_supersedes_guidance_id UNIQUE (supersedes_guidance_id)
);

CREATE INDEX ix_company_guidance_company_metric_period ON company_guidance_observations (company_id, metric_definition_id, period_end);

CREATE INDEX ix_company_guidance_observations_company_id ON company_guidance_observations (company_id);

CREATE INDEX ix_company_guidance_observations_metric_definition_id ON company_guidance_observations (metric_definition_id);

CREATE TABLE financial_model_driver_projections (
    id UUID NOT NULL, 
    external_driver_id VARCHAR(200) NOT NULL, 
    model_id UUID NOT NULL, 
    revision_id UUID NOT NULL, 
    scenario VARCHAR(8) NOT NULL, 
    metric_definition_id UUID NOT NULL, 
    forecast_year INTEGER NOT NULL, 
    period_type VARCHAR(16) NOT NULL, 
    period_start DATE NOT NULL, 
    period_end DATE NOT NULL, 
    value NUMERIC(38, 12) NOT NULL, 
    value_qualifier VARCHAR(16) NOT NULL, 
    unit VARCHAR(64) NOT NULL, 
    scale NUMERIC(38, 12) NOT NULL, 
    currency VARCHAR(3), 
    basis VARCHAR(120) NOT NULL, 
    scope_json JSON NOT NULL, 
    rationale TEXT NOT NULL, 
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_financial_model_driver_projections PRIMARY KEY (id), 
    CONSTRAINT ck_financial_model_driver_projections_scenario CHECK (scenario IN ('BEAR','BASE','BULL')), 
    CONSTRAINT ck_financial_model_driver_projections_period_type CHECK (period_type IN ('DATE','MONTH','QUARTER','FY','TTM','EVENT')), 
    CONSTRAINT ck_financial_model_driver_projections_period_dates CHECK (period_start <= period_end), 
    CONSTRAINT ck_financial_model_driver_projections_forecast_year CHECK (forecast_year > 0), 
    CONSTRAINT ck_financial_model_driver_projections_value_qualifier CHECK (value_qualifier IN ('EQ','APPROX','GT','GTE','LT','LTE')), 
    CONSTRAINT ck_financial_model_driver_projections_scale CHECK (scale > 0), 
    CONSTRAINT ck_financial_model_driver_projections_currency CHECK (currency IS NULL OR currency ~ '^[A-Z]{3}$'), 
    CONSTRAINT fk_financial_model_driver_projections_model_id_financial_models FOREIGN KEY(model_id) REFERENCES financial_models (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_financial_model_driver_revision FOREIGN KEY(model_id, revision_id) REFERENCES financial_model_revisions (model_id, id) ON DELETE RESTRICT, 
    CONSTRAINT fk_financial_model_driver_projections_metric_definition_2304 FOREIGN KEY(metric_definition_id) REFERENCES company_metric_definitions (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_financial_model_driver_external_id UNIQUE (external_driver_id)
);

CREATE INDEX ix_financial_model_driver_revision_metric ON financial_model_driver_projections (revision_id, metric_definition_id, forecast_year);

CREATE INDEX ix_financial_model_driver_projections_model_id ON financial_model_driver_projections (model_id);

CREATE INDEX ix_financial_model_driver_projections_revision_id ON financial_model_driver_projections (revision_id);

CREATE INDEX ix_financial_model_driver_projections_metric_definition_id ON financial_model_driver_projections (metric_definition_id);

UPDATE alembic_version SET version_num='c6d8e4f1a290' WHERE alembic_version.version_num = 'b59f16c8a203';

-- Running upgrade c6d8e4f1a290 -> d7b4a6c8e2f0

CREATE TABLE company_observation_proposals (
    id UUID NOT NULL, 
    company_id UUID NOT NULL, 
    producer_id VARCHAR(160) NOT NULL, 
    external_batch_id VARCHAR(160) NOT NULL, 
    contract_type VARCHAR(60) NOT NULL, 
    payload_data JSON NOT NULL, 
    content_fingerprint VARCHAR(64) NOT NULL, 
    status VARCHAR(16) NOT NULL, 
    issue TEXT, 
    preview_fingerprint VARCHAR(64), 
    accepted_record_ids JSON NOT NULL, 
    reviewer_id VARCHAR(160), 
    decision_note TEXT, 
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    reviewed_at TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_company_observation_proposals PRIMARY KEY (id), 
    CONSTRAINT fk_company_observation_proposals_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT uq_company_observation_producer_batch UNIQUE (producer_id, external_batch_id), 
    CONSTRAINT ck_company_observation_proposals_status CHECK (status IN ('PENDING','READY','CONFLICT','INVALID','ACCEPTED','REJECTED'))
);

CREATE INDEX ix_company_observation_proposals_company_status ON company_observation_proposals (company_id, status);

UPDATE alembic_version SET version_num='d7b4a6c8e2f0' WHERE alembic_version.version_num = 'c6d8e4f1a290';

COMMIT;

