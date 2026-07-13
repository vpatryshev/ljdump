#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for dwscrape.py — the journal-subdomain construction. Dreamwidth maps
underscores in usernames to hyphens in the host (juan_gandhi ->
juan-gandhi.dreamwidth.org); an underscore host fails TLS verification. This is a
regression guard for that fix.
"""

import os
import sys
import unittest

# Ensure the scripts directory is on the path so imports resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from account import Account
from dwscrape import DreamwidthScraper


def _scraper(journal_name):
    acct = Account("https://www.dreamwidth.org", "u", "p")
    return DreamwidthScraper(acct, journal_name, verbose=False)


class TestSubdomain(unittest.TestCase):
    def test_underscore_becomes_hyphen_in_host(self):
        s = _scraper("juan_gandhi")
        self.assertEqual(s.base_url, "https://juan-gandhi.dreamwidth.org")

    def test_multiple_underscores(self):
        s = _scraper("a_b_c")
        self.assertEqual(s.base_url, "https://a-b-c.dreamwidth.org")

    def test_name_without_underscore_unchanged(self):
        s = _scraper("kdanilov")
        self.assertEqual(s.base_url, "https://kdanilov.dreamwidth.org")

    def test_journal_name_keeps_underscore(self):
        # The DB path / table keys use the underscore form, so journal_name
        # itself must NOT be hyphenated.
        s = _scraper("juan_gandhi")
        self.assertEqual(s.journal_name, "juan_gandhi")


if __name__ == "__main__":
    unittest.main()
