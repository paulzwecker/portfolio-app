"""Read-only market scope inspection through the authenticated API."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import pytest
from browser_server import fixture_application, fixture_read_engine, fixture_settings
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_market_data_bootstrap import _crosswalk, _mapping, _prepare, _seed_canonical_scope

from portfolio_api.domain.models import (
    HoldingPosition,
    HoldingSnapshot,
    Listing,
    MarketDataBootstrapRun,
    Security,
)
from portfolio_api.market_data_bootstrap import preview_market_data_bootstrap


@pytest.mark.integration
def test_scope_preview_is_authenticated_read_only_and_never_prepares(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        listing_id, security_id, company_id = str(listing.id), str(security.id), str(company.id)
        schema = str(session.scalar(text("SELECT current_schema()")))

    monkeypatch.setattr(
        "portfolio_api.domain.routes._load_crosswalk", lambda _: (crosswalk, digest)
    )
    modes: list[tuple[object, object]] = []

    def checked_preview(session: Session, **kwargs: Any) -> dict[str, Any]:
        modes.append(
            (
                session.scalar(text("SHOW transaction_read_only")),
                session.scalar(text("SHOW transaction_isolation")),
            )
        )
        return preview_market_data_bootstrap(session, **kwargs)

    monkeypatch.setattr(
        "portfolio_api.domain.routes.preview_market_data_bootstrap", checked_preview
    )
    settings = fixture_settings().model_copy(
        update={"app_env": "preview", "api_access_token": SecretStr("synthetic-preview-token")}
    )
    reader = fixture_read_engine(postgres_engine.url, schema, settings)
    try:
        with TestClient(fixture_application(reader, settings)) as client:
            path = "/v1/market-data/bootstrap-scope?start_date=2026-10-01&end_date=2026-10-05"
            assert client.get(path).status_code == 401
            headers = {"x-api-access-token": "synthetic-preview-token"}
            response = client.get(path, headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "READY"
            assert data["selected_listing_count"] == data["verified_listing_mapping_count"] == 1
            assert data["listing_review"] == [
                {
                    "listing_id": listing_id,
                    "security_id": security_id,
                    "company_id": company_id,
                    "company_name": "Synthetic Example Corporation",
                    "venue": "NASDAQ",
                    "ticker": "SYNTH",
                    "currency": "USD",
                    "security_type": "COMMON_STOCK",
                    "priority": "HELD",
                    "held_quantity": "2.5000000000",
                    "mapping_verified": True,
                    "provider_symbol": "SYNTH",
                }
            ]
            assert data["omitted_listing_count"] == 0
            assert data["holdings_snapshot"]["completeness"] == "COMPLETE"
            assert data["listing_priority_counts"]["HELD"] == 1
            assert data["required_fx_pairs"] == ["USD/EUR"]
            assert data["provider_requests_planned"] == 2
            assert data["provider_requests"] == data["database_writes"] == 0
            assert client.post(path, headers=headers).status_code == 405
            invalid = client.get(
                "/v1/market-data/bootstrap-scope?start_date=2026-10-05&end_date=2026-10-01",
                headers=headers,
            )
            assert invalid.status_code == 422
        assert modes == [("on", "repeatable read")]
        monkeypatch.setattr(
            "portfolio_api.domain.routes._load_crosswalk",
            lambda _: (crosswalk.model_copy(update={"mappings": ()}), digest),
        )
        with TestClient(fixture_application(reader, settings)) as client:
            unmatched = client.get(path, headers=headers).json()
            assert unmatched["status"] == "BLOCKED"
            assert unmatched["listing_review"][0]["mapping_verified"] is False
            assert unmatched["listing_review"][0]["provider_symbol"] is None
            assert unmatched["unresolved_listings"][0]["subject_key"] == listing_id
            monkeypatch.setattr("portfolio_api.market_data_bootstrap.SCOPE_REVIEW_LISTING_LIMIT", 0)
            bounded = client.get(path, headers=headers).json()
            assert bounded["listing_review"] == []
            assert bounded["omitted_listing_count"] == bounded["selected_listing_count"] == 1
        production_settings = settings.model_copy(
            update={"database_target_environment": "production"}
        )
        with TestClient(fixture_application(reader, production_settings)) as client:
            blocked = client.get(path, headers=headers)
            assert blocked.status_code == 200
            assert blocked.json()["status"] == "BLOCKED_CANONICAL_IMPORT"
            assert blocked.json()["canonical_import_readiness"]["ready"] is False
        with Session(postgres_engine) as session:
            assert session.scalar(select(func.count()).select_from(MarketDataBootstrapRun)) == 0
    finally:
        reader.dispose()


@pytest.mark.integration
def test_review_identities_match_the_guarded_manifest_including_unmapped_funds(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session, session.begin():
        company, security, listing = _seed_canonical_scope(session)
        crosswalk, digest = _crosswalk(_mapping(company.id, security.id, listing.id))
        fund = Security(name="Synthetic fund", security_type="ETF", company_id=None)
        session.add(fund)
        session.flush()
        fund_listing = Listing(security_id=fund.id, venue="XNAS", ticker="FUND", currency=None)
        session.add(fund_listing)
        session.flush()
        original_snapshot = session.scalar(select(HoldingSnapshot))
        assert original_snapshot is not None
        snapshot = HoldingSnapshot(
            portfolio_id=original_snapshot.portfolio_id,
            effective_at=datetime(2026, 10, 7, tzinfo=UTC),
            completeness="PARTIAL",
            actor="IMPORT",
            reason="Synthetic partial evidence",
            source="synthetic-test",
        )
        session.add(snapshot)
        session.flush()
        unknown_listing = Listing(
            security_id=fund.id, venue="XNAS", ticker="UNKNOWN", currency="USD"
        )
        tiny_listing = Listing(security_id=fund.id, venue="XNAS", ticker="TINY", currency="USD")
        session.add_all([unknown_listing, tiny_listing])
        session.flush()
        session.info["new_snapshot_ids"] = {snapshot.id}
        try:
            session.add_all(
                [
                    HoldingPosition(
                        snapshot_id=snapshot.id, listing_id=listing.id, quantity=Decimal("2.5")
                    ),
                    HoldingPosition(
                        snapshot_id=snapshot.id, listing_id=fund_listing.id, quantity=Decimal("0")
                    ),
                    HoldingPosition(
                        snapshot_id=snapshot.id, listing_id=unknown_listing.id, quantity=None
                    ),
                    HoldingPosition(
                        snapshot_id=snapshot.id,
                        listing_id=tiny_listing.id,
                        quantity=Decimal("0.0000000001"),
                    ),
                ]
            )
            session.flush()
        finally:
            session.info.pop("new_snapshot_ids", None)

        preview = preview_market_data_bootstrap(
            session,
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 5),
            target_environment="development",
            include_listing_review=True,
        )
        run = _prepare(session, crosswalk, digest)
        manifest = cast(list[dict[str, Any]], run.scope["listings"])
        assert preview["omitted_listing_count"] == 0
        assert preview["holdings_snapshot"]["completeness"] == "PARTIAL"
        assert [row["listing_id"] for row in preview["listing_review"]] == [
            row["identity"]["listing_id"] for row in manifest
        ]
        assert [row["provider_symbol"] for row in preview["listing_review"]] == [
            row["mapping"]["provider_symbol"] if row["mapping"] else None for row in manifest
        ]
        unmapped_fund = next(row for row in preview["listing_review"] if row["ticker"] == "FUND")
        assert unmapped_fund["company_id"] is unmapped_fund["company_name"] is None
        assert unmapped_fund["currency"] is None and unmapped_fund["mapping_verified"] is False
        assert unmapped_fund["held_quantity"] == "0.0000000000"
        assert (
            next(row for row in preview["listing_review"] if row["ticker"] == "TINY")[
                "held_quantity"
            ]
            == "0.0000000001"
        )
        assert (
            next(row for row in preview["listing_review"] if row["ticker"] == "UNKNOWN")[
                "held_quantity"
            ]
            is None
        )
        assert preview["status"] == run.status == "BLOCKED"


@pytest.mark.integration
def test_review_reports_missing_snapshot_without_inventing_holdings(
    postgres_engine: Engine,
) -> None:
    crosswalk, digest = _crosswalk(_mapping(uuid4(), uuid4(), uuid4()))
    with Session(postgres_engine) as session:
        report = preview_market_data_bootstrap(
            session,
            crosswalk=crosswalk,
            crosswalk_sha256=digest,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 5),
            target_environment="development",
            include_listing_review=True,
        )
        assert report["holdings_snapshot"] is None
        assert report["listing_review"] == []
        assert report["listing_priority_counts"]["HELD"] == 0
        assert report["status"] == "BLOCKED"
