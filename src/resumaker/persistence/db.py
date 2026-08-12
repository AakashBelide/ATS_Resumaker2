"""SQLite persistence: the *derived* index over the canonical files.

Design: files under `outputs/<run>/` remain the source of truth for artifacts; this DB
holds queryable metadata for history/analytics (`runs`) and the job-watchlist
(`companies`, `company_boards`, `jobs`). SQLite is the right call for a single-user,
self-hosted tool - zero ops, one file, WAL for concurrent reads. A per-call connection
(SQLite's recommended pattern under threads) keeps the API's worker + request handlers
safe without a pool.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from resumaker.config import get_settings
from resumaker.domain.ingestion import (
    BoardRef,
    Company,
    JobRecord,
    OnboardEvent,
    OnboardingRun,
    RunRecord,
    TrackerEntry,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS company_boards (
    company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    source      TEXT NOT NULL,
    token       TEXT NOT NULL,
    extra       TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (company_id, source, token)
);
CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    url          TEXT NOT NULL DEFAULT '',
    title        TEXT NOT NULL DEFAULT '',
    company      TEXT NOT NULL DEFAULT '',
    location     TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'new',
    posted_at    TEXT NOT NULL DEFAULT '',
    comp         TEXT NOT NULL DEFAULT '',
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    UNIQUE (source, external_id)
);
CREATE TABLE IF NOT EXISTS runs (
    id               TEXT PRIMARY KEY,
    job_id           INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    url              TEXT NOT NULL DEFAULT '',
    out_dir          TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'pending',
    recommend_apply  INTEGER,
    fit_0_100        REAL,
    ats_overall      REAL,
    fact_gate_pass   INTEGER,
    ats_verify_pass  INTEGER,
    page_count       INTEGER,
    cost_usd         REAL NOT NULL DEFAULT 0,
    error            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    finished_at      TEXT
);
CREATE TABLE IF NOT EXISTS tracker (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    url              TEXT NOT NULL DEFAULT '',
    company          TEXT NOT NULL DEFAULT '',
    title            TEXT NOT NULL DEFAULT '',
    stage            TEXT NOT NULL DEFAULT 'interested',
    run_id           TEXT NOT NULL DEFAULT '',
    fit_0_100        REAL,
    recommend_apply  INTEGER,
    sponsorship      TEXT NOT NULL DEFAULT '',
    match_error      TEXT,
    notes            TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    UNIQUE (url)
);
CREATE TABLE IF NOT EXISTS notified (
    source       TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    notified_at  TEXT NOT NULL,
    PRIMARY KEY (source, external_id)
);
CREATE TABLE IF NOT EXISTS onboarding_runs (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    careers_url  TEXT NOT NULL DEFAULT '',
    method       TEXT NOT NULL DEFAULT '',
    state        TEXT NOT NULL DEFAULT 'running',
    question     TEXT NOT NULL DEFAULT '',
    board        TEXT NOT NULL DEFAULT '',    -- JSON BoardRef, or '' when unresolved
    evidence     TEXT NOT NULL DEFAULT '{}',  -- JSON
    events       TEXT NOT NULL DEFAULT '[]',  -- JSON [{stage,status,detail,ts}]
    cost_usd     REAL NOT NULL DEFAULT 0,
    turns        INTEGER NOT NULL DEFAULT 0,
    error        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_tracker_stage ON tracker(stage);
CREATE INDEX IF NOT EXISTS idx_onboarding_created ON onboarding_runs(created_at DESC);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """A per-call connection with sane pragmas. Commits on clean exit, rolls back on error.

    Dual-mode: stdlib `sqlite3` on a local file by default; libSQL (Turso) when configured. Both
    expose the same surface (execute/executemany/executescript + `row["col"]` cursors), so the
    rest of this module is backend-agnostic."""
    s = get_settings()
    path = s.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if s.turso_url or s.db_backend == "libsql":
        from resumaker.persistence.libsql_shim import connect as _libsql_connect  # noqa: PLC0415
        conn: Any = _libsql_connect(db_path=str(path), turso_url=s.turso_url,
                                    auth_token=s.turso_auth_token)
        conn.execute("PRAGMA foreign_keys = ON")   # WAL is a local-file concept; skip for libSQL
    else:
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if absent + apply lightweight column migrations. Idempotent."""
    with connect() as conn:
        conn.executescript(_SCHEMA)
        _migrate(conn)


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, coldef: str) -> None:
    """Add a column if the table lacks it (additive migration for DBs from an older schema).

    Tolerates a 'duplicate column' error: on libSQL/Turso the embedded replica's local metadata
    can lag the remote, so `PRAGMA table_info` may report the column absent while the ALTER hits
    an up-to-date remote that already has it. The column existing is exactly the success state,
    so we swallow that specific error (and only that one)."""
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if name in cols:
        return
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")
    except Exception as e:  # noqa: BLE001 - narrow to duplicate-column below; re-raise anything else
        if "duplicate column" not in str(e).lower():
            raise


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive migrations for DBs created by an earlier schema (add-column only)."""
    _ensure_column(conn, "jobs", "posted_at", "posted_at TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "jobs", "comp", "comp TEXT NOT NULL DEFAULT ''")
    _ensure_column(conn, "tracker", "match_error", "match_error TEXT")


# ------------------------------------------------------------------ runs
def record_run(run: RunRecord) -> None:
    """Insert or update a run row (upsert on the run id)."""
    with connect() as conn:
        conn.execute(
            """INSERT INTO runs (id, job_id, url, out_dir, status, recommend_apply,
                   fit_0_100, ats_overall, fact_gate_pass, ats_verify_pass, page_count,
                   cost_usd, error, created_at, finished_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   job_id=excluded.job_id, url=excluded.url, out_dir=excluded.out_dir,
                   status=excluded.status, recommend_apply=excluded.recommend_apply,
                   fit_0_100=excluded.fit_0_100, ats_overall=excluded.ats_overall,
                   fact_gate_pass=excluded.fact_gate_pass,
                   ats_verify_pass=excluded.ats_verify_pass, page_count=excluded.page_count,
                   cost_usd=excluded.cost_usd, error=excluded.error,
                   finished_at=excluded.finished_at""",
            (run.id, run.job_id, run.url, run.out_dir, run.status,
             _b(run.recommend_apply), run.fit_0_100, run.ats_overall,
             _b(run.fact_gate_pass), _b(run.ats_verify_pass), run.page_count,
             run.cost_usd, run.error, run.created_at or _now(), run.finished_at),
        )


def get_run(run_id: str) -> RunRecord | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return _run_from_row(row) if row else None


def list_runs(limit: int = 50) -> list[RunRecord]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_run_from_row(r) for r in rows]


# ------------------------------------------------------------------ jobs
def upsert_job(job: JobRecord) -> tuple[int, bool]:
    """Insert a new posting or refresh `last_seen`. Returns (job_id, is_new_or_changed).

    Dedup identity is (source, external_id). If the row exists and `content_hash`
    changed, we bump `last_seen` and flag it changed (re-run worthy); if unchanged we
    just touch `last_seen`."""
    now = _now()
    with connect() as conn:
        existing = conn.execute(
            "SELECT id, content_hash FROM jobs WHERE source=? AND external_id=?",
            (job.source, job.external_id)).fetchone()
        if existing is None:
            cur = conn.execute(
                """INSERT INTO jobs (source, external_id, url, title, company, location,
                       content_hash, status, posted_at, comp, first_seen, last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job.source, job.external_id, job.url, job.title, job.company,
                 job.location, job.content_hash, "new", job.posted_at, job.comp, now, now))
            return int(cur.lastrowid or 0), True
        changed = existing["content_hash"] != job.content_hash
        conn.execute(
            "UPDATE jobs SET last_seen=?, content_hash=?, url=?, title=?, location=?, comp=? "
            "WHERE id=?",
            (now, job.content_hash, job.url, job.title, job.location, job.comp, existing["id"]))
        return int(existing["id"]), changed


