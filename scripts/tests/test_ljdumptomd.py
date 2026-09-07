#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for ljdumptomd.py — pure/importable helpers:
parse_date_range (date-range parsing + validation), filter_entries (tag and
date-range filtering), html_to_markdown (HTML->markdown conversion helpers),
handle_images (image reference rewriting, with network downloads mocked),
create_entry_markdown (metadata/title formatting) and write_markdown (temp file I/O).
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

# Ensure the scripts directory is on the path so sibling imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ljdumptomd import (
    parse_date_range,
    filter_entries,
    html_to_markdown,
    handle_images,
    create_entry_markdown,
    write_markdown,
)


def _unix(year, month, day):
    """UTC unix timestamp for a given calendar date (used to build fixtures)."""
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


def _entry(itemid=1, subject="Subj", event="body", taglist=None, url=None,
           when=None):
    """Build a minimal entry dict matching what ljdumptomd expects."""
    if when is None:
        when = _unix(2020, 6, 15)
    return {
        "itemid": itemid,
        "subject": subject,
        "event": event,
        "props_taglist": taglist,
        "url": url,
        "eventtime_unix": when,
    }


class TestParseDateRange(unittest.TestCase):
    def test_none_returns_none_pair(self):
        self.assertEqual(parse_date_range(None), (None, None))

    def test_empty_string_returns_none_pair(self):
        self.assertEqual(parse_date_range(""), (None, None))

    def test_valid_range(self):
        start, end = parse_date_range("2020-01-01:2020-12-31")
        self.assertEqual(start, datetime(2020, 1, 1))
        self.assertEqual(end, datetime(2020, 12, 31))

    def test_whitespace_around_dates_is_trimmed(self):
        start, end = parse_date_range(" 2020-01-01 : 2020-12-31 ")
        self.assertEqual(start, datetime(2020, 1, 1))
        self.assertEqual(end, datetime(2020, 12, 31))

    def test_wrong_number_of_parts_raises(self):
        with self.assertRaises(ValueError):
            parse_date_range("2020-01-01")

    def test_three_parts_raises(self):
        with self.assertRaises(ValueError):
            parse_date_range("2020-01-01:2020-06-01:2020-12-31")

    def test_start_after_end_raises(self):
        with self.assertRaises(ValueError):
            parse_date_range("2020-12-31:2020-01-01")

    def test_bad_date_format_raises(self):
        with self.assertRaises(ValueError):
            parse_date_range("2020/01/01:2020/12/31")


class TestFilterEntries(unittest.TestCase):
    def setUp(self):
        self.entries = [
            _entry(1, taglist="travel, photos", when=_unix(2019, 5, 1)),
            _entry(2, taglist="work", when=_unix(2020, 6, 15)),
            _entry(3, taglist=None, when=_unix(2021, 1, 1)),
            _entry(4, taglist="photos", when=_unix(2022, 3, 3)),
        ]

    def _ids(self, result):
        return [e["itemid"] for e in result]

    def test_no_filters_returns_all(self):
        with patch("builtins.print"):
            self.assertEqual(self._ids(filter_entries(self.entries)),
                             [1, 2, 3, 4])

    def test_single_tag_filter(self):
        with patch("builtins.print"):
            self.assertEqual(self._ids(filter_entries(self.entries, tags=["work"])),
                             [2])

    def test_tag_filter_matches_any_of_multiple(self):
        with patch("builtins.print"):
            got = filter_entries(self.entries, tags=["work", "photos"])
        self.assertEqual(self._ids(got), [1, 2, 4])

    def test_tag_filter_matches_within_multi_tag_entry(self):
        with patch("builtins.print"):
            got = filter_entries(self.entries, tags=["travel"])
        self.assertEqual(self._ids(got), [1])

    def test_entry_without_tags_excluded_when_tag_filter_set(self):
        with patch("builtins.print"):
            got = filter_entries(self.entries, tags=["work"])
        self.assertNotIn(3, self._ids(got))

    def test_no_matching_tag_returns_empty(self):
        with patch("builtins.print"):
            got = filter_entries(self.entries, tags=["nonexistent"])
        self.assertEqual(got, [])

    def test_start_date_filter(self):
        with patch("builtins.print"):
            got = filter_entries(self.entries, start_date=datetime(2020, 1, 1))
        self.assertEqual(self._ids(got), [2, 3, 4])

    def test_end_date_filter(self):
        with patch("builtins.print"):
            got = filter_entries(self.entries, end_date=datetime(2020, 12, 31))
        self.assertEqual(self._ids(got), [1, 2])

    def test_date_range_and_tag_combined(self):
        with patch("builtins.print"):
            got = filter_entries(
                self.entries,
                tags=["photos"],
                start_date=datetime(2020, 1, 1),
                end_date=datetime(2023, 1, 1),
            )
        self.assertEqual(self._ids(got), [4])


