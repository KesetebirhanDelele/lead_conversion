"""
tests/db/test_postgres_module.py

Unit tests for execution/db/postgres.py.
No real Postgres connection is needed — psycopg2 is mocked throughout.
Tests cover: _adapt SQL, _PgRow access, _PgConnection interface,
connect() ImportError path, and init_db() table creation calls.
"""

from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from execution.db.postgres import (
    _PgConnection,
    _PgRow,
    _adapt,
    connect,
    init_db,
)


class TestAdaptSQL(unittest.TestCase):

    def test_single_placeholder(self):
        self.assertEqual(_adapt("SELECT * FROM t WHERE id = ?"), "SELECT * FROM t WHERE id = %s")

    def test_multiple_placeholders(self):
        self.assertEqual(_adapt("SELECT ? + ?"), "SELECT %s + %s")

    def test_no_placeholder_unchanged(self):
        sql = "SELECT * FROM leads"
        self.assertEqual(_adapt(sql), sql)


class TestPgRow(unittest.TestCase):

    def setUp(self):
        self.row = _PgRow(["id", "name", "score"], ("abc", "Test", 85))

    def test_string_key_access(self):
        self.assertEqual(self.row["id"], "abc")
        self.assertEqual(self.row["name"], "Test")
        self.assertEqual(self.row["score"], 85)

    def test_integer_index_access(self):
        self.assertEqual(self.row[0], "abc")
        self.assertEqual(self.row[1], "Test")
        self.assertEqual(self.row[2], 85)

    def test_get_existing_key(self):
        self.assertEqual(self.row.get("name"), "Test")

    def test_get_missing_key_default(self):
        self.assertIsNone(self.row.get("missing"))
        self.assertEqual(self.row.get("missing", "x"), "x")

    def test_keys(self):
        self.assertEqual(self.row.keys(), ["id", "name", "score"])


class TestPgConnection(unittest.TestCase):

    def _make_conn(self, fetchone_return=None, fetchall_return=None, description=None):
        mock_cur = unittest.mock.MagicMock()
        mock_cur.description = description or [("col1",), ("col2",)]
        mock_cur.fetchone.return_value = fetchone_return
        mock_cur.fetchall.return_value = fetchall_return or []

        mock_raw = unittest.mock.MagicMock()
        mock_raw.cursor.return_value = mock_cur

        return _PgConnection(mock_raw), mock_raw, mock_cur

    def test_execute_adapts_placeholders(self):
        pg_conn, raw, cur = self._make_conn()
        pg_conn.execute("SELECT * FROM t WHERE id = ?", ["abc"])
        cur.execute.assert_called_once_with("SELECT * FROM t WHERE id = %s", ["abc"])

    def test_execute_returns_pg_cursor(self):
        from execution.db.postgres import _PgCursor
        pg_conn, raw, cur = self._make_conn()
        result = pg_conn.execute("SELECT 1")
        self.assertIsInstance(result, _PgCursor)

    def test_fetchone_returns_pg_row(self):
        pg_conn, raw, cur = self._make_conn(
            fetchone_return=("v1", "v2"),
            description=[("col1",), ("col2",)],
        )
        result = pg_conn.execute("SELECT 1")
        row = result.fetchone()
        self.assertIsInstance(row, _PgRow)
        self.assertEqual(row["col1"], "v1")

    def test_fetchone_none_returns_none(self):
        pg_conn, raw, cur = self._make_conn(fetchone_return=None)
        result = pg_conn.execute("SELECT 1")
        self.assertIsNone(result.fetchone())

    def test_commit_calls_underlying(self):
        pg_conn, raw, cur = self._make_conn()
        pg_conn.commit()
        raw.commit.assert_called_once()

    def test_close_calls_underlying(self):
        pg_conn, raw, cur = self._make_conn()
        pg_conn.close()
        raw.close.assert_called_once()

    def test_context_manager_closes(self):
        pg_conn, raw, cur = self._make_conn()
        with pg_conn:
            pass
        raw.close.assert_called_once()


class TestConnectFunction(unittest.TestCase):

    def test_raises_import_error_when_psycopg2_missing(self):
        with unittest.mock.patch.dict("sys.modules", {"psycopg2": None}):
            with self.assertRaises(ImportError):
                connect("postgresql://localhost/test")

    def test_returns_pg_connection_when_psycopg2_present(self):
        mock_psycopg2 = unittest.mock.MagicMock()
        mock_raw_conn = unittest.mock.MagicMock()
        mock_psycopg2.connect.return_value = mock_raw_conn

        with unittest.mock.patch.dict("sys.modules", {"psycopg2": mock_psycopg2}):
            result = connect("postgresql://localhost/test")
            self.assertIsInstance(result, _PgConnection)
            mock_psycopg2.connect.assert_called_once_with("postgresql://localhost/test")


class TestInitDb(unittest.TestCase):

    def test_init_db_calls_execute_for_each_table(self):
        mock_conn = unittest.mock.MagicMock()
        init_db(mock_conn)
        # init_db should have called execute at least once per table (10+ tables + indexes)
        self.assertGreater(mock_conn.execute.call_count, 10)

    def test_init_db_calls_commit(self):
        mock_conn = unittest.mock.MagicMock()
        init_db(mock_conn)
        mock_conn.commit.assert_called()

    def test_init_db_includes_quiz_scores_table(self):
        mock_conn = unittest.mock.MagicMock()
        init_db(mock_conn)
        all_sql = " ".join(
            call[0][0] for call in mock_conn.execute.call_args_list
        )
        self.assertIn("quiz_scores", all_sql)

    def test_init_db_includes_sync_records_table(self):
        mock_conn = unittest.mock.MagicMock()
        init_db(mock_conn)
        all_sql = " ".join(
            call[0][0] for call in mock_conn.execute.call_args_list
        )
        self.assertIn("sync_records", all_sql)


if __name__ == "__main__":
    unittest.main()
