#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for compare_from_db.py — the pure normalization / diff / colorizing
helpers, plus compare_entry() driven by stub db/account objects.
"""

import os
import sys
import unittest
import xmlrpc.client

# Ensure the scripts directory is on the path so imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compare_from_db as c

ESC = "\033"


class TestNorm(unittest.TestCase):
    def test_none_becomes_empty_string(self):
        self.assertEqual(c._norm(None), "")

    def test_plain_string_unchanged(self):
        self.assertEqual(c._norm("hello"), "hello")

    def test_crlf_and_cr_normalized_to_lf(self):
        self.assertEqual(c._norm("a\r\nb\rc"), "a\nb\nc")

    def test_xmlrpc_binary_decoded(self):
        self.assertEqual(c._norm(xmlrpc.client.Binary("щ".encode("utf-8"))), "щ")


class TestDocument(unittest.TestCase):
    def test_document_layout(self):
        doc = c._document({"subject": "S", "tags": "T", "event": "l1\nl2"})
        self.assertEqual(doc, ["Subject: S", "Tags: T", "", "l1", "l2"])


class TestPaint(unittest.TestCase):
    def test_wraps_non_empty_text(self):
        self.assertEqual(c._paint("x", c._BLUE), c._BLUE + "x" + c._RESET)

    def test_empty_text_stays_empty(self):
        self.assertEqual(c._paint("", c._BLUE), "")


class TestHighlightPair(unittest.TestCase):
    def test_identical_lines_unchanged(self):
        a, b = c._highlight_pair("abc", "abc")
        self.assertEqual((a, b), ("abc", "abc"))

    def test_replacement_colored_per_side(self):
        a, b = c._highlight_pair("cat", "cot")
        self.assertEqual(a, "c" + c._paint("a", c._BLUE) + "t")
        self.assertEqual(b, "c" + c._paint("o", c._RED) + "t")

    def test_pure_insertion_only_colors_online_side(self):
        a, b = c._highlight_pair("ab", "abc")
        self.assertEqual(a, "ab")                       # nothing unique to db
        self.assertEqual(b, "ab" + c._paint("c", c._RED))


class TestRenderDiff(unittest.TestCase):
    def test_identical_message_when_no_differences(self):
        out = c.render_diff(7, {}, {}, [])
        self.assertEqual(out, "Entry 7: database and online versions are identical.")

    def test_plain_diff_has_no_ansi_and_shows_both_sides(self):
        db = {"subject": "a", "tags": "", "event": "x"}
        online = {"subject": "b", "tags": "", "event": "x"}
        diffs = [{"field": "subject", "db": "a", "online": "b"}]
        out = c.render_diff(9925, db, online, diffs, color=False)
        self.assertNotIn(ESC, out)
        self.assertIn("database:9925 vs online:9925 — differs in subject", out)
        self.assertIn("-Subject: a", out)
        self.assertIn("+Subject: b", out)

    def test_colored_diff_contains_ansi_codes(self):
        db = {"subject": "a", "tags": "", "event": "x"}
        online = {"subject": "b", "tags": "", "event": "x"}
        diffs = [{"field": "subject", "db": "a", "online": "b"}]
        out = c.render_diff(9925, db, online, diffs, color=True)
        self.assertIn(ESC, out)


# --- compare_entry with stub db/account -----------------------------------

class _FakeDB:
    def __init__(self, rows_by_id):
        self._rows = rows_by_id

    def get(self, itemid):
        return self._rows.get(itemid, [])


class _FakeAccount:
    def __init__(self, events_by_id):
        self._events = events_by_id

    def get(self, itemid, journal=None):
        return self._events.get(itemid)


def _db_row(subject="S", tags="work", event="body"):
    return {"subject": subject, "props_taglist": tags, "event": event}


def _online_ev(subject="S", tags="work", event="body"):
    return {"subject": subject, "props": {"taglist": tags}, "event": event}


class TestCompareEntry(unittest.TestCase):
    def test_identical(self):
        db = _FakeDB({5: [_db_row()]})
        acct = _FakeAccount({5: _online_ev()})
        res = c.compare_entry(db, acct, 5)
        self.assertTrue(res["in_db"])
        self.assertTrue(res["online"])
        self.assertTrue(res["identical"])
        self.assertEqual(res["differences"], [])
        self.assertIn("identical", res["report"])

    def test_differing_subject(self):
        db = _FakeDB({5: [_db_row(subject="old")]})
        acct = _FakeAccount({5: _online_ev(subject="new")})
        res = c.compare_entry(db, acct, 5)
        self.assertFalse(res["identical"])
        self.assertEqual([d["field"] for d in res["differences"]], ["subject"])
        self.assertIn("differs in subject", res["report"])

    def test_line_ending_only_difference_is_ignored(self):
        db = _FakeDB({5: [_db_row(event="a\r\nb")]})
        acct = _FakeAccount({5: _online_ev(event="a\nb")})
        res = c.compare_entry(db, acct, 5)
        self.assertTrue(res["identical"])

    def test_missing_in_db(self):
        db = _FakeDB({})
        acct = _FakeAccount({5: _online_ev()})
        res = c.compare_entry(db, acct, 5)
        self.assertFalse(res["in_db"])
        self.assertTrue(res["online"])
        self.assertIn("exists online but not in the database", res["report"])

    def test_missing_online(self):
        db = _FakeDB({5: [_db_row()]})
        acct = _FakeAccount({})
        res = c.compare_entry(db, acct, 5)
        self.assertTrue(res["in_db"])
        self.assertFalse(res["online"])
        self.assertIn("exists in the database but not online", res["report"])

    def test_missing_both(self):
        res = c.compare_entry(_FakeDB({}), _FakeAccount({}), 5)
        self.assertFalse(res["in_db"])
        self.assertFalse(res["online"])
        self.assertIn("not found in the database or online", res["report"])


if __name__ == "__main__":
    unittest.main()
