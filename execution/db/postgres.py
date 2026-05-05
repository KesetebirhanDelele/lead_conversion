"""
execution/db/postgres.py

PostgreSQL backend — mirrors the execution/db/sqlite.py interface so all
existing callers (connect / init_db) work without import changes when
DATABASE_URL is configured.

Requires: psycopg2-binary
Install:  pip install psycopg2-binary

Paramstyle adapter
------------------
All application SQL uses ? placeholders (SQLite style). The _PgConnection
wrapper converts ? → %s transparently so no SQL has to change.

Env-switching
-------------
Set DATABASE_URL to a postgres:// or postgresql:// URI. The sqlite.py
connect() and init_db() functions delegate here automatically when
db_path is None and DATABASE_URL is set.

Example:
    DATABASE_URL=postgresql://user:password@localhost:5432/lead_conversion

Row access
----------
psycopg2 cursors return plain tuples by default. _PgRow wraps each row
to support both column-name access (row["col"]) and integer access (row[0]),
matching sqlite3.Row semantics.
"""

from __future__ import annotations

import re
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Row wrapper — emulates sqlite3.Row dict+int access
# ---------------------------------------------------------------------------

class _PgRow:
    """Wraps a psycopg2 row tuple + column names to emulate sqlite3.Row."""

    def __init__(self, cols: list[str], vals: tuple) -> None:
        self._cols = cols
        self._vals = vals
        self._map  = {c: v for c, v in zip(cols, vals)}

    def __getitem__(self, key: str | int):
        if isinstance(key, int):
            return self._vals[key]
        return self._map[key]

    def get(self, key: str, default=None):
        return self._map.get(key, default)

    def keys(self):
        return self._cols

    def __iter__(self):
        return iter(self._vals)

    def __repr__(self):
        return repr(self._map)


# ---------------------------------------------------------------------------
# Cursor wrapper
# ---------------------------------------------------------------------------

_Q_RE = re.compile(r"\?")


def _adapt(sql: str) -> str:
    """Replace ? placeholders with %s for psycopg2."""
    return _Q_RE.sub("%s", sql)


class _PgCursor:
    """Wraps a psycopg2 cursor, adapting paramstyle and row access."""

    def __init__(self, cur) -> None:
        self._cur = cur

    def _rows(self, rows) -> list[_PgRow]:
        if not rows or not self._cur.description:
            return rows or []
        cols = [d[0] for d in self._cur.description]
        return [_PgRow(cols, r) for r in rows]

    def _one(self, row) -> _PgRow | None:
        if row is None or not self._cur.description:
            return row
        cols = [d[0] for d in self._cur.description]
        return _PgRow(cols, row)

    def fetchone(self):
        return self._one(self._cur.fetchone())

    def fetchall(self):
        return self._rows(self._cur.fetchall())

    def __getitem__(self, idx: int):
        row = self.fetchone()
        return row[idx] if row is not None else None


# ---------------------------------------------------------------------------
# Connection wrapper
# ---------------------------------------------------------------------------

class _PgConnection:
    """Wraps a psycopg2 connection, adapting ? → %s and rows to _PgRow."""

    def __init__(self, conn) -> None:
        self._conn = conn
        self.row_factory = None  # compatibility shim; unused for postgres

    def execute(self, sql: str, params: Sequence[Any] = ()) -> _PgCursor:
        cur = self._conn.cursor()
        cur.execute(_adapt(sql), list(params))
        return _PgCursor(cur)

    def executescript(self, sql: str) -> None:
        """Execute a multi-statement SQL block (strips comments, splits on ;)."""
        cur = self._conn.cursor()
        for stmt in (s.strip() for s in sql.split(";") if s.strip()):
            cur.execute(stmt)
        self._conn.commit()

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._conn.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def connect(database_url: str) -> _PgConnection:
    """Open a PostgreSQL connection and return a _PgConnection wrapper.

    Args:
        database_url: Full PostgreSQL DSN, e.g.
                      "postgresql://user:pass@localhost:5432/dbname"

    Returns:
        _PgConnection with ? → %s paramstyle adaptation.

    Raises:
        ImportError: if psycopg2 is not installed.
        psycopg2.OperationalError: if the database is unreachable.
    """
    try:
        import psycopg2
    except ImportError as exc:
        raise ImportError(
            "psycopg2 is required for PostgreSQL support. "
            "Install with: pip install psycopg2-binary"
        ) from exc

    raw = psycopg2.connect(database_url)
    raw.autocommit = False
    return _PgConnection(raw)


