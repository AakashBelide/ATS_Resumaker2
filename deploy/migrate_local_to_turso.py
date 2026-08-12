"""One-shot migration: copy the local SQLite DB (+ the profile/preferences/house_rules JSON
files) up to hosted Turso, so the cloud app has all your companies, scraped jobs, tracker,
runs, and profile - and you can continue online.

Reads the local file directly (stdlib sqlite3) and writes straight to remote Turso (libSQL),
bypassing the app's env-driven db layer so there's no ambiguity about which side is which.
Idempotent (INSERT OR REPLACE) and re-runnable. Run from the repo root:

    env $(grep -E '^(TURSO_DATABASE_URL|TURSO_AUTH_TOKEN)=' .env | xargs) \\
        uv run python deploy/migrate_local_to_turso.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from resumaker.config import get_settings
from resumaker.persistence.db import _SCHEMA

# Parents before children (FK-safe), then the FK-free tables.
TABLES = ["companies", "jobs", "company_boards", "runs", "tracker",
          "notified", "documents", "onboarding_runs"]
DOCS = ["profile", "preferences", "house_rules"]


def _import_json_docs(local: sqlite3.Connection, data_dir: Path) -> None:
    """Seed the local `documents` table from the profile/*.json files so they get copied up."""
    local.execute("""CREATE TABLE IF NOT EXISTS documents (
        name TEXT PRIMARY KEY, json TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    for name in DOCS:
        f = data_dir / "profile" / f"{name}.json"
        if f.exists():
            local.execute(
                "INSERT OR REPLACE INTO documents (name, json, updated_at) VALUES (?,?,?)",
                (name, f.read_text(), datetime.now(UTC).isoformat()))
    local.commit()


def main() -> None:
    s = get_settings()
    if not (s.turso_url and s.turso_auth_token):
        sys.exit("TURSO_DATABASE_URL + TURSO_AUTH_TOKEN must be set (source them from .env).")

    local_path = s.db_path
    if not local_path.exists():
        sys.exit(f"local DB not found at {local_path}")
    local = sqlite3.connect(local_path)
    local.row_factory = sqlite3.Row
    _import_json_docs(local, s.data_root)

    # Direct remote connection. libSQL does one network round-trip per statement, so we pack many
    # rows into each INSERT (multi-row VALUES) - ~5k jobs become ~80 statements, not 5000. Chunk
    # size keeps bound params under SQLite's 999 limit.
    import libsql_experimental as libsql
    remote = libsql.connect(s.turso_url, auth_token=s.turso_auth_token)
    remote.executescript(_SCHEMA)   # idempotent: CREATE TABLE IF NOT EXISTS ... (adds `documents`)

    total = 0
    for table in TABLES:
        try:
            rows = local.execute(f"SELECT * FROM {table}").fetchall()
        except sqlite3.OperationalError:
            print(f"  {table}: (absent locally, skipped)")
            continue
        if not rows:
            print(f"  {table}: 0 rows")
            continue
        cols = list(rows[0].keys())
        collist = ",".join(cols)
        one = "(" + ",".join("?" for _ in cols) + ")"
        chunk = max(1, 900 // len(cols))       # stay under the 999 bound-param limit
        for i in range(0, len(rows), chunk):
            batch = rows[i:i + chunk]
            sql = f"INSERT OR REPLACE INTO {table} ({collist}) VALUES {','.join(one for _ in batch)}"
            params = tuple(v for r in batch for v in (r[c] for c in cols))
            remote.execute(sql, params)
        remote.commit()
        print(f"  {table}: {len(rows)} rows -> Turso", flush=True)
        total += len(rows)

    # verify a couple of counts on the remote side
    print("--- remote verification ---")
    for table in ("companies", "jobs", "tracker", "documents"):
        n = remote.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"  remote {table}: {n}")
    print(f"done: {total} rows migrated to Turso")


if __name__ == "__main__":
    main()
