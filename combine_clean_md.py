#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Combine individual markdown files and clean them up.
Removes tags, original links, titles, and pagebreaks.
Converts date lines into headers.
"""

import os
import re
import sys
import glob
from ljdumpops import *

def clean_markdown_content(content):
    """Clean up markdown content according to specified rules."""
    lines = content.split('\n')
    result = []
    skip_next = False

    for i, line in enumerate(lines):
        # Skip if we marked this line to be skipped
        if skip_next:
            skip_next = False
            continue

        # Remove \pagebreak lines
        if line.strip() == r'\pagebreak':
            continue

        # Remove title lines (e.g., "# dybr")
        if re.match(r'^#\s+\w+\s*$', line):
            continue

        # Convert "**Date:** <date>" to "## <date>"
        date_match = re.match(r'^\*\*Date:\*\*\s+(.... \d+, \d\d\d\d).*$', line)
        if date_match:
            date=date_match.group(1)
            result.append(f"## {date}")
            continue

        # Remove "**Original:** <url>" lines
        if re.match(r'^\*\*Original:\*\*\s+https?://', line):
            continue

        # Remove "**Tags:** <tags>" lines
        if re.match(r'^\*\*Tags:\*\*\s+', line):
            continue

        # Remove "**Next:** [link]" lines
        if re.match(r'^\*\*Next:\*\*\s+\[', line):
            continue

        # Remove "**Previous:** [link]" lines
        if re.match(r'^\*\*Previous:\*\*\s+\[', line):
            continue

        result.append(line)

    entry = '\n'.join(result)
    return entry

def combine_markdown_files(config, input_pattern, output_file):
    """Combine multiple markdown files into one, cleaning as we go."""
    # Get all matching files and sort them
    files = sorted(glob.glob(input_pattern))

    if not files:
        fail(f"No files found matching pattern: {input_pattern}")

    print(f"Found {len(files)} files to combine")

    # Read and combine all files
    combined_content = []

    # Add front matter
    title = config.get("title", "No Name")
    author = config.get("author", "(anonymous)")
    combined_content.append(f"% {title}\n")
    combined_content.append(f"% {author}\n")
    combined_content.append("% \n\n")

    for filename in files:
        print(f"Processing: {filename}")
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            cleaned = clean_markdown_content(content)
            combined_content.append(cleaned)
            combined_content.append("")  # Add spacing between entries

    # Write the combined file
    final_content = '\n'.join(combined_content)

    # Clean up multiple consecutive blank lines
    final_content = re.sub(r'\n{3,}', '\n\n', final_content)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(final_content)

    print(f"Combined file written to: {output_file}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        fail("Usage: combine_clean_md.py id <input_pattern> <output_file>\n" +
             "Example: combine_clean_md.py 'JuanEnrique_markdown/*.md' JuanEnrique_combined.md")
    id=sys.argv[1]
    input_pattern = sys.argv[2]
    output_file = sys.argv[3]
    config = load_config(f"{id}.json"   )
    combine_markdown_files(config, input_pattern, output_file)
