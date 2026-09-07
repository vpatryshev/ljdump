#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for cache.py (path, clear, clearAll, isFresh, get, put, getOrCall).

Covers cache set/get hit and miss, TTL expiry, persistence across "instances"
(re-reading from the on-disk cache directory), and missing-key behavior.
"""

import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Ensure the scripts directory is on the path so `from cache import ...` resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cache
from cache import path, clear, clearAll, isFresh, get, put, getOrCall


class CacheTestBase(unittest.TestCase):
    """Redirects the module-level cache directory to a temporary directory.

    cache.py binds CACHEPATH/TTL at import time and creates a `cache/` dir as a
    side effect. We do not modify the source; instead each test points
    cache.CACHEPATH at a fresh temp dir and restores the originals afterward.
    """

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self._orig_cachepath = cache.CACHEPATH
        self._orig_ttl = cache.TTL
        cache.CACHEPATH = self.tmpdir

    def tearDown(self):
        cache.CACHEPATH = self._orig_cachepath
        cache.TTL = self._orig_ttl
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestPath(CacheTestBase):
    def test_path_joins_key_under_cache_dir(self):
        self.assertEqual(path("mykey"), self.tmpdir / "mykey")


class TestPutGet(CacheTestBase):
    def test_get_hit_returns_put_value(self):
        value = "--test contents\nof file 'test1'--"
        put("test1", value)
        self.assertEqual(get("test1"), value)

    def test_get_miss_returns_none_for_unknown_key(self):
        self.assertIsNone(get("never-stored"))

    def test_put_then_get_roundtrips_unicode(self):
        value = "Ро́ссия ☃ — snowman"
        put("uni", value)
        self.assertEqual(get("uni"), value)

    def test_put_overwrites_existing_value(self):
        put("k", "first")
        put("k", "second")
        self.assertEqual(get("k"), "second")


class TestClear(CacheTestBase):
    def test_clear_removes_existing_key(self):
        put("test1", "data")
        self.assertTrue(path("test1").exists())
        clear("test1")
        self.assertFalse(path("test1").exists())
        self.assertIsNone(get("test1"))

    def test_clear_nonexistent_key_is_noop(self):
        # Must not raise for a key that was never stored.
        clear("non existent file")

    def test_clearAll_empties_the_cache(self):
        put("a", "1")
        put("b", "2")
        put("c", "3")
        clearAll()
        self.assertEqual(list(self.tmpdir.iterdir()), [])
        self.assertIsNone(get("a"))
        self.assertIsNone(get("b"))
        self.assertIsNone(get("c"))


class TestFreshnessAndTTL(CacheTestBase):
    def test_isFresh_false_for_missing_key(self):
        self.assertFalse(isFresh("missing"))

    def test_isFresh_true_for_freshly_written(self):
        put("fresh", "value")
        self.assertTrue(isFresh("fresh"))

    def test_ttl_expiry_makes_value_unavailable(self):
        cache.TTL = 1  # 1 second TTL, matching the original inline self-test
        put("test2", "this file gets expired soon")
        # Still fresh immediately after writing.
        self.assertEqual(get("test2"), "this file gets expired soon")

        # Simulate the clock advancing past the TTL by patching time.time as
        # referenced inside the cache module (avoids a real sleep).
        p = path("test2")
        future = p.stat().st_mtime + cache.TTL + 1
        with mock.patch.object(cache.time, "time", return_value=future):
            self.assertFalse(isFresh("test2"))
            self.assertIsNone(get("test2"))

    def test_value_still_fresh_just_before_ttl(self):
        cache.TTL = 100
        put("k", "v")
        p = path("k")
        just_before = p.stat().st_mtime + cache.TTL - 1
        with mock.patch.object(cache.time, "time", return_value=just_before):
            self.assertTrue(isFresh("k"))
            self.assertEqual(get("k"), "v")


class TestGetOrCall(CacheTestBase):
    def test_getOrCall_computes_and_caches_on_miss(self):
        calls = []

        def fun(key):
            calls.append(key)
            return f"<<{key}-1>>"

        value1 = getOrCall("test3", fun)
        self.assertEqual(value1, "<<test3-1>>")
        self.assertEqual(calls, ["test3"])

        # Second call is a hit: fun must not be invoked again.
        value2 = getOrCall("test3", lambda key: f"<<{key}-OTHER>>")
        self.assertEqual(value2, "<<test3-1>>")
        self.assertEqual(calls, ["test3"])

    def test_getOrCall_recomputes_after_ttl_expiry(self):
        cache.TTL = 1
        v1 = getOrCall("test3", lambda key: f"<<{key}-1>>")
        self.assertEqual(v1, "<<test3-1>>")

        future = path("test3").stat().st_mtime + cache.TTL + 1
        with mock.patch.object(cache.time, "time", return_value=future):
            v3 = getOrCall("test3", lambda key: f"<<{key}-3>>")
        self.assertEqual(v3, "<<test3-3>>")


class TestPersistenceAcrossInstances(CacheTestBase):
    def test_value_persists_and_is_readable_from_disk(self):
        # Emulates a second "instance": the value written earlier is served from
        # the on-disk cache directory without any in-memory state.
        put("persisted", "durable-value")
        # Drop any notion of in-memory caching by reading directly via get(),
        # which re-reads the file from disk.
        self.assertEqual(get("persisted"), "durable-value")
        # And confirm the raw file on disk holds the content.
        self.assertEqual(
            (self.tmpdir / "persisted").read_text(encoding="utf-8"),
            "durable-value",
        )


if __name__ == "__main__":
    unittest.main()
