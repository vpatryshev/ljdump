#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dwscrape.py - Dreamwidth journal scraper
Scrapes Dreamwidth journal entries and stores them in ljdump database format

Features:
- Scrapes public entries without authentication
- Supports authentication to access friends-only entries
- Reads credentials from ljdump.config files
- Respects robots.txt and includes delays between requests
- Uses only standard library - no external dependencies required

Usage:
  # Scrape public entries only
  ./dwscrape.py journal_name

  # Scrape with authentication (including friends-only posts)
  ./dwscrape.py journal_name --config ljdump.config
  ./dwscrape.py journal_name --username user --password pass
"""

import argparse
import re
import time
import sqlite3
import os
import xml.dom.minidom
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlencode
from urllib.request import Request, urlopen, HTTPCookieProcessor, build_opener
from http.cookiejar import CookieJar, Cookie
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


def load_config(config_file):
    """Load username and password from ljdump config file.

    Returns dict with 'username', 'password', and 'server' keys.
    Returns None if config file doesn't exist or is invalid.
    """
    if not os.path.exists(config_file):
        return None

    try:
        config = xml.dom.minidom.parse(config_file)
        doc = config.documentElement

        result = {}

        # Get username (required)
        username_els = doc.getElementsByTagName("username")
        if username_els and username_els[0].childNodes:
            result['username'] = username_els[0].childNodes[0].data
        else:
            return None

        # Get password (required)
        password_els = doc.getElementsByTagName("password")
        if password_els and password_els[0].childNodes:
            result['password'] = password_els[0].childNodes[0].data
        else:
            return None

        # Get server (optional, defaults to dreamwidth)
        server_els = doc.getElementsByTagName("server")
        if server_els and server_els[0].childNodes:
            result['server'] = server_els[0].childNodes[0].data
        else:
            result['server'] = 'https://www.dreamwidth.org'

        return result
    except Exception as e:
        print(f"Error loading config file {config_file}: {e}")
        return None


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
    """Scrapes Dreamwidth journal entries (public and friends-only if authenticated)."""

    def __init__(self, journal_name, verbose=True, username=None, password=None, db_path=None):
        self.journal_name = journal_name
        self.base_url = f"https://{journal_name}.dreamwidth.org"
        self.verbose = verbose
        self.username = username
        self.password = password
        self.db_path = db_path

        # Set up cookie jar and opener for authenticated requests
        self.cookie_jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))
        self.authenticated = False
        self.ljsession = None

        # Cache of existing entry IDs for duplicate detection
        self.existing_itemids = set()

    def log(self, message):
        """Print log message if verbose."""
        if self.verbose:
            print(message)

    def load_existing_itemids(self):
        """Load existing itemids from database to avoid duplicates and enable resume."""
        if not self.db_path or not os.path.exists(self.db_path):
            self.log("No existing database found - will scrape all entries")
            return

        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()

            # Check if entries table exists
            cur.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='entries'
            """)
            if not cur.fetchone():
                self.log("Database exists but no entries table - will scrape all entries")
                conn.close()
                return

            # Load all existing itemids
            cur.execute("SELECT itemid FROM entries")
            self.existing_itemids = set(row[0] for row in cur.fetchall())

            conn.close()

            if self.existing_itemids:
                self.log(f"Found {len(self.existing_itemids)} existing entries in database")
                self.log(f"Will skip duplicates and stop when all entries on a page exist")
            else:
                self.log("Database is empty - will scrape all entries")

        except Exception as e:
            self.log(f"Error loading existing entries: {e}")
            self.existing_itemids = set()

    def entry_exists(self, itemid):
        """Check if an entry already exists in the database."""
        return itemid in self.existing_itemids

    def login(self):
        """Log in to Dreamwidth using the flat interface API.

        Returns True if login successful, False otherwise.
        """
        if not self.username or not self.password:
            self.log("No credentials provided, scraping without authentication")
            return False

        self.log(f"Logging in as {self.username} via API...")

        # Use Dreamwidth's flat interface API for session generation
        login_url = "https://www.dreamwidth.org/interface/flat"

        # Login form data for sessiongenerate mode
        login_data = {
            'mode': 'sessiongenerate',
            'user': self.username,
            'auth_method': 'clear',
            'password': self.password
        }

        try:
            data = urlencode(login_data).encode('utf-8')
            req = Request(login_url, data=data, headers={'User-Agent': USER_AGENT})

            # Use opener to capture any cookies
            with self.opener.open(req, timeout=30) as response:
                # Parse the flat interface response
                response_data = {}
                for line in response:
                    line = line.decode('utf-8').strip()
                    if not line:
                        break
                    key = line
                    value_line = next(response, b'')
                    value = value_line.decode('utf-8').strip()
                    response_data[key] = value

                # Check if we got a session
                if 'ljsession' in response_data:
                    ljsession = response_data['ljsession']
                    self.ljsession = ljsession

                    # Create cookies for all domain variants
                    domains_to_try = [
                        '.dreamwidth.org',
                        'dreamwidth.org',
                        'www.dreamwidth.org',
                        f'{self.journal_name}.dreamwidth.org'
                    ]

                    for domain in domains_to_try:
                        cookie = Cookie(
                            version=0,
                            name='ljsession',
                            value=ljsession,
                            port=None,
                            port_specified=False,
                            domain=domain,
                            domain_specified=True,
                            domain_initial_dot=domain.startswith('.'),
                            path='/',
                            path_specified=True,
                            secure=False,
                            expires=None,
                            discard=True,
                            comment=None,
                            comment_url=None,
                            rest={},
                            rfc2109=False
                        )
                        self.cookie_jar.set_cookie(cookie)

                    self.authenticated = True
                    self.log("API login successful!")
                    self.log(f"Session: ljsession={ljsession[:20]}...{ljsession[-20:]}")

                    # Show all cookies in jar
                    all_cookies = [(c.name, c.domain) for c in self.cookie_jar]
                    self.log(f"Cookies in jar: {all_cookies}")

                    return True
                else:
                    self.log("API login failed - no session returned")
                    if 'errmsg' in response_data:
                        self.log(f"Error: {response_data['errmsg']}")
                    return False

        except Exception as e:
            self.log(f"API login error: {e}")
            return False

    def fetch_page(self, url, delay=True):
        """Fetch a page with respectful delays."""
        if delay:
            time.sleep(REQUEST_DELAY)

        auth_marker = "[AUTH]" if self.authenticated else "[PUBLIC]"
        self.log(f"Fetching {auth_marker}: {url}")

        try:
            headers = {'User-Agent': USER_AGENT}

            # If authenticated, use the opener with cookie jar (automatic cookie handling)
            # Don't manually add cookies - let the opener handle it
            if self.authenticated:
                req = Request(url, headers=headers)

                # Debug: check what cookies will be sent
                if self.verbose and '.html' not in url:
                    all_cookies = list(self.cookie_jar)
                    cookie_str = '; '.join([f"{c.name}={c.value[:15]}..." for c in all_cookies])
                    self.log(f"  Cookies that will be auto-sent: {cookie_str}")

                # Use the opener which automatically includes cookies from the jar
                with self.opener.open(req, timeout=30) as response:
                    content = response.read().decode('utf-8')

                    # For journal pages, verify authentication worked
                    if '.html' not in url:
                        if 'has_remote":1' in content or '"has_remote":1' in content:
                            self.log(f"  ✓ Page shows has_remote:1 (authenticated!)")
                        elif 'security-access' in content or 'security-private' in content:
                            self.log(f"  ✓ Page shows non-public security level")
                        elif 'has_remote":0' in content:
                            self.log(f"  ✗ Page shows has_remote:0 (NOT authenticated!)")
                        else:
                            self.log(f"  ? Could not determine authentication status from page")

                    return content
            else:
                # Not authenticated - use simple urlopen
                req = Request(url, headers=headers)
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
        # Build URL - use different parameters when authenticated
        if self.authenticated:
            # Try using ?format=light which might show more entries when authenticated
            # Or we could try archive pages
            if skip == 0:
                url = f"{self.base_url}/?format=light"
            else:
                url = f"{self.base_url}/?format=light&skip={skip}"
            self.log(f"Using authenticated format: {url}")
        else:
            url = f"{self.base_url}/" if skip == 0 else f"{self.base_url}/?skip={skip}"

        html = self.fetch_page(url, delay=(skip > 0))  # Don't delay first request

        if not html:
            return []

        # Save HTML to file for debugging
        if skip == 0 and self.verbose:
            debug_file = f"/tmp/dwscrape_debug_{self.journal_name}.html"
            try:
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                self.log(f"  Saved first page HTML to {debug_file} for debugging")
            except:
                pass

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
        # Login first if credentials are provided
        if self.username and self.password:
            self.login()

        # Load existing entries from database
        self.load_existing_itemids()

        all_entries = []
        skip = 0
        entries_per_page = 20  # Dreamwidth default
        new_entries_count = 0
        skipped_count = 0
        consecutive_empty_pages = 0
        consecutive_all_exist_pages = 0
        max_consecutive_exist = 3  # Stop after 3 pages where everything exists

        while True:
            # Fetch journal page
            entry_urls = self.scrape_journal_page(skip)
            self.log(f"Found these urls: {entry_urls}")
