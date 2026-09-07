#!/usr/bin/env python3
"""Fix LaTeX special characters in markdown content for PDF generation."""

import os
import glob
import re

# Map of LaTeX special characters to their escaped forms. Applied in a single
# pass (see below) so that characters inserted by one replacement (e.g. the
# braces in \textbackslash{}) are never re-escaped by a later one.
_LATEX_MAP = {
    '\\': r'\textbackslash{}',
    '&': r'\&',
    '%': r'\%',
    '$': r'\$',
    '#': r'\#',
    '_': r'\_',
    '{': r'\{',
    '}': r'\}',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
}
_LATEX_RE = re.compile('|'.join(re.escape(c) for c in _LATEX_MAP))

def escape_latex_in_text(text):
    """
    Escape special LaTeX characters, but be smart about it.
    We need to escape these characters when they appear in regular text,
    but not break markdown formatting.
    """
    # LaTeX special characters that need escaping
    # & % $ # _ { } ~ ^ \

    # We'll protect inline code first, then escape, then restore
    code_blocks = []
    inline_codes = []

    # Temporarily replace code blocks with placeholders
    def save_code_block(match):
        code_blocks.append(match.group(0))
        return f"<<<CODEBLOCK{len(code_blocks)-1}>>>"

    def save_inline_code(match):
        inline_codes.append(match.group(0))
        return f"<<<INLINECODE{len(inline_codes)-1}>>>"

    # Save code blocks (```...```)
    text = re.sub(r'```.*?```', save_code_block, text, flags=re.DOTALL)

    # Save inline code (`...`)
    text = re.sub(r'`[^`]+`', save_inline_code, text)

    # Now escape LaTeX special characters in the remaining text. A single
    # regex pass replaces each original character exactly once, so escape
    # sequences we insert are not themselves re-escaped.
    text = _LATEX_RE.sub(lambda m: _LATEX_MAP[m.group(0)], text)

    # Restore code blocks
    for i, code in enumerate(code_blocks):
        text = text.replace(f"<<<CODEBLOCK{i}>>>", code)

    # Restore inline code
    for i, code in enumerate(inline_codes):
        text = text.replace(f"<<<INLINECODE{i}>>>", code)

    return text

def clean_entry_content(content):
    """Clean up entry content by removing unwanted elements."""
    # Remove navigation links
    content = re.sub(r'\n+---\n+\*\*Previous:.*$', '', content, flags=re.MULTILINE|re.DOTALL)
    content = re.sub(r'\n+---\n+## This is the end.*$', '', content, flags=re.MULTILINE|re.DOTALL)

    # Remove title line (e.g., "# dybr")
    content = re.sub(r'^#\s+\w+\s*\n', '', content, flags=re.MULTILINE)

    # Remove "**Original:**" line
    content = re.sub(r'\*\*Original:\*\*\s+https?://[^\n]+\n', '', content)

    # Remove "**Tags:**" line
    content = re.sub(r'\*\*Tags:\*\*[^\n]+\n', '', content)

    # Change "**Date:**" to just the date value (remove the label)
    content = re.sub(r'\*\*Date:\*\*\s+', '', content)

    return content.rstrip()

def combine_and_fix_markdown(directory="JuanEnrique", output_file="JuanEnrique_fixed.md"):
    """Combine all markdown files and fix LaTeX special characters."""
    pattern = os.path.join(directory, "*.md")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"No markdown files found in {directory}")
        return False

    print(f"Processing {len(files)} markdown files...")

    with open(output_file, 'w', encoding='utf-8') as outfile:
        # Add YAML front matter for pandoc
        outfile.write("---\n")
        outfile.write("title: JuanEnrique - Confessions\n")
        outfile.write("geometry: margin=1in\n")
        outfile.write("fontsize: 11pt\n")
        outfile.write("documentclass: book\n")
        outfile.write("---\n\n")

        for i, filepath in enumerate(files):
            if (i + 1) % 50 == 0:
                print(f"  Processed {i+1}/{len(files)}...")

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Clean entry content (remove tags, titles, links, etc.)
            content = clean_entry_content(content)

            # Escape LaTeX special characters
            content = escape_latex_in_text(content)

            # Add page break before each entry (except first)
            if i > 0:
                outfile.write("\n\n\\newpage\n\n")

            outfile.write(content)
            outfile.write("\n\n")

    print(f"✓ Fixed markdown saved to: {output_file}")
    return True

def main():
    os.chdir('/Users/vladpatryshev/projects/confessions')

    if combine_and_fix_markdown():
        print("\nNow you can generate PDF with:")
        print("  pandoc JuanEnrique_fixed.md -o JuanEnrique.pdf --pdf-engine=xelatex --toc --toc-depth=2")

if __name__ == "__main__":
    main()
