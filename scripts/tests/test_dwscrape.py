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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


class TestExtractEntryDatetime(unittest.TestCase):
    """Guards the entry-date regex against both Dreamwidth markup styles."""

    def setUp(self):
        self.s = _scraper("taki-net")

    def test_full_month_name_space_separated(self):
        # taki-net style: full month, weekday prefix, space before the day
        html = ('<span class="datetime"><span class="date">Sunday, '
                '<a href="/2027/04/">April</a> <a href="/2027/04/11/">11th</a>, '
                '<a href="/2027/">2027</a></span> '
                '<span class="time">02:21 am</span></span>')
        dt = self.s.extract_entry_datetime(html)
        self.assertIsNotNone(dt)
        self.assertEqual((dt.year, dt.month, dt.day, dt.hour, dt.minute),
                         (2027, 4, 11, 2, 21))

    def test_abbreviated_month_period_separated(self):
        # older style: abbreviated month with a period after the link
        html = ('<span class="datetime"><span class="date">'
                '<a>Nov</a>. <a>29th</a>, <a>2022</a></span> '
                '<span class="time">05:58 am</span></span>')
        dt = self.s.extract_entry_datetime(html)
        self.assertIsNotNone(dt)
        self.assertEqual((dt.year, dt.month, dt.day, dt.hour, dt.minute),
                         (2022, 11, 29, 5, 58))

    def test_pm_time(self):
        html = ('<span class="datetime"><span class="date">'
                '<a>June</a> <a>3rd</a>, <a>2021</a></span> '
                '<span class="time">09:19 pm</span></span>')
        dt = self.s.extract_entry_datetime(html)
        self.assertEqual(dt.hour, 21)

    def test_no_datetime_returns_none(self):
        self.assertIsNone(self.s.extract_entry_datetime("<p>no date here</p>"))


if __name__ == "__main__":
    unittest.main()
