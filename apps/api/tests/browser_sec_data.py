"""Synthetic SEC provider evidence for the real read-only browser fixture."""

from uuid import UUID

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from test_fundamentals_bootstrap import CIK, SyntheticSecProvider, _execute

from portfolio_api.fundamentals_bootstrap import prepare_fundamentals_bootstrap
from portfolio_api.reported_fundamentals import record_cik_mapping


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
