"""Synthetic-provider regression tests for the bounded market-data bootstrap."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api.database_write_target import install_database_write_target_guard
from portfolio_api.domain.models import (
    CanonicalBootstrapRun,
    Company,
    CorporateAction,
    CurrentLifecycle,
    ExternalRawPayload,
    FxObservation,
    HoldingPosition,
    HoldingSnapshot,
    LifecycleEvent,
    Listing,
    MarketDataBatch,
    MarketDataBootstrapCheckpoint,
    MarketDataBootstrapRun,
    Portfolio,
    PriceObservation,
    Security,
)
from portfolio_api.external_data import (
    CanonicalSubjectKind,
    ExternalDataDomain,
    ProviderQuery,
    RawProviderRecord,
)
from portfolio_api.market_data_bootstrap import (
    MarketDataBootstrapError,
    _canonical_batch_counts,
    _canonical_batch_fingerprint,
    _next_checkpoint,
    _parser,
    _temporal_issues,
    _verify_target,
    _write_private_report,
    execute_market_data_bootstrap,
    prepare_market_data_bootstrap,
    preview_market_data_bootstrap,
    reconcile_market_data_bootstrap,
)
from portfolio_api.settings import Settings
from portfolio_api.yahoo_finance import (
    ProviderFetchFailure,
    YahooListingCrosswalk,
    YahooListingMapping,
)

START = date(2026, 10, 1)
END = date(2026, 10, 5)
RETRIEVED_AT = datetime(2026, 10, 6, 20, tzinfo=UTC)


def _listing_payload(*, symbol: str = "SYNTH") -> bytes:
    timestamps = [
        int(datetime(2026, 10, 2, 13, 30, tzinfo=UTC).timestamp()),
        int(datetime(2026, 10, 5, 13, 30, tzinfo=UTC).timestamp()),
    ]
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": symbol,
                            "currency": "USD",
                            "exchangeName": "NMS",
                            "fullExchangeName": "NasdaqGS",
                            "instrumentType": "EQUITY",
                            "exchangeTimezoneName": "America/New_York",
                            "regularMarketPrice": 120.5,
                            "regularMarketTime": int(
                                datetime(2026, 10, 5, 19, 45, tzinfo=UTC).timestamp()
                            ),
                        },
                        "timestamp": timestamps,
                        "indicators": {
                            "quote": [{"close": [120.125, 121.25], "volume": [1200, 1300]}],
                            "adjclose": [{"adjclose": [119.875, 121.0]}],
                        },
                        "events": {
                            "dividends": {
                                str(int(datetime(2026, 10, 2, 13, 30, tzinfo=UTC).timestamp())): {
                                    "amount": 0.125,
                                }
                            },
                            "splits": {
                                str(int(datetime(2026, 10, 5, 13, 30, tzinfo=UTC).timestamp())): {
                                    "splitRatio": "2:1",
                                }
                            },
                        },
                    }
                ],
                "error": None,
            }
        },
        separators=(",", ":"),
    ).encode()


def _fx_payload() -> bytes:
    timestamps = [
        int(datetime(2026, 10, 2, tzinfo=UTC).timestamp()),
        int(datetime(2026, 10, 5, tzinfo=UTC).timestamp()),
    ]
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": "EUR=X",
                            "currency": "EUR",
                            "exchangeName": "CCY",
                            "instrumentType": "CURRENCY",
                            "regularMarketPrice": 0.92,
                            "regularMarketTime": int(
                                datetime(2026, 10, 6, 18, tzinfo=UTC).timestamp()
                            ),
                        },
                        "timestamp": timestamps,
                        "indicators": {"quote": [{"close": [0.91, 0.915]}]},
                    }
                ],
                "error": None,
            }
        },
        separators=(",", ":"),
    ).encode()


def _empty_payload(domain: ExternalDataDomain) -> bytes:
    symbol = "SYNTH" if domain == ExternalDataDomain.MARKET_DATA else "EUR=X"
    currency = "USD" if domain == ExternalDataDomain.MARKET_DATA else "EUR"
    instrument = "EQUITY" if domain == ExternalDataDomain.MARKET_DATA else "CURRENCY"
    exchange = "NMS" if domain == ExternalDataDomain.MARKET_DATA else "CCY"
    return json.dumps(
        {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "symbol": symbol,
                            "currency": currency,
                            "exchangeName": exchange,
                            "instrumentType": instrument,
                            "exchangeTimezoneName": "America/New_York",
                        },
                        "timestamp": [],
                        "indicators": {"quote": [{"close": []}]},
                    }
                ],
                "error": None,
            }
        },
        separators=(",", ":"),
    ).encode()


def _mapping(company_id: UUID, security_id: UUID, listing_id: UUID) -> YahooListingMapping:
    return YahooListingMapping(
        venue="NASDAQ",
        ticker="SYNTH",
        currency="USD",
        security_type="COMMON_STOCK",
        provider_symbol="SYNTH",
        provider_exchange_code="NMS",
        provider_exchange_name="NasdaqGS",
        provider_instrument_type="EQUITY",
        mapping_basis="SYNTHETIC_TEST_FIXTURE",
        verification_status="VERIFIED",
        canonical_company_id=company_id,
        canonical_security_id=security_id,
        canonical_listing_id=listing_id,
    )


def _crosswalk(mapping: YahooListingMapping) -> tuple[YahooListingCrosswalk, str]:
    crosswalk = YahooListingCrosswalk(
        provider_id="YAHOO_FINANCE",
        provider_schema_version="yahoo-chart-v8",
        verified_at=RETRIEVED_AT,
        mappings=(mapping,),
    )
    digest = hashlib.sha256(crosswalk.model_dump_json().encode()).hexdigest()
    return crosswalk, digest


def _seed_canonical_scope(session: Session) -> tuple[Company, Security, Listing]:
    company_id, security_id, listing_id = uuid4(), uuid4(), uuid4()
    company = Company(id=company_id, name="Synthetic Example Corporation")
    security = Security(
        id=security_id,
        company_id=company_id,
        name="Synthetic Example Common",
        security_type="COMMON_STOCK",
    )
    listing = Listing(
        id=listing_id,
        security_id=security_id,
        venue="NASDAQ",
        ticker="SYNTH",
        currency="USD",
    )
    lifecycle = LifecycleEvent(
        id=uuid4(),
        company_id=company_id,
        sequence=1,
        previous_state=None,
        new_state="PORTFOLIO",
        effective_at=datetime(2026, 10, 1, tzinfo=UTC),
        actor="IMPORT",
        reason="Synthetic integration fixture",
        source="synthetic-test",
    )
    portfolio = Portfolio(id=uuid4(), name="Synthetic Portfolio", base_currency="EUR")
    snapshot = HoldingSnapshot(
        id=uuid4(),
        portfolio_id=portfolio.id,
        effective_at=datetime(2026, 10, 1, tzinfo=UTC),
        actor="IMPORT",
        reason="Synthetic integration fixture",
        source="synthetic-test",
        completeness="COMPLETE",
    )
    session.add(company)
    session.flush()
    session.add(security)
    session.flush()
    session.add(listing)
    session.add(lifecycle)
    session.add(portfolio)
    session.flush()
    session.add(snapshot)
    session.flush()
    session.add(CurrentLifecycle(company_id=company_id, event_id=lifecycle.id))
    session.flush()
    session.info["new_snapshot_ids"] = {snapshot.id}
    try:
        session.add(
            HoldingPosition(
                snapshot_id=snapshot.id,
                listing_id=listing_id,
                quantity=Decimal("2.5"),
            )
        )
        session.flush()
    finally:
        session.info.pop("new_snapshot_ids", None)
    return company, security, listing


class SyntheticProvider:
    def __init__(self, *, mode: str = "valid") -> None:
        self.mode = mode
        self.failures: list[ProviderFetchFailure] = []
        self.calls: list[ProviderQuery] = []
        self.listing_mappings: dict[UUID, YahooListingMapping] = {}

    def bind_listing_ids(self, listing_ids: dict[UUID, YahooListingMapping]) -> None:
        self.listing_mappings = dict(listing_ids)

    async def fetch(self, query: ProviderQuery) -> Sequence[RawProviderRecord]:
        self.calls.append(query)
        self.failures = []
        subject = query.subjects[0]
        if self.mode == "transport_failure":
            key = (
                f"LISTING:{subject.id}"
                if subject.kind == CanonicalSubjectKind.LISTING
                else (f"FX:{subject.base_currency}/{subject.quote_currency}")
            )
            self.failures.append(
                ProviderFetchFailure(
                    source_record_id=key,
                    provider_symbol="SYNTHETIC",
                    message="Synthetic bounded transport failure",
                    code="NETWORK_ERROR",
                    retryable=True,
                )
            )
            return []
        if subject.kind == CanonicalSubjectKind.LISTING:
            listing_id = subject.id
            assert listing_id is not None
            source_record_id = f"LISTING:{listing_id}"
            payload = (
                _empty_payload(query.domain)
                if self.mode == "empty"
                else _listing_payload(symbol="WRONG" if self.mode == "wrong_identity" else "SYNTH")
            )
        else:
            source_record_id = f"FX:{subject.base_currency}/{subject.quote_currency}"
            payload = _empty_payload(query.domain) if self.mode == "empty" else _fx_payload()
        if (
            self.mode == "missing_listing_close" and subject.kind == CanonicalSubjectKind.LISTING
        ) or (
            self.mode == "missing_fx_close" and subject.kind == CanonicalSubjectKind.CURRENCY_PAIR
        ):
            broken = json.loads(payload)
            broken["chart"]["result"][0]["indicators"]["quote"][0]["close"][1] = None
            payload = json.dumps(broken, separators=(",", ":")).encode()
        return [
            RawProviderRecord(
                domain=query.domain,
                provider_id="YAHOO_FINANCE",
                provider_schema_version="yahoo-chart-v8",
                source_record_id=source_record_id,
                source_url="https://synthetic.example.invalid/chart",
                media_type="application/json",
                retrieved_at=RETRIEVED_AT,
                payload=payload,
                payload_sha256=hashlib.sha256(payload).hexdigest(),
            )
        ]


def _prepare(
    session: Session,
    crosswalk: YahooListingCrosswalk,
    digest: str,
) -> MarketDataBootstrapRun:
    return prepare_market_data_bootstrap(
        session,
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        start_date=START,
        end_date=END,
        target_environment="development",
    )


@pytest.mark.integration
def test_bootstrap_preview_is_read_only_and_rejects_duplicate_exact_mappings(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        mapping = _mapping(company.id, security.id, listing.id)
        duplicate = mapping.model_copy()
        crosswalk, _digest = _crosswalk(mapping.model_copy())
        crosswalk = crosswalk.model_copy(update={"mappings": (mapping, duplicate)})
        digest = hashlib.sha256(crosswalk.model_dump_json().encode()).hexdigest()

        preview = preview_market_data_bootstrap(
            session,
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            start_date=START,
            end_date=END,
            target_environment="development",
        )

        assert preview["status"] == "BLOCKED"
        assert preview["provider_requests"] == 0
        assert preview["database_writes"] == 0
        assert preview["unresolved_listings"][0]["code"] == (
            "VERIFIED_PROVIDER_MAPPING_MISSING_OR_AMBIGUOUS"
        )
        assert session.scalar(select(func.count()).select_from(MarketDataBootstrapRun)) == 0


@pytest.mark.integration
def test_postgres18_market_bootstrap_resumes_and_is_idempotent(
    postgres_engine: Engine,
) -> None:
    from pydantic import SecretStr

    from portfolio_api.database_write_target import verify_database_write_target

    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        run = _prepare(session, crosswalk, digest)
        run_id = run.id
        assert run.status == "PREPARED"
        checkpoint = session.scalar(
            select(MarketDataBootstrapCheckpoint).where(
                MarketDataBootstrapCheckpoint.run_id == run.id,
                MarketDataBootstrapCheckpoint.subject_kind == "LISTING",
            )
        )
        assert checkpoint is not None
        checkpoint.status = "RUNNING"
        checkpoint.attempt_count = 1

    target_settings = Settings(
        database_url=SecretStr(postgres_engine.url.render_as_string(hide_password=False)),
        app_env="development",
        database_target_environment="development",
        database_target_database=postgres_engine.url.database,
        database_local_test_writes_authorized=True,
    )
    audit: list[Mapping[str, Any]] = []
    install_database_write_target_guard(
        postgres_engine,
        target_settings,
        operation="market_data_bootstrap_test",
        operation_kind="bootstrap",
        audit_sink=audit.append,
    )
    verify_database_write_target(postgres_engine)
    _verify_target(postgres_engine, target_settings, "development")
    assert audit

    provider = SyntheticProvider()
    first = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=1,
        min_request_interval_seconds=0,
    )
    assert len(provider.calls) == 1
    assert first["pending_checkpoints"] == 1

    final = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=10,
        min_request_interval_seconds=0,
    )
    assert len(provider.calls) == 2
    assert final["status"] == "PARTIAL"  # Yahoo corporate actions remain unverified facts.
    assert final["canonical_totals"] == {
        "raw_payloads": 2,
        "price_observations": 2,
        "corporate_actions": 2,
        "fx_observations": 2,
    }
    assert final["listing_coverage"][0]["currency"] == "USD"
    assert final["listing_coverage"][0]["price_status"] == "AVAILABLE"
    assert final["history_window_coverage"] == "NOT_ASSESSED"
    assert final["status_scope"] == "CHECKPOINT_EXECUTION_NOT_EXPECTED_SESSION_COVERAGE"
    listing_evidence = final["listing_coverage"][0]["history_window_evidence"]
    assert listing_evidence["distinct_observed_dates"] == 2
    assert listing_evidence["first_observed_date"] == "2026-10-02"
    assert listing_evidence["last_observed_date"] == "2026-10-05"
    assert listing_evidence["maximum_calendar_spacing_days"] == 3
    assert final["listing_coverage"][0]["provider_mapping"]["provider_exchange_code"] == "NMS"
    assert final["listing_coverage"][0]["provider_mapping"]["provider_instrument_type"] == "EQUITY"
    assert final["listing_coverage"][0]["provider_current_quote_rows_skipped"] == 1
    assert final["fx_coverage"][0]["pair"] == "USD/EUR"
    assert final["fx_coverage"][0]["current_quote_rows"] == 0
    assert final["normalization_warning_count"] == 0
    assert final["warning_evidence_unrecorded_checkpoints"] == 0
    fx_evidence = final["fx_coverage"][0]["history_window_evidence"]
    assert fx_evidence["distinct_observed_dates"] == 2
    assert fx_evidence["last_observed_date"] == "2026-10-05"

    with Session(postgres_engine) as session:
        prices = list(session.scalars(select(PriceObservation)))
        actions = list(session.scalars(select(CorporateAction)))
        rates = list(session.scalars(select(FxObservation)))
        payloads = list(session.scalars(select(ExternalRawPayload)))
        assert len(prices) == 2 and all(row.price_kind == "DAILY_CLOSE" for row in prices)
        assert {row.provider_close for row in prices} == {
            Decimal("120.125"),
            Decimal("121.25"),
        }
        assert all(row.currency == "USD" and row.provider_symbol == "SYNTH" for row in prices)
        assert len(actions) == 2 and all(not row.verified for row in actions)
        assert len(rates) == 2 and all(
            (row.base_currency, row.quote_currency) == ("USD", "EUR") for row in rates
        )
        assert len(payloads) == 2 and all(row.payload_sha256 for row in payloads)
        assert all(row.retrieved_at == RETRIEVED_AT for row in payloads)
        reconciliation = reconcile_market_data_bootstrap(
            session, run_id, target_environment="development"
        )
        assert reconciliation["reconciliation"]["status"] == "MATCHED"
        from portfolio_api.historical_bootstrap_review import reconcile_historical_checkpoint

        listing_checkpoint = session.scalar(
            select(MarketDataBootstrapCheckpoint).where(
                MarketDataBootstrapCheckpoint.run_id == run_id,
                MarketDataBootstrapCheckpoint.subject_kind == "LISTING",
            )
        )
        assert listing_checkpoint is not None
        scoped = reconcile_historical_checkpoint(session, run_id, listing_checkpoint.id)
        assert scoped.status == "MATCHED" and scoped.issue_codes == []
        assert set(scoped.model_dump()) == {
            "run_id",
            "checkpoint_id",
            "checked_at",
            "status",
            "issue_codes",
        }
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("portfolio_api.historical_bootstrap_review.MAX_RECONCILIATION_ROWS", 0)
            assert (
                reconcile_historical_checkpoint(session, run_id, listing_checkpoint.id).status
                == "LIMIT_EXCEEDED"
            )
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                "portfolio_api.historical_bootstrap_review.MAX_RECONCILIATION_PAYLOAD_BYTES", 1
            )
            assert (
                reconcile_historical_checkpoint(session, run_id, listing_checkpoint.id).status
                == "LIMIT_EXCEEDED"
            )
        with session.begin_nested() as savepoint:
            receipt = dict(listing_checkpoint.report)
            coverage = dict(receipt["coverage"])
            coverage["canonical_fingerprint"] = None
            receipt["coverage"] = coverage
            listing_checkpoint.report = receipt
            session.flush()
            assert (
                reconcile_historical_checkpoint(session, run_id, listing_checkpoint.id).status
                == "NOT_RECORDED"
            )
            savepoint.rollback()
        with pytest.raises(LookupError):
            reconcile_historical_checkpoint(session, uuid4(), listing_checkpoint.id)
        assert reconciliation["listing_coverage"][0]["history_window_evidence"] == listing_evidence
        assert reconciliation["fx_coverage"][0]["history_window_evidence"] == fx_evidence

    count_before = len(provider.calls)
    replay = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=10,
        min_request_interval_seconds=0,
    )
    assert len(provider.calls) == count_before
    assert replay["canonical_totals"] == final["canonical_totals"]
    assert replay["listing_coverage"][0]["history_window_evidence"] == listing_evidence
    assert replay["fx_coverage"][0]["history_window_evidence"] == fx_evidence

    with Session(postgres_engine) as session, session.begin():
        checkpoint = session.scalar(
            select(MarketDataBootstrapCheckpoint)
            .where(MarketDataBootstrapCheckpoint.run_id == run_id)
            .limit(1)
        )
        assert checkpoint is not None
        checkpoint_report = dict(checkpoint.report)
        coverage_value = checkpoint_report["coverage"]
        assert isinstance(coverage_value, dict)
        coverage = dict(coverage_value)
        coverage["canonical_fingerprint"] = "0" * 64
        checkpoint_report["coverage"] = coverage
        checkpoint.report = checkpoint_report
    with Session(postgres_engine) as session:
        tampered = reconcile_market_data_bootstrap(
            session, run_id, target_environment="development"
        )
        assert tampered["reconciliation"]["status"] == "MISMATCH"
        assert any(
            row["code"] == "CANONICAL_FINGERPRINT_MISMATCH"
            for row in tampered["reconciliation"]["differences"]
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("mode", "coverage_key", "warning_code"),
    [
        ("missing_listing_close", "listing_coverage", "PRICE_ROWS_WITHOUT_CLOSE"),
        ("missing_fx_close", "fx_coverage", "FX_ROWS_WITHOUT_CLOSE"),
    ],
)
def test_missing_provider_close_is_retained_and_reported_without_zero_or_retry(
    postgres_engine: Engine, mode: str, coverage_key: str, warning_code: str
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        run_id = _prepare(session, crosswalk, digest).id
    provider = SyntheticProvider(mode=mode)
    report = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=10,
        min_request_interval_seconds=0,
    )
    assert report["status"] == "PARTIAL"
    assert report["normalization_warning_count"] == 1
    assert report["warning_evidence_unrecorded_checkpoints"] == 0
    assert report[coverage_key][0]["normalization_warnings_captured"] is True
    assert report[coverage_key][0]["normalization_warnings"][0]["code"] == warning_code
    assert report["history_window_coverage"] == "NOT_ASSESSED"
    assert len(provider.calls) == 2
    repeated = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=10,
        min_request_interval_seconds=0,
    )
    assert repeated["status"] == "PARTIAL"
    assert repeated["normalization_warning_count"] == 1
    assert len(provider.calls) == 2
    # An older run may have persisted COMPLETE before warnings affected status.
    with Session(postgres_engine) as session, session.begin():
        old_run = session.get(MarketDataBootstrapRun, run_id)
        assert old_run is not None
        old_run.status = "COMPLETE"
    reevaluated = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=10,
        min_request_interval_seconds=0,
    )
    assert reevaluated["status"] == "PARTIAL"
    assert len(provider.calls) == 2
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        reconciliation = reconcile_market_data_bootstrap(
            session, run_id, target_environment="development"
        )
        assert reconciliation["reconciliation"]["status"] == "MATCHED"
        assert reconciliation["normalization_warning_count"] == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(PriceObservation)
                .where(PriceObservation.split_adjusted_close <= 0)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count()).select_from(FxObservation).where(FxObservation.rate <= 0)
            )
            == 0
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("case", "subject_kind", "expected_code"),
    [
        ("missing_batch", "LISTING", "BATCH_REFERENCE_MISSING"),
        ("missing_raw", "LISTING", "SOURCE_PAYLOAD_MISSING"),
        ("raw_corrupt", "LISTING", "SOURCE_PAYLOAD_HASH_MISMATCH"),
        ("raw_provenance", "LISTING", "SOURCE_PAYLOAD_PROVENANCE_MISMATCH"),
        ("batch_provider", "LISTING", "BATCH_PROVIDER_MISMATCH"),
        ("current_quote", "LISTING", "UNEXPECTED_PRICE_KIND"),
        ("price_outside", "LISTING", "PRICE_OUTSIDE_REQUESTED_WINDOW"),
        ("price_wrong_listing", "LISTING", "CHECKPOINT_SUBJECT_MISMATCH"),
        ("action_outside", "LISTING", "ACTION_OUTSIDE_REQUESTED_WINDOW"),
        ("action_wrong_listing", "LISTING", "CHECKPOINT_SUBJECT_MISMATCH"),
        ("unexpected_fx", "LISTING", "UNEXPECTED_DOMAIN_ROWS"),
        ("fx_outside", "FX_PAIR", "FX_OUTSIDE_REQUESTED_WINDOW"),
        ("fx_wrong_pair", "FX_PAIR", "CHECKPOINT_SUBJECT_MISMATCH"),
        ("fx_future_observation", "FX_PAIR", "OBSERVATION_AFTER_RETRIEVAL"),
    ],
)
def test_reconciliation_rejects_missing_or_out_of_scope_persisted_evidence(
    postgres_engine: Engine, case: str, subject_kind: str, expected_code: str
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        run_id = _prepare(session, crosswalk, digest).id
    execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=SyntheticProvider(),
        max_checkpoints=10,
        min_request_interval_seconds=0,
    )
    # Corrupt only this disposable fixture. Update receipt hashes too, proving the
    # independent scope validation catches more than a fingerprint mismatch.
    with Session(postgres_engine) as session, session.begin():
        checkpoint = session.scalar(
            select(MarketDataBootstrapCheckpoint).where(
                MarketDataBootstrapCheckpoint.run_id == run_id,
                MarketDataBootstrapCheckpoint.subject_kind == subject_kind,
            )
        )
        assert checkpoint is not None and checkpoint.batch_id is not None
        checkpoint_id = checkpoint.id
        batch_id = checkpoint.batch_id
        if case == "missing_batch":
            checkpoint.batch_id = None
        else:
            if case == "missing_raw":
                session.execute(
                    delete(ExternalRawPayload).where(ExternalRawPayload.batch_id == batch_id)
                )
            if case == "raw_corrupt":
                session.execute(
                    update(ExternalRawPayload)
                    .where(ExternalRawPayload.batch_id == batch_id)
                    .values(payload_bytes=gzip.compress(b"changed source bytes"))
                )
            if case == "raw_provenance":
                session.execute(
                    update(ExternalRawPayload)
                    .where(ExternalRawPayload.batch_id == batch_id)
                    .values(domain="FX")
                )
            if case == "batch_provider":
                session.execute(
                    update(MarketDataBatch)
                    .where(MarketDataBatch.id == batch_id)
                    .values(provider_id="OTHER_PROVIDER")
                )
            if case in {"price_wrong_listing", "action_wrong_listing"}:
                original = session.get(Listing, checkpoint.listing_id)
                assert original is not None
                alternate = Listing(
                    id=uuid4(),
                    security_id=original.security_id,
                    venue="NYSE",
                    ticker="SYNTH-ALT",
                    currency="USD",
                )
                session.add(alternate)
                session.flush()
                model = PriceObservation if case == "price_wrong_listing" else CorporateAction
                session.execute(
                    update(model).where(model.batch_id == batch_id).values(listing_id=alternate.id)
                )
            if case == "current_quote":
                session.execute(
                    update(PriceObservation)
                    .where(PriceObservation.batch_id == batch_id)
                    .values(price_kind="CURRENT_QUOTE")
                )
            elif case == "price_outside":
                session.execute(
                    update(PriceObservation)
                    .where(PriceObservation.batch_id == batch_id)
                    .values(market_date=datetime(2026, 9, 30, tzinfo=UTC))
                )
            elif case == "action_outside":
                session.execute(
                    update(CorporateAction)
                    .where(CorporateAction.batch_id == batch_id)
                    .values(effective_date=datetime(2026, 10, 6, tzinfo=UTC))
                )
            elif case == "fx_outside":
                session.execute(
                    update(FxObservation)
                    .where(FxObservation.batch_id == batch_id)
                    .values(effective_at=datetime(2026, 10, 6, tzinfo=UTC))
                )
            elif case == "fx_wrong_pair":
                session.execute(
                    update(FxObservation)
                    .where(FxObservation.batch_id == batch_id)
                    .values(base_currency="EUR", quote_currency="USD")
                )
            elif case == "fx_future_observation":
                session.execute(
                    update(FxObservation)
                    .where(FxObservation.batch_id == batch_id)
                    .values(observed_at=datetime(2026, 10, 7, tzinfo=UTC))
                )
            elif case == "unexpected_fx":
                session.add(
                    FxObservation(
                        id=uuid4(),
                        base_currency="USD",
                        quote_currency="EUR",
                        rate=Decimal("0.9"),
                        data_quality="PASS",
                        effective_at=datetime(2026, 10, 2, tzinfo=UTC),
                        recorded_at=RETRIEVED_AT,
                        batch_id=batch_id,
                        source_ref=f"synthetic-extra-{uuid4()}",
                        provider="SYNTHETIC",
                        source="synthetic",
                        actor="SYSTEM",
                        reason="fixture",
                    )
                )
                session.flush()
            checkpoint_report = dict(checkpoint.report)
            coverage_value = checkpoint_report["coverage"]
            assert isinstance(coverage_value, dict)
            coverage = dict(coverage_value)
            coverage["canonical_counts"] = _canonical_batch_counts(session, batch_id)
            coverage["canonical_fingerprint"] = _canonical_batch_fingerprint(session, batch_id)
            checkpoint_report["coverage"] = coverage
            checkpoint.report = checkpoint_report
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        report = reconcile_market_data_bootstrap(session, run_id, target_environment="development")
        assert report["reconciliation"]["status"] == "MISMATCH"
        assert expected_code in {issue["code"] for issue in report["reconciliation"]["differences"]}
        if subject_kind == "LISTING":
            from portfolio_api.historical_bootstrap_review import reconcile_historical_checkpoint

            scoped = reconcile_historical_checkpoint(session, run_id, checkpoint_id)
            assert scoped.status == "MISMATCH" and expected_code in scoped.issue_codes


@pytest.mark.integration
@pytest.mark.parametrize(
    "mode,expected_status",
    [("empty", "UNAVAILABLE"), ("transport_failure", "FAILED")],
)
def test_provider_gaps_are_distinguished_from_ingestion_failures(
    postgres_engine: Engine,
    mode: str,
    expected_status: str,
) -> None:
    from portfolio_api.historical_bootstrap_review import latest_historical_bootstrap_review

    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        run = _prepare(session, crosswalk, digest)
        run_id = run.id

    result = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=SyntheticProvider(mode=mode),
        max_checkpoints=1,
        min_request_interval_seconds=0,
    )
    with Session(postgres_engine) as session:
        checkpoint = session.scalar(
            select(MarketDataBootstrapCheckpoint).where(
                MarketDataBootstrapCheckpoint.run_id == run_id,
                MarketDataBootstrapCheckpoint.subject_kind == "LISTING",
            )
        )
        assert checkpoint is not None
        assert checkpoint.status == expected_status
        if mode == "transport_failure":
            assert checkpoint.retryable
            assert checkpoint.failure_code == "NETWORK_ERROR"
        else:
            assert not checkpoint.retryable
            assert checkpoint.failure_code == "NO_PROVIDER_DATA"
        assert result["failed_checkpoints"] == (1 if expected_status == "FAILED" else 0)
    with Session(postgres_engine) as session, session.begin():
        session.execute(text("SET TRANSACTION READ ONLY"))
        review = latest_historical_bootstrap_review(session, run_id=run_id)
        row = review.listings[0]
        assert row.reason == (
            "CHECKPOINT_FAILED" if mode == "transport_failure" else "CHECKPOINT_UNAVAILABLE"
        )
        assert row.checkpoint_diagnostics is not None
        assert row.checkpoint_diagnostics.failure_kind == (
            "OTHER" if mode == "transport_failure" else "NO_PROVIDER_DATA"
        )
        assert row.checkpoint_diagnostics.retryable == (mode == "transport_failure")
        assert row.scheduled_session_review is None and row.requested_window_review is None


@pytest.mark.integration
def test_bootstrap_blocks_crosswalk_digest_change_before_provider_calls(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        run = _prepare(session, crosswalk, digest)
        run_id = run.id

    provider = SyntheticProvider()
    result = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256="0" * 64,
        provider=provider,
        min_request_interval_seconds=0,
    )
    assert result["status"] == "BLOCKED"
    assert not provider.calls


@pytest.mark.integration
def test_unallowlisted_required_fx_pair_blocks_preparation_and_provider_access(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        portfolio = session.scalar(select(Portfolio))
        assert portfolio is not None
        portfolio.base_currency = "XXX"
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))

        preview = preview_market_data_bootstrap(
            session,
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            start_date=START,
            end_date=END,
            target_environment="development",
        )
        run = _prepare(session, crosswalk, digest)
        run_id = run.id

        assert preview["status"] == "BLOCKED"
        assert preview["unmapped_fx_pairs"] == ["USD/XXX"]
        assert run.status == "BLOCKED"

    provider = SyntheticProvider()
    result = execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        min_request_interval_seconds=0,
    )
    assert result["status"] == "BLOCKED"
    assert not provider.calls


@pytest.mark.integration
def test_changed_listing_identity_blocks_its_checkpoint_before_fetch(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        run = _prepare(session, crosswalk, digest)
        run_id = run.id
        session.execute(update(Listing).where(Listing.id == listing.id).values(ticker="CHANGED"))

    provider = SyntheticProvider()
    execute_market_data_bootstrap(
        postgres_engine,
        run_id,
        target_environment="development",
        crosswalk=crosswalk,
        crosswalk_sha256=digest,
        provider=provider,
        max_checkpoints=10,
        min_request_interval_seconds=0,
    )
    assert all(query.domain != ExternalDataDomain.MARKET_DATA for query in provider.calls)
    with Session(postgres_engine) as session:
        checkpoint = session.scalar(
            select(MarketDataBootstrapCheckpoint).where(
                MarketDataBootstrapCheckpoint.run_id == run_id,
                MarketDataBootstrapCheckpoint.subject_kind == "LISTING",
            )
        )
        assert checkpoint is not None
        assert checkpoint.status == "BLOCKED"
        assert checkpoint.failure_code == "CANONICAL_LISTING_IDENTITY_CHANGED"


def test_temporal_validation_rejects_future_observation_and_out_of_window_action() -> None:
    from types import SimpleNamespace

    retrieved_at = datetime(2026, 10, 6, tzinfo=UTC)
    plan = {
        "records": [SimpleNamespace(retrieved_at=retrieved_at)],
        "prices": [],
        "fx": [],
        "actions": [
            {
                "source_action_id": "synthetic-action",
                "observed_at": datetime(2026, 10, 7, tzinfo=UTC),
                "effective_date": datetime(2026, 9, 30, tzinfo=UTC),
            }
        ],
        "report": {},
    }
    issues = _temporal_issues(plan, start_date=START, end_date=END)
    assert {issue["code"] for issue in issues} == {
        "OBSERVATION_AFTER_RETRIEVAL",
        "ACTION_OUTSIDE_REQUESTED_WINDOW",
    }


def test_bootstrap_window_rejects_more_than_ten_years() -> None:
    from portfolio_api.market_data_bootstrap import _validate_date_window

    with pytest.raises(MarketDataBootstrapError, match="ten years"):
        _validate_date_window(date(2010, 1, 1), date(2026, 10, 5))


def test_market_bootstrap_cli_accepts_explicit_production_scope() -> None:
    args = _parser().parse_args(
        [
            "preview",
            "--target-environment",
            "production",
            "--start-date",
            START.isoformat(),
            "--end-date",
            END.isoformat(),
        ]
    )
    assert args.target_environment == "production"


@pytest.mark.parametrize(
    ("read_only", "expected"),
    ((False, "write"), (True, "read_only")),
)
def test_market_data_commands_use_target_preflight_for_operation_kind(
    monkeypatch: pytest.MonkeyPatch,
    read_only: bool,
    expected: str,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "portfolio_api.market_data_bootstrap.verify_database_read_only_preflight",
        lambda *_args, **_kwargs: calls.append("read_only"),
    )
    monkeypatch.setattr(
        "portfolio_api.market_data_bootstrap.verify_database_preflight",
        lambda *_args, **_kwargs: calls.append("write"),
    )
    _verify_target(
        None,  # type: ignore[arg-type]
        Settings(database_target_environment="production"),
        "production",
        read_only=read_only,
    )
    assert calls == [expected]


@pytest.mark.integration
def test_market_production_preview_reports_missing_canonical_import(
    postgres_engine: Engine,
) -> None:
    crosswalk, digest = _crosswalk(_mapping(uuid4(), uuid4(), uuid4()))
    with Session(postgres_engine) as session:
        report = preview_market_data_bootstrap(
            session,
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            start_date=START,
            end_date=END,
            target_environment="production",
        )

    assert report["status"] == "BLOCKED_CANONICAL_IMPORT"
    assert report["canonical_import_readiness"]["status"] == "MISSING"


@pytest.mark.integration
def test_market_bootstrap_production_scope_is_frozen_and_prioritizes_held_before_watchlist(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        held_company, held_security, held_listing = _seed_canonical_scope(session)
        watch_company_id, watch_security_id, watch_listing_id = uuid4(), uuid4(), uuid4()
        watch_company = Company(id=watch_company_id, name="Synthetic Watchlist Corporation")
        watch_security = Security(
            id=watch_security_id,
            company_id=watch_company_id,
            name="Synthetic Watchlist Common",
            security_type="COMMON_STOCK",
        )
        watch_listing = Listing(
            id=watch_listing_id,
            security_id=watch_security_id,
            venue="NASDAQ",
            ticker="WATCH",
            currency="USD",
        )
        watch_lifecycle = LifecycleEvent(
            id=uuid4(),
            company_id=watch_company_id,
            sequence=1,
            previous_state=None,
            new_state="WATCHLIST",
            effective_at=datetime(2026, 10, 1, tzinfo=UTC),
            actor="IMPORT",
            reason="Synthetic integration fixture",
            source="synthetic-test",
        )
        session.add(watch_company)
        session.flush()
        session.add(watch_security)
        session.flush()
        session.add(watch_listing)
        session.add(watch_lifecycle)
        session.flush()
        session.add(CurrentLifecycle(company_id=watch_company_id, event_id=watch_lifecycle.id))
        session.flush()
        held_mapping = _mapping(held_company.id, held_security.id, held_listing.id)
        watch_mapping = held_mapping.model_copy(
            update={
                "ticker": "WATCH",
                "provider_symbol": "WATCH",
                "canonical_company_id": watch_company_id,
                "canonical_security_id": watch_security_id,
                "canonical_listing_id": watch_listing_id,
            }
        )
        crosswalk, digest = _crosswalk(held_mapping)
        crosswalk = crosswalk.model_copy(update={"mappings": (held_mapping, watch_mapping)})
        digest = hashlib.sha256(crosswalk.model_dump_json().encode()).hexdigest()
        session.add(
            CanonicalBootstrapRun(
                id=uuid4(),
                input_digest="a" * 64,
                source_digest="b" * 64,
                portfolio_snapshot_run_id="1" * 32,
                market_snapshot_run_id="2" * 32,
                import_version="synthetic-test",
                observed_at=RETRIEVED_AT,
                recorded_at=RETRIEVED_AT,
                status="APPLIED",
                report={"reconciliation": {"status": "MATCHED"}, "source_gaps": []},
            )
        )
        session.flush()

        run = prepare_market_data_bootstrap(
            session,
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            start_date=START,
            end_date=END,
            target_environment="production",
        )

        frozen_listings = run.scope.get("listings")
        assert isinstance(frozen_listings, list)
        assert all(isinstance(item, dict) for item in frozen_listings)
        assert run.target_environment == "production"
        assert frozen_listings[0]["identity"]["listing_id"] == str(held_listing.id)
        assert frozen_listings[0]["priority_tier"] == "HELD"
        assert frozen_listings[1]["identity"]["listing_id"] == str(watch_listing_id)
        assert frozen_listings[1]["priority_tier"] == "WATCHLIST"
        first_checkpoint = _next_checkpoint(session, run, RETRIEVED_AT)
        assert first_checkpoint is not None
        assert first_checkpoint.listing_id == held_listing.id

        scoped_preview = preview_market_data_bootstrap(
            session,
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            start_date=START,
            end_date=END,
            target_environment="production",
            company_id=watch_company_id,
        )
        assert scoped_preview["selected_listing_count"] == 1
        assert scoped_preview["listing_priority_counts"]["WATCHLIST"] == 1


@pytest.mark.integration
def test_production_market_ingestion_stops_before_provider_without_reconciled_import(
    postgres_engine: Engine,
) -> None:
    company_id, security_id, listing_id, run_id = uuid4(), uuid4(), uuid4(), uuid4()
    crosswalk, digest = _crosswalk(_mapping(company_id, security_id, listing_id))
    with Session(postgres_engine) as session, session.begin():
        session.add(
            MarketDataBootstrapRun(
                id=run_id,
                input_digest="c" * 64,
                provider_id="YAHOO_FINANCE",
                provider_schema_version="yahoo-chart-v8",
                crosswalk_sha256=digest,
                target_environment="production",
                start_date=START,
                end_date=END,
                scope={"listings": []},
                status="PREPARED",
                prepared_at=RETRIEVED_AT,
                report={},
            )
        )

    provider = SyntheticProvider()
    with pytest.raises(
        MarketDataBootstrapError,
        match="requested target environment does not match",
    ):
        execute_market_data_bootstrap(
            postgres_engine,
            run_id,
            target_environment="rehearsal",
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            provider=provider,
            max_checkpoints=1,
            min_request_interval_seconds=0,
        )
    assert provider.calls == []
    with pytest.raises(
        MarketDataBootstrapError,
        match="requires a reconciled canonical portfolio import",
    ):
        execute_market_data_bootstrap(
            postgres_engine,
            run_id,
            target_environment="production",
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            provider=provider,
            max_checkpoints=1,
            min_request_interval_seconds=0,
        )
    assert provider.calls == []


def test_market_bootstrap_company_id_is_supported_for_bounded_scope() -> None:
    company_id = uuid4()
    args = _parser().parse_args(
        [
            "prepare",
            "--target-environment",
            "production",
            "--start-date",
            START.isoformat(),
            "--end-date",
            END.isoformat(),
            "--company-id",
            str(company_id),
        ]
    )
    assert args.company_id == company_id


def test_private_report_is_create_only_and_written_outside_the_repository(
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "synthetic-market-report.json"
    report = {"status": "COMPLETE", "provider_payload_hash": "a" * 64}

    _write_private_report(report_path, report)

    assert json.loads(report_path.read_text()) == report
    if os.name != "nt":
        assert report_path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(MarketDataBootstrapError, match="already exists"):
        _write_private_report(report_path, report)
