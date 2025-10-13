#!/usr/bin/env python3
"""Add navigation links to markdown files in chronological order."""

import os
import glob
import re

def add_navigation_links(directory="JuanEnrique", repo_base="https://github.com/vpatryshev/confessions/blob/main"):
    # Get all markdown files and sort them by filename (which includes date)
    pattern = os.path.join(directory, "*.md")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"No markdown files found in {directory}")
        return

    print(f"Found {len(files)} markdown files")

    # Process each file
    for i, filepath in enumerate(files):
        # Read the file
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Remove any existing navigation links at the end
        # Look for markdown links or "This is the end" at the bottom
        content = re.sub(r'\n+---\n+\*\*Previous:.*$', '', content, flags=re.MULTILINE|re.DOTALL)
        content = re.sub(r'\n+---\n+\*\*Next:.*$', '', content, flags=re.MULTILINE|re.DOTALL)
        content = re.sub(r'\n+---\n+## This is the end.*$', '', content, flags=re.MULTILINE|re.DOTALL)
        content = content.rstrip()

        # Add navigation links
        navigation = "\n\n---\n\n"

        # Add previous link if not first file
        if i > 0:
            prev_file = os.path.basename(files[i - 1])
            prev_url = f"{repo_base}/{directory}/{prev_file}"
            navigation += f"**Previous:** [{prev_file}]({prev_url})\n\n"

        # Add next link if not last file
        if i < len(files) - 1:
            next_file = os.path.basename(files[i + 1])
            next_url = f"{repo_base}/{directory}/{next_file}"
            navigation += f"**Next:** [{next_file}]({next_url})\n"
        else:
            # Last file - add "This is the end"
            navigation += "## This is the end\n\n**The End** 🎬\n"

        # Write back
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content + navigation)

        if (i + 1) % 50 == 0:
            print(f"Processed {i + 1}/{len(files)} files...")

    print(f"Done! Updated {len(files)} files")
    print(f"First file: {os.path.basename(files[0])}")
    print(f"Last file: {os.path.basename(files[-1])}")

if __name__ == "__main__":
    add_navigation_links()
