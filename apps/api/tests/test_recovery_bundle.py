import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text
from test_postgres_migration import _insert_synthetic_portfolio, migration_databases  # noqa: F401

from portfolio_api import postgres_migration as pg
from portfolio_api import recovery_bundle as recovery


def test_recovery_native_tools_are_read_only() -> None:
    from sqlalchemy.engine import make_url

    url = make_url("postgresql://user:secret@source.neon.tech/neondb?sslmode=verify-full")
    endpoint = pg.DatabaseEndpoint(
        "recovery_source", url, "source.neon.tech", 5432, "neondb", "user", "public"
    )
    env = pg._native_tool_environment(endpoint)
    assert "default_transaction_read_only=on" in env["PGOPTIONS"]
    assert env["PGSSLMODE"] == "verify-full"


def test_production_backup_requires_explicit_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_TARGET_ENVIRONMENT", raising=False)
    with pytest.raises(pg.MigrationToolError, match="explicit production"):
        recovery.production_source()


def test_production_backup_uses_existing_read_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_TARGET_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://user:secret@source.neon.tech/neondb?sslmode=verify-full",
    )
    engine = Mock()
    factory = Mock(return_value=engine)
    guard = Mock(side_effect=pg.MigrationToolError("identity mismatch"))
    monkeypatch.setattr(recovery, "create_database_engine", factory)
    monkeypatch.setattr(recovery, "verify_database_read_only_preflight", guard)
    with pytest.raises(pg.MigrationToolError, match="identity mismatch"):
        recovery.production_source()
    assert factory.call_args.kwargs == {"read_only": True}
    guard.assert_called_once_with(
        engine,
        configured_target_environment="production",
        requested_target_environment="production",
    )
    engine.dispose.assert_called_once()


def test_backup_rejects_noninteractive_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "recovery",
            "backup",
            "--source",
            "production",
            "--output",
            str(tmp_path / "out.age"),
            "--staging-root",
            str(tmp_path),
            "--recipient",
            "age1test",
        ],
    )
    monkeypatch.setattr(recovery, "production_source", Mock())
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    backup = Mock()
    monkeypatch.setattr(recovery, "create_bundle", backup)
    assert recovery.main() == 2
    backup.assert_not_called()
    assert not (tmp_path / "out.age").exists()


@pytest.mark.integration
def test_encrypted_recovery_roundtrip(migration_databases: dict[str, Any], tmp_path: Path) -> None:  # noqa: F811
    if not shutil.which("age") or not shutil.which("age-keygen"):
        if os.environ.get("CI"):
            pytest.fail("CI must install age and age-keygen for the recovery rehearsal")
        pytest.skip("Install age and age-keygen for encrypted recovery integration")
    key = tmp_path / "identity.txt"
    generated = subprocess.run(["age-keygen", "-o", str(key)], capture_output=True, check=True)
    assert generated.returncode == 0
    recipient = (
        subprocess.run(["age-keygen", "-y", str(key)], capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )
    _insert_synthetic_portfolio(migration_databases["source_url"])
    # Exercise the production export role on an explicitly disposable local source.
    # Live identity verification is separately tested; never impersonate a Neon host.
    source = replace(
        pg.endpoint_from_environment("source"), role="recovery_source", test_target=False
    )
    output = tmp_path / "protected.age"
    recovery.create_bundle(source, output, tmp_path, recipient)
    assert output.read_bytes().startswith(b"age-encryption.org/v1")
    assert not list(tmp_path.glob("recovery-*"))
    with pytest.raises(pg.MigrationToolError, match="exists"):
        recovery.create_bundle(source, output, tmp_path, recipient)
    wrong_key = tmp_path / "wrong-key.txt"
    subprocess.run(["age-keygen", "-o", str(wrong_key)], capture_output=True, check=True)
    with pytest.raises(pg.MigrationToolError):
        recovery.unseal(output, tmp_path / "wrong", wrong_key)
    assert not (tmp_path / "wrong").exists()
    corrupted = tmp_path / "corrupt.age"
    corrupted.write_bytes(output.read_bytes()[:-20])
    with pytest.raises(pg.MigrationToolError):
        recovery.unseal(corrupted, tmp_path / "bad", key)
    assert not (tmp_path / "bad").exists()
    stage = tmp_path / "decrypted"
    recovery.unseal(output, stage, key)
    with pytest.raises(FileExistsError):
        recovery.unseal(output, stage, key)
    assert (stage / "database.dump").is_file()
    access = json.loads((stage / "access.json").read_text())
    assert access["roles"] and access["relations"]
    assert "rolpassword" not in (stage / "access.json").read_text()
    target = pg.endpoint_from_environment("target")
    result = pg.restore(
        stage / "database.dump", target, confirmation=f"RESTORE {target.host}/{target.database}"
    )
    assert result["status"] == "RESTORED_AND_RECONCILED"
    assert result["data_differences"] == {"table_differences": {}, "sequence_differences": {}}
    engine = create_engine(migration_databases["source_url"])
    try:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE public.companies ENABLE ROW LEVEL SECURITY"))
        with pytest.raises(pg.MigrationToolError, match="RLS"):
            recovery.access_inventory(source)
    finally:
        engine.dispose()