def init_db(conn: _PgConnection) -> None:
    """Create all application tables in PostgreSQL if they do not exist.

    Equivalent to sqlite.init_db() — same tables, same columns, Postgres syntax.
    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS).

    Args:
        conn: An open _PgConnection (or any compatible connection wrapper).
    """
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS leads (
            id             TEXT PRIMARY KEY,
            phone          TEXT,
            email          TEXT,
            name           TEXT,
            ghl_contact_id TEXT,
            created_at     TEXT,
            updated_at     TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS course_enrollments (
            id          TEXT PRIMARY KEY,
            lead_id     TEXT NOT NULL REFERENCES leads(id),
            course_id   TEXT NOT NULL DEFAULT 'FREE_INTRO_AI_V0',
            enrolled_at TEXT,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            UNIQUE (lead_id, course_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS course_invites (
            id            TEXT PRIMARY KEY,
            lead_id       TEXT NOT NULL REFERENCES leads(id),
            course_id     TEXT NOT NULL DEFAULT 'FREE_INTRO_AI_V0',
            generated_at  TEXT,
            sent_at       TEXT,
            channel       TEXT,
            token         TEXT,
            first_used_at TEXT,
            metadata_json TEXT
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_course_invites_token ON course_invites (token)",
        """
        CREATE TABLE IF NOT EXISTS progress_events (
            id            TEXT PRIMARY KEY,
            lead_id       TEXT NOT NULL REFERENCES leads(id),
            course_id     TEXT NOT NULL DEFAULT 'FREE_INTRO_AI_V0',
            section       TEXT,
            occurred_at   TEXT,
            metadata_json TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS course_state (
            lead_id           TEXT NOT NULL,
            course_id         TEXT NOT NULL DEFAULT 'FREE_INTRO_AI_V0',
            current_section   TEXT,
            completion_pct    REAL,
            last_activity_at  TEXT,
            started_at        TEXT,
            avg_quiz_score    REAL,
            avg_quiz_attempts REAL,
            updated_at        TEXT,
            PRIMARY KEY (lead_id, course_id),
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hot_lead_signals (
            lead_id    TEXT PRIMARY KEY REFERENCES leads(id),
            signal     TEXT,
            score      REAL,
            reason     TEXT,
            updated_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sync_records (
            id            SERIAL PRIMARY KEY,
            lead_id       TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            destination   TEXT NOT NULL,
            status        TEXT NOT NULL,
            reason        TEXT,
            payload_json  TEXT,
            response_json TEXT,
            error         TEXT,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            UNIQUE (lead_id, destination, status)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_sync_records_status  ON sync_records (status)",
        "CREATE INDEX IF NOT EXISTS idx_sync_records_lead_id ON sync_records (lead_id)",
        """
        CREATE TABLE IF NOT EXISTS reflection_responses (
            id            SERIAL PRIMARY KEY,
            lead_id       TEXT NOT NULL,
            course_id     TEXT NOT NULL,
            section_id    TEXT NOT NULL,
            prompt_index  INTEGER NOT NULL,
            response_text TEXT NOT NULL,
            created_at    TEXT,
            UNIQUE (lead_id, course_id, section_id, prompt_index)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_reflection_lead_course ON reflection_responses (lead_id, course_id)",
        """
        CREATE TABLE IF NOT EXISTS lead_final_scores (
            lead_id      TEXT NOT NULL,
            course_id    TEXT NOT NULL DEFAULT 'FREE_INTRO_AI_V0',
            final_label  TEXT NOT NULL,
            final_score  INTEGER,
            finalized_at TEXT NOT NULL,
            PRIMARY KEY (lead_id, course_id),
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_lead_final_scores_label ON lead_final_scores (final_label)",
        """
        CREATE TABLE IF NOT EXISTS quiz_scores (
            id          SERIAL PRIMARY KEY,
            lead_id     TEXT NOT NULL REFERENCES leads(id),
            course_id   TEXT NOT NULL DEFAULT 'FREE_INTRO_AI_V0',
            section_id  TEXT NOT NULL,
            quiz_id     TEXT NOT NULL,
            score_pct   REAL NOT NULL,
            attempts    INTEGER NOT NULL,
            recorded_at TEXT NOT NULL,
            UNIQUE (lead_id, course_id, section_id, quiz_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_quiz_scores_lead_course ON quiz_scores (lead_id, course_id)",
    ]

    for stmt in stmts:
        if stmt.strip():
            conn.execute(stmt)
    conn.commit()
