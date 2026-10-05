"""canonical reported financial statement observations

Revision ID: f84c92d17a61
Revises: d7a43c90e215
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f84c92d17a61"
down_revision: str | Sequence[str] | None = "d7a43c90e215"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "company_provider_identifiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=120), nullable=False),
        sa.Column("identifier_type", sa.String(length=24), nullable=False),
        sa.Column("identifier_value", sa.String(length=20), nullable=False),
        sa.Column("provider_company_name", sa.String(length=300), nullable=False),
        sa.Column("evidence_source", sa.String(length=1000), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "identifier_type IN ('SEC_CIK')", name="ck_company_provider_identifiers_identifier_type"
        ),
        sa.CheckConstraint(
            "length(evidence_source) > 0", name="ck_company_provider_identifiers_evidence_source"
        ),
        sa.CheckConstraint(
            "actor IN ('LOCAL_USER','SYSTEM','IMPORT')",
            name="ck_company_provider_identifiers_actor",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_company_provider_identifiers_company_id_companies",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_company_provider_identifiers"),
        sa.UniqueConstraint(
            "provider_id",
            "identifier_type",
            "identifier_value",
            name="uq_company_provider_identifiers_external_id",
        ),
    )
    op.create_index(
        "ix_company_provider_identifiers_company_id",
        "company_provider_identifiers",
        ["company_id"],
        unique=False,
    )

    op.create_table(
        "reported_fundamental_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=120), nullable=False),
        sa.Column("provider_schema_version", sa.String(length=120), nullable=True),
        sa.Column("normalizer_version", sa.String(length=80), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("query_scope", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_summary", sa.JSON(), nullable=False),
        sa.Column("reconciliation", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "length(source_digest) = 64", name="ck_reported_fundamental_batches_source_digest"
        ),
        sa.CheckConstraint(
            "domain = 'REPORTED_FUNDAMENTALS'", name="ck_reported_fundamental_batches_domain"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reported_fundamental_batches"),
        sa.UniqueConstraint(
            "source_digest", "normalizer_version", name="uq_fundamental_batches_digest_version"
        ),
    )

    op.alter_column("external_raw_payloads", "batch_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column(
        "external_raw_payloads",
        sa.Column("reported_fundamental_batch_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_external_raw_payloads_fundamental_batch",
        "external_raw_payloads",
        "reported_fundamental_batches",
        ["reported_fundamental_batch_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_external_raw_payloads_reported_fundamental_batch_id",
        "external_raw_payloads",
        ["reported_fundamental_batch_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_external_payload_fundamental_batch_record",
        "external_raw_payloads",
        ["reported_fundamental_batch_id", "source_record_id"],
    )
    op.create_check_constraint(
        "ck_external_raw_payloads_exactly_one_batch",
        "external_raw_payloads",
        "(batch_id IS NOT NULL AND reported_fundamental_batch_id IS NULL) OR "
        "(batch_id IS NULL AND reported_fundamental_batch_id IS NOT NULL)",
    )

    op.create_table(
        "reported_fundamental_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("security_id", sa.Uuid(), nullable=True),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=120), nullable=False),
        sa.Column("provider_entity_id", sa.String(length=80), nullable=False),
        sa.Column("source_priority", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("statement", sa.String(length=32), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=12), nullable=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(38, 12), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("source_taxonomy", sa.String(length=80), nullable=False),
        sa.Column("source_concept", sa.String(length=200), nullable=False),
        sa.Column("source_unit", sa.String(length=80), nullable=False),
        sa.Column("accession_number", sa.String(length=24), nullable=True),
        sa.Column("form", sa.String(length=20), nullable=True),
        sa.Column("frame", sa.String(length=24), nullable=True),
        sa.Column("source_record_id", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("source_ref", sa.String(length=1000), nullable=False),
        sa.Column("observation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("mapping_priority", sa.Integer(), nullable=False),
        sa.Column("revision_context", sa.String(length=32), nullable=False),
        sa.Column("data_quality", sa.String(length=20), nullable=False),
        sa.Column("quality_reason", sa.String(length=1000), nullable=True),
        sa.Column("supersedes_observation_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "metric IN ('REVENUE','GROSS_PROFIT','OPERATING_INCOME','NET_INCOME',"
            "'CASH_AND_CASH_EQUIVALENTS','CURRENT_DEBT','NONCURRENT_DEBT',"
            "'OPERATING_CASH_FLOW','CAPITAL_EXPENDITURES',"
            "'DILUTED_WEIGHTED_AVERAGE_SHARES')",
            name="ck_reported_fundamental_observations_metric",
        ),
        sa.CheckConstraint(
            "statement IN ('INCOME_STATEMENT','BALANCE_SHEET','CASH_FLOW_STATEMENT')",
            name="ck_reported_fundamental_observations_statement",
        ),
        sa.CheckConstraint(
            "period_type IN ('ANNUAL','QUARTERLY','INSTANT')",
            name="ck_reported_fundamental_observations_period_type",
        ),
        sa.CheckConstraint(
            "(period_type = 'INSTANT' AND period_start IS NULL) OR "
            "(period_type <> 'INSTANT' AND period_start IS NOT NULL "
            "AND period_start <= period_end)",
            name="ck_reported_fundamental_observations_period_dates",
        ),
        sa.CheckConstraint(
            "value IS NOT NULL", name="ck_reported_fundamental_observations_value_required"
        ),
        sa.CheckConstraint(
            "source_priority >= 0 AND mapping_priority >= 0",
            name="ck_reported_fundamental_observations_priorities",
        ),
        sa.CheckConstraint(
            "revision_context IN ('ORIGINAL','COMPARATIVE_REPORTED',"
            "'POTENTIAL_RESTATEMENT','AMENDED_FILING')",
            name="ck_reported_fundamental_observations_revision_context",
        ),
        sa.CheckConstraint(
            "data_quality IN ('PASS','DATA_CHECK','INVALID')",
            name="ck_reported_fundamental_observations_data_quality",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_reported_fundamental_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["security_id"],
            ["securities.id"],
            name="fk_reported_fundamental_security",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["reported_fundamental_batches.id"],
            name="fk_reported_fundamental_batch",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_observation_id"],
            ["reported_fundamental_observations.id"],
            name="fk_reported_fundamental_supersedes",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reported_fundamental_observations"),
        sa.UniqueConstraint(
            "provider_id",
            "source_record_id",
            "observation_fingerprint",
            name="uq_reported_fundamental_source_version",
        ),
    )
    op.create_index(
        "ix_reported_fundamental_observations_company_id",
        "reported_fundamental_observations",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_reported_fundamental_observations_batch_id",
        "reported_fundamental_observations",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_reported_fundamentals_company_metric_period",
        "reported_fundamental_observations",
        ["company_id", "metric", "period_end"],
        unique=False,
    )
    op.create_index(
        "ix_reported_fundamentals_company_known_at",
        "reported_fundamental_observations",
        ["company_id", "recorded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reported_fundamentals_company_known_at", table_name="reported_fundamental_observations"
    )
    op.drop_index(
        "ix_reported_fundamentals_company_metric_period",
        table_name="reported_fundamental_observations",
    )
    op.drop_index(
        "ix_reported_fundamental_observations_batch_id",
        table_name="reported_fundamental_observations",
    )
    op.drop_index(
        "ix_reported_fundamental_observations_company_id",
        table_name="reported_fundamental_observations",
    )
    op.drop_table("reported_fundamental_observations")
    op.execute(
        """DO $$ DECLARE item record; BEGIN
        FOR item IN
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'external_raw_payloads'::regclass
              AND contype = 'c'
              AND lower(pg_get_constraintdef(oid)) LIKE '%reported_fundamental_batch_id%'
        LOOP
            EXECUTE format('ALTER TABLE external_raw_payloads DROP CONSTRAINT %I', item.conname);
        END LOOP;
        END $$"""
    )
    op.drop_constraint(
        "uq_external_payload_fundamental_batch_record", "external_raw_payloads", type_="unique"
    )
    op.drop_index(
        "ix_external_raw_payloads_reported_fundamental_batch_id", table_name="external_raw_payloads"
    )
    op.drop_constraint(
        "fk_external_raw_payloads_fundamental_batch",
        "external_raw_payloads",
        type_="foreignkey",
    )
    op.drop_column("external_raw_payloads", "reported_fundamental_batch_id")
    op.alter_column("external_raw_payloads", "batch_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_table("reported_fundamental_batches")
    op.drop_index(
        "ix_company_provider_identifiers_company_id", table_name="company_provider_identifiers"
    )
    op.drop_table("company_provider_identifiers")
