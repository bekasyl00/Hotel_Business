"""Build an empty, private Django schema snapshot from disposable local databases.

Run with backend/.venv/bin/python. This command refuses non-loopback PostgreSQL,
never reads application rows from the configured database, and never deploys SQL.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import quote

import environ
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "tynys"
EXCLUDED_DUMP_LINES = re.compile(
    r"^(?:\\(?:un)?restrict\b|SET (?:transaction_timeout|idle_session_timeout)\s*=)",
    re.MULTILINE,
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--pg-bin", type=Path, default=Path("/Library/PostgreSQL/17/bin")
    )
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    return parser.parse_args()


def local_connection(env_name):
    environ.Env.read_env(ROOT / "backend/.env")
    config = environ.Env().db(env_name)
    if config["ENGINE"] != "django.db.backends.postgresql" or config.get(
        "HOST"
    ) not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise RuntimeError("Schema export requires a loopback-only PostgreSQL URL.")
    return {
        "host": config["HOST"],
        "port": config.get("PORT") or 5432,
        "user": config.get("USER") or "",
        "password": config.get("PASSWORD") or "",
        "dbname": "postgres",
        "connect_timeout": 10,
    }


def database_env(base, name):
    result = os.environ.copy()
    host = f"[{base['host']}]" if ":" in base["host"] else base["host"]
    result.update(
        {
            "DATABASE_URL": (
                f"postgresql://{quote(base['user'], safe='')}:{quote(base['password'], safe='')}"
                f"@{host}:{base['port']}/{name}"
            ),
            "DB_SCHEMA": SCHEMA,
            "DB_SSLMODE": "disable",
            "DB_SSLROOTCERT": "",
            "DB_TRANSACTION_POOLER": "False",
            "DB_CONN_MAX_AGE": "0",
            "MEDIA_STORAGE": "local",
            "PGHOST": base["host"],
            "PGPORT": str(base["port"]),
            "PGUSER": base["user"],
            "PGPASSWORD": base["password"],
            "PGDATABASE": name,
            "PGSSLMODE": "disable",
        }
    )
    return result


def run(command, env):
    result = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    if result.returncode:
        # Do not echo subprocess environments or connection diagnostics containing credentials.
        raise RuntimeError(
            f"Command failed ({Path(command[0]).name}); no SQL was deployed."
        )
    return result.stdout


def migrate(env, *, check=False):
    arguments = [
        sys.executable,
        str(ROOT / "backend/manage.py"),
        "migrate",
        "--noinput",
    ]
    if check:
        arguments.append("--check")
    return run(arguments, env)


def hardening_sql():
    return """
REVOKE ALL ON SCHEMA tynys FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA tynys FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA tynys FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA tynys FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA tynys REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA tynys REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA tynys REVOKE ALL ON FUNCTIONS FROM PUBLIC;
DO $hardening$
DECLARE client_role text;
DECLARE item record;
BEGIN
    FOREACH client_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = client_role) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA tynys FROM %I', client_role);
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA tynys FROM %I', client_role);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA tynys FROM %I', client_role);
            EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA tynys FROM %I', client_role);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA tynys REVOKE ALL ON TABLES FROM %I', client_role);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA tynys REVOKE ALL ON SEQUENCES FROM %I', client_role);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA tynys REVOKE ALL ON FUNCTIONS FROM %I', client_role);
        END IF;
    END LOOP;
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = 'tynys' LOOP
        EXECUTE format('ALTER TABLE tynys.%I ENABLE ROW LEVEL SECURITY', item.tablename);
    END LOOP;
END
$hardening$;
"""


def compose_snapshot(dump, migrations):
    kept = [line for line in dump.splitlines() if not EXCLUDED_DUMP_LINES.match(line)]
    dump = "\n".join(kept).replace(
        "CREATE SCHEMA tynys;", "CREATE SCHEMA IF NOT EXISTS tynys;"
    )
    if any(line.startswith("\\") for line in dump.splitlines()):
        raise RuntimeError("Unexpected psql metacommand in pg_dump output.")
    ledger = ",\n".join(
        f"({sql.Literal(app).as_string()}, {sql.Literal(name).as_string()}, CURRENT_TIMESTAMP)"
        for app, name in migrations
    )
    return (
        """-- Generated from fresh local Django migrations; no application/user rows copied.
-- Initial empty-schema bootstrap only. Apply as the schema owner after review.
-- No client RLS policies or runtime credentials are created. Owner access bypasses RLS.
BEGIN;
SET LOCAL lock_timeout = '5s';
DO $empty_schema$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'tynys' AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
    ) THEN
        RAISE EXCEPTION 'tynys must be empty; use Django migrations for an existing installation';
    END IF;
END
$empty_schema$;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA extensions;
DO $extension_schema$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
        WHERE e.extname = 'btree_gist' AND n.nspname = 'extensions'
    ) THEN
        RAISE EXCEPTION 'btree_gist must be installed in the extensions schema';
    END IF;
