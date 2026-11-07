"""Read-only onboarding uses real domain validators with fictional model inputs."""

import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import ReadOnlySqlTransaction
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from synthetic_financial_fixtures import (
    dcf_fixture,
    owner_cash_flow_fixture,
    residual_income_fixture,
)
from test_google_sheets_sync import _publish_research_evidence
from test_model_publications import publication

from portfolio_api.bootstrap_preflight import BootstrapPreflightError
from portfolio_api.database_write_target import install_database_read_only_guard
from portfolio_api.main import create_app
from portfolio_api.model_publication_preflight import (
    PublicationPreflightError,
    load_publication,
    main,
    run_preflight,
)
from portfolio_api.settings import Settings
from portfolio_api.workbook_sources import WorkbookSourceError


@pytest.mark.parametrize(
    "payload,expected,code",
    [
        (b"{}", "0" * 64, "PUBLICATION_HASH_MISMATCH"),
        (b"{}", "bad", "PUBLICATION_HASH_INVALID"),
        (b"x" * 1_000_001, "0" * 64, "PUBLICATION_TOO_LARGE"),
    ],
    ids=["hash-mismatch", "invalid-hash", "size-bound"],
)
def test_bad_source_is_blocked_before_parsing_or_database_access(
    tmp_path: Path,
    payload: bytes,
    expected: str,
    code: str,
) -> None:
    source = tmp_path / "publication.json"
    source.write_bytes(payload)
    with patch("portfolio_api.model_publication_preflight.parse_portable_contract") as parse:
        with pytest.raises(PublicationPreflightError, match=code):
            load_publication(source, expected)
        parse.assert_not_called()


def test_cli_sanitizes_invalid_values_and_rejects_repository_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.json"
    source.write_text('{"private_assumption":"never-print-this"}', encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    args = [
        "inspect",
        "--publication",
        str(source),
        "--publication-sha256",
        digest,
        "--store",
        str(tmp_path / "store"),
    ]
    assert main(args) == 2
    output = capsys.readouterr().out
    assert "never-print-this" not in output and str(tmp_path) not in output
    assert json.loads(output)["status"] == "BLOCKED"
    with pytest.raises(WorkbookSourceError):
        load_publication(Path("AGENTS.md"), digest)


def inventory(engine: Engine) -> list[object]:
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
        tables: list[str] = [
            str(row[0])
            for row in connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname=:s ORDER BY tablename"),
                {"s": schema},
            ).all()
        ]
        counts = [
            (table, connection.scalar(text(f'SELECT count(*) FROM "{table}"'))) for table in tables
        ]
        sequences = connection.execute(
            text(
                "SELECT sequencename, last_value FROM pg_sequences "
                "WHERE schemaname=:s ORDER BY sequencename"
            ),
            {"s": schema},
        ).all()
        return [counts, sequences]