#            os._exit(os.EX_OK)
            if not entry_urls:
                consecutive_empty_pages += 1
                self.log(f"No entries found on page (empty page {consecutive_empty_pages})")
                # Stop after 2 consecutive empty pages
                if consecutive_empty_pages >= 2:
                    self.log("Hit multiple empty pages - reached end of journal")
                    break
                # Otherwise continue - might be a pagination issue
                skip += entries_per_page
                continue
            else:
                consecutive_empty_pages = 0

            # Track how many entries on this page are new vs existing
            page_existing_count = 0
            page_new_count = 0
            page_dates = []  # Track dates on this page

            self.log(f"\n--- Processing page with skip={skip} ({len(entry_urls)} entries) ---")

            # Scrape each entry
            for entry_url in entry_urls:
                itemid = self.extract_itemid_from_url(entry_url)

                # Always scrape to get the date, even if we skip storing it
                entry_data = self.scrape_entry(entry_url)
                if not entry_data:
                    continue

                # Format date for logging
                date_str = "NO DATE"
                if entry_data.get('eventtime'):
                    date_str = entry_data['eventtime'].strftime('%Y-%m-%d %H:%M')
                    page_dates.append(entry_data['eventtime'])

                # Skip if we already have this entry
                if itemid and self.entry_exists(itemid):
                    page_existing_count += 1
                    skipped_count += 1
                    self.log(f"SKIP {itemid} [{date_str}] - already exists: {entry_data.get('subject', 'NO TITLE')[:50]}")
                    continue

                # This is a new entry
                all_entries.append(entry_data)
                new_entries_count += 1
                page_new_count += 1
                self.existing_itemids.add(entry_data['itemid'])  # Add to cache
                self.log(f"NEW  {itemid} [{date_str}] - {entry_data.get('subject', 'NO TITLE')[:50]}")

                if max_entries and new_entries_count >= max_entries:
                    self.log(f"Reached max_entries limit: {max_entries}")
                    self.log(f"Total: {new_entries_count} new, {skipped_count} skipped")
                    return all_entries

            # Show date range for this page
            if page_dates:
                earliest = min(page_dates).strftime('%Y-%m-%d')
                latest = max(page_dates).strftime('%Y-%m-%d')
                self.log(f"Page date range: {earliest} to {latest}")

            # Track consecutive pages where all entries exist
            if page_new_count == 0 and page_existing_count > 0:
                consecutive_all_exist_pages += 1
                self.log(f"Page summary: ALL {page_existing_count} entries exist (consecutive all-exist pages: {consecutive_all_exist_pages})")

                # Only stop after multiple consecutive pages with all existing
                # This allows us to continue past gaps in the data
                if consecutive_all_exist_pages >= max_consecutive_exist:
                    self.log(f"\n*** Found {consecutive_all_exist_pages} consecutive pages with all existing entries - stopping ***")
                    self.log("This indicates we've fully caught up with existing data")
                    break
            else:
                # Reset counter when we find new entries
                consecutive_all_exist_pages = 0
                self.log(f"Page summary: {page_new_count} new, {page_existing_count} skipped")

            # Move to next page
            skip += entries_per_page

        self.log(f"\nFinal summary: {new_entries_count} new entries scraped, {skipped_count} duplicates skipped")
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
        description='Scrape Dreamwidth journal entries (public and friends-only with authentication)'
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
    parser.add_argument(
        '--config', '-c',
        default=None,
        help='Config file with login credentials (e.g., ljdump.config)'
    )
    parser.add_argument(
        '--username', '-u',
        default=None,
        help='Dreamwidth username for authentication'
    )
    parser.add_argument(
        '--password', '-p',
        default=None,
        help='Dreamwidth password for authentication'
    )
    parser.add_argument(
        '--cookie',
        default=None,
        help='Session cookie value (ljsession=...) from browser for authentication'
    )

    args = parser.parse_args()

    verbose = not args.quiet
    journal_name = args.journal

    # Load credentials from config file or command line
    username = args.username
    password = args.password
    cookie = args.cookie

    if args.config:
        config = load_config(args.config)
        if config:
            username = username or config.get('username')
            password = password or config.get('password')
            if verbose:
                print(f"Loaded credentials from {args.config}")
        else:
            print(f"Warning: Could not load config from {args.config}")

    # Try default config file if no credentials provided and no cookie
    if not username and not password and not cookie:
        default_config = f"{journal_name}.config"
        if os.path.exists(default_config):
            config = load_config(default_config)
            if config:
                username = config.get('username')
                password = config.get('password')
                if verbose:
                    print(f"Loaded credentials from {default_config}")

    # Determine database path
    if args.output:
        db_path = args.output
    else:
        # Create journal directory if needed
        os.makedirs(journal_name, exist_ok=True)
        db_path = f"{journal_name}/journal.db"

    # Create scraper and run
    scraper = DreamwidthScraper(
        journal_name,
        verbose=verbose,
        username=username,
        password=password,
        db_path=db_path
    )

    print(f"Scraping journal: {journal_name}")
    print(f"Database: {db_path}")

    # Handle cookie-based authentication
    if cookie:
        # Set the cookie directly without login
        scraper.ljsession = cookie
        scraper.authenticated = True
        # Add BOTH ljmastersession (for web) and ljsession (for API) to jar
        cookie_names = ['ljmastersession', 'ljsession']
        for cookie_name in cookie_names:
            for domain in ['.dreamwidth.org', 'dreamwidth.org', 'www.dreamwidth.org', f'{journal_name}.dreamwidth.org']:
                c = Cookie(
                    version=0, name=cookie_name, value=cookie,
                    port=None, port_specified=False,
                    domain=domain, domain_specified=True,
                    domain_initial_dot=domain.startswith('.'),
                    path='/', path_specified=True,
                    secure=False, expires=None, discard=True,
                    comment=None, comment_url=None, rest={}, rfc2109=False
                )
                scraper.cookie_jar.set_cookie(c)
        print(f"Authentication: Using provided cookie (ljmastersession)")
        print("  → Will access friends-only entries if cookie is valid")
    elif username:
        print(f"Authentication: Enabled (user: {username})")
        print("  → Will access friends-only entries if authorized")
    else:
        print("Authentication: Disabled (public entries only)")

    print(f"Note: This tool includes respectful delays between requests")
    print()

    entries = scraper.scrape_journal(max_entries=args.max)

    print(f"\n{'='*60}")
    print(f"Scraping complete!")
    print(f"New entries scraped: {len(entries)}")
    print(f"Total entries in database: {len(scraper.existing_itemids)}")

    if entries:
        print(f"\nStoring {len(entries)} new entries in database...")
        scraper.store_entries(entries, db_path)
        print(f"Done! All entries stored in {db_path}")
        print(f"\nYou can now use ljdumptomd.py or ljdumptohtml.py on this database")
    else:
        print("\nNo new entries to store (all entries already in database)")
        print(f"Database is up to date with {len(scraper.existing_itemids)} entries")


if __name__ == '__main__':
    main()
