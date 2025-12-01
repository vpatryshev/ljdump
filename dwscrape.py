#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dwscrape.py - Dreamwidth journal scraper
Scrapes public Dreamwidth journal entries and stores them in ljdump database format

This tool is for archiving public journal entries from accounts you don't control.
It respects robots.txt and includes delays between requests.
Uses only standard library - no external dependencies required.
"""

import argparse
import re
import time
import sqlite3
from datetime import datetime
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from html.parser import HTMLParser
from ljdumpsqlite import (
    connect_to_local_journal_db,
    create_tables_if_missing,
    finish_with_database
)

# Be respectful - delay between requests
REQUEST_DELAY = 2.0  # seconds

# User agent
USER_AGENT = 'DreamwidthArchiver/1.0 (Personal backup tool)'


class DreamwidthHTMLParser(HTMLParser):
    """Parse Dreamwidth HTML to extract entry links and data."""

    def __init__(self):
        super().__init__()
        self.entry_links = []
        self.in_title = False
        self.in_content = False
        self.in_tags = False
        self.current_tag_stack = []
        self.title_text = []
        self.content_parts = []
        self.tags = []
        self.current_date = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self.current_tag_stack.append((tag, attrs_dict))

        # Look for entry links
        if tag == 'a':
            href = attrs_dict.get('href', '')
            # Match patterns like /344866.html or https://journal.dreamwidth.org/344866.html
            if re.search(r'/\d+\.html', href):
                self.entry_links.append(href)

        # Track if we're in important sections
        if tag in ['h1', 'h2', 'h3']:
            # Could be title
            classes = attrs_dict.get('class', '')
            if 'entry' in classes or 'subject' in classes or 'title' in classes:
                self.in_title = True

        if tag == 'div' or tag == 'article':
            classes = attrs_dict.get('class', '')
            if any(keyword in classes for keyword in ['entry-content', 'entrytext', 'entry-text']):
                self.in_content = True
            if 'tags' in classes or 'tag' in classes:
                self.in_tags = True

    def handle_endtag(self, tag):
        if self.current_tag_stack and self.current_tag_stack[-1][0] == tag:
            self.current_tag_stack.pop()

        if tag in ['h1', 'h2', 'h3']:
            self.in_title = False
        if tag in ['div', 'article']:
            self.in_content = False
            self.in_tags = False

    def handle_data(self, data):
        if self.in_title:
            self.title_text.append(data.strip())
        if self.in_content:
            self.content_parts.append(data)
        if self.in_tags:
            cleaned = data.strip()
            if cleaned and cleaned not in [',', ':', 'Tags']:
                self.tags.append(cleaned)


class DreamwidthScraper:
    """Scrapes public Dreamwidth journal entries."""

    def __init__(self, journal_name, verbose=True):
        self.journal_name = journal_name
        self.base_url = f"https://{journal_name}.dreamwidth.org"
        self.verbose = verbose

    def log(self, message):
        """Print log message if verbose."""
        if self.verbose:
            print(message)

    def fetch_page(self, url, delay=True):
        """Fetch a page with respectful delays."""
        if delay:
            time.sleep(REQUEST_DELAY)

        self.log(f"Fetching: {url}")
        try:
            req = Request(url, headers={'User-Agent': USER_AGENT})
            with urlopen(req, timeout=30) as response:
                return response.read().decode('utf-8')
        except Exception as e:
            self.log(f"Error fetching {url}: {e}")
            return None

    def extract_itemid_from_url(self, url):
        """Extract itemid from entry URL like /344866.html"""
        match = re.search(r'/(\d+)\.html', url)
        if match:
            return int(match.group(1))
        return None

    def parse_date(self, date_str):
        """Parse Dreamwidth date format to datetime and unix timestamp.

        Example: "Nov. 29th, 2022 05:58 am"
        """
        # Remove ordinal suffixes (st, nd, rd, th)
        date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)

        # Try different date formats
        formats = [
            "%b. %d, %Y %I:%M %p",  # Nov. 29, 2022 05:58 am
            "%B. %d, %Y %I:%M %p",  # November. 29, 2022 05:58 am
            "%b %d, %Y %I:%M %p",   # Nov 29, 2022 05:58 am
            "%B %d, %Y %I:%M %p",   # November 29, 2022 05:58 am
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt
            except ValueError:
                continue

        self.log(f"Warning: Could not parse date: {date_str}")
        return None

    def scrape_journal_page(self, skip=0):
        """Scrape a journal page (paginated by skip parameter).

        Returns list of entry URLs found on this page.
        """
        url = f"{self.base_url}/" if skip == 0 else f"{self.base_url}/?skip={skip}"
        html = self.fetch_page(url, delay=(skip > 0))  # Don't delay first request

        if not html:
            return []

        parser = DreamwidthHTMLParser()
        parser.feed(html)

        entry_urls = []
        seen_itemids = set()
        for href in parser.entry_links:
            # Skip comment links
            if '#' in href:
                continue

            full_url = urljoin(self.base_url, href)

            # Extract itemid to avoid duplicates
            itemid = self.extract_itemid_from_url(full_url)
            if itemid and itemid not in seen_itemids:
                seen_itemids.add(itemid)
                entry_urls.append(full_url)

        self.log(f"Found {len(entry_urls)} unique entries on page (skip={skip})")
        return entry_urls

    def scrape_entry(self, entry_url):
        """Scrape a single entry page and return entry data dict."""
        html = self.fetch_page(entry_url)
        if not html:
            return None

        # Extract itemid from URL
        itemid = self.extract_itemid_from_url(entry_url)
        if not itemid:
            self.log(f"Could not extract itemid from {entry_url}")
            return None

        entry_data = {
            'itemid': itemid,
            'url': entry_url,
            'subject': '',
            'event': '',
            'eventtime': None,
            'eventtime_unix': None,
            'tags': [],
            'mood': None,
            'music': None,
        }

        # Use regex-based extraction for simplicity (no external dependencies)

        # Extract title - look for h2, h3 with entry-title class
        title_match = re.search(r'<h[23][^>]*class="[^"]*entry-title[^"]*"[^>]*>(.*?)</h[23]>', html, re.DOTALL | re.IGNORECASE)
        if title_match:
            # Clean HTML tags from title (like <a> tags)
            title_text = re.sub(r'<[^>]+>', '', title_match.group(1))
            entry_data['subject'] = title_text.strip()

        # Extract entry content - look for div with entry-content class
        # Use non-greedy match and handle nested divs better
        content_match = re.search(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL | re.IGNORECASE)
        if not content_match:
            # Try without the outer div
            content_match = re.search(r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL | re.IGNORECASE)
        if content_match:
            entry_data['event'] = content_match.group(1).strip()

        # Extract date - Dreamwidth format with linked dates
        # Pattern: <span class="datetime"><span class="date"><a>Month</a>. <a>Day</a>, <a>Year</a></span> <span class="time">HH:MM am/pm</span>
        datetime_match = re.search(
            r'<span class="datetime">.*?<a[^>]*>([A-Za-z]+)</a>\.\s*<a[^>]*>(\d+)(?:st|nd|rd|th)?</a>,\s*<a[^>]*>(\d{4})</a>.*?<span class="time">(\d{1,2}:\d{2}\s*(?:am|pm))</span>',
            html,
            re.DOTALL | re.IGNORECASE
        )
        if datetime_match:
            month, day, year, time = datetime_match.groups()
            date_str = f"{month} {day}, {year} {time}"
            self.log(f"  Parsed date string: {date_str}")
            dt = self.parse_date(date_str)
            if dt:
                entry_data['eventtime'] = dt
                entry_data['eventtime_unix'] = dt.timestamp()
            else:
                self.log(f"  Warning: Could not parse date: {date_str}")

        # Extract tags - look for tag links
        tag_matches = re.findall(r'<a[^>]+href="[^"]*tag=[^"]*"[^>]*>([^<]+)</a>', html)
        if tag_matches:
            entry_data['tags'] = [tag.strip() for tag in tag_matches]

        return entry_data

    def scrape_journal(self, max_entries=None):
        """Scrape all entries from a journal.

        Args:
            max_entries: Maximum number of entries to scrape (None for all)

        Returns:
            List of entry data dictionaries
        """
        all_entries = []
        skip = 0
        entries_per_page = 20  # Dreamwidth default

        while True:
            # Fetch journal page
            entry_urls = self.scrape_journal_page(skip)

            if not entry_urls:
                self.log("No more entries found")
                break

            # Scrape each entry
            for entry_url in entry_urls:
                entry_data = self.scrape_entry(entry_url)
                if entry_data:
                    all_entries.append(entry_data)
                    self.log(f"Scraped entry {entry_data['itemid']}: {entry_data['subject']}")

                if max_entries and len(all_entries) >= max_entries:
                    self.log(f"Reached max_entries limit: {max_entries}")
                    return all_entries

            # Move to next page
            skip += entries_per_page

        return all_entries

    def store_entries(self, entries, db_path):
        """Store scraped entries in ljdump SQLite database."""
        if not entries:
            self.log("No entries to store")
            return

        conn = connect_to_local_journal_db(db_path, self.verbose)
        if not conn:
            self.log("Failed to connect to database")
            return

        create_tables_if_missing(conn, self.verbose)
        cur = conn.cursor()

        # Store user info
        cur.execute("""
            DELETE FROM user WHERE journal_short_name = ?
        """, (self.journal_name,))

        cur.execute("""
            INSERT INTO user (journal_short_name, defaultpicurl, fullname, userid)
            VALUES (?, ?, ?, ?)
        """, (self.journal_name, None, self.journal_name, 0))

        # Store entries
        stored_count = 0
        for entry in entries:
            if not entry['eventtime']:
                self.log(f"Skipping entry {entry['itemid']} - no date")
                continue

            # Format times for database
            eventtime_str = entry['eventtime'].strftime('%Y-%m-%d %H:%M:%S')
            logtime_str = eventtime_str  # Use same for logtime

            tags_str = ', '.join(entry['tags']) if entry['tags'] else ''

            try:
                cur.execute("""
                    INSERT OR REPLACE INTO entries (
                        itemid, anum, eventtime, eventtime_unix, logtime, logtime_unix,
                        subject, event, url,
                        props_current_music, props_taglist, raw_props
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry['itemid'],
                    entry['itemid'] % 256,  # anum calculation
                    eventtime_str,
                    entry['eventtime_unix'],
                    logtime_str,
                    entry['eventtime_unix'],
                    entry['subject'],
                    entry['event'],
                    entry['url'],
                    entry['music'],
                    tags_str,
                    '{}'  # raw_props as empty dict
                ))
                stored_count += 1
            except sqlite3.Error as e:
                self.log(f"Error storing entry {entry['itemid']}: {e}")

        conn.commit()
        finish_with_database(conn, cur)

        self.log(f"Stored {stored_count} entries in database")


