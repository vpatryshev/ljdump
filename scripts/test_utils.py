#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for utils.py (possible_unicode_or_none, object_to_xml_string).
"""

import os
import sys
import unittest
import xmlrpc.client

# Ensure the scripts directory is on the path so `from utils import ...` resolves
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import possible_unicode_or_none, object_to_xml_string


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


if __name__ == "__main__":
    unittest.main()