def set_job_status(job_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))


def get_job(job_id: int) -> JobRecord | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _job_from_row(row) if row else None


# ------------------------------------------------------------------ notifications (RI.4)
def unnotified(jobs: list[JobRecord]) -> list[JobRecord]:
    """Return only the jobs we have NOT already emailed (dedup on (source, external_id)), so a
    posting is never sent twice across ticks."""
    if not jobs:
        return []
    with connect() as conn:
        seen = {(r["source"], r["external_id"])
                for r in conn.execute("SELECT source, external_id FROM notified").fetchall()}
    return [j for j in jobs if (j.source, j.external_id) not in seen]


def mark_notified(jobs: list[JobRecord]) -> None:
    """Record that these jobs have been emailed (idempotent)."""
    if not jobs:
        return
    now = _now()
    with connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO notified (source, external_id, notified_at) VALUES (?,?,?)",
            [(j.source, j.external_id, now) for j in jobs])


def list_jobs(status: str | None = None, limit: int = 100) -> list[JobRecord]:
    q = "SELECT * FROM jobs"
    args: list = []
    if status:
        q += " WHERE status=?"
        args.append(status)
    q += " ORDER BY last_seen DESC LIMIT ?"
    args.append(limit)
    with connect() as conn:
        rows = conn.execute(q, args).fetchall()
    return [_job_from_row(r) for r in rows]