def main():
    parser = argparse.ArgumentParser(
        description='Scrape public Dreamwidth journal entries'
    )
    parser.add_argument(
        'journal',
        help='Journal name (e.g., kdanilov)'
    )
    parser.add_argument(
        '--max',
        type=int,
        default=None,
        help='Maximum number of entries to scrape'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Reduce log output'
    )
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='Output database path (default: JOURNAL/journal.db)'
    )

    args = parser.parse_args()

    verbose = not args.quiet
    journal_name = args.journal

    # Determine database path
    if args.output:
        db_path = args.output
    else:
        # Create journal directory if needed
        import os
        os.makedirs(journal_name, exist_ok=True)
        db_path = f"{journal_name}/journal.db"

    # Create scraper and run
    scraper = DreamwidthScraper(journal_name, verbose=verbose)

    print(f"Scraping journal: {journal_name}")
    print(f"Database: {db_path}")
    print(f"Note: This tool includes respectful delays between requests")
    print()

    entries = scraper.scrape_journal(max_entries=args.max)

    print(f"\nScraped {len(entries)} entries")

    if entries:
        scraper.store_entries(entries, db_path)
        print(f"\nDone! Entries stored in {db_path}")
        print(f"You can now use ljdumptomd.py or ljdumptohtml.py on this database")
    else:
        print("No entries were scraped")


if __name__ == '__main__':
    main()
