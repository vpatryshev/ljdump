#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for account.py — the pure message/auth construction in Account.
These are privacy-critical: a wrong security mapping could publish a
friends-only or private entry.
"""

import datetime as dt
import os
import sys
import unittest

# Ensure the scripts directory is on the path so `from account import ...` resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from account import Account


def _account():
    # Account.__init__ builds an xmlrpc ServerProxy but performs no network I/O.
    return Account("https://www.dreamwidth.org", "alice", "secret")


class TestBuildMessageSecurity(unittest.TestCase):
    """Security level must map correctly — this guards against privacy leaks."""

    def setUp(self):
        self.acct = _account()

    def _security(self, level):
        return self.acct._build_message("s", "b", "", level, None)

    def test_public(self):
        msg = self._security("public")
        self.assertEqual(msg["security"], "public")
        self.assertNotIn("allowmask", msg)

    def test_friends_uses_usemask_and_allowmask(self):
        msg = self._security("friends")
        self.assertEqual(msg["security"], "usemask")
        self.assertEqual(msg["allowmask"], 1)

    def test_private(self):
        msg = self._security("private")
        self.assertEqual(msg["security"], "private")
        self.assertNotIn("allowmask", msg)

    def test_unknown_level_falls_back_to_public(self):
        msg = self._security("banana")
        self.assertEqual(msg["security"], "public")


class TestBuildMessageContent(unittest.TestCase):
    def setUp(self):
        self.acct = _account()

    def test_core_fields(self):
        msg = self.acct._build_message("My subject", "Body text", "t1, t2",
                                       "public", None)
        self.assertEqual(msg["username"], "alice")
        self.assertEqual(msg["subject"], "My subject")
        self.assertEqual(msg["event"], "Body text")
        self.assertEqual(msg["ver"], 1)
        self.assertEqual(msg["lineendings"], "unix")
        self.assertEqual(msg["props"]["taglist"], "t1, t2")

    def test_backdated_when_post_date_given(self):
        when = dt.datetime(2013, 12, 7, 14, 14)
        msg = self.acct._build_message("s", "b", "", "public", when)
        self.assertEqual(
            (msg["year"], msg["mon"], msg["day"], msg["hour"], msg["min"]),
            (2013, 12, 7, 14, 14))
        self.assertTrue(msg["props"]["opt_backdated"])

    def test_not_backdated_when_no_post_date(self):
        msg = self.acct._build_message("s", "b", "", "public", None)
        self.assertFalse(msg["props"]["opt_backdated"])


class TestAuth(unittest.TestCase):
    def test_auth_fields(self):
        auth = _account()._auth()
        self.assertEqual(auth, {
            "auth_method": "clear",
            "username": "alice",
            "password": "secret",
        })


if __name__ == "__main__":
    unittest.main()