# ------------------------------------------------------------------ discovery (RA.1)
_ORDER_SQL = {"recent": "first_seen DESC", "company": "company ASC, first_seen DESC",
              "title": "title ASC"}


def _job_where(company: str | None, source: str | None, location_like: str | None,
               title_like: str | None, since_days: int | None,
               status: str | None) -> tuple[str, list]:
    """Build a parameterized WHERE for the jobs table. Recency uses `first_seen` (our own
    reliable timestamp), since ATS `posted_at` is inconsistent/absent across sources."""
    clauses: list[str] = []
    args: list = []

    def add(clause: str, value: object) -> None:
        clauses.append(clause)
        args.append(value)

    if company:
        add("company = ?", company)
    if source:
        add("source = ?", source)
    if location_like:
        add("lower(location) LIKE ?", f"%{location_like.lower()}%")
    if title_like:
        add("lower(title) LIKE ?", f"%{title_like.lower()}%")
    if since_days is not None:
        add("first_seen >= ?", (datetime.now(UTC) - timedelta(days=since_days)).isoformat())
    if status:
        add("status = ?", status)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


def query_jobs(*, company: str | None = None, source: str | None = None,
               location_like: str | None = None, title_like: str | None = None,
               since_days: int | None = None, status: str | None = None,
               order: str = "recent", limit: int = 50, offset: int = 0) -> list[JobRecord]:
    """Deterministic filtered/sorted/paged query over `jobs` (Discovery, RA.1). No LLM."""
    where, args = _job_where(company, source, location_like, title_like, since_days, status)
    order_sql = _ORDER_SQL.get(order, _ORDER_SQL["recent"])
    q = f"SELECT * FROM jobs{where} ORDER BY {order_sql} LIMIT ? OFFSET ?"
    with connect() as conn:
        rows = conn.execute(q, [*args, limit, offset]).fetchall()
    return [_job_from_row(r) for r in rows]


def count_jobs(*, company: str | None = None, source: str | None = None,
               location_like: str | None = None, title_like: str | None = None,
               since_days: int | None = None, status: str | None = None) -> int:
    where, args = _job_where(company, source, location_like, title_like, since_days, status)
    with connect() as conn:
        return int(conn.execute(f"SELECT count(*) FROM jobs{where}", args).fetchone()[0])


def job_facets(*, company: str | None = None, source: str | None = None,
               location_like: str | None = None, title_like: str | None = None,
               since_days: int | None = None, status: str | None = None) -> dict:
    """Counts by company + source over the same filter (for Discovery filter chips)."""
    where, args = _job_where(company, source, location_like, title_like, since_days, status)
    with connect() as conn:
        cos = conn.execute(
            f"SELECT company, count(*) n FROM jobs{where} GROUP BY company ORDER BY n DESC",
            args).fetchall()
        srcs = conn.execute(
            f"SELECT source, count(*) n FROM jobs{where} GROUP BY source ORDER BY n DESC",
            args).fetchall()
    return {"companies": {r["company"]: r["n"] for r in cos},
            "sources": {r["source"]: r["n"] for r in srcs}}


# ------------------------------------------------------------------ companies
def add_company(company: Company) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO companies (name, active, created_at) VALUES (?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET active=excluded.active RETURNING id",
            (company.name, int(company.active), company.created_at or _now()))
        row = cur.fetchone()
        assert row is not None  # RETURNING always yields a row here
        cid = int(row["id"])
        for b in company.boards:
            conn.execute(
                "INSERT OR REPLACE INTO company_boards (company_id, source, token, extra) "
                "VALUES (?,?,?,?)",
                (cid, b.source, b.token, _json(b.extra)))
    return cid


def remove_company(name: str) -> int:
    """Delete a company (and its boards, via cascade) from the watchlist. Returns rows removed."""
    with connect() as conn:
        cur = conn.execute("DELETE FROM companies WHERE name=?", (name,))
        return cur.rowcount


