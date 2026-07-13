#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for update_from_db.py — parse_itemids() (single id, list, whitespace,
empty segments, and error handling on bad or empty input).
"""

import os
import sys
import unittest
from unittest.mock import patch

# Ensure the scripts directory is on the path so imports resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from update_from_db import parse_itemids


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


if __name__ == "__main__":
    unittest.main()
