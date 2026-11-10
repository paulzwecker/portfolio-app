"""Synthetic SEC issuer review: explicit identity, no source inference."""

import json
import sys
from uuid import uuid4

import pytest
from browser_server import fixture_read_engine, fixture_settings
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from portfolio_api import reported_fundamentals
from portfolio_api.domain.models import Company, CompanyProviderIdentifier
from portfolio_api.fundamentals_bootstrap import preview_fundamentals_bootstrap
from portfolio_api.reported_fundamentals import preview_cik_mapping, record_cik_mapping


@pytest.mark.integration
def test_cli_preview_checks_target_and_never_writes(
    postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    issuer_id = uuid4()
    with Session(postgres_engine) as session, session.begin():
        session.add(Company(id=issuer_id, name="Synthetic canonical issuer"))
        schema = session.scalar(text("SELECT current_schema()"))
    assert schema is not None
    settings = fixture_settings().model_copy(
        update={"database_target_database": postgres_engine.url.database}
    )
    calls: list[bool] = []

    def create_reader(_settings: object, **kwargs: object) -> Engine:
        calls.append(kwargs.get("read_only") is True)
        return fixture_read_engine(postgres_engine.url, schema, settings)

    monkeypatch.setattr(reported_fundamentals, "Settings", lambda: settings)
    monkeypatch.setattr(reported_fundamentals, "create_database_engine", create_reader)
    args = [
        "reported_fundamentals",
        "map-preview",
        "--target-environment",
        "development",
        "--company-id",
        str(issuer_id),
        "--cik",
        "0000000001",
        "--provider-company-name",
        "Synthetic issuer",
        "--evidence-source",
        "https://www.sec.gov/edgar/browse/?CIK=0000000001",
    ]
    monkeypatch.setattr(sys, "argv", args)
    assert reported_fundamentals._run_cli() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PROPOSED"
    args[3] = "production"
    assert reported_fundamentals._run_cli() == 1
    assert "does not match" in capsys.readouterr().err
    assert calls == [True, True]
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(CompanyProviderIdentifier)) == 0


@pytest.mark.integration
def test_explicit_issuer_review_and_recording_fail_closed_on_conflicts(
    postgres_engine: Engine,
) -> None:
    issuer_id, other_id = uuid4(), uuid4()
    cik = "0000000001"
    name = "Synthetic Issuer Inc."
    evidence = "https://www.sec.gov/edgar/browse/?CIK=0000000001"
    with Session(postgres_engine) as session, session.begin():
        session.add_all(
            [
                Company(id=issuer_id, name="Synthetic canonical issuer"),
                Company(id=other_id, name="Other synthetic issuer"),
            ]
        )
    with Session(postgres_engine) as session:
        proposed = preview_cik_mapping(session, issuer_id, cik, name, evidence)
        assert proposed["status"] == "PROPOSED"
        assert proposed["canonical_company_name"] == "Synthetic canonical issuer"
        assert proposed["evidence_validation"] == "URL_STRUCTURE_ONLY"
        assert proposed["review_required"] is True
        assert proposed["database_writes"] == proposed["provider_requests"] == 0
        assert session.scalar(select(func.count()).select_from(CompanyProviderIdentifier)) == 0
        first = record_cik_mapping(session, issuer_id, cik, name, evidence)
        assert record_cik_mapping(session, issuer_id, cik, name, evidence).id == first.id
        assert preview_cik_mapping(session, issuer_id, cik, name, evidence)["status"] == "EXISTING"
        assert (
            preview_fundamentals_bootstrap(session, target_environment="rehearsal")[
                "mapped_company_count"
            ]
            == 1
        )
        for target, proposed_cik, proposed_name, source in [
            (other_id, cik, name, evidence),
            (
                issuer_id,
                "0000000002",
                "Different issuer",
                "https://www.sec.gov/edgar/browse/?CIK=2",
            ),
            (issuer_id, cik, "Changed issuer name", evidence),
            (issuer_id, cik, name, "https://www.sec.gov/Archives/edgar/data/1/index.html"),
        ]:
            with pytest.raises(ValueError):
                preview_cik_mapping(session, target, proposed_cik, proposed_name, source)
            with pytest.raises(ValueError):
                record_cik_mapping(session, target, proposed_cik, proposed_name, source)
        assert session.scalar(select(func.count()).select_from(CompanyProviderIdentifier)) == 1
        session.commit()


@pytest.mark.integration
def test_issuer_evidence_requires_exact_sec_identity_without_writes(
    postgres_engine: Engine,
) -> None:
    issuer_id = uuid4()
    with Session(postgres_engine) as session:
        session.add(Company(id=issuer_id, name="Synthetic canonical issuer"))
        session.flush()
        bad_sources = [
            "https://sec.gov.evil.example/edgar/browse/?CIK=1",
            "https://user@www.sec.gov/edgar/browse/?CIK=1",
            "https://www.sec.gov:444/edgar/browse/?CIK=1",
            "https://www.sec.gov/edgar/browse/?CIK=2",
            "https://www.sec.gov/search?q=0000000001",
            "http://www.sec.gov/edgar/browse/?CIK=1",
        ]
        for source in bad_sources:
            with pytest.raises(ValueError, match="SEC.gov issuer URL"):
                record_cik_mapping(session, issuer_id, "0000000001", "Synthetic issuer", source)
        assert session.scalar(select(func.count()).select_from(CompanyProviderIdentifier)) == 0
        assert (
            preview_cik_mapping(
                session,
                issuer_id,
                "0000000001",
                "Synthetic issuer",
                "https://www.sec.gov/Archives/edgar/data/1/filing.html",
            )["status"]
            == "PROPOSED"
        )
