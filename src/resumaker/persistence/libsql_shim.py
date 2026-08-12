"""libSQL (Turso) connection shim — sqlite3.Row-compatible.

Cloud Run has no persistent disk, so the SQLite *file* can't live there; Turso (libSQL) is the
hosted, SQLite-compatible DB. The libSQL Python driver speaks the same SQL but returns plain
tuples (no `row["col"]` access) — which `db.py` relies on everywhere. This shim wraps a libSQL
connection so its cursors yield Row objects supporting BOTH `r[0]` and `r["col"]`, exactly like
`sqlite3.Row`. Result: `db.py` is unchanged; only `connect()` chooses the backend.

Local dev/prod default stays on stdlib `sqlite3`; libSQL is used when configured (Turso URL, or
`RESUMAKER_DB_BACKEND=libsql` to exercise this path against a local file with no cloud account).
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any


class Row:
    """sqlite3.Row-like: index (`r[0]`) and column-name (`r["name"]`) access + `.keys()`."""
    __slots__ = ("_cols", "_vals")

    def __init__(self, cols: tuple[str, ...], vals: tuple[Any, ...]):
        self._cols = cols
        self._vals = vals

    def __getitem__(self, key: int | str) -> Any:
        if isinstance(key, int):
            return self._vals[key]
        return self._vals[self._cols.index(key)]

    def keys(self) -> list[str]:
        return list(self._cols)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._vals)

    def __len__(self) -> int:
        return len(self._vals)


class _Cursor:
    """Eagerly materializes results at construction, so the underlying libSQL cursor is fully
    consumed immediately. Without this, an unconsumed SELECT/RETURNING cursor left open when the
    transaction commits raises libSQL's "SQL statements in progress"."""

    def __init__(self, cur: Any):
        self.description = cur.description
        self.lastrowid = getattr(cur, "lastrowid", None)
        self.rowcount = getattr(cur, "rowcount", -1)
        cols = tuple(d[0] for d in (self.description or ()))
        try:
            raw = cur.fetchall()
        except Exception:  # noqa: BLE001 - non-SELECT statements have nothing to fetch
            raw = None
        self._rows: list[Row] = [Row(cols, tuple(r)) for r in (raw or [])]
        self._i = 0

    def fetchone(self) -> Row | None:
        if self._i < len(self._rows):
            row = self._rows[self._i]
            self._i += 1
            return row
        return None

    def fetchall(self) -> list[Row]:
        rest = self._rows[self._i:]
        self._i = len(self._rows)
        return rest

    def __iter__(self) -> Iterator[Row]:
        while self._i < len(self._rows):
            yield self.fetchone()  # type: ignore[misc]


class LibsqlConnection:
    """Thin wrapper exposing the sqlite3.Connection surface `db.py` uses, with Row-wrapped cursors."""

    def __init__(self, conn: Any):
        self._conn = conn

    def execute(self, sql: str, params: Iterable[Any] = ()) -> _Cursor:
        # libSQL wants no 2nd arg for a param-free statement; mirror sqlite3's flexibility.
        cur = self._conn.execute(sql, tuple(params)) if params else self._conn.execute(sql)
        return _Cursor(cur)

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> _Cursor:
        return _Cursor(self._conn.executemany(sql, [tuple(p) for p in seq]))

    def executescript(self, script: str) -> None:
        self._conn.executescript(script)

    def cursor(self) -> _Cursor:
        return _Cursor(self._conn.cursor())

    def commit(self) -> None:
        self._conn.commit()

    def sync(self) -> None:
        # Embedded replica: push/pull with the primary. Remote-only connections have nothing to
        # sync (writes already hit the primary), so this is a no-op there.
        if hasattr(self._conn, "sync"):
            self._conn.sync()

    def rollback(self) -> None:
        # libSQL may not implement rollback identically; best-effort.
        if hasattr(self._conn, "rollback"):
            self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def connect(*, db_path: str, turso_url: str | None, auth_token: str | None,
            sync_interval: int | None = None, remote_only: bool = False) -> LibsqlConnection:
    """Open a libSQL connection. Three modes:

      - remote-only (`remote_only`, Turso): no local file - every query goes straight to the Turso
        primary over HTTP. Best on scale-to-zero (no cold-start sync, ~0 Embedded Syncs, always
        latest); costs ~30-50ms network per query.
      - embedded replica (Turso, default): a local file kept in sync with the primary. `sync_interval`
        enables background auto-sync so ONE long-lived connection serves local-replica reads in ~ms
        (a full sync per short-lived connection would be a ~3s round-trip).
      - local file (no `turso_url`): exercises the libSQL path locally.

    `check_same_thread=False` lets the shared connection be used across the API's worker threads."""
    import libsql_experimental as libsql  # noqa: PLC0415

    if turso_url and remote_only:
        # No replica: pass the Turso URL as the database so libSQL talks to the primary directly.
        conn = libsql.connect(database=turso_url, auth_token=auth_token or "",
                              check_same_thread=False)
    elif turso_url:
        # Embedded replica: a local file kept in sync with Turso (fast reads, durable via Turso).
        conn = libsql.connect(db_path, sync_url=turso_url, auth_token=auth_token or "",
                              sync_interval=sync_interval, check_same_thread=False)
        conn.sync()   # one initial pull; subsequent freshness comes from the background auto-sync
    else:
        conn = libsql.connect(db_path)
    return LibsqlConnection(conn)
