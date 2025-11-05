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


import os, codecs, argparse, xml.dom.minidom
from datetime import datetime
import re
from ljdumpsqlite import *


def write_markdown(filename, markdown_content):
    """Write markdown content to a file."""
    with codecs.open(filename, "w", "UTF-8") as f:
        f.write(markdown_content)


def html_to_markdown(html_content):
    """Convert HTML content to Markdown (basic conversion)."""

    # Remove HTML line breaks
    md = re.sub(r'<br\s*/?>', '\n', html_content, flags=re.IGNORECASE)

    # Convert bold tags
    md = re.sub(r'<b>(.*?)</b>', r'**\1**', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<strong>(.*?)</strong>', r'**\1**', md, flags=re.IGNORECASE|re.DOTALL)

    # Convert italic tags
    md = re.sub(r'<i>(.*?)</i>', r'*\1*', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<em>(.*?)</em>', r'*\1*', md, flags=re.IGNORECASE|re.DOTALL)

    # Convert links
    md = re.sub(r'<a\s+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', r'[\2](\1)', md, flags=re.IGNORECASE|re.DOTALL)

    # Convert images
    md = re.sub(r'<img\s+src=["\']([^"\']+)["\'][^>]*/?>', r'![](\1)', md, flags=re.IGNORECASE)

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

#     if (re.search("line = s takeWhile", md)):
#         print("\n\n\nGOT SUSPECT 5")
#         print(md)

    # Convert <pre>
    md = re.sub(r'<code><pre>(.*?)</pre></code>', r'\n```\1\n```\n', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<pre><code>(.*?)</code></pre>', r'\n```\1\n```\n', md, flags=re.IGNORECASE|re.DOTALL)
    md = re.sub(r'<pre>(.*?)</pre>', r'\n```\1\n```\n', md, flags=re.IGNORECASE|re.DOTALL)

    # Convert <code>
    md = re.sub(r'<code>(.*?)</code>', r'`\1`', md, flags=re.IGNORECASE|re.DOTALL)

#     if (re.search("line = s takeWhile", md)):
#         print("\n\n\nGOT CONVERTED")
#         print(md)
#         os._exit(os.EX_IOERR)

#     if (gotapre):
#         print("\n\n\nGOT IT!!!!")
#         print(md)
#         os._exit(os.EX_IOERR)
#
    # Convert paragraphs
    md = re.sub(r'<p[^>]*>', '', md, flags=re.IGNORECASE)
    md = re.sub(r'</p>', '\n\n', md, flags=re.IGNORECASE)

#     # Remove remaining HTML tags
#     md = re.sub(r'<[^>]+>', '', md)

    # Clean up multiple newlines
    md = re.sub(r'\n{3,}', '\n\n', md)

    return md.strip()


def create_entry_markdown(entry, comments, moods_by_id):
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

    # Mood
    if entry['props_current_moodid'] is not None and entry['props_current_moodid'] in moods_by_id:
        lines.append(f"**Mood:** {moods_by_id[entry['props_current_moodid']]['name']}")

    # Music
    if entry['props_current_music']:
        lines.append(f"**Music:** {entry['props_current_music']}")

#     lines.append("")
#     lines.append("---")
    lines.append("")

    # Entry content
    entry_content = html_to_markdown(entry['event'])
    lines.append(entry_content)

    # Comments
    if comments and len(comments) > 0:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"## Comments ({len(comments)})")
        lines.append("")

        # Sort comments by date
        sorted_comments = sorted(comments, key=lambda x: x['date_unix'] if x['date_unix'] else 0)

        for comment in sorted_comments:
            lines.append("---")
            lines.append("")
            if comment['subject']:
                lines.append(f"### {comment['subject']}")
                lines.append("")

            if comment['user']:
                lines.append(f"**From:** {comment['user']}")
            else:
                lines.append("**From:** (Anonymous)")

            if comment['date_unix']:
                c_date = datetime.utcfromtimestamp(comment['date_unix'])
                c_dh = int(f'{c_date:%I}')
                c_date_str = f"{c_date:%b}. {c_date.day}, {c_date:%Y} {c_dh}:{c_date:%M} {c_date:%p}"
                lines.append(f"**Date:** {c_date_str}")

            lines.append("")
            comment_content = html_to_markdown(comment['body'])
            lines.append(comment_content)
            lines.append("")

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

    for entry in entries:
        # Check date range
        if start_date or end_date:
            entry_date = datetime.utcfromtimestamp(entry['eventtime_unix'])
            if start_date and entry_date < start_date:
                continue
            if end_date and entry_date > end_date:
                continue

        # Check tags
        if tags:
            entry_tags = []
            if entry['props_taglist']:
                entry_tags = [t.strip() for t in entry['props_taglist'].split(',')]

            # Check if any of the requested tags match
            has_matching_tag = False
            for tag in tags:
                if tag in entry_tags:
                    has_matching_tag = True
                    break

            if not has_matching_tag:
                continue

        filtered.append(entry)

    return filtered


def ljdumptomd(journal_short_name, tags=None, date_range=None, verbose=True):
    """Convert LiveJournal/Dreamwidth entries from database to Markdown files."""
    if verbose:
        print(f"Starting conversion for: {journal_short_name}")

    # Parse date range if provided
    start_date, end_date = parse_date_range(date_range)

    # Parse tags if provided (comma-separated)
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(',')]

    # Connect to database
    conn = connect_to_local_journal_db(f"{journal_short_name}/journal.db", verbose)
    if not conn:
        fail(f"Database could not be opened for journal {journal_short_name}")
    cur = conn.cursor()

    # Fetch all entries and comments
    all_entries = get_all_events(cur, verbose)
    all_comments = get_all_comments(cur, verbose)

    # Create arrays of comments by entry ID
    comments_grouped_by_entry = {}
    for entry in all_entries:
        e_id = entry['itemid']
        comments_grouped_by_entry[e_id] = []
    for comment in all_comments:
        e_id = comment['entryid']
        if e_id not in comments_grouped_by_entry:
            comments_grouped_by_entry[e_id] = []
        comments_grouped_by_entry[e_id].append(comment)

    # Fetch mood information
    all_moods = get_all_moods(cur, verbose)
    moods_by_id = {}
    for mood in all_moods:
        moods_by_id[mood['id']] = mood

    # Sort entries by date
    entries_by_date = sorted(all_entries, key=lambda x: x['eventtime_unix'], reverse=False)

    # Filter entries
    filtered_entries = filter_entries(entries_by_date, tag_list, start_date, end_date)

#     for entry in filtered_entries:
#       print(entry['id'], entry['eventtime_unix'])
#
#     print("And?")
#     os._exit(os.EX_USAGE)

    if verbose:
        print(f"Found {len(all_entries)} total entries")
        print(f"After filtering: {len(filtered_entries)} entries")
        if tag_list:
            print(f"Filtering by tags: {', '.join(tag_list)}")
        if start_date or end_date:
            print(f"Date range: {start_date} to {end_date}")

    # Create output directory
    output_dir = f"{journal_short_name}_markdown"
    try:
        os.mkdir(output_dir)
    except OSError as e:
        if e.errno == 17:  # Directory already exists
            pass

    # Generate markdown files
    if verbose:
        print(f"Generating {len(filtered_entries)} markdown files...")

    for entry in filtered_entries:
        entry_date = datetime.utcfromtimestamp(entry['eventtime_unix'])

        # Create filename with date and itemid
        filename = f"{entry_date.strftime('%Y-%m-%d')}_{entry['itemid']}.md"
        filepath = os.path.join(output_dir, filename)

        # Generate markdown content
        markdown_content = create_entry_markdown(
            entry=entry,
            comments=comments_grouped_by_entry[entry['itemid']],
            moods_by_id=moods_by_id
        )

        # Write to file
        write_markdown(filepath, markdown_content)

        # Set file timestamp to match entry date
        entry_timestamp = entry['eventtime_unix']
        os.utime(filepath, (entry_timestamp, entry_timestamp))

    finish_with_database(conn, cur)

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

    ljdumptomd(
        journal_short_name=journal_name,
        tags=args.tags,
        date_range=args.date_range,
        verbose=args.verbose
    )
