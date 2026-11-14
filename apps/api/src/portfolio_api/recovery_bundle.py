"""Operator-only encrypted recovery bundles; no scheduler or production restore."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url

from portfolio_api import postgres_migration as pg
from portfolio_api.bootstrap_preflight import verify_database_read_only_preflight
from portfolio_api.database import create_database_engine
from portfolio_api.settings import Settings

MEMBERS = ("database.dump", "database.dump.manifest.json", "access.json")


def production_source() -> pg.DatabaseEndpoint:
    """Reuse the live Neon read guard; never enable the application write guard."""
    settings = Settings(_env_file=None)
    if settings.database_target_environment != "production" or settings.database_url is None:
        raise pg.MigrationToolError("Select an explicit production read target in the environment.")
    engine = create_database_engine(settings, read_only=True)
    if engine is None:
        raise pg.MigrationToolError("Production connection is required.")
    try:
        verify_database_read_only_preflight(
            engine,
            configured_target_environment=settings.database_target_environment,
            requested_target_environment="production",
        )
    finally:
        engine.dispose()
    url = make_url(settings.database_url.get_secret_value())
    if not url.host or not url.host.endswith(".neon.tech") or "-pooler." in url.host:
        raise pg.MigrationToolError("Recovery requires the verified direct Neon endpoint.")
    if url.query.get("sslmode") != "verify-full" or not url.username or not url.database:
        raise pg.MigrationToolError("Recovery requires explicit identity and verify-full TLS.")
    # Native pg_dump must use the same CA selection as the guarded Python connection.
    if "sslrootcert" not in url.query and os.environ.get("PGSSLROOTCERT"):
        url = url.update_query_dict({"sslrootcert": os.environ["PGSSLROOTCERT"]})
    assert url.host and url.database and url.username
    return pg.DatabaseEndpoint(
        role="recovery_source",
        url=url,
        host=url.host,
        port=url.port or 5432,
        database=url.database,
        username=url.username,
        schema="public",
    )


def access_inventory(source: pg.DatabaseEndpoint) -> dict[str, Any]:
    """Private recovery evidence, without role passwords; never replay grants automatically."""
    queries = {
        "databases": """
            SELECT datname, pg_get_userbyid(datdba), datacl::text FROM pg_database ORDER BY
            datname
        """,
        "roles": """
            SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin,
            rolreplication, rolbypassrls, rolconnlimit, rolvaliduntil::text, rolconfig FROM
            pg_roles ORDER BY rolname
        """,
        "memberships": """
            SELECT pg_get_userbyid(roleid), pg_get_userbyid(member), pg_get_userbyid(grantor),
            admin_option, inherit_option, set_option FROM pg_auth_members ORDER BY 1,2,3
        """,
        "schemas": """
            SELECT nspname, pg_get_userbyid(nspowner), nspacl::text FROM pg_namespace WHERE
            nspname !~ '^pg_' AND nspname <> 'information_schema' ORDER BY 1
        """,
        "relations": """
            SELECT n.nspname, c.relname, c.relkind::text, pg_get_userbyid(c.relowner),
            c.relacl::text, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c JOIN
            pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY 1,2
        """,
        "columns": """
            SELECT c.relname, a.attname, a.attacl::text FROM pg_attribute a JOIN pg_class c ON
            c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE
            n.nspname='public' AND a.attacl IS NOT NULL ORDER BY 1,2
        """,
        "default_privileges": """
            SELECT pg_get_userbyid(defaclrole), defaclnamespace::regnamespace::text,
            defaclobjtype::text, defaclacl::text FROM pg_default_acl ORDER BY 1,2,3
        """,
        "role_settings": """
            SELECT d.datname, r.rolname, s.setconfig FROM pg_db_role_setting s LEFT JOIN
            pg_database d ON d.oid=s.setdatabase LEFT JOIN pg_roles r ON r.oid=s.setrole ORDER
            BY 1,2
        """,
    }
    with pg.connect_read_only(source) as connection:
        pg.connection_identity(connection, source)
        result = {
            name: [list(row) for row in connection.execute(query)]
            for name, query in queries.items()
        }
    if any(row[5] or row[6] for row in result["relations"]):
        raise pg.MigrationToolError(
            "RLS is enabled; this bounded recovery path requires separate review."
        )
    return result


def _age(arguments: list[str], output: Path) -> None:
    executable = shutil.which("age")
    if executable is None:
        raise pg.MigrationToolError("Install the reviewed age CLI and add it to PATH.")
    with output.open("xb") as handle:
        try:
            result = subprocess.run(
                [executable, *arguments],
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.PIPE,
                timeout=1800,
                check=False,
            )
            if result.returncode:
                raise pg.MigrationToolError(
                    "age failed; check the key and file integrity privately."
                )
        except BaseException:
            handle.close()
            output.unlink(missing_ok=True)
            raise


def seal(stage: Path, output: Path, recipient: str) -> None:
    if not recipient.startswith("age1") or any(c.isspace() for c in recipient):
        raise pg.MigrationToolError("Use an age native public recipient key.")
    pg.verify_backup(stage / MEMBERS[0])
    with tempfile.TemporaryDirectory(prefix="seal-", dir=stage) as temp:
        bundle = Path(temp) / "bundle.zip"
        with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_STORED) as archive:
            for name in MEMBERS:
                archive.write(stage / name, name)
        _age(["--encrypt", "--recipient", recipient, str(bundle)], output)


def unseal(bundle: Path, stage: Path, identity: Path) -> None:
    """Decrypt to a new private directory, validate fixed members and the native archive."""
    stage.mkdir(exist_ok=False)
    try:
        with tempfile.TemporaryDirectory(prefix="unseal-", dir=stage) as temp:
            plain = Path(temp) / "bundle.zip"
            _age(["--decrypt", "--identity", str(identity), str(bundle)], plain)
            with zipfile.ZipFile(plain) as archive:
                if sorted(archive.namelist()) != sorted(MEMBERS):
                    raise pg.MigrationToolError(
                        "Recovery bundle contains unexpected or duplicate files."
                    )
                for name in MEMBERS:
                    with archive.open(name) as src, (stage / name).open("xb") as dst:
                        shutil.copyfileobj(src, dst)
        pg.verify_backup(stage / MEMBERS[0])
        json.loads((stage / "access.json").read_text(encoding="utf-8"))
    except BaseException:
        # Only remove the new directory owned by this invocation, never an existing path.
        shutil.rmtree(stage)
        raise


def create_bundle(
    source: pg.DatabaseEndpoint, output: Path, staging_root: Path, recipient: str
) -> None:
    if output.exists():
        raise pg.MigrationToolError("Output already exists; never overwrite a recovery point.")
    if not shutil.which("age"):
        raise pg.MigrationToolError("Install the reviewed age CLI before exporting data.")
    with tempfile.TemporaryDirectory(prefix="recovery-", dir=staging_root) as temporary:
        stage = Path(temporary)
        access = access_inventory(source)
        pg.backup(stage / MEMBERS[0], source)
        if access_inventory(source) != access:
            raise pg.MigrationToolError(
                "Access controls changed during export; freeze changes and retry."
            )
        (stage / "access.json").write_text(json.dumps(access, indent=2), encoding="utf-8")
        seal(stage, output, recipient)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    preflight = sub.add_parser("preflight")
    preflight.add_argument("--source", choices=("local", "production"), required=True)
    preflight.add_argument("--report", type=Path, required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("--source", choices=("local", "production"), required=True)
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--staging-root", type=Path, required=True)
    backup.add_argument("--recipient", required=True)
    decrypt = sub.add_parser("decrypt")
    decrypt.add_argument("--bundle", type=Path, required=True)
    decrypt.add_argument("--destination", type=Path, required=True)
    decrypt.add_argument("--identity", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            path = pg._safe_output_path(args.report)
            if path.exists() or not path.parent.is_dir():
                raise pg.MigrationToolError("Select a new report path in a private directory.")
            source = (
                production_source()
                if args.source == "production"
                else pg.endpoint_from_environment("source")
            )
            report = {"inventory": pg.inventory(source), "access": access_inventory(source)}
            with path.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2)
            print("READ_ONLY_INVENTORY_CREATED; this is not a backup or a restore verification.")
        elif args.command == "backup":
            output = pg._safe_output_path(args.output)
            staging = pg._safe_output_path(args.staging_root)
            if not staging.is_dir() or not output.parent.is_dir():
                raise pg.MigrationToolError("Select existing authorized private directories.")
            source = (
                production_source()
                if args.source == "production"
                else pg.endpoint_from_environment("source")
            )
            if not sys.stdin.isatty():
                raise pg.MigrationToolError("Backup requires an interactive operator terminal.")
            expected = f"BACKUP {source.host}/{source.database}"
            print(f"Encrypted output: {output}\nPlaintext staging root: {staging}")
            print("Confirm destination, encrypted staging, key custody and frozen writers.")
            if input(f"Type {expected}: ") != expected:
                raise pg.MigrationToolError("Operator confirmation did not match.")
            create_bundle(source, output, staging, args.recipient)
            print("ENCRYPTED_EXPORT_CREATED; decryption and restore rehearsal still required.")
        else:
            unseal(
                pg._safe_output_path(args.bundle),
                pg._safe_output_path(args.destination),
                args.identity,
            )
            print("DECRYPTED_ARCHIVE_VERIFIED; restore and access-control review still required.")
        return 0
    except pg.MigrationToolError as error:
        print(f"RECOVERY_BLOCKED: {error}", file=sys.stderr)
        return 2
    except Exception:
        # Native diagnostics may contain credentials or private data; never echo arbitrary errors.
        print(
            "RECOVERY_FAILED; check prerequisites privately. No production restore was attempted.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