def set_company_active(name: str, active: bool) -> bool:
    """Pause (active=False) or resume (active=True) a company's scraping. Inactive companies
    are skipped by `ingest_all` (list_companies(active_only=True)); on resume, the next sweep
    simply ingests whatever is live on the board then (no gap backfill). Returns True if a
    row was updated."""
    with connect() as conn:
        cur = conn.execute("UPDATE companies SET active=? WHERE name=?", (int(active), name))
        return cur.rowcount > 0


def list_companies(active_only: bool = True) -> list[Company]:
    with connect() as conn:
        q = "SELECT * FROM companies" + (" WHERE active=1" if active_only else "")
        rows = conn.execute(q).fetchall()
        out: list[Company] = []
        for r in rows:
            boards = conn.execute(
                "SELECT source, token, extra FROM company_boards WHERE company_id=?",
                (r["id"],)).fetchall()
            out.append(Company(
                id=r["id"], name=r["name"], active=bool(r["active"]),
                created_at=_dt(r["created_at"]),
                boards=[_board(b) for b in boards]))
    return out


# ------------------------------------------------------------------ onboarding runs (Phase C)
def upsert_onboarding_run(run: OnboardingRun) -> None:
    """Insert or update an onboarding run (upsert on id). `created_at` is set once on insert."""
    now = _now()
    created = run.created_at.isoformat() if run.created_at else now
    with connect() as conn:
        conn.execute(
            """INSERT INTO onboarding_runs (id, name, careers_url, method, state, question,
                   board, evidence, events, cost_usd, turns, error, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name, careers_url=excluded.careers_url, method=excluded.method,
                   state=excluded.state, question=excluded.question, board=excluded.board,
                   evidence=excluded.evidence, events=excluded.events, cost_usd=excluded.cost_usd,
                   turns=excluded.turns, error=excluded.error, updated_at=excluded.updated_at""",
            (run.id, run.name, run.careers_url, run.method, run.state, run.question,
             _json(run.board.model_dump()) if run.board else "",
             _json(run.evidence), _json([e.model_dump() for e in run.events]),
             run.cost_usd, run.turns, run.error, created, now),
        )


def get_onboarding_run(run_id: str) -> OnboardingRun | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM onboarding_runs WHERE id=?", (run_id,)).fetchone()
    return _onboarding_from_row(row) if row else None


def list_onboarding_runs(limit: int = 50) -> list[OnboardingRun]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM onboarding_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_onboarding_from_row(r) for r in rows]


# ------------------------------------------------------------------ analytics (RA.4/RA.5)
def jobs_daily(days: int = 14) -> list[dict]:
    """New listings per day (by `first_seen`) over the last `days`, most-recent first."""
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    with connect() as conn:
        rows = conn.execute(
            "SELECT substr(first_seen,1,10) d, count(*) n FROM jobs "
            "WHERE first_seen >= ? GROUP BY d ORDER BY d DESC", (cutoff,)).fetchall()
    return [{"date": r["d"], "count": r["n"]} for r in rows]


