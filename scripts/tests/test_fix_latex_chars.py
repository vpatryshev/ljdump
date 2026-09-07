#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for fix_latex_chars.py.

Covers the importable pure-logic functions:
  - escape_latex_in_text: escaping of LaTeX special characters
    (& % $ # _ { } ~ ^ \\) with protection of fenced code blocks
    (```...```) and inline code (`...`).
  - clean_entry_content: regex-based removal of navigation links,
    title lines, Original/Tags lines, and the Date label.

Escaping is done in a single pass, so characters inserted by one
replacement are not re-escaped. Note the function is not idempotent:
it treats its input as raw (unescaped) text.
"""

import os
import sys
import unittest
from unittest import mock

# Ensure the scripts directory is on the path so `from fix_latex_chars import ...` resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fix_latex_chars import (
    escape_latex_in_text,
    clean_entry_content,
    combine_and_fix_markdown,
)


class TestEscapeLatexInText(unittest.TestCase):
    def test_plain_text_unchanged(self):
        self.assertEqual(escape_latex_in_text("plain text"), "plain text")

    def test_empty_string(self):
        self.assertEqual(escape_latex_in_text(""), "")

    def test_ampersand(self):
        self.assertEqual(escape_latex_in_text("a & b"), r"a \& b")

    def test_percent(self):
        self.assertEqual(escape_latex_in_text("100%"), r"100\%")

    def test_dollar(self):
        self.assertEqual(escape_latex_in_text("$5"), r"\$5")

    def test_hash(self):
        self.assertEqual(escape_latex_in_text("a#b"), r"a\#b")

    def test_underscore(self):
        self.assertEqual(escape_latex_in_text("a_b"), r"a\_b")

    def test_braces(self):
        self.assertEqual(escape_latex_in_text("{x}"), r"\{x\}")

    def test_tilde(self):
        # ~ maps to \textasciitilde{}; the {} it introduces is NOT re-escaped
        # because the tilde replacement runs after the brace replacements.
        self.assertEqual(escape_latex_in_text("~"), r"\textasciitilde{}")

    def test_caret(self):
        # ^ maps to \textasciicircum{}; likewise the introduced {} is not re-escaped.
        self.assertEqual(escape_latex_in_text("^"), r"\textasciicircum{}")

    def test_tilde_in_context(self):
        self.assertEqual(escape_latex_in_text("a~b"), r"a\textasciitilde{}b")

    def test_caret_in_context(self):
        self.assertEqual(escape_latex_in_text("a^b"), r"a\textasciicircum{}b")

    def test_backslash_escapes_cleanly(self):
        # A single pass replaces each original char once, so the braces/backslash
        # inserted by \textbackslash{} are not themselves re-escaped.
        self.assertEqual(
            escape_latex_in_text("a\\b"),
            "a" + r"\textbackslash{}" + "b",
        )

    def test_multiple_specials_together(self):
        self.assertEqual(
            escape_latex_in_text("50% & $10 #tag"),
            r"50\% \& \$10 \#tag",
        )

    def test_inline_code_is_preserved(self):
        # Content inside `...` must not be escaped.
        self.assertEqual(
            escape_latex_in_text("call `a_b & c` now"),
            "call `a_b & c` now",
        )

    def test_inline_code_with_specials_untouched(self):
        self.assertEqual(
            escape_latex_in_text("`100% & $x`"),
            "`100% & $x`",
        )

    def test_fenced_code_block_preserved(self):
        text = "before ```a_b & c%``` after"
        self.assertEqual(escape_latex_in_text(text), "before ```a_b & c%``` after")

    def test_fenced_code_block_multiline_preserved(self):
        text = "intro\n```\nx = a & b_c\n```\noutro"
        self.assertEqual(escape_latex_in_text(text), "intro\n```\nx = a & b_c\n```\noutro")

    def test_text_around_code_still_escaped(self):
        # Specials outside the protected region are escaped; those inside are not.
        text = "50% `raw_&` 60%"
        self.assertEqual(escape_latex_in_text(text), r"50\% `raw_&` 60\%")

    def test_multiple_inline_codes(self):
        text = "`a_1` mid & `b_2`"
        self.assertEqual(escape_latex_in_text(text), r"`a_1` mid \& `b_2`")

    def test_already_escaped_ampersand_is_escaped_once(self):
        # escape_latex_in_text is not idempotent (it treats input as raw text):
        # the literal backslash becomes \textbackslash{} and the & becomes \&,
        # each in a single pass with no re-escaping of inserted characters.
        result = escape_latex_in_text(r"\&")
        self.assertEqual(result, r"\textbackslash{}\&")

    def test_unicode_preserved(self):
        self.assertEqual(escape_latex_in_text("Ро́ссия ☃"), "Ро́ссия ☃")

    def test_placeholder_ordering_multiple_blocks(self):
        # Two fenced blocks with different content restore to correct positions.
        text = "```AAA_``` middle & ```BBB%```"
        self.assertEqual(
            escape_latex_in_text(text),
            r"```AAA_``` middle \& ```BBB%```",
        )


class TestCleanEntryContent(unittest.TestCase):
    def test_removes_title_line(self):
        self.assertEqual(clean_entry_content("# dybr\nbody"), "body")

    def test_removes_original_line(self):
        self.assertEqual(
            clean_entry_content("**Original:** https://x.com/y\nbody"),
            "body",
        )

    def test_removes_original_line_http(self):
        self.assertEqual(
            clean_entry_content("**Original:** http://x.com/y\nbody"),
            "body",
        )

    def test_removes_tags_line(self):
        self.assertEqual(
            clean_entry_content("**Tags:** alpha, beta\nbody"),
            "body",
        )

    def test_strips_date_label_but_keeps_value(self):
        self.assertEqual(
            clean_entry_content("**Date:** Jan 1, 2020\nbody"),
            "Jan 1, 2020\nbody",
        )

    def test_removes_previous_navigation(self):
        self.assertEqual(
            clean_entry_content("body\n\n---\n\n**Previous:** [x](y)"),
            "body",
        )

    def test_removes_end_navigation(self):
        self.assertEqual(
            clean_entry_content("body\n\n---\n\n## This is the end of things"),
            "body",
        )

    def test_rstrips_trailing_whitespace(self):
        self.assertEqual(clean_entry_content("body   \n\n"), "body")

    def test_combined_cleanup(self):
        content = (
            "# dybr\n"
            "**Date:** Jan 1, 2020\n"
            "**Original:** https://x.com/y\n"
            "**Tags:** a, b\n"
            "real content\n"
            "\n---\n\n**Previous:** [p](q)"
        )
        self.assertEqual(
            clean_entry_content(content),
            "Jan 1, 2020\nreal content",
        )

    def test_leaves_ordinary_content_alone(self):
        content = "Just a paragraph with no special markers."
        self.assertEqual(clean_entry_content(content), content)


class TestCombineAndFixMarkdown(unittest.TestCase):
    @mock.patch("builtins.print")
    def test_returns_false_when_no_files(self, _mock_print):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            empty_dir = os.path.join(tmp, "empty")
            os.makedirs(empty_dir)
            out = os.path.join(tmp, "out.md")
            result = combine_and_fix_markdown(directory=empty_dir, output_file=out)
            self.assertFalse(result)
            self.assertFalse(os.path.exists(out))

    @mock.patch("builtins.print")
    def test_combines_and_fixes_files(self, _mock_print):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            with open(os.path.join(src, "001.md"), "w", encoding="utf-8") as f:
                f.write("# dybr\n**Tags:** t\n50% content")
            with open(os.path.join(src, "002.md"), "w", encoding="utf-8") as f:
                f.write("second & entry")

            out = os.path.join(tmp, "out.md")
            result = combine_and_fix_markdown(directory=src, output_file=out)
            self.assertTrue(result)

            with open(out, "r", encoding="utf-8") as f:
                text = f.read()

            # YAML front matter present
            self.assertIn("title: JuanEnrique - Confessions", text)
            self.assertIn("documentclass: book", text)
            # Escaped content from both files
            self.assertIn(r"50\% content", text)
            self.assertIn(r"second \& entry", text)
            # Page break inserted before the second entry (files sorted by name)
            self.assertIn("\\newpage", text)
            # Removed markers do not appear
            self.assertNotIn("# dybr", text)
            self.assertNotIn("**Tags:**", text)


if __name__ == "__main__":
    unittest.main()
