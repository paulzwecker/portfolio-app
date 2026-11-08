"""Fictional portfolio facts imported through the real bounded Yahoo pipeline."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlsplit

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_cloud_market_refresh import source_payload
from test_market_data_bootstrap import _mapping

from portfolio_api.domain import schemas as s
from portfolio_api.domain import services
from portfolio_api.domain.models import Actor, Listing, Security
from portfolio_api.market_data_startup import run_cloud_incremental_refresh
from portfolio_api.settings import Settings
from portfolio_api.yahoo_finance import (
    YahooFinanceProvider,
    YahooListingCrosswalk,
    YahooListingMapping,
)

PortfolioDataState = Literal["unpriced", "fx-outage", "valued"]


def prepare_portfolio_data(
    engine: Engine, directory: Path, state: PortfolioDataState, settings: Settings
) -> dict[str, object]:
    at = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        company = services.create_company(
            session, s.CompanyCreate(name="Synthetic Example Corporation", reporting_currency="USD")
        )
        stock = services.create_security(
            session,
            company.id,
            s.SecurityCreate(name="Synthetic Common", security_type="COMMON_STOCK"),
        )
        listing = services.create_listing(
            session, stock.id, s.ListingCreate(ticker="SYNTH", venue="NASDAQ", currency="USD")
        )
        fund = Security(name="Synthetic Global ETF", security_type="ETF", company_id=None)
        session.add(fund)
        session.flush()
        fund_listing = Listing(security_id=fund.id, ticker="SYNF", venue="XETRA", currency="EUR")
        session.add(fund_listing)
        session.flush()
        portfolio = services.create_portfolio(
            session, s.PortfolioCreate(name="Synthetic Daily Data Portfolio", base_currency="EUR")
        )
        snapshot = services.record_holdings(
            session,
            portfolio.id,
            s.SnapshotCreate(
                actor=Actor.IMPORT,
                reason="Fictional browser rehearsal",
                source="browser-market-fixture-v1",
                effective_at=at - timedelta(days=1),
                completeness="COMPLETE",
                positions=[
                    s.PositionInput(listing_id=listing.id, quantity=Decimal("2.5")),
                    s.PositionInput(listing_id=fund_listing.id, quantity=Decimal("1")),
                ],
                cash_positions=[
                    s.CashInput(currency="EUR", balance=Decimal("10")),
                    s.CashInput(currency="USD", balance=Decimal("5")),
                ],
            ),
        )
        target = services.create_targets(
            session,
            portfolio.id,
            s.TargetCreate(
                actor=Actor.IMPORT,
                reason="Fictional independent targets",
                source="browser-market-fixture-v1",
                effective_at=at - timedelta(days=1),
                allocations=[s.AllocationInput(company_id=company.id, weight=Decimal("0.5"))],
            ),
        )
        services.accept_targets(session, portfolio.id, target.id)
        crosswalk = YahooListingCrosswalk(
            provider_id="YAHOO_FINANCE",
            provider_schema_version="yahoo-chart-v8",
            verified_at=at,
            mappings=(
                _mapping(company.id, stock.id, listing.id),
                YahooListingMapping(
                    venue="XETRA",
                    ticker="SYNF",
                    currency="EUR",
                    security_type="ETF",
                    provider_symbol="SYNF.DE",
                    provider_exchange_code="GER",
                    provider_exchange_name="XETRA",
                    provider_instrument_type="ETF",
                    mapping_basis="SYNTHETIC_TEST_FIXTURE",
                    verification_status="VERIFIED",
                    canonical_security_id=fund.id,
                    canonical_listing_id=fund_listing.id,
                ),
            ),
        )
        identity = {
            "company_id": str(company.id),
            "portfolio_id": str(portfolio.id),
            "snapshot_id": str(snapshot.id),
            "target_revision_id": str(target.id),
            "stock_listing_id": str(listing.id),
            "fund_listing_id": str(fund_listing.id),
        }
    path = directory / "synthetic-crosswalk.json"
    raw = crosswalk.model_dump_json().encode()
    path.write_bytes(raw)
    calls: list[str] = []

    def transport(url: str) -> bytes:
        parsed = urlsplit(url)
        symbol = unquote(parsed.path.rsplit("/", 1)[-1])
        parameters = parse_qs(parsed.query)
        assert symbol in {"SYNTH", "SYNF.DE", "EUR=X"}
        assert int(parameters["period2"][0]) - int(parameters["period1"][0]) == 90 * 86400
        calls.append(symbol)
        if symbol == "EUR=X" and state == "fx-outage":
            raise URLError("Synthetic FX outage")
        if symbol != "SYNF.DE":
            return source_payload(symbol, at)
        payload = json.loads(source_payload("SYNTH", at))
        result = payload["chart"]["result"][0]
        result["meta"].update(
            symbol=symbol,
            currency="EUR",
            exchangeName="GER",
            fullExchangeName="XETRA",
            instrumentType="ETF",
            exchangeTimezoneName="Europe/Berlin",
            regularMarketPrice=100,
        )
        result["indicators"] = {
            "quote": [{"close": [99, 100], "volume": [1200, 1300]}],
            "adjclose": [{"adjclose": [99, 100]}],
        }
        return json.dumps(payload).encode()

    def provider(mapping: YahooListingCrosswalk) -> YahooFinanceProvider:
        return YahooFinanceProvider(mapping, transport=transport, retries=0)

    status: object = "UNAVAILABLE"
    if state != "unpriced":
        with (
            patch("portfolio_api.market_data_startup.CROSSWALK_PATH", path),
            patch("portfolio_api.external_ingestion.YahooFinanceProvider", provider),
            Session(engine) as session,
        ):
            status = run_cloud_incremental_refresh(session, settings, at)["status"]
        assert status == ("FAILED" if state == "fx-outage" else "COMPLETE")
        assert len(calls) == 3
    return {
        **identity,
        "scenario": state,
        "ingestion_status": status,
        "crosswalk_sha256": hashlib.sha256(raw).hexdigest(),
        "provider_request_count": len(calls),
    }