END
$extension_schema$;
"""
        + dump
        + "\n\nINSERT INTO tynys.django_migrations (app, name, applied) VALUES\n"
        + ledger
        + ";\n"
        + hardening_sql()
        + "\nCOMMIT;\n"
    )


def table_counts(connection):
    names = [
        row[0]
        for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY tablename",
            (SCHEMA,),
        )
    ]
    return {
        name: connection.execute(
            sql.SQL("SELECT count(*) FROM {}.{}").format(
                sql.Identifier(SCHEMA), sql.Identifier(name)
            )
        ).fetchone()[0]
        for name in names
    }


def main():
    args = parse_args()
    if args.output.suffix != ".sql":
        raise RuntimeError("Output must use a .sql extension; the manifest uses .json.")
    if args.output.exists():
        raise RuntimeError("Output already exists; choose a new snapshot path.")
    pg_dump = args.pg_bin / "pg_dump"
    if not pg_dump.is_file():
        located = shutil.which("pg_dump")
        if not located:
            raise RuntimeError("PostgreSQL pg_dump is required.")
        pg_dump = Path(located)
    base = local_connection(args.database_url_env)
    suffix = uuid.uuid4().hex[:10]
    source_name, restore_name = (
        f"tynys_schema_export_{suffix}",
        f"tynys_schema_restore_{suffix}",
    )
    created = []
    with psycopg.connect(**base, autocommit=True) as admin:
        if admin.info.server_version // 10000 != 17:
            raise RuntimeError(
                "Use PostgreSQL 17 to match the target bootstrap version."
            )
        try:
            for name in [source_name, restore_name]:
                admin.execute(
                    sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                        sql.Identifier(name)
                    )
                )
                created.append(name)
            with psycopg.connect(
                **{**base, "dbname": source_name}, autocommit=True
            ) as source:
                source.execute("CREATE SCHEMA tynys")
                source.execute("CREATE SCHEMA extensions")
                source.execute("CREATE EXTENSION btree_gist WITH SCHEMA extensions")
            source_env, restore_env = (
                database_env(base, source_name),
                database_env(base, restore_name),
            )
            migrate(source_env)
            with psycopg.connect(**{**base, "dbname": source_name}) as source:
                migrations = source.execute(
                    "SELECT app, name FROM tynys.django_migrations ORDER BY id"
                ).fetchall()
            dump = run(
                [
                    str(pg_dump),
                    "--schema-only",
                    "--no-owner",
                    "--no-privileges",
                    "--schema",
                    SCHEMA,
                ],
                source_env,
            )
            snapshot = compose_snapshot(dump, migrations)
            with psycopg.connect(
                **{**base, "dbname": restore_name}, autocommit=True
            ) as restored:
                restored.execute(snapshot, prepare=False)
                counts = table_counts(restored)
                if counts.pop("django_migrations") != len(migrations) or any(
                    counts.values()
                ):
                    raise RuntimeError(
                        "Restored snapshot contains unexpected table data."
                    )
                secured = restored.execute(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='tynys' AND c.relkind='r' AND c.relrowsecurity"
                ).fetchone()[0]
                if secured != len(counts) + 1:
                    raise RuntimeError("Every restored table must have RLS enabled.")
                public_access = restored.execute(
                    "SELECT count(*) FROM pg_namespace n, "
                    "LATERAL aclexplode(coalesce(n.nspacl, acldefault('n', n.nspowner))) a "
                    "WHERE n.nspname='tynys' AND a.grantee=0"
                ).fetchone()[0]
                if (
                    public_access
                    or restored.execute(
                        "SELECT count(*) FROM pg_policies WHERE schemaname='tynys'"
                    ).fetchone()[0]
                ):
                    raise RuntimeError(
                        "Snapshot must not expose a client schema or client RLS policies."
                    )
                try:
                    restored.execute(snapshot, prepare=False)
                except psycopg.errors.RaiseException:
                    restored.rollback()
                else:
                    raise RuntimeError(
                        "Snapshot must refuse an existing nonempty schema."
                    )
            migrate(restore_env, check=True)
            migration_output = migrate(restore_env)
            if "No migrations to apply." not in migration_output:
                raise RuntimeError("Restored migration ledger is incomplete.")
            manifest = {
                "schema": SCHEMA,
                "postgresMajor": 17,
                "tableCount": len(counts) + 1,
                "migrationCount": len(migrations),
                "migrationLedger": [list(item) for item in migrations],
                "businessRowsCopied": 0,
                "restoredEmptyTablesVerified": True,
                "allTablesRlsEnabled": True,
                "publicSchemaAccessRevokedVerified": True,
                "existingSchemaRejectedVerified": True,
                "restoreMigrateCheckPassed": True,
                "restoreMigrateHadNoPendingChanges": True,
                "sha256": hashlib.sha256(snapshot.encode()).hexdigest(),
                "bytes": len(snapshot.encode()),
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(snapshot)
            args.output.with_suffix(".json").write_text(
                json.dumps(manifest, indent=2) + "\n"
            )
            print(
                json.dumps({"output": str(args.output.resolve()), **manifest}, indent=2)
            )
        finally:
            for name in reversed(created):
                admin.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(name)
                    )
                )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, psycopg.Error) as exc:
        print(
            f"Schema export stopped: {type(exc).__name__}. No remote database was accessed.",
            file=sys.stderr,
        )
        if isinstance(exc, RuntimeError):
            print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