class TestHtmlToMarkdown(unittest.TestCase):
    def test_bold_tags(self):
        self.assertEqual(html_to_markdown("<b>hi</b>"), "**hi**")

    def test_strong_tags(self):
        self.assertEqual(html_to_markdown("<strong>hi</strong>"), "**hi**")

    def test_italic_tags(self):
        self.assertEqual(html_to_markdown("<i>hi</i>"), "*hi*")

    def test_em_tags(self):
        self.assertEqual(html_to_markdown("<em>hi</em>"), "*hi*")

    def test_headers(self):
        self.assertEqual(html_to_markdown("<h1>Title</h1>").strip(), "# Title")
        self.assertEqual(html_to_markdown("<h3>Sub</h3>").strip(), "### Sub")

    def test_line_break_removed(self):
        self.assertEqual(html_to_markdown("a<br/>b"), "a\nb")

    def test_paragraphs_become_blank_line_separated(self):
        self.assertEqual(html_to_markdown("<p>a</p><p>b</p>"), "a\n\nb")

    def test_unordered_list(self):
        out = html_to_markdown("<ul><li>one</li><li>two</li></ul>")
        self.assertIn("- one", out)
        self.assertIn("- two", out)

    def test_code_inline(self):
        self.assertEqual(html_to_markdown("<code>x=1</code>"), "`x=1`")

    def test_pre_block_becomes_fence(self):
        out = html_to_markdown("<pre>print(1)</pre>")
        self.assertIn("```", out)
        self.assertIn("print(1)", out)

    def test_sub_and_sup(self):
        self.assertEqual(html_to_markdown("H<sub>2</sub>O"), "H~2~O")
        self.assertEqual(html_to_markdown("x<sup>2</sup>"), "x^2^")

    def test_multiple_newlines_collapsed(self):
        # Three or more newlines collapse to a blank-line separator.
        self.assertEqual(html_to_markdown("a<br/><br/><br/><br/>b"), "a\n\nb")

    def test_leading_trailing_whitespace_stripped(self):
        self.assertEqual(html_to_markdown("   <b>hi</b>   "), "**hi**")

    def test_none_output_dir_leaves_images_untouched_via_handle(self):
        # With no output_dir, images pass through unchanged.
        html = '<img src="http://example.com/a.png" />'
        self.assertEqual(html_to_markdown(html), html)


class TestHandleImages(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()

    def tearDown(self):
        for name in os.listdir(self._dir):
            os.unlink(os.path.join(self._dir, name))
        os.rmdir(self._dir)

    def test_no_output_dir_returns_content_unchanged(self):
        html = '<img src="http://example.com/a.png" />'
        self.assertEqual(handle_images(html, None), html)

    def test_local_image_left_untouched(self):
        html = '<img src="local.png" />'
        # Non-http src is skipped entirely, no download attempted.
        self.assertEqual(handle_images(html, self._dir), html)

    def test_remote_image_downloaded_and_rewritten(self):
        url = "http://example.com/pic.png"
        expected_name = None

        class FakeResponse:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        with patch("ljdumptomd.urllib.request.urlopen",
                   return_value=FakeResponse(b"PNGDATA")) as m_open, \
                patch("ljdumptomd.subprocess.run") as m_run, \
                patch("builtins.print"):
            # 'file' type check reports a non-WebP so no conversion happens.
            m_run.return_value = type("R", (), {"stdout": "PNG image data"})()
            out = handle_images(f'<img src="{url}" />', self._dir)

        m_open.assert_called_once()
        # Rewritten to a local hashed filename, and file written to temp dir.
        self.assertRegex(out, r'<img src="img_[0-9a-f]{12}\.png"\s*>')
        written = [n for n in os.listdir(self._dir) if n.startswith("img_")]
        self.assertEqual(len(written), 1)

    def test_download_failure_keeps_original_tag(self):
        url = "http://example.com/broken.png"
        tag = f'<img src="{url}" />'
        with patch("ljdumptomd.urllib.request.urlopen",
                   side_effect=Exception("boom")), \
                patch("builtins.print"):
            out = handle_images(tag, self._dir)
        self.assertEqual(out, tag)


class TestCreateEntryMarkdown(unittest.TestCase):
    def test_title_and_date_and_body(self):
        entry = _entry(
            itemid=42, subject="Hello", event="<b>world</b>",
            when=_unix(2020, 6, 15),
        )
        out = create_entry_markdown(entry)
        self.assertIn("# Hello", out)
        self.assertIn("**Date:**", out)
        self.assertIn("**world**", out)

    def test_date_formatting(self):
        # 2020-06-15 00:00:00 UTC -> "Jun. 15, 2020 12:00 AM"
        entry = _entry(when=_unix(2020, 6, 15))
        out = create_entry_markdown(entry)
        self.assertIn("Jun. 15, 2020 12:00 AM", out)

    def test_url_included_when_present(self):
        entry = _entry(url="http://example.com/e")
        out = create_entry_markdown(entry)
        self.assertIn("**Original:** http://example.com/e", out)

    def test_url_omitted_when_absent(self):
        entry = _entry(url=None)
        out = create_entry_markdown(entry)
        self.assertNotIn("**Original:**", out)

    def test_tags_included_when_present(self):
        entry = _entry(taglist="travel, photos")
        out = create_entry_markdown(entry)
        self.assertIn("**Tags:** travel, photos", out)

    def test_tags_omitted_when_absent(self):
        entry = _entry(taglist=None)
        out = create_entry_markdown(entry)
        self.assertNotIn("**Tags:**", out)


class TestWriteMarkdown(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()

    def tearDown(self):
        for name in os.listdir(self._dir):
            os.unlink(os.path.join(self._dir, name))
        os.rmdir(self._dir)

    def test_writes_utf8_content(self):
        path = os.path.join(self._dir, "out.md")
        content = "# Título ☃\n\nПривет"
        write_markdown(path, content)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), content)


if __name__ == "__main__":
    unittest.main()
