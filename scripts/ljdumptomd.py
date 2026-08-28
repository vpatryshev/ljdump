#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# ljdumptomd.py - convert sqlite livejournal archive to markdown files
# Garrett Birkel et al
# Version 1.0
#
# LICENSE
#
# This software is provided 'as-is', without any express or implied
# warranty.  In no event will the author be held liable for any damages
# arising from the use of this software.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely, subject to the following restrictions:
#
# 1. The origin of this software must not be misrepresented; you must not
#    claim that you wrote the original software. If you use this software
#    in a product, an acknowledgment in the product documentation would be
#    appreciated but is not required.
# 2. Altered source versions must be plainly marked as such, and must not be
#    misrepresented as being the original software.
# 3. This notice may not be removed or altered from any source distribution.
#
# Copyright (c) 2024 Garrett Birkel and contributors


import os, codecs, argparse, xml.dom.minidom, sys
from datetime import datetime
import urllib.request
import urllib.parse
import hashlib
import subprocess
import re
from utils import *

# Add this script's directory to path so sibling modules resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ljdb import *


def write_markdown(filename, markdown_content):
    """Write markdown content to a file."""
    with codecs.open(filename, "w", "UTF-8") as f:
        f.write(markdown_content)

def clip(what, where, tag):
    if what in where:
        i = where.find(what)
        print(f"------------------------{tag} @{i} of {len(where)}")
        j=min(i+480, len(where))
        print(where)
        print(f"======================={tag}")