def tracker_funnel() -> dict[str, int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT stage, count(*) n FROM tracker GROUP BY stage").fetchall()
    return {r["stage"]: r["n"] for r in rows}


def run_stats() -> dict:
    """Run counts by status + avg fit/ATS + total recorded cost."""
    with connect() as conn:
        by = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, count(*) n FROM runs GROUP BY status").fetchall()}
        a = conn.execute(
            "SELECT count(*) total, avg(fit_0_100) af, avg(ats_overall) aa, "
            "sum(cost_usd) c FROM runs").fetchone()
    return {"total": int(a["total"] or 0), "by_status": by,
            "avg_fit": round(a["af"], 1) if a["af"] is not None else None,
            "avg_ats": round(a["aa"], 1) if a["aa"] is not None else None,
            "total_cost_usd": round(a["c"] or 0.0, 4)}


# ------------------------------------------------------------------ tracker (RA.2)
def upsert_tracker(entry: TrackerEntry) -> int:
    """Insert a tracked job or refresh its match fields (keyed on url). Preserves `stage`
    and `notes` on re-add (a re-match shouldn't reset the owner's lifecycle/notes)."""
    now = _now()
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO tracker (job_id, url, company, title, stage, run_id, fit_0_100,
                   recommend_apply, sponsorship, match_error, notes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(url) DO UPDATE SET
                   job_id=excluded.job_id, company=excluded.company, title=excluded.title,
                   run_id=excluded.run_id, fit_0_100=excluded.fit_0_100,
                   recommend_apply=excluded.recommend_apply, sponsorship=excluded.sponsorship,
                   match_error=excluded.match_error, updated_at=excluded.updated_at
               RETURNING id""",
            (entry.job_id, entry.url, entry.company, entry.title, entry.stage, entry.run_id,
             entry.fit_0_100, _b(entry.recommend_apply), entry.sponsorship, entry.match_error,
             entry.notes, now, now))
        row = cur.fetchone()
        assert row is not None
        return int(row["id"])


def list_tracker(stage: str | None = None) -> list[TrackerEntry]:
    q = "SELECT * FROM tracker"
    args: list = []
    if stage:
        q += " WHERE stage=?"
        args.append(stage)
    q += " ORDER BY updated_at DESC"
    with connect() as conn:
        rows = conn.execute(q, args).fetchall()
    return [_tracker_from_row(r) for r in rows]


def get_tracker(entry_id: int) -> TrackerEntry | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM tracker WHERE id=?", (entry_id,)).fetchone()
    return _tracker_from_row(row) if row else None


def set_tracker_stage(entry_id: int, stage: str) -> bool:
    with connect() as conn:
        cur = conn.execute("UPDATE tracker SET stage=?, updated_at=? WHERE id=?",
                           (stage, _now(), entry_id))
        return cur.rowcount > 0


def set_tracker_notes(entry_id: int, notes: str) -> bool:
    with connect() as conn:
        cur = conn.execute("UPDATE tracker SET notes=?, updated_at=? WHERE id=?",
                           (notes, _now(), entry_id))
        return cur.rowcount > 0


def remove_tracker(entry_id: int) -> int:
    with connect() as conn:
        return conn.execute("DELETE FROM tracker WHERE id=?", (entry_id,)).rowcount


# ------------------------------------------------------------------ row mappers
def _b(v: bool | None) -> int | None:
    return None if v is None else int(v)


def _json(d: Any) -> str:
    return json.dumps(d)


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _board(row: sqlite3.Row) -> BoardRef:
    return BoardRef(source=row["source"], token=row["token"],
                    extra=json.loads(row["extra"] or "{}"))


def _run_from_row(r: sqlite3.Row) -> RunRecord:
    return RunRecord(
        id=r["id"], job_id=r["job_id"], url=r["url"], out_dir=r["out_dir"],
        status=r["status"],
        recommend_apply=None if r["recommend_apply"] is None else bool(r["recommend_apply"]),
        fit_0_100=r["fit_0_100"], ats_overall=r["ats_overall"],
        fact_gate_pass=None if r["fact_gate_pass"] is None else bool(r["fact_gate_pass"]),
        ats_verify_pass=None if r["ats_verify_pass"] is None else bool(r["ats_verify_pass"]),
        page_count=r["page_count"], cost_usd=r["cost_usd"], error=r["error"],
        created_at=_dt(r["created_at"]), finished_at=_dt(r["finished_at"]))


def _tracker_from_row(r: sqlite3.Row) -> TrackerEntry:
    return TrackerEntry(
        id=r["id"], job_id=r["job_id"], url=r["url"], company=r["company"], title=r["title"],
        stage=r["stage"], run_id=r["run_id"], fit_0_100=r["fit_0_100"],
        recommend_apply=None if r["recommend_apply"] is None else bool(r["recommend_apply"]),
        sponsorship=r["sponsorship"], match_error=r["match_error"], notes=r["notes"],
        created_at=_dt(r["created_at"]), updated_at=_dt(r["updated_at"]))


def _onboarding_from_row(r: sqlite3.Row) -> OnboardingRun:
    board = json.loads(r["board"]) if r["board"] else None
    return OnboardingRun(
        id=r["id"], name=r["name"], careers_url=r["careers_url"], method=r["method"],
        state=r["state"], question=r["question"],
        board=BoardRef(**board) if board else None,
        evidence=json.loads(r["evidence"] or "{}"),
        events=[OnboardEvent(**e) for e in json.loads(r["events"] or "[]")],
        cost_usd=r["cost_usd"], turns=r["turns"], error=r["error"],
        created_at=_dt(r["created_at"]), updated_at=_dt(r["updated_at"]))


def _job_from_row(r: sqlite3.Row) -> JobRecord:
    return JobRecord(
        id=r["id"], source=r["source"], external_id=r["external_id"], url=r["url"],
        title=r["title"], company=r["company"], location=r["location"],
        content_hash=r["content_hash"], status=r["status"], posted_at=r["posted_at"],
        comp=r["comp"],
        first_seen=_dt(r["first_seen"]), last_seen=_dt(r["last_seen"]))
