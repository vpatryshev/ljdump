#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for journal.py (Journal class: construction, workdir derivation,
and write_text file I/O + timestamp handling).
"""

import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch

# Ensure the scripts directory is on the path so `from journal import ...` resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from journal import Journal


class TestJournalInit(unittest.TestCase):
    def test_name_is_stored(self):
        j = Journal("myjournal")
        self.assertEqual(j.name, "myjournal")

    def test_workdir_is_derived_from_name(self):
        j = Journal("myjournal")
        self.assertEqual(j.workdir, "work/myjournal")

    def test_workdir_with_unicode_name(self):
        j = Journal("Ро́ссия")
        self.assertEqual(j.workdir, "work/Ро́ссия")


class TestJournalWriteText(unittest.TestCase):
    def setUp(self):
        # Create an isolated temp directory that plays the role of the
        # Journal.workdir so file writes never touch the real tree.
        self.tmpdir = tempfile.mkdtemp()
        self.j = Journal("unit-test")
        # Point workdir at the temp directory (no source refactor needed).
        self.j.workdir = self.tmpdir

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @staticmethod
    def _flush():
        # write_text now closes the file via a `with` block, so content is on
        # disk as soon as it returns. Kept as a no-op so call sites read clearly.
        pass

    def test_writes_content_to_expected_path(self):
        self.j.write_text("entry.txt", "hello world", timestamp=1000)
        self._flush()
        path = os.path.join(self.tmpdir, "entry.txt")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="UTF-8") as f:
            self.assertEqual(f.read(), "hello world")

    def test_writes_utf8_content(self):
        content = "Ро́ссия ☃ — café"
        self.j.write_text("uni.txt", content, timestamp=1000)
        self._flush()
        path = os.path.join(self.tmpdir, "uni.txt")
        with open(path, encoding="UTF-8") as f:
            self.assertEqual(f.read(), content)
        # Verify it was actually encoded as UTF-8 on disk.
        with open(path, "rb") as f:
            self.assertEqual(f.read().decode("UTF-8"), content)

    def test_empty_content(self):
        self.j.write_text("empty.txt", "", timestamp=1000)
        self._flush()
        path = os.path.join(self.tmpdir, "empty.txt")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.path.getsize(path), 0)

    def test_path_is_workdir_slash_filename(self):
        # Assert the path-construction contract directly by mocking the file
        # write + utime, independent of the buffering/close behavior.
        with patch("journal.codecs.open") as mock_open, \
                patch("journal.os.utime") as mock_utime:
            self.j.write_text("sub.txt", "content", timestamp=1000)
        expected_path = f"{self.tmpdir}/sub.txt"
        mock_open.assert_called_once_with(expected_path, "w", "UTF-8")
        # The file is used as a context manager, so the write goes through the
        # object returned by __enter__.
        mock_open.return_value.__enter__.return_value.write.assert_called_once_with(
            "content")
        mock_utime.assert_called_once_with(expected_path, (1000, 1000))

    def test_explicit_timestamp_passed_to_utime(self):
        # write_text sets the timestamp via os.utime; assert it forwards the
        # given value.
        ts = 1234567890
        with patch("journal.os.utime") as mock_utime:
            self.j.write_text("ts.txt", "data", timestamp=ts)
        mock_utime.assert_called_once_with(
            f"{self.tmpdir}/ts.txt", (ts, ts))

    def test_explicit_timestamp_lands_on_disk(self):
        # The file is closed before os.utime runs, so the mtime actually sticks
        # (regression guard for the leaked-handle bug that clobbered it).
        ts = 1234567890
        self.j.write_text("ondisk.txt", "data", timestamp=ts)
        path = os.path.join(self.tmpdir, "ondisk.txt")
        self.assertEqual(int(os.path.getmtime(path)), ts)

    def test_default_timestamp_uses_module_time(self):
        # With no timestamp, write_text calls journal.time.time() at call time,
        # so patching it controls the value handed to os.utime.
        with patch("journal.time.time", return_value=555.0), \
                patch("journal.os.utime") as mock_utime:
            self.j.write_text("clock.txt", "x")
        mock_utime.assert_called_once_with(
            f"{self.tmpdir}/clock.txt", (555.0, 555.0))

    def test_overwrite_replaces_content(self):
        self.j.write_text("dup.txt", "first", timestamp=1000)
        self._flush()
        self.j.write_text("dup.txt", "second", timestamp=2000)
        self._flush()
        path = os.path.join(self.tmpdir, "dup.txt")
        with open(path, encoding="UTF-8") as f:
            self.assertEqual(f.read(), "second")


if __name__ == "__main__":
    unittest.main()
