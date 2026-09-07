#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for combine_clean_md.py
(clean_markdown_content, combine_markdown_files).

Covers the markdown cleaning rules (stripping titles, pagebreaks, Original/
Tags/Next/Previous metadata, converting Date lines into ## headers) and the
file-combining path (front matter, ordering, blank-line collapsing, empty-glob
failure) using temp files.
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch

# Ensure the scripts directory is on the path so `from combine_clean_md import ...` resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from combine_clean_md import clean_markdown_content, combine_markdown_files


class TestCleanMarkdownContent(unittest.TestCase):
    def test_removes_pagebreak(self):
        out = clean_markdown_content("before\n\\pagebreak\nafter")
        self.assertNotIn(r"\pagebreak", out)
        self.assertIn("before", out)
        self.assertIn("after", out)

    def test_removes_title_line(self):
        # "# dybr" is a single-word H1 title and should be dropped
        out = clean_markdown_content("# dybr\nbody text")
        self.assertNotIn("# dybr", out)
        self.assertIn("body text", out)

    def test_keeps_multiword_heading(self):
        # Only single-word titles match the removal regex
        out = clean_markdown_content("# Two Words\nbody")
        self.assertIn("# Two Words", out)

    def test_converts_date_line_to_header(self):
        out = clean_markdown_content("**Date:** June 5, 2019 10:30 AM")
        self.assertIn("## June 5, 2019", out)
        self.assertNotIn("**Date:**", out)

    def test_date_header_strips_trailing_time(self):
        out = clean_markdown_content("**Date:** Jan. 1, 2020 09:00 PM")
        self.assertEqual(out.strip(), "## Jan. 1, 2020")

    def test_removes_original_link(self):
        out = clean_markdown_content(
            "**Original:** https://example.livejournal.com/123.html")
        self.assertEqual(out.strip(), "")

    def test_removes_original_link_http(self):
        out = clean_markdown_content("**Original:** http://example.com/1")
        self.assertEqual(out.strip(), "")

    def test_removes_tags_line(self):
        out = clean_markdown_content("**Tags:** music, life")
        self.assertEqual(out.strip(), "")

    def test_removes_next_link(self):
        out = clean_markdown_content("**Next:** [Some Entry](next.md)")
        self.assertEqual(out.strip(), "")

    def test_removes_previous_link(self):
        out = clean_markdown_content("**Previous:** [Some Entry](prev.md)")
        self.assertEqual(out.strip(), "")

    def test_keeps_ordinary_content(self):
        content = "This is a paragraph.\n\nAnother paragraph."
        self.assertEqual(clean_markdown_content(content), content)

    def test_full_entry_cleaning(self):
        content = "\n".join([
            "# dybr",
            "**Date:** July 4, 2018 12:00 PM",
            "**Original:** https://x.livejournal.com/9.html",
            "**Tags:** foo, bar",
            "",
            "Real body content here.",
            "",
            "**Previous:** [a](a.md)",
            "**Next:** [b](b.md)",
            r"\pagebreak",
        ])
        out = clean_markdown_content(content)
        self.assertIn("## July 4, 2018", out)
        self.assertIn("Real body content here.", out)
        self.assertNotIn("# dybr", out)
        self.assertNotIn("**Original:**", out)
        self.assertNotIn("**Tags:**", out)
        self.assertNotIn("**Previous:**", out)
        self.assertNotIn("**Next:**", out)
        self.assertNotIn(r"\pagebreak", out)


class TestCombineMarkdownFiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name, content):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    @patch("builtins.print")
    def test_combines_in_sorted_order_with_front_matter(self, _mock_print):
        self._write("02.md", "**Date:** Feb. 2, 2020 01:00 AM\nSecond body")
        self._write("01.md", "**Date:** Jan. 1, 2020 01:00 AM\nFirst body")
        out_path = os.path.join(self.tmpdir, "out.md")
        config = {"title": "My Book", "author": "Jane Doe"}

        combine_markdown_files(config, os.path.join(self.tmpdir, "*.md"), out_path)

        with open(out_path, encoding="utf-8") as f:
            result = f.read()

        # Front matter (pandoc %-lines)
        self.assertIn("% My Book", result)
        self.assertIn("% Jane Doe", result)
        # Sorted order: 01 before 02
        self.assertLess(result.index("First body"), result.index("Second body"))
        # Date lines converted to headers
        self.assertIn("## Jan. 1, 2020", result)
        self.assertIn("## Feb. 2, 2020", result)

    @patch("builtins.print")
    def test_uses_config_defaults(self, _mock_print):
        self._write("01.md", "body")
        out_path = os.path.join(self.tmpdir, "out.md")

        combine_markdown_files({}, os.path.join(self.tmpdir, "*.md"), out_path)

        with open(out_path, encoding="utf-8") as f:
            result = f.read()
        self.assertIn("% No Name", result)
        self.assertIn("% (anonymous)", result)

    @patch("builtins.print")
    def test_collapses_multiple_blank_lines(self, _mock_print):
        self._write("01.md", "line1\n\n\n\n\nline2")
        out_path = os.path.join(self.tmpdir, "out.md")

        combine_markdown_files({}, os.path.join(self.tmpdir, "*.md"), out_path)

        with open(out_path, encoding="utf-8") as f:
            result = f.read()
        self.assertNotIn("\n\n\n", result)

    @patch("builtins.print")
    def test_no_files_calls_fail(self, _mock_print):
        # fail() calls exit(1), which raises SystemExit
        out_path = os.path.join(self.tmpdir, "out.md")
        with self.assertRaises(SystemExit):
            combine_markdown_files(
                {}, os.path.join(self.tmpdir, "nope_*.md"), out_path)


if __name__ == "__main__":
    unittest.main()
