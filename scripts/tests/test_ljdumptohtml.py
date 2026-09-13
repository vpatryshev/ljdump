#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for ljdumptohtml.py.

Covers the pure, importable HTML-generation helpers:
  - create_template_page          (stylesheet path prefix, title, journal name)
  - render_comment_and_subcomments_containers / render_comments_section
                                  (comment tree building, depth nesting, date/user rendering)
  - render_one_entry_container    (comment-count pluralization, tags, mood/music, userpic)
  - resolve_cached_image_references (image URL rewriting, Dreamwidth normalization, uncached list)
  - create_single_entry_page      (prev/next nav, body insertion, newline->br)
  - create_history_page           (pagination nav counts/links, body interleaving)
  - create_table_of_contents_page (entry count, sections, by-tag, by-month, date formatting)
  - create_uncached_images_report_page (count banner, per-entry url count)
  - download_entry_image          (network mocked; success, non-image, HTTP/URL errors)

The top-level orchestrator ljdumptohtml() is covered by an end-to-end
characterization test (TestLjdumptohtmlOrchestrator) that runs it against a real
temporary LJDB in a temporary working directory with image caching disabled (no
network). The __main__ argparse block is not covered.
"""

import os
import sys
import tempfile
import shutil
import unittest
import urllib.error
from datetime import datetime
from unittest.mock import patch, MagicMock
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ljdumptohtml import (
    Journal,
    ljdumptohtml,
    _group_comments_by_entry,
    _index_by,
    _group_entries_by_tag,
    create_template_page,
    render_comment_and_subcomments_containers,
    render_comments_section,
    render_one_entry_container,
    resolve_cached_image_references,
    create_single_entry_page,
    create_history_page,
    create_table_of_contents_page,
    create_uncached_images_report_page,
    download_entry_image,
)
from ljdb import LJDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A fixed timestamp: 2024-03-15 14:33:20 UTC
FIXED_TS = 1710513200


def _tostr(element):
    """Serialize an ElementTree element to a unicode string."""
    return ET.tostring(element, encoding="unicode")


def _comment(id=1, parentid=None, subject="Re: Hi", body="A comment",
             user="reader", date_unix=FIXED_TS):
    return {
        "id": id,
        "parentid": parentid,
        "subject": subject,
        "body": body,
        "user": user,
        "date_unix": date_unix,
    }


def _entry(itemid=1, subject="Hello", eventtime_unix=FIXED_TS, taglist=None,
           moodid=None, music=None, picture_keyword=None,
           url="https://example.com/1", event="body text"):
    return {
        "itemid": itemid,
        "subject": subject,
        "eventtime_unix": eventtime_unix,
        "props_taglist": taglist,
        "props_current_moodid": moodid,
        "props_current_music": music,
        "props_picture_keyword": picture_keyword,
        "url": url,
        "event": event,
    }


# ---------------------------------------------------------------------------
# create_template_page
# ---------------------------------------------------------------------------

class TestCreateTemplatePage(unittest.TestCase):
    def setUp(self):
        self.journal = Journal("myjournal")

    def test_returns_page_and_content_element(self):
        page, content = create_template_page(self.journal, "Title", True)
        self.assertEqual(page.tag, "html")
        # content is the innermost entries div
        self.assertEqual(content.tag, "div")

    def test_subfolder_uses_relative_stylesheet_path(self):
        page, _ = create_template_page(self.journal, "Title", in_subfolder=True)
        s = _tostr(page)
        self.assertIn('href="../stylesheet.css"', s)

    def test_top_level_uses_plain_stylesheet_path(self):
        page, _ = create_template_page(self.journal, "Title", in_subfolder=False)
        s = _tostr(page)
        self.assertIn('href="stylesheet.css"', s)
        self.assertNotIn('href="../stylesheet.css"', s)

    def test_title_text_present(self):
        page, _ = create_template_page(self.journal, "My Page Title", True)
        self.assertIn("<title>My Page Title</title>", _tostr(page))

    def test_journal_name_rendered_in_header(self):
        page, _ = create_template_page(self.journal, "Title", True)
        self.assertIn("myjournal", _tostr(page))

    def test_charset_meta_present(self):
        page, _ = create_template_page(self.journal, "Title", True)
        self.assertIn('charset="utf-8"', _tostr(page))


# ---------------------------------------------------------------------------
# Comment tree building
# ---------------------------------------------------------------------------

class TestCommentThreading(unittest.TestCase):
    def test_single_comment_depth_and_id(self):
        c = _comment(id=1)
        container = render_comment_and_subcomments_containers(
            c, {1: c}, {1: []}, {}, depth=1)
        self.assertEqual(container.attrib["data-comment-depth"], "1")
        self.assertIn('id="cmt1"', _tostr(container))

    def test_nested_children_increase_depth(self):
        # 1 -> 2 -> 4 (chain), and a sibling 3 at top level
        c1, c2, c3, c4 = (_comment(1), _comment(2, 1),
                          _comment(3), _comment(4, 2))
        by_id = {1: c1, 2: c2, 3: c3, 4: c4}
        children = {1: [2], 2: [4], 3: [], 4: []}
        container = render_comment_and_subcomments_containers(
            c1, by_id, children, {}, depth=1)
        s = _tostr(container)
        # comment 4 is nested two levels below comment 1 -> depth 3
        self.assertIn("comment-depth-3", s)
        self.assertIn('id="cmt2"', s)
        self.assertIn('id="cmt4"', s)

    def test_render_comments_section_groups_top_level(self):
        comments = [_comment(1, None), _comment(2, 1),
                    _comment(3, None), _comment(4, 2)]
        by_id = {c["id"]: c for c in comments}
        wrapper = render_comments_section({"itemid": 10}, comments, by_id, {})
        # wrapper > inner > [top-level threads]
        inner = list(wrapper)[0]
        top_threads = list(inner)
        self.assertEqual(len(top_threads), 2)  # comments 1 and 3 are top-level

    def test_render_comments_section_includes_all_comments(self):
        comments = [_comment(1, None), _comment(2, 1),
                    _comment(3, None), _comment(4, 2)]
        by_id = {c["id"]: c for c in comments}
        s = _tostr(render_comments_section({"itemid": 10}, comments, by_id, {}))
        for cid in ("cmt1", "cmt2", "cmt3", "cmt4"):
            self.assertIn('id="%s"' % cid, s)

    def test_comment_with_no_date_renders_none(self):
        c = _comment(id=5, date_unix=None)
        container = render_comment_and_subcomments_containers(
            c, {5: c}, {5: []}, {}, depth=1)
        self.assertIn("(None)", _tostr(container))

    def test_comment_with_date_renders_formatted_date(self):
        c = _comment(id=6, date_unix=FIXED_TS)
        s = _tostr(render_comment_and_subcomments_containers(
            c, {6: c}, {6: []}, {}, depth=1))
        self.assertIn("Date: ", s)
        self.assertIn("Mar. 15", s)
        self.assertIn("2024", s)

    def test_comment_with_no_user_renders_none(self):
        c = _comment(id=7, user=None)
        s = _tostr(render_comment_and_subcomments_containers(
            c, {7: c}, {7: []}, {}, depth=1))
        self.assertIn("(None)", s)

    def test_comment_with_user_links_to_dreamwidth(self):
        c = _comment(id=8, user="alice")
        s = _tostr(render_comment_and_subcomments_containers(
            c, {8: c}, {8: []}, {}, depth=1))
        self.assertIn("/users/alice", s)


# ---------------------------------------------------------------------------
# render_one_entry_container
# ---------------------------------------------------------------------------

class TestRenderOneEntryContainer(unittest.TestCase):
    def setUp(self):
        self.journal = Journal("myjournal")

    def test_entry_id_and_title(self):
        w = render_one_entry_container(self.journal, _entry(itemid=42, subject="X"),
                                       0, {}, {})
        s = _tostr(w)
        self.assertIn('id="entry-wrapper-42"', s)
        self.assertIn("../entries/entry-42.html", s)

    def test_permalink_original_url(self):
        w = render_one_entry_container(
            self.journal, _entry(url="https://example.com/orig"), 0, {}, {})
        s = _tostr(w)
        self.assertIn("https://example.com/orig", s)
        self.assertIn("Original", s)

    def test_zero_comments_no_comment_link(self):
        w = render_one_entry_container(self.journal, _entry(), 0, {}, {})
        s = _tostr(w)
        self.assertNotIn("comment", s.lower())

    def test_single_comment_singular_text(self):
        w = render_one_entry_container(self.journal, _entry(), 1, {}, {})
        s = _tostr(w)
        self.assertIn("1 comment", s)
        self.assertNotIn("1 comments", s)

    def test_multiple_comments_plural_text(self):
        w = render_one_entry_container(self.journal, _entry(), 5, {}, {})
        self.assertIn("5 comments", _tostr(w))

    def test_tags_rendered_as_links(self):
        w = render_one_entry_container(
            self.journal, _entry(taglist="music, travel, life"), 0, {}, {})
        s = _tostr(w)
        self.assertEqual(s.count('rel="tag"'), 3)
        self.assertIn("../index.html#music", s)

    def test_single_tag(self):
        w = render_one_entry_container(
            self.journal, _entry(taglist="solo"), 0, {}, {})
        s = _tostr(w)
        self.assertEqual(s.count('rel="tag"'), 1)
        self.assertIn("../index.html#solo", s)

    def test_no_tags_no_tag_section(self):
        w = render_one_entry_container(
            self.journal, _entry(taglist=None), 0, {}, {})
        self.assertNotIn('rel="tag"', _tostr(w))

    def test_mood_rendered_when_present(self):
        moods = {5: {"id": 5, "name": "cheerful"}}
        w = render_one_entry_container(
            self.journal, _entry(moodid=5), 0, {}, moods)
        s = _tostr(w)
        self.assertIn("Current Mood: ", s)
        self.assertIn("cheerful", s)

    def test_music_rendered_when_present(self):
        w = render_one_entry_container(
            self.journal, _entry(music="Jazz FM"), 0, {}, {})
        s = _tostr(w)
        self.assertIn("Current Music: ", s)
        self.assertIn("Jazz FM", s)

    def test_no_metadata_when_absent(self):
        w = render_one_entry_container(self.journal, _entry(), 0, {}, {})
        s = _tostr(w)
        self.assertNotIn("metadata bottom-metadata", s)

    def test_custom_userpic_used_when_keyword_matches(self):
        icons = {"mypic": {"filename": "p.png"}}
        w = render_one_entry_container(
            self.journal, _entry(picture_keyword="mypic"), 0, icons, {})
        self.assertIn("../userpics/p.png", _tostr(w))

    def test_datestamp_formatted(self):
        w = render_one_entry_container(self.journal, _entry(), 0, {}, {})
        s = _tostr(w)
        self.assertIn("Mar. 15", s)
        self.assertIn("2024", s)


# ---------------------------------------------------------------------------
# resolve_cached_image_references
# ---------------------------------------------------------------------------

class TestResolveCachedImageReferences(unittest.TestCase):
    def test_cached_url_rewritten_to_local_path(self):
        content = '<img src="http://foo.com/a.png">'
        mapping = {"http://foo.com/a.png": "F1.png"}
        out, uncached = resolve_cached_image_references(content, mapping)
        self.assertIn('../images/F1.png', out)
        self.assertEqual(uncached, [])

    def test_uncached_url_reported(self):
        content = '<img src="http://none.com/z.png">'
        out, uncached = resolve_cached_image_references(content, {})
        # Unchanged content, url reported as uncached
        self.assertIn("http://none.com/z.png", out)
        self.assertEqual(uncached, ["http://none.com/z.png"])

    def test_dreamwidth_hosted_url_normalized_before_lookup(self):
        # The sized DW URL should map to the unsized cache key.
        content = '<img src="https://acct.dreamwidth.org/file/100x100/img.jpg">'
        mapping = {"https://acct.dreamwidth.org/file/img.jpg": "F2.png"}
        out, uncached = resolve_cached_image_references(content, mapping)
        self.assertIn("../images/F2.png", out)
        self.assertEqual(uncached, [])

    def test_dreamwidth_uncached_reports_normalized_url(self):
        content = '<img src="https://acct.dreamwidth.org/file/100x100/img.jpg">'
        out, uncached = resolve_cached_image_references(content, {})
        self.assertEqual(uncached, ["https://acct.dreamwidth.org/file/img.jpg"])

    def test_multiple_images_mixed(self):
        content = ('a <img src="http://foo.com/a.png"> '
                   'b <img src="http://bar.com/b.png">')
        mapping = {"http://foo.com/a.png": "F1.png"}
        out, uncached = resolve_cached_image_references(content, mapping)
        self.assertIn("../images/F1.png", out)
        self.assertEqual(uncached, ["http://bar.com/b.png"])

    def test_no_images_returns_unchanged(self):
        content = "just some text, no images here"
        out, uncached = resolve_cached_image_references(content, {})
        self.assertEqual(out, content)
        self.assertEqual(uncached, [])


# ---------------------------------------------------------------------------
# create_single_entry_page
# ---------------------------------------------------------------------------

class TestCreateSingleEntryPage(unittest.TestCase):
    def setUp(self):
        self.journal = Journal("myjournal")

    def test_returns_string_with_entry_body(self):
        page = create_single_entry_page(
            self.journal, _entry(event="UNIQUEBODY"), [], {}, {}, {})
        self.assertIsInstance(page, str)
        self.assertIn("UNIQUEBODY", page)

    def test_newlines_converted_to_br(self):
        page = create_single_entry_page(
            self.journal, _entry(event="line1\nline2"), [], {}, {}, {})
        self.assertIn("line1<br />line2", page)

    def test_previous_and_next_navigation_links(self):
        page = create_single_entry_page(
            self.journal, _entry(itemid=5), [], {}, {}, {},
            previous_entry=_entry(itemid=4), next_entry=_entry(itemid=6))
        self.assertIn("entry-4.html", page)
        self.assertIn("entry-6.html", page)
        self.assertIn("Previous Entry", page)
        self.assertIn("Next Entry", page)

    def test_no_navigation_when_no_neighbors(self):
        page = create_single_entry_page(
            self.journal, _entry(itemid=5), [], {}, {}, {})
        self.assertNotIn("Previous Entry", page)
        self.assertNotIn("Next Entry", page)

    def test_comment_body_inserted(self):
        comments = [_comment(id=1, body="COMMENTBODY")]
        page = create_single_entry_page(
            self.journal, _entry(itemid=5), comments, {}, {}, {})
        self.assertIn("COMMENTBODY", page)


# ---------------------------------------------------------------------------
# create_history_page  (pagination math / navigation)
# ---------------------------------------------------------------------------

class TestCreateHistoryPage(unittest.TestCase):
    def setUp(self):
        self.journal = Journal("myjournal")

    def _render(self, page_number, prev_count, next_count, entries=None):
        if entries is None:
            entries = [_entry(itemid=1, event="BODY1")]
        comments = {e["itemid"]: [] for e in entries}
        return create_history_page(
            self.journal, entries, comments, {}, {}, {},
            page_number=page_number,
            previous_page_entry_count=prev_count,
            next_page_entry_count=next_count)

    def test_middle_page_has_both_nav_links(self):
        s = self._render(page_number=2, prev_count=20, next_count=5)
        self.assertIn("page-1.html", s)
        self.assertIn("page-3.html", s)
        self.assertIn("Previous 20", s)
        self.assertIn("Next 5", s)

    def test_first_page_no_previous(self):
        s = self._render(page_number=1, prev_count=0, next_count=20)
        self.assertNotIn("Previous", s)
        self.assertIn("Next 20", s)
        self.assertIn("page-2.html", s)

    def test_last_page_no_next(self):
        s = self._render(page_number=3, prev_count=20, next_count=0)
        self.assertIn("Previous 20", s)
        self.assertNotIn("Next", s)
        self.assertIn("page-2.html", s)

    def test_entry_bodies_interleaved(self):
        entries = [_entry(itemid=1, event="ALPHA"),
                   _entry(itemid=2, event="BETA")]
        s = self._render(page_number=1, prev_count=0, next_count=0,
                         entries=entries)
        self.assertIn("ALPHA", s)
        self.assertIn("BETA", s)


# ---------------------------------------------------------------------------
# create_table_of_contents_page
# ---------------------------------------------------------------------------

class TestCreateTableOfContentsPage(unittest.TestCase):
    def setUp(self):
        self.journal = Journal("myjournal")
        self.d = datetime(2024, 3, 15, 14, 30, 0)

    def _render(self, entry_count=1):
        entries_toc = [[{"date": self.d, "subject": "First",
                         "filename": "entries/entry-1.html"}]]
        hist_toc = [{"from": self.d, "to": self.d,
                     "filename": "history/page-1.html"}]
        tags = ["music"]
        by_tag = {"music": [{"date": self.d, "subject": "First",
                             "filename": "entries/entry-1.html"}]}
        return create_table_of_contents_page(
            self.journal, entry_count, entries_toc, hist_toc, tags, by_tag)

    def test_entry_count_banner(self):
        s = self._render(entry_count=7)
        self.assertIn("Number of entries: 7", s)

    def test_section_headings_present(self):
        s = self._render()
        self.assertIn("Entries As History Pages", s)
        self.assertIn("Entries By Tag", s)
        self.assertIn("All Entries By Month", s)
        self.assertIn("Uncached Image Report", s)

    def test_history_link_present(self):
        s = self._render()
        self.assertIn("history/page-1.html", s)

    def test_tag_section_present(self):
        s = self._render()
        self.assertIn('id="music"', s)

    def test_month_banner_formatted(self):
        s = self._render()
        self.assertIn("2024 March", s)

    def test_entry_link_present(self):
        s = self._render()
        self.assertIn("entries/entry-1.html", s)


# ---------------------------------------------------------------------------
# create_uncached_images_report_page
# ---------------------------------------------------------------------------

class TestCreateUncachedImagesReportPage(unittest.TestCase):
    def setUp(self):
        self.journal = Journal("myjournal")
        self.d = datetime(2024, 3, 15, 14, 30, 0)

    def test_empty_report(self):
        s = create_uncached_images_report_page(self.journal, [])
        self.assertIn("Number of entries with uncached (possibly broken) images: 0", s)

    def test_title_is_interpolated(self):
        # Regression guard: the page title was a plain string missing the f
        # prefix, so it rendered the literal "{journal.name}".
        s = create_uncached_images_report_page(self.journal, [])
        self.assertIn("myjournal uncached images", s)
        self.assertNotIn("{journal.name}", s)

    def test_report_with_entries_and_url_count(self):
        uc = [({"date": self.d, "subject": "Entry",
                "filename": "entries/entry-1.html"},
               ["http://a", "http://b", "http://c"])]
        s = create_uncached_images_report_page(self.journal, uc)
        self.assertIn("Number of entries with uncached (possibly broken) images: 1", s)
        self.assertIn("(3)", s)  # number of uncached urls for the entry
        self.assertIn("entries/entry-1.html", s)


# ---------------------------------------------------------------------------
# download_entry_image  (network mocked)
# ---------------------------------------------------------------------------

class TestDownloadEntryImage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.prev_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        self.journal = Journal("J")
        os.makedirs(self.journal.workdir, exist_ok=True)

    def tearDown(self):
        os.chdir(self.prev_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_response(self, maintype="image", content_type="image/png"):
        resp = MagicMock()
        resp.headers.get_content_maintype.return_value = maintype
        resp.info.return_value = {"Content-Type": content_type}
        # shutil.copyfileobj reads in chunks; return data then EOF
        resp.read.side_effect = [b"imagedata", b""]
        # download_entry_image uses urlopen(...) as a context manager
        resp.__enter__.return_value = resp
        resp.__exit__.return_value = False
        return resp

    def test_successful_download_writes_file(self):
        resp = self._make_response()
        with patch("ljdumptohtml.urllib.request.urlopen", return_value=resp):
            code, filename = download_entry_image(
                "http://x.com/pic.png", self.journal, "2024-03", 7,
                "http://x.com/entry", "uq")
        self.assertEqual(code, 0)
        self.assertIsNotNone(filename)
        self.assertTrue(filename.endswith(".png"))
        self.assertTrue(os.path.exists(os.path.join(self.journal.workdir, "images", filename)))

    def test_non_image_content_skipped(self):
        resp = self._make_response(maintype="text", content_type="text/html")
        with patch("ljdumptohtml.urllib.request.urlopen", return_value=resp), \
                patch("builtins.print"):
            code, filename = download_entry_image(
                "http://x.com/notimage", self.journal, "2024-03", 1, None, None)
        self.assertEqual(code, 1)
        self.assertIsNone(filename)

    def test_http_error_returns_code(self):
        err = urllib.error.HTTPError(
            "http://x.com/pic.png", 404, "Not Found", {}, None)
        with patch("ljdumptohtml.urllib.request.urlopen", side_effect=err), \
                patch("builtins.print"):
            code, filename = download_entry_image(
                "http://x.com/pic.png", self.journal, "2024-03", 1, None, None)
        self.assertEqual(code, 404)
        self.assertIsNone(filename)

    def test_url_error_returns_two(self):
        err = urllib.error.URLError("boom")
        with patch("ljdumptohtml.urllib.request.urlopen", side_effect=err), \
                patch("builtins.print"):
            code, filename = download_entry_image(
                "http://x.com/pic.png", self.journal, "2024-03", 1, None, None)
        self.assertEqual(code, 2)
        self.assertIsNone(filename)

    def test_generic_exception_returns_one(self):
        with patch("ljdumptohtml.urllib.request.urlopen",
                   side_effect=RuntimeError("unexpected")), \
                patch("builtins.print"):
            code, filename = download_entry_image(
                "http://x.com/pic.png", self.journal, "2024-03", 1, None, None)
        self.assertEqual(code, 1)
        self.assertIsNone(filename)


# ---------------------------------------------------------------------------
# ljdumptohtml  (end-to-end orchestrator, real temp DB, no network)
# ---------------------------------------------------------------------------

def _make_event(itemid=1, subject="Hello", event="Body text",
                eventtime="2024-03-15 10:00:00", logtime="2024-03-15 10:01:00",
                taglist="music, life", url="https://example.com/1"):
    """Minimal valid event dict, matching what the server/LJDB expects."""
    return {
        "itemid": itemid, "anum": itemid * 256,
        "eventtime": eventtime, "logtime": logtime,
        "subject": subject, "event": event, "url": url,
        "props": {"taglist": taglist, "current_music": "Song",
                  "commentalter": None, "current_moodid": None,
                  "import_source": None, "interface": "web",
                  "opt_backdated": None, "picture_keyword": None,
                  "picture_mapid": None},
    }


def _make_comment(id=1, entryid=1, date="2024-03-15T11:00:00Z", user="reader",
                  subject="Re: Hello", body="Nice post", parentid="0",
                  posterid="42", state="S"):
    return {"id": id, "entryid": entryid, "date": date, "parentid": parentid,
            "posterid": posterid, "user": user, "subject": subject,
            "body": body, "state": state}


class TestOrchestratorHelpers(unittest.TestCase):
    """Unit tests for the pure helpers extracted from ljdumptohtml()."""

    def test_group_comments_by_entry(self):
        entries = [{"itemid": 1}, {"itemid": 2}]
        comments = [{"entryid": 1, "body": "a"}, {"entryid": 1, "body": "b"},
                    {"entryid": 2, "body": "c"}]
        grouped = _group_comments_by_entry(entries, comments)
        self.assertEqual([c["body"] for c in grouped[1]], ["a", "b"])
        self.assertEqual([c["body"] for c in grouped[2]], ["c"])

    def test_group_comments_entry_with_no_comments_gets_empty_list(self):
        grouped = _group_comments_by_entry([{"itemid": 5}], [])
        self.assertEqual(grouped[5], [])

    def test_group_comments_orphan_comment_creates_group(self):
        # A comment whose entry isn't in the entries list still gets a bucket.
        grouped = _group_comments_by_entry([], [{"entryid": 9, "body": "x"}])
        self.assertEqual(len(grouped[9]), 1)

    def test_index_by(self):
        rows = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        self.assertEqual(_index_by(rows, "id"), {1: rows[0], 2: rows[1]})

    def test_index_by_empty(self):
        self.assertEqual(_index_by([], "id"), {})

    def test_group_entries_by_tag(self):
        entries = [
            {"itemid": 1, "eventtime_unix": FIXED_TS, "subject": "One",
             "props_taglist": "music, life"},
            {"itemid": 2, "eventtime_unix": FIXED_TS, "subject": "Two",
             "props_taglist": "life"},
        ]
        tags, by_tag = _group_entries_by_tag(entries)
        self.assertEqual(tags, ["life", "music"])  # sorted
        self.assertEqual(len(by_tag["life"]), 2)
        self.assertEqual(len(by_tag["music"]), 1)
        self.assertEqual(by_tag["music"][0]["subject"], "One")

    def test_group_entries_by_tag_skips_untagged(self):
        entries = [{"itemid": 1, "eventtime_unix": FIXED_TS, "subject": "X",
                    "props_taglist": None}]
        tags, by_tag = _group_entries_by_tag(entries)
        self.assertEqual(tags, [])
        self.assertEqual(by_tag, {})


class TestLjdumptohtmlOrchestrator(unittest.TestCase):
    """Drive the whole ljdumptohtml() pipeline against a real temp LJDB.

    Regression guard for two bugs this path had: (1) it wrote entry/history
    pages under journal.workdir while creating the directories under
    journal.name, so from a repo-root cwd the writes landed in a directory that
    was never created; (2) the standalone entry point passed a db *path string*
    where a db *object* was required.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.prev_cwd = os.getcwd()
        os.chdir(self.tmpdir)
        # Support files the orchestrator copies into the journal folder at the end.
        with open("stylesheet.css", "w") as f:
            f.write("/* css */")
        with open("user.png", "wb") as f:
            f.write(b"\x89PNG")
        self.journal = Journal("myjournal")
        os.makedirs(self.journal.workdir, exist_ok=True)
        self.db = LJDB(f"{self.journal.workdir}/journal.db", verbose=False,
                       create=True)
        self.config = type("Cfg", (), {"unique": None, "verbose": False})()

    def tearDown(self):
        os.chdir(self.prev_cwd)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self):
        with patch("builtins.print"):
            ljdumptohtml(self.config, self.db, "myjournal", cache_images=False)

    def test_generates_expected_files_and_content(self):
        self.db.insert_or_update_event(
            _make_event(itemid=1, subject="First Post", event="Hello world"))
        self.db.insert_or_update_event(
            _make_event(itemid=2, subject="Second Post", event="More text",
                        eventtime="2024-04-20 09:00:00",
                        logtime="2024-04-20 09:01:00", taglist="life"))
        self.db.insert_or_update_comment(
            _make_comment(id=1, entryid=1, body="Great first post"))

        self._run()

        wd = self.journal.workdir
        # Core pages land under journal.workdir (the write/makedirs bug).
        for rel in ("index.html", "uncached_images_report.html",
                    "entries/entry-1.html", "entries/entry-2.html",
                    "history/page-1.html", "stylesheet.css", "user.png"):
            self.assertTrue(os.path.exists(os.path.join(wd, rel)),
                            f"expected {rel} under {wd}")

        with open(os.path.join(wd, "entries", "entry-1.html")) as f:
            entry1 = f.read()
        self.assertIn("First Post", entry1)
        self.assertIn("Hello world", entry1)
        self.assertIn("Great first post", entry1)  # comment rendered

        with open(os.path.join(wd, "index.html")) as f:
            toc = f.read()
        self.assertIn("First Post", toc)
        self.assertIn("Second Post", toc)
        # Tags from both entries appear in the by-tag section of the TOC.
        self.assertIn("music", toc)
        self.assertIn("life", toc)

    def test_empty_journal_still_writes_toc(self):
        # No entries at all: the pipeline should still produce a TOC/index.
        self._run()
        wd = self.journal.workdir
        self.assertTrue(os.path.exists(os.path.join(wd, "index.html")))
        with open(os.path.join(wd, "index.html")) as f:
            self.assertIn("myjournal archive", f.read())


if __name__ == "__main__":
    unittest.main()
