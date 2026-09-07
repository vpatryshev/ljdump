#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for update_entries.py.

Covers:
  * parse_sed() — the importable sed-style s/pattern/replacement/[g] parser:
    separator handling, the 'g' flag -> count semantics, alternate separators,
    empty pattern/replacement, and error handling on bad syntax.
  * The substitution *application* that main() performs, composed as
    re.sub(pattern, replacement, event, count=count) using parse_sed output.
  * WHERE-filter selection and dry-run vs. real UPDATE semantics against a
    temporary LJDB, mirroring the exact SQL main() issues. main()'s DB logic
    itself is not importable (it is trapped inside main(), guarded by
    `if __name__ == "__main__"`), so these DB behaviors are exercised through
    LJDB using the same queries; see the report note for that gap.
"""

import os
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure the scripts directory is on the path so imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from update_entries import parse_sed
from ljdb import LJDB


class TestParseSed(unittest.TestCase):
    def test_basic_no_flag_count_is_one(self):
        self.assertEqual(parse_sed("s/old/new/"), ("old", "new", 1))

    def test_global_flag_count_is_zero(self):
        self.assertEqual(parse_sed("s/old/new/g"), ("old", "new", 0))

    def test_two_part_form_without_trailing_sep(self):
        # s{sep}pattern{sep}replacement  (only 2 parts) is accepted, count=1
        self.assertEqual(parse_sed("s/old/new"), ("old", "new", 1))

    def test_alternate_separator(self):
        self.assertEqual(parse_sed("s#a#b#g"), ("a", "b", 0))

    def test_alternate_separator_with_slashes_in_content(self):
        # Using a non-slash separator lets the content contain slashes.
        self.assertEqual(parse_sed("s|a/b|c/d|"), ("a/b", "c/d", 1))

    def test_empty_pattern_and_replacement(self):
        self.assertEqual(parse_sed("s///"), ("", "", 1))

    def test_empty_replacement(self):
        self.assertEqual(parse_sed("s/foo//"), ("foo", "", 1))

    def test_flags_other_than_g_treated_as_non_global(self):
        # Only 'g' triggers count=0; anything else leaves count=1.
        self.assertEqual(parse_sed("s/a/b/i"), ("a", "b", 1))

    def test_g_anywhere_in_flags(self):
        self.assertEqual(parse_sed("s/a/b/ig"), ("a", "b", 0))

    def test_must_start_with_s(self):
        with self.assertRaises(ValueError):
            parse_sed("x/a/b/")

    def test_too_many_parts_fails(self):
        with self.assertRaises(ValueError):
            parse_sed("s/a/b/c/d")

    def test_too_few_parts_fails(self):
        # s{sep}pattern  -> only 1 part after split
        with self.assertRaises(ValueError):
            parse_sed("s/onlyone")


class TestSubstitutionApplication(unittest.TestCase):
    """Exercise the same re.sub composition main() uses on entry text."""

    def _apply(self, expr, text):
        pattern, replacement, count = parse_sed(expr)
        return re.sub(pattern, replacement, text, count=count)

    def test_single_replacement_replaces_first_only(self):
        self.assertEqual(self._apply("s/foo/bar/", "foo foo foo"), "bar foo foo")

    def test_global_replacement_replaces_all(self):
        self.assertEqual(self._apply("s/foo/bar/g", "foo foo foo"), "bar bar bar")

    def test_regex_pattern_applies(self):
        self.assertEqual(self._apply(r"s/\d+/#/g", "a1 b22 c333"), "a# b# c#")

    def test_no_match_leaves_text_unchanged(self):
        text = "nothing to change here"
        self.assertEqual(self._apply("s/xyz/abc/g", text), text)

    def test_deletion_via_empty_replacement(self):
        self.assertEqual(self._apply("s/<br>//g", "a<br>b<br>c"), "abc")


class TestWhereFilterAndDryRun(unittest.TestCase):
    """
    Validate the WHERE-filter selection and dry-run/real-update behaviors that
    main() relies on, using a temporary LJDB and the exact SQL from main().
    """

    SELECT_SQL = "SELECT itemid, event FROM entries WHERE {where}"
    UPDATE_SQL = """
        UPDATE entries
        SET event = ?
        WHERE itemid = ?
    """

    def setUp(self):
        # LJDB writes a db.log into the parent dir and requires the file to
        # exist (or create=True); use a private temp dir for clean teardown.
        self._dir = tempfile.mkdtemp()
        self._path = os.path.join(self._dir, "journal.db")

        # Let LJDB create its full schema (entries table has several NOT NULL
        # columns plus indexes), then insert complete rows via raw sqlite3.
        with patch("builtins.print"):
            self.db = LJDB(self._path, verbose=False, create=True)

        conn = sqlite3.connect(self._path)
        # entries requires: eventtime, eventtime_unix, logtime, logtime_unix,
        # event, raw_props (all NOT NULL). Fill them with placeholders and vary
        # only itemid / event / props_taglist which are what the tests care about.
        conn.executemany(
            """INSERT INTO entries (
                   itemid, eventtime, eventtime_unix, logtime, logtime_unix,
                   event, props_taglist, raw_props)
               VALUES (?,?,?,?,?,?,?,?)""",
            [(1, "2020-01-01 00:00:00", 0.0, "2020-01-01 00:00:00", 0.0,
              "hello world", "music", "<props/>"),
             (2, "2020-01-02 00:00:00", 0.0, "2020-01-02 00:00:00", 0.0,
              "hello there", "life", "<props/>"),
             (3, "2020-01-03 00:00:00", 0.0, "2020-01-03 00:00:00", 0.0,
              "goodbye world", "music", "<props/>")])
        conn.commit()
        conn.close()

    def tearDown(self):
        try:
            self.db.close(None)
        except Exception:
            pass
        for name in ("journal.db", "db.log"):
            p = os.path.join(self._dir, name)
            try:
                os.unlink(p)
            except FileNotFoundError:
                pass
        try:
            os.rmdir(self._dir)
        except OSError:
            pass

    def _select(self, where):
        cur = self.db.cursor()
        cur.execute(self.SELECT_SQL.format(where=where))
        return cur.fetchall()

    def test_where_filter_selects_only_matching_rows(self):
        rows = self._select("props_taglist = 'music'")
        ids = sorted(r[0] for r in rows)
        self.assertEqual(ids, [1, 3])

    def test_where_filter_single_match(self):
        rows = self._select("props_taglist = 'life'")
        self.assertEqual([r[0] for r in rows], [2])

    def test_where_filter_no_match(self):
        rows = self._select("itemid > 9999")
        self.assertEqual(rows, [])

    def test_null_event_is_skipped_like_main(self):
        # main() guards `if event is None: continue` before calling re.sub, so a
        # NULL event must be skipped without error. entries.event is NOT NULL in
        # the LJDB schema, so we simulate the fetched row set directly here.
        rows = [(1, "hello world"), (99, None), (2, "hello there")]
        pattern, replacement, count = parse_sed("s/hello/hi/g")
        updated = 0
        for itemid, event in rows:
            if event is None:
                continue
            new_event = re.sub(pattern, replacement, event, count=count)
            if new_event != event:
                updated += 1
        # itemid 1 and 2 change; the None row is skipped without raising.
        self.assertEqual(updated, 2)

    def test_dry_run_does_not_mutate_db(self):
        # Simulate the dry-run branch: compute new_event but never UPDATE.
        rows = self._select("props_taglist = 'music'")
        pattern, replacement, count = parse_sed("s/hello/hi/g")
        changed = 0
        for itemid, event in rows:
            if event is None:
                continue
            new_event = re.sub(pattern, replacement, event, count=count)
            if new_event != event:
                changed += 1
            # dry-run: intentionally do NOT execute the UPDATE
        self.assertEqual(changed, 1)  # sanity: itemid=1 would have changed

        # Verify the stored event is untouched despite a computed change.
        after = dict(self._select("itemid = 1"))
        self.assertEqual(after[1], "hello world")

    def test_real_update_mutates_only_matching_rows(self):
        rows = self._select("props_taglist = 'music'")
        pattern, replacement, count = parse_sed("s/hello/hi/g")
        cur = self.db.cursor()
        for itemid, event in rows:
            if event is None:
                continue
            new_event = re.sub(pattern, replacement, event, count=count)
            if new_event == event:
                continue
            cur.execute(self.UPDATE_SQL, (new_event, itemid))
        self.db.close(cur)

        # Reconnect and verify: itemid=1 changed, itemid=2 (not selected) intact.
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        got = {r["itemid"]: r["event"]
               for r in conn.execute("SELECT itemid, event FROM entries")}
        conn.close()
        self.assertEqual(got[1], "hi world")       # selected + matched -> changed
        self.assertEqual(got[2], "hello there")     # not selected (life) -> intact
        self.assertEqual(got[3], "goodbye world")   # selected but no match -> intact


if __name__ == "__main__":
    unittest.main()