def html_to_markdown(html_content, output_dir=None):
    """Convert HTML content to Markdown (basic conversion)."""
    # Remove HTML line breaks
    md = re.sub(r'<br([^>]*)/?>', '\n', html_content, flags=re.IGNORECASE)

    # Convert bold tags
    md = re.sub(r'<b>(.*?)</b>', r'**\1**', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<strong>(.*?)</strong>', r'**\1**', md, flags=re.IGNORECASE|re.DOTALL)

    # Convert italic tags
    md = re.sub(r'<i>(.*?)</i>', r'*\1*', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<em>(.*?)</em>', r'*\1*', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<em>(.*?)</em>', r'*\1*', md, flags=re.IGNORECASE|re.DOTALL)

    #convert garbage
    badspan=r'<span style="color: rgb\(62, 62, 62\); font-family:\s*&quot;Trebuchet MS&quot;,\s*Arial,\s*sans-serif;\s*font-size:\s*20px;[^>]*>(.*?)</span>'
    md = re.sub(badspan, r'\1', md, flags=re.IGNORECASE|re.DOTALL)
    baddiv1=r'<div class="entry-content" [^>]*>(.*?)</div>'
    md = re.sub(baddiv1, r'\1', md, flags=re.IGNORECASE|re.DOTALL)
    baddiv2=r'<div class="inner" [^>]*>(.*?)</div>'
    md = re.sub(baddiv2, r'\1', md, flags=re.IGNORECASE|re.DOTALL)
    baddiv3=r'<div class="contents" [^>]*>(.*?)</div>'
    md = re.sub(baddiv3, r'\1', md, flags=re.IGNORECASE|re.DOTALL)
    baddiv=r'<div[^>]*>(.*?)</div>'
    md = re.sub(baddiv, r'\1', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<div class=[^>]*>&nbsp;</div>', ' ', md, flags=re.IGNORECASE|re.DOTALL)

    md = handle_images(md, output_dir)

    # Convert headers (h1-h6)
    for level in range(1, 7):
        md = re.sub(rf'<h{level}[^>]*>(.*?)</h{level}>', lambda m: '#' * level + ' ' + m.group(1) + '\n', md, flags=re.IGNORECASE|re.DOTALL)

    # Convert unordered lists
    md = re.sub(r'<ul[^>]*>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</ul>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1', md, flags=re.IGNORECASE|re.DOTALL)

    # Convert ordered lists (basic)
    md = re.sub(r'<ol[^>]*>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</ol>', '', md, flags=re.IGNORECASE)

    # Convert blockquotes
    md = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', lambda m: '\n'.join('> ' + line for line in m.group(1).strip().split('\n')), md, flags=re.IGNORECASE|re.DOTALL)

    # Convert <pre>
    md = re.sub(r'<code><pre>(.*?)</pre></code>', r'\n```\1\n```\n', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<pre><code>(.*?)</code></pre>', r'\n```\1\n```\n', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<pre>(.*?)</pre>', r'\n```\1\n```\n', md, flags=re.IGNORECASE|re.DOTALL)

    # Convert <code>
    md = re.sub(r'<code>(.*?)</code>', r'`\1`', md, flags=re.IGNORECASE|re.DOTALL)

    # convert strong
    md = re.sub(r'<strong>(.*?)</strong>', r'**\1**', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', md, flags=re.IGNORECASE)

    # convert sub and sup
    md = re.sub(r'<sub[^>]*>(.*?)</sub>', r'~\1~', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<sup[^>]*>(.*?)</sup>', r'^\1^', md, flags=re.IGNORECASE|re.DOTALL)

    # Convert paragraphs
    md = re.sub(r'<p[^>]*>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</p>', '\n\n', md, flags=re.IGNORECASE)

    # remove spans and brs and bad bs
    md = re.sub(r'<span[^>]*>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</span>', 'Ï', md, flags=re.IGNORECASE)
    md = re.sub(r'<br[^>]*/>', '\n\n', md, flags=re.IGNORECASE)

#     # Remove remaining HTML tags
#     md = re.sub(r'<[^>]+>', '', md)

    # Clean up multiple newlines
    md = re.sub(r'\n{3,}', '\n\n', md)

    return md.strip()

def handle_images(html_content, output_dir=None):
    """Download images and change references in the content"""
    if not output_dir:
        return html_content
    # Pattern to match <img> tags and extract src
    img_pattern = r'<img\s+([^>]*?)src=["\']([^"\']+)["\']([^>]*?)/?>'

    def download_and_replace(match):
        before_src = match.group(1)
        img_url = match.group(2)
        after_src = match.group(3)

        # Skip if it's already a local file (doesn't start with http)
        if not img_url.startswith('http'):
            return match.group(0)

        try:
            # Create a unique filename based on URL hash
            url_hash = hashlib.md5(img_url.encode()).hexdigest()[:12]

            # Try to get extension from URL
            parsed_url = urllib.parse.urlparse(img_url)
            path = parsed_url.path
            ext = os.path.splitext(path)[1]
            if not ext or len(ext) > 5:
                ext = '.jpg'  # default

            local_filename = f"img_{url_hash}{ext}"
            local_path = os.path.join(output_dir, local_filename)
            # Download image if it doesn't exist
            # TODO: this one does not work https://pbs.twimg.com/media/E3mngOKWUAAQOhi?format=png&amp;name=small
            if not os.path.exists(local_path):
                print(f"Downloading image: {img_url} to {local_path}")
                headers = {'User-Agent': 'Mozilla/5.0 (compatible; ljdumptomd/1.0)'}
                req = urllib.request.Request(img_url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    img_data = response.read()
                    with open(local_path, 'wb') as f:
                        f.write(img_data)
                print(f"  Saved as: {local_filename} in {local_path}")
                if not os.path.exists(local_path):
                  fail(f"Failed to create {local_path}")

            # Check if the file is actually WebP (regardless of extension)
            # This works for both newly downloaded and existing files
            png_filename = f"img_{url_hash}.png"
            png_path = os.path.join(output_dir, png_filename)

            # If PNG version exists, use it
            if os.path.exists(png_path):
                local_filename = png_filename
            elif os.path.exists(local_path):
                # Check if it's WebP and needs conversion
                try:
                    file_check = subprocess.run(['file', '-b', local_path],
                                              capture_output=True, text=True, timeout=5)
                    file_type = file_check.stdout.strip()

                    if 'Web/P' in file_type or ('RIFF' in file_type and 'Web' in file_type):
                        # It's a WebP file, convert to PNG
                        print(f"  Converting WebP to PNG: {local_filename} -> {png_filename}")
                        subprocess.run(['sips', '-s', 'format', 'png', local_path,
                                      '--out', png_path],
                                     capture_output=True, timeout=30)
                        # Use PNG file instead
                        local_filename = png_filename

                except Exception as e:
                    print(f"  Warning: Could not check/convert file format: {e}")

            # Return updated img tag with local reference
            return f'<img {before_src}src="{local_filename}"{after_src}>'

        except Exception as e:
            print(f"Warning: Failed to download {img_url}: {e}")
            # Return original tag if download fails
            return match.group(0)

    # Replace all img tags
    result = re.sub(img_pattern, download_and_replace, html_content, flags=re.IGNORECASE)
    return result

def create_entry_markdown(entry, output_dir=None):
    """Create markdown content for a single entry."""
    lines = []

    # Title
    lines.append(f"# {entry['subject']}")
    lines.append("")

    # Metadata
    d = datetime.utcfromtimestamp(entry['eventtime_unix'])
    dh = int(f'{d:%I}')
    date_str = f"{d:%b}. {d.day}, {d:%Y} {dh}:{d:%M} {d:%p}"
    lines.append(f"**Date:** {date_str}")

    if entry['url']:
        lines.append(f"**Original:** {entry['url']}")

    # Tags
    if entry['props_taglist']:
        tags = entry['props_taglist'].split(', ')
        lines.append(f"**Tags:** {', '.join(tags)}")


#     lines.append("")
#     lines.append("---")
    lines.append("")

    # Entry content
    entry_content = html_to_markdown(entry['event'], output_dir)
    lines.append(entry_content)
    return '\n'.join(lines)


def parse_date_range(date_range_str):
    """Parse a date range string (e.g., '2020-01-01:2020-12-31')."""
    if not date_range_str:
        return None, None

    parts = date_range_str.split(':')
    if len(parts) != 2:
        raise ValueError("Date range must be in format YYYY-MM-DD:YYYY-MM-DD")

    start_date = datetime.strptime(parts[0].strip(), '%Y-%m-%d')
    end_date = datetime.strptime(parts[1].strip(), '%Y-%m-%d')

    if start_date > end_date:
        raise ValueError("Start date must be before end date")

    return start_date, end_date


def filter_entries(entries, tags=None, start_date=None, end_date=None):
    """Filter entries by tags and/or date range."""
    filtered = []

    print(f"Filtering totally {len(entries)} entries looking for {tags}.")

    for entry in entries:
        # Check date range#
        entry_date = datetime.utcfromtimestamp(entry['eventtime_unix'])
        if start_date and entry_date < start_date:
            continue
        if end_date and entry_date > end_date:
            continue

        entry_tags = []
        if entry['props_taglist']:
            entry_tags = [t.strip() for t in entry['props_taglist'].split(',')]

#        print(f"{start_date} < {entry_date} < {end_date} with {entry_tags}")

        # Check tags
        if tags:
            # print(f"tags {entry_tags} has {tags} ?")
            # Check if any of the requested tags match
            has_matching_tag = False
            for tag in tags:
                if tag in entry_tags:
                    has_matching_tag = True
#                    print(f"{entry['itemid']}@{entry_date} is good")

                    break

            if not has_matching_tag:
                continue

        filtered.append(entry)
    return filtered


def ljdumptomd(journal_short_name, tags=None, date_range=None, verbose=True):
    """Convert LiveJournal/Dreamwidth entries from database to Markdown files."""
    if verbose:
        print(f"Starting conversion for: {journal_short_name} for tags ${tags}")

    os.chdir("work")

    # Parse date range if provided
    start_date, end_date = parse_date_range(date_range)

    # Parse tags if provided (comma-separated)
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(',')]

    # Connect to database
    db = LJDB(f"{journal_short_name}/journal.db", verbose)

    # Fetch all entries
    all_entries = db.get_all_events()

    # Sort entries by date
    entries_by_date = sorted(all_entries, key=lambda x: x['eventtime_unix'], reverse=False)

    # Filter entries
    filtered_entries = filter_entries(entries_by_date, tag_list, start_date, end_date)

    if verbose:
        print(f"Out of {len(all_entries)} entries in total")
        if start_date or end_date:
            print(f"Date range: {start_date} to {end_date}")
        if tag_list:
            print(f"Filtered by tags: {', '.join(tag_list)}")

        print(f"After filtering: {len(filtered_entries)} entries")

    print(f"Found {len(filtered_entries)} entries with {tag_list}.")


    # Create output directory
    output_dir = f"{journal_short_name}/markdown"

    db.close(None)

    try:
        os.mkdir(output_dir)
#        print(f"Created {os. getcwd()}/{output_dir}")
    except OSError as e:
        if e.errno == 17:  # Directory already exists
            pass
    # need to removed old md files, keeping the rest of the content
    os.system(f"rm -rf {os. getcwd()}/{output_dir}/*.md")

    # Generate markdown files
    if verbose:
        print(f"Generating {len(filtered_entries)} markdown files...")

    for entry in filtered_entries:
        entry_date = datetime.utcfromtimestamp(entry['eventtime_unix'])

        # Create filename with date and itemid
        filename = f"{entry_date.strftime('%Y-%m-%d')}_{entry['itemid']}.md"
        print(f"entry at {entry_date} -> {filename}", end="\r")
        filepath = os.path.join(output_dir, filename)

        # Generate markdown content
        markdown_content = create_entry_markdown(
            entry=entry,
            output_dir=output_dir
        )

        # Write to file
        write_markdown(filepath, markdown_content)

        # Set file timestamp to match entry date
        entry_timestamp = entry['eventtime_unix']
        os.utime(filepath, (entry_timestamp, entry_timestamp))

    if verbose:
        print(f"Done! Markdown files written to {output_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LiveJournal archive to Markdown utility")
    parser.add_argument("--quiet", "-q", action='store_false', dest='verbose',
                        help="reduce log output")
    parser.add_argument("--tags", "-t", type=str, dest='tags',
                        help='comma-separated list of tags to filter by (e.g., "travel, photos")')
    parser.add_argument("--dates", "-d", type=str, dest='date_range',
                        help='date range to select in format YYYY-MM-DD:YYYY-MM-DD (e.g., "2020-01-01:2020-12-31")')
    parser.add_argument("journal", type=str, nargs='?',
                        help='journal name (directory containing journal.db)')

    args = parser.parse_args()

    # Determine journal name
    journal_name = None
    if args.journal:
        journal_name = args.journal
    elif os.access("ljdump.config", os.F_OK):
        config = xml.dom.minidom.parse("ljdump.config")
        username = config.documentElement.getElementsByTagName("username")[0].childNodes[0].data
        journals = [e.childNodes[0].data for e in config.documentElement.getElementsByTagName("journal")]
        if not journals:
            journal_name = username
        else:
            journal_name = journals[0]
    else:
        print("Error: No journal specified and no ljdump.config found")
        print("Usage: ljdumptomd.py [--tags TAGS] [--dates DATERANGE] [journal_name]")
        os._exit(os.EX_USAGE)

    print(f"Extracting tags: {args.tags}, dates: {args.date_range}, journal_name: {journal_name}")

    ljdumptomd(
        journal_short_name=journal_name,
        tags=args.tags,
        date_range=args.date_range,
        verbose=args.verbose
    )
