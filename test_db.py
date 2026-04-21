#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for db.py
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure the ljdump directory is on the path so `from utils import *` resolves
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import DB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(path: str, with_entries: bool = True, with_status: bool = False):
    """Create a minimal SQLite database at *path* suitable for DB tests."""
    conn = sqlite3.connect(path)
    if with_entries:
        conn.execute("""
            CREATE TABLE entries (
                itemid       INTEGER PRIMARY KEY,
                subject      TEXT,
                event        TEXT,
                eventtime    TEXT,
                props_taglist TEXT
            )
        """)
        conn.execute("""
            INSERT INTO entries VALUES
                (1, 'Hello World', 'First entry body', '2024-01-15 10:00:00', 'tag1,tag2'),
                (2, 'Second Post', 'Second entry body', '2024-02-20 14:30:00', 'tag2,tag3'),
                (3, NULL,         'No subject entry',  '2024-03-01 09:00:00', NULL)
        """)
    if with_status:
        conn.execute("""
            CREATE TABLE status (
                lastsync           TEXT,
                lastmaxcommentid   INTEGER
            )
        """)
        conn.execute("INSERT INTO status VALUES ('2024-01-01 00:00:00', 0)")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDBInit(unittest.TestCase):
    def test_opens_existing_database(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path)
            db = DB(path)
            self.assertIsNotNone(db)
        finally:
            os.unlink(path)

    def test_fails_on_missing_file(self):
        """DB.__init__ calls fail() (which calls exit(1)) when the file is absent."""
        with patch("builtins.print"), self.assertRaises(SystemExit):
            DB("/nonexistent/path/no_such_file.db")

    def test_verbose_logs_opening_message(self, ):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path)
            with patch("builtins.print") as mock_print:
                DB(path, verbose=True)
                printed = " ".join(str(c) for c in mock_print.call_args_list)
                self.assertIn("Opening local database", printed)
        finally:
            os.unlink(path)

    def test_no_verbose_no_log(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path)
            with patch("builtins.print") as mock_print:
                DB(path, verbose=False)
                mock_print.assert_not_called()
        finally:
            os.unlink(path)


class TestDBCursor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._path = self._tmp.name
        self._tmp.close()
        _make_db(self._path)
        self.db = DB(self._path)

    def tearDown(self):
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass

    def test_cursor_returns_sqlite_cursor(self):
        cur = self.db.cursor()
        self.assertIsInstance(cur, sqlite3.Cursor)

    def test_cursor_is_usable(self):
        cur = self.db.cursor()
        cur.execute("SELECT 1")
        row = cur.fetchone()
        self.assertEqual(row[0], 1)


class TestDBExists(unittest.TestCase):
    def test_returns_truthy_when_entries_table_present(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path, with_entries=True)
            db = DB(path)
            self.assertIsNotNone(db.exists())
        finally:
            os.unlink(path)

    def test_returns_falsy_when_entries_table_absent(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            _make_db(path, with_entries=False)
            db = DB(path)
            self.assertIsNone(db.exists())
        finally:
            os.unlink(path)


class TestDBLog(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            self._path = f.name
        _make_db(self._path)

    def tearDown(self):
        os.unlink(self._path)

    def test_log_prints_when_verbose(self):
        with patch("builtins.print") as mock_print:
            db = DB(self._path, verbose=True)
            mock_print.reset_mock()
            db.log("test message")
            mock_print.assert_called_once_with("test message")

    def test_log_silent_when_not_verbose(self):
        db = DB(self._path, verbose=False)
        with patch("builtins.print") as mock_print:
            db.log("test message")
            mock_print.assert_not_called()


class TestDBExecute(unittest.TestCase):
    """
    execute() is a fire-and-forget wrapper: it returns None.
    NOTE: Because of this, select() (which calls self.execute(sql).fetchall())
    will raise AttributeError — see TestDBSelectBug below.
    """

    def setUp(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            self._path = f.name
        _make_db(self._path)
        self.db = DB(self._path)

    def tearDown(self):
        os.unlink(self._path)

    def test_execute_returns_none(self):
        result = self.db.execute("SELECT 1")
        self.assertIsNone(result)

    def test_execute_runs_ddl(self):
        self.db.execute("CREATE TABLE IF NOT EXISTS _tmp_test (x INTEGER)")
        cur = self.db.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE name='_tmp_test'")
        self.assertIsNotNone(cur.fetchone())


class TestDBSelectBug(unittest.TestCase):
    """
    Documents the known bug in select(): it calls self.execute(sql).fetchall(),
    but execute() returns None, so an AttributeError is raised every time.
    """

    def setUp(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            self._path = f.name
        _make_db(self._path)
        self.db = DB(self._path)

    def tearDown(self):
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass

    def test_select_raises_attribute_error_due_to_execute_returning_none(self):
        with patch("builtins.print"), self.assertRaises(AttributeError):
            self.db.select("itemid = 1")

    def test_get_raises_attribute_error_due_to_execute_returning_none(self):
        with patch("builtins.print"), self.assertRaises(AttributeError):
            self.db.get(1)


class TestDBSetSyncStatus(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            self._path = f.name
        _make_db(self._path, with_entries=True, with_status=True)
        self.db = DB(self._path)

    def tearDown(self):
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass

    def test_set_sync_status_updates_row(self):
        status = {
            'last_sync': '2024-06-01 12:00:00',
            'last_max_comment_id': 42,
        }
        self.db.set_sync_status(status)
        # commit + close so changes are durable
        self.db.close(None)
        # verify via a fresh connection that the data is actually persisted
        conn = sqlite3.connect(self._path)
        row = conn.execute("SELECT lastsync, lastmaxcommentid FROM status").fetchone()
        conn.close()
        self.assertEqual(row[0], '2024-06-01 12:00:00')
        self.assertEqual(row[1], 42)


class TestDBClose(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            self._path = f.name
        _make_db(self._path)
        self.db = DB(self._path)

    def tearDown(self):
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass

    def test_close_with_cursor(self):
        cur = self.db.cursor()
        # Should not raise
        self.db.close(cur)

    def test_close_with_none(self):
        # close(None) should skip cursor.close() and just commit+close the connection
        self.db.close(None)

    def test_connection_unusable_after_close(self):
        self.db.close(None)
        # Any subsequent operation on the connection should raise ProgrammingError
        with self.assertRaises(Exception):
            self.db.cursor().execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