def test_cli_keeps_driver_errors_private(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch(
        "portfolio_api.model_publication_preflight.run_preflight",
        side_effect=RuntimeError("password=private-host-secret"),
    ):
        assert (
            main(
                [
                    "preview",
                    "--publication",
                    str(tmp_path / "source.json"),
                    "--publication-sha256",
                    "0" * 64,
                    "--store",
                    str(tmp_path),
                    "--target-environment",
                    "production",
                ]
            )
            == 2
        )
    output = capsys.readouterr().out
    assert json.loads(output) == {"status": "BLOCKED", "code": "PREFLIGHT_FAILED"}


@pytest.mark.integration
@pytest.mark.parametrize(
    "method",
    [
        "dcf",
        "owner-cash-flow",
        "residual-income",
    ],
)
def test_native_preflight_replay_and_mutation_rejection(
    postgres_engine: Engine,
    tmp_path: Path,
    method: str,
) -> None:
    fixtures = {
        "dcf": dcf_fixture,
        "owner-cash-flow": owner_cash_flow_fixture,
        "residual-income": residual_income_fixture,
    }
    with (
        patch("portfolio_api.main.create_database_engine", return_value=postgres_engine),
        TestClient(create_app(Settings(database_url=None))) as client,
    ):
        company = client.post("/v1/companies", json={"name": "Preflight fixture"}).json()
        security = client.post(
            f"/v1/companies/{company['id']}/securities",
            json={"name": "Fixture shares", "security_type": "COMMON_STOCK"},
        ).json()
        listing = client.post(
            f"/v1/securities/{security['id']}/listings",
            json={"venue": "NASDAQ", "ticker": "PREFLIGHT", "currency": "USD"},
        ).json()
        revision = {
            **copy.deepcopy(fixtures[method]()["input"]),
            "effective_at": datetime.now(UTC).isoformat(),
            "base_revision_id": None,
            "source_revision_id": None,
            "actor": "LOCAL_USER",
            "source": "Synthetic preflight",
            "rationale": "Synthetic accepted base.",
        }
        route = "financial-models" if method == "dcf" else f"canonical-financial-models/{method}"
        body = {
            "model_name": method,
            "valuation_listing_id": listing["id"],
            "model_currency": "USD",
            "initial_revision": revision,
        }
        if method == "dcf":
            body["model_type"] = "UFCF_DCF_10Y_FADE"
        response = client.post(f"/v1/companies/{company['id']}/{route}", json=body)
        assert response.status_code == 201, response.text
        model = response.json()
        evidence_id, _ = _publish_research_evidence(
            client,
            company_id=company["id"],
            security_id=security["id"],
            observed_at=datetime.now(UTC),
            stream_key="preflight-fixture",
        )
        prefix = "financial-models" if method == "dcf" else "canonical-financial-models"
        contract = client.get(f"/v1/{prefix}/{model['id']}/contract").json()
        contract["proposal"] = {
            "author_id": "fixture-agent",
            "authored_at": datetime.now(UTC).isoformat(),
            "source_reference": "https://example.test/evidence",
        }
        contract["supporting_evidence"] = [
            {
                "evidence_type": "RESEARCH_REVISION",
                "reference_id": evidence_id,
                "relationship": "SUPPORTS",
            }
        ]
        contract["candidate_revision"]["source_revision_id"] = "preflight-r2"
        contract["candidate_revision"]["rationale"] = "Evidence-backed synthetic change."
        candidate = contract["candidate_revision"]
        if method == "dcf":
            candidate["scenarios"][1]["years"][0]["revenue_growth"] = "0.21"
        elif method == "owner-cash-flow":
            candidate["owner_cash_flow"]["scenarios"][1]["years"][0]["owner_cash_flow_margin"] = (
                "0.052"
            )
        else:
            candidate["residual_income"]["scenarios"][1]["starting_roe"] = "0.156"
        preview = client.post(f"/v1/{prefix}/{model['id']}/contract/preview", json=contract).json()
        item = publication(contract, preview["calculated_outputs"])

    source = tmp_path / "publication.json"
    store = tmp_path / "store"

    def freeze(value: object) -> str:
        source.write_text(json.dumps(value), encoding="utf-8")
        return hashlib.sha256(source.read_bytes()).hexdigest()

    digest = freeze(item)
    baseline = inventory(postgres_engine)
    with postgres_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    settings = Settings(
        database_url=postgres_engine.url.render_as_string(hide_password=False),
        app_env="development",
        database_target_environment="development",
        database_target_database=postgres_engine.url.database,
        database_production_writes_authorized=False,
        neon_project_id="inherited-production-project",
        neon_branch_id="inherited-production-branch",
        neon_endpoint_id="inherited-production-endpoint",
    )

    def read_engine(*args: object, **kwargs: object) -> Engine:
        assert kwargs == {"read_only": True}
        engine = create_engine(
            postgres_engine.url,
            connect_args={
                "options": f"-c search_path={schema} -c default_transaction_read_only=on"
            },
            hide_parameters=True,
        )
        install_database_read_only_guard(engine, settings)
        return engine

    def run(expected: str) -> dict[str, object]:
        return run_preflight(
            source=source,
            expected_sha256=expected,
            store_root=store,
            target_environment="development",
            settings=settings,
        )

    def report(result: dict[str, object]) -> dict[str, object]:
        data = json.loads(
            (store / "model-publication-preflight" / "runs" / f"{result['run_id']}.json").read_text(
                encoding="utf-8"
            )
        )

        return cast(dict[str, object], data)

    with patch(
        "portfolio_api.model_publication_preflight.create_database_engine", side_effect=read_engine
    ):
        first, second = run(digest), run(digest)
        assert first["status"] == second["status"] == "READY_FOR_REVIEW"
        assert first["acceptance_authorized"] is False
        target = report(first)["target"]
        assert isinstance(target, dict)
        assert target["provider"] == "local_postgresql"
        assert target["project_id"] is target["branch_id"] is target["endpoint_id"] is None
        assert report(first)["preview"] == report(second)["preview"]
        assert report(first)["publication_json"] == source.read_text(encoding="utf-8")
        assert (
            hashlib.sha256(str(report(first)["publication_json"]).encode("utf-8")).hexdigest()
            == digest
        )
        with patch(
            "portfolio_api.model_publication_preflight.preview_publication"
        ) as domain_preview:
            with pytest.raises(BootstrapPreflightError):
                run_preflight(
                    source=source,
                    expected_sha256=digest,
                    store_root=store,
                    target_environment="production",
                    settings=settings,
                )
            domain_preview.assert_not_called()
        wrong_value = copy.deepcopy(item)
        values = wrong_value["published_fair_values"]
        assert isinstance(values, dict)
        values["weighted_fv"] = "1"
        assert run(freeze(wrong_value))["status"] == "INVALID"
        changed = copy.deepcopy(contract)
        new_base = str(uuid4())
        if method == "dcf":
            changed["base_revision"]["revision_id"] = new_base
            changed["base_calculation"]["revision_id"] = new_base
            changed["base_calculation"]["outputs"]["revision_id"] = new_base
        else:
            changed["base_revision_id"] = new_base
        assert (
            run(freeze(publication(changed, preview["calculated_outputs"])))["status"] == "CONFLICT"
        )
        changed = copy.deepcopy(contract)
        if method == "dcf":
            changed["model"]["model_id"] = str(uuid4())
        else:
            changed["model_id"] = str(uuid4())
        assert (
            run(freeze(publication(changed, preview["calculated_outputs"])))["status"]
            == "MISSING_CANONICAL_MODEL"
        )

        # Guard backstop: an accidental mutation in a reused validator is rejected.
        def mutate(session: Session, *args: object) -> None:
            session.execute(text("DELETE FROM financial_model_revisions"))

        freeze(item)
        with patch(
            "portfolio_api.model_publication_preflight.preview_portable_contract",
            side_effect=mutate,
        ):
            from portfolio_api.database_write_target import DatabaseReadOnlyError

            with pytest.raises(DatabaseReadOnlyError):
                run(digest)
        # PostgreSQL itself also rejects a mutation even without the SQLAlchemy hook.
        engine = read_engine(read_only=True)
        try:
            with engine.connect() as connection:
                driver = connection.connection.driver_connection
                assert driver is not None
                with driver.cursor() as cursor, pytest.raises(ReadOnlySqlTransaction):
                    cursor.execute("CREATE TABLE forbidden_write(id integer)")
        finally:
            engine.dispose()
    assert inventory(postgres_engine) == baseline
    with patch(
        "portfolio_api.model_publication_preflight.create_database_engine",
        side_effect=AssertionError("offline inspection connected"),
    ):
        assert (
            run_preflight(
                source=source, expected_sha256=digest, store_root=store, target_environment=None
            )["status"]
            == "SCHEMA_VALID"
        )
