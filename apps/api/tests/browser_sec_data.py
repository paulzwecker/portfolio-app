"""Synthetic SEC provider evidence for the real read-only browser fixture."""

import json
from unittest.mock import patch
from urllib.error import URLError
from uuid import UUID, uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_fundamentals_bootstrap import (
    CIK,
    MAIN_SUBMISSIONS,
    SyntheticSecProvider,
    _execute,
    _facts_record,
)

from portfolio_api.domain.models import Company
from portfolio_api.external_data import ExternalDataDomain
from portfolio_api.external_ingestion import run_scheduled
from portfolio_api.fundamentals_bootstrap import prepare_fundamentals_bootstrap
from portfolio_api.reported_fundamentals import record_cik_mapping
from portfolio_api.settings import Settings


def prepare_sec_data(engine: Engine, metadata: dict[str, object], scenario: str) -> None:
    metadata["scenario"] = scenario
    metadata["provider_request_count"] = 0
    if scenario == "sec-unmapped":
        return
    company_id = UUID(str(metadata["company_id"]))
    portfolio_id = UUID(str(metadata["portfolio_id"]))
    with Session(engine) as session, session.begin():
        record_cik_mapping(
            session,
            company_id,
            CIK,
            "Synthetic Holdings Inc.",
            "https://www.sec.gov/edgar/browse/?CIK=1",
        )
        run = prepare_fundamentals_bootstrap(
            session, target_environment="rehearsal", portfolio_id=portfolio_id
        )
        run_id = run.id
    provider = SyntheticSecProvider()
    _execute(engine, run_id, provider, 10)
    metadata["provider_request_count"] = len(provider.calls)
    if scenario == "sec-outage":
        with Session(engine) as session, session.begin():
            retry = prepare_fundamentals_bootstrap(
                session, target_environment="rehearsal", portfolio_id=portfolio_id
            )
            retry_id = retry.id
        failed = SyntheticSecProvider(fail_first_source_request=True)
        _execute(engine, retry_id, failed, 1)
        metadata["provider_request_count"] = len(provider.calls) + len(failed.calls)
    if scenario.startswith("sec-refresh-"):
        if scenario == "sec-refresh-partial":
            with Session(engine) as session, session.begin():
                other = Company(name="Synthetic secondary issuer", reporting_currency="USD")
                session.add(other)
                session.flush()
                record_cik_mapping(
                    session,
                    other.id,
                    "0000000002",
                    "Other Synthetic Inc.",
                    "https://www.sec.gov/edgar/browse/?CIK=2",
                )
                issuer_ids = {company_id, other.id}
        else:
            issuer_ids = {company_id}
        requests = 0

        def download(url: str, _agent: str) -> bytes:
            nonlocal requests
            requests += 1
            if scenario == "sec-refresh-outage":
                raise URLError("Synthetic SEC refresh outage")
            payload = _facts_record().payload if "companyfacts" in url else MAIN_SUBMISSIONS.payload
            assert payload is not None
            data = json.loads(payload)
            if "CIK0000000002" in url:
                data = json.loads(payload.decode().replace(CIK, "0000000002"))
                data["cik"] = 2
                data["entityName" if "companyfacts" in url else "name"] = "Other Synthetic Inc."
            return json.dumps(data).encode()

        with (
            patch("portfolio_api.reported_fundamentals._download_sec_json", download),
            patch("portfolio_api.source_documents._download_sec_json", download),
            patch("portfolio_api.external_ingestion.time.sleep"),
            Session(engine) as session,
        ):
            run_scheduled(
                session,
                Settings(_env_file=None, sec_user_agent="Synthetic App test@example.invalid"),
                domains=[
                    ExternalDataDomain.REPORTED_FUNDAMENTALS,
                    ExternalDataDomain.SOURCE_DOCUMENTS,
                ],
                company_ids=issuer_ids,
                request_nonce=uuid4(),
                sec_research_scope=True,
            )
            session.commit()
        metadata["provider_request_count"] = len(provider.calls) + requests
