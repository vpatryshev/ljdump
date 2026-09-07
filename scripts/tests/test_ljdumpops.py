#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for ljdumpops.py (load_config JSON loader, MimeExtensions constant).
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

# Ensure the scripts directory is on the path so `from ljdumpops import ...` resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ljdumpops import load_config, MimeExtensions


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self.paths = []

    def tearDown(self):
        for p in self.paths:
            if os.path.exists(p):
                os.remove(p)

    def _write_temp(self, content):
        fd, path = tempfile.mkstemp(suffix=".json")
        self.paths.append(path)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def test_valid_json_round_trip(self):
        data = {
            "author": "Dante Alighieri",
            "title": "Commedia Divina",
            "input_files": "CommediaDivina/*.md",
            "output_pdf": "CommediaDivina.pdf",
        }
        path = self._write_temp(json.dumps(data))
        self.assertEqual(load_config(path), data)

    def test_valid_json_unicode_round_trip(self):
        data = {"author": "Ро́ссия ☃", "title": "Тест"}
        path = self._write_temp(json.dumps(data, ensure_ascii=False))
        self.assertEqual(load_config(path), data)

    def test_empty_object(self):
        path = self._write_temp("{}")
        self.assertEqual(load_config(path), {})

    def test_json_array_top_level(self):
        path = self._write_temp("[1, 2, 3]")
        self.assertEqual(load_config(path), [1, 2, 3])

    def test_malformed_json_raises(self):
        path = self._write_temp("{ not valid json ")
        with self.assertRaises(json.JSONDecodeError):
            load_config(path)

    def test_missing_file_calls_fail_and_exits(self):
        # On a missing file, load_config calls fail(), which prints to stderr
        # and exits(1) -> SystemExit.
        missing = os.path.join(tempfile.gettempdir(),
                               "definitely_missing_ljdumpops_config.json")
        if os.path.exists(missing):
            os.remove(missing)
        with patch("builtins.print"), self.assertRaises(SystemExit):
            load_config(missing)


class TestMimeExtensions(unittest.TestCase):
    def test_is_dict(self):
        self.assertIsInstance(MimeExtensions, dict)

    def test_expected_mappings(self):
        self.assertEqual(MimeExtensions["image/gif"], ".gif")
        self.assertEqual(MimeExtensions["image/jpeg"], ".jpg")
        self.assertEqual(MimeExtensions["image/png"], ".png")

    def test_exact_contents(self):
        self.assertEqual(
            MimeExtensions,
            {
                "image/gif": ".gif",
                "image/jpeg": ".jpg",
                "image/png": ".png",
            },
        )

    def test_unknown_mime_absent(self):
        self.assertNotIn("image/webp", MimeExtensions)


if __name__ == "__main__":
    unittest.main()
