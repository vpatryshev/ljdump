#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for update_from_db.py — parse_itemids() (single id, list, whitespace,
empty segments, and error handling on bad or empty input).
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure the scripts directory is on the path so imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import DB
from update_from_db import parse_itemids, select_itemids


class TestParseItemids(unittest.TestCase):
    def test_single(self):
        self.assertEqual(parse_itemids("12345"), [12345])

    def test_comma_list(self):
        self.assertEqual(parse_itemids("1,2,3"), [1, 2, 3])

    def test_whitespace_is_trimmed(self):
        self.assertEqual(parse_itemids(" 1, 2 ,3 "), [1, 2, 3])

    def test_empty_segments_skipped(self):
        self.assertEqual(parse_itemids("1,,2"), [1, 2])

    def test_trailing_comma(self):
        self.assertEqual(parse_itemids("1,"), [1])

    def test_invalid_itemid_fails(self):
        # fail() prints to stderr and raises SystemExit
        with patch("builtins.print"), self.assertRaises(SystemExit):
            parse_itemids("1,x")

    def test_empty_input_fails(self):
        with patch("builtins.print"), self.assertRaises(SystemExit):
            parse_itemids("")

    def test_only_commas_fails(self):
        with patch("builtins.print"), self.assertRaises(SystemExit):
            parse_itemids(",,")


class TestSelectItemids(unittest.TestCase):
    def setUp(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            self._path = f.name
        conn = sqlite3.connect(self._path)
        conn.execute("""
            CREATE TABLE entries (
                itemid INTEGER PRIMARY KEY, subject TEXT, event TEXT,
                eventtime TEXT, props_taglist TEXT)
        """)
        conn.executemany(
            "INSERT INTO entries VALUES (?,?,?,?,?)",
            [(9927, "c", "c", "t", "life"),
             (9925, "a", "a", "t", "work"),
             (9926, "b", "b", "t", "work")])
        conn.commit()
        conn.close()
        self.db = DB(self._path)

    def tearDown(self):
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass

    def test_returns_matching_ids_sorted(self):
        with patch("builtins.print"):
            self.assertEqual(select_itemids(self.db, "props_taglist = 'work'"),
                             [9925, 9926])

    def test_single_match(self):
        with patch("builtins.print"):
            self.assertEqual(select_itemids(self.db, "props_taglist = 'life'"),
                             [9927])

    def test_no_match_returns_empty(self):
        with patch("builtins.print"):
            self.assertEqual(select_itemids(self.db, "itemid > 99999"), [])


if __name__ == "__main__":
    unittest.main()
