#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for utils.py (possible_unicode_or_none, object_to_xml_string,
ts_to_utc, format_entry_date).
"""

import os
import sys
import unittest
import xmlrpc.client
from datetime import datetime, timezone

# Ensure the scripts directory is on the path so `from utils import ...` resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (possible_unicode_or_none, object_to_xml_string,
                   ts_to_utc, format_entry_date)


class TestPossibleUnicodeOrNone(unittest.TestCase):
    def test_none_passthrough(self):
        self.assertIsNone(possible_unicode_or_none(None))

    def test_plain_string_unchanged(self):
        self.assertEqual(possible_unicode_or_none("hello"), "hello")

    def test_unicode_string_unchanged(self):
        self.assertEqual(possible_unicode_or_none("Ро́ссия ☃"), "Ро́ссия ☃")

    def test_non_string_is_stringified(self):
        self.assertEqual(possible_unicode_or_none(123), "123")

    def test_xmlrpc_binary_is_decoded_as_utf8(self):
        blob = xmlrpc.client.Binary("щ".encode("utf-8"))
        self.assertEqual(possible_unicode_or_none(blob), "щ")

    def test_empty_string_stays_empty(self):
        self.assertEqual(possible_unicode_or_none(""), "")


class TestObjectToXmlString(unittest.TestCase):
    def test_flat_dict(self):
        # dicts preserve insertion order in Python 3.7+, so output is deterministic
        out = object_to_xml_string("", "props", {"a": "x", "b": "y"})
        self.assertEqual(out, "<props>\n<a>x</a>\n<b>y</b>\n</props>\n")

    def test_escapes_xml_special_characters(self):
        out = object_to_xml_string("", "props", {"a": "x & y <z>"})
        self.assertEqual(out, "<props>\n<a>x &amp; y &lt;z&gt;</a>\n</props>\n")

    def test_non_string_values_are_stringified(self):
        out = object_to_xml_string("", "props", {"n": 42})
        self.assertEqual(out, "<props>\n<n>42</n>\n</props>\n")

    def test_nested_dict_recurses(self):
        # Regression guard: this path used an undefined name `f` before the fix.
        out = object_to_xml_string("", "props", {"outer": {"inner": "v"}})
        self.assertEqual(
            out, "<props>\n<outer>\n<inner>v</inner>\n</outer>\n</props>\n")

    def test_accumulator_is_prepended(self):
        out = object_to_xml_string("PREFIX", "props", {"a": "x"})
        self.assertEqual(out, "PREFIX<props>\n<a>x</a>\n</props>\n")


class TestTsToUtc(unittest.TestCase):
    def test_epoch(self):
        self.assertEqual(ts_to_utc(0), datetime(1970, 1, 1, 0, 0, 0))

    def test_known_timestamp_is_naive_utc(self):
        # 2024-03-15 14:30:00 UTC
        d = ts_to_utc(1710513000)
        self.assertEqual(d, datetime(2024, 3, 15, 14, 30, 0))
        self.assertIsNone(d.tzinfo)  # naive, matching the old utcfromtimestamp

    def test_matches_aware_conversion(self):
        ts = 1710513000
        self.assertEqual(
            ts_to_utc(ts),
            datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None))


class TestFormatEntryDate(unittest.TestCase):
    def test_strips_leading_zero_from_hour(self):
        # 09:03 AM -> "9:03 AM" (no leading zero on the hour)
        self.assertEqual(
            format_entry_date(datetime(2020, 1, 5, 9, 3, 0)),
            "Jan. 5, 2020 9:03 AM")

    def test_pm_and_two_digit_hour(self):
        self.assertEqual(
            format_entry_date(datetime(2024, 3, 15, 14, 30, 0)),
            "Mar. 15, 2024 2:30 PM")

    def test_midnight(self):
        self.assertEqual(
            format_entry_date(datetime(2024, 12, 1, 0, 5, 0)),
            "Dec. 1, 2024 12:05 AM")


if __name__ == "__main__":
    unittest.main()
