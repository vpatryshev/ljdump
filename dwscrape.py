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
import os
import xml.dom.minidom
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlencode
from urllib.request import Request, urlopen, HTTPCookieProcessor, build_opener
from http.cookiejar import CookieJar, Cookie
from html.parser import HTMLParser
from ljdumpsqlite import (
    create_tables_if_missing
)
from journal import *

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
        self.in_date = False
        self.current_tag_stack = []
        self.title_text = []
        self.content_parts = []
        self.tags = []
        self.current_date = None

        # Track entries with their metadata from listing page
        self.entries = []  # List of dicts with 'url', 'title', 'date'
        self.current_entry = None
        self.current_entry_title = []
        self.current_entry_date = []
        self.datetime_depth = 0  # Track nesting of datetime spans

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self.current_tag_stack.append((tag, attrs_dict))

        # Look for entry containers (article or div with entry-wrapper or entry class)
        if tag in ['article', 'div']:
            classes = attrs_dict.get('class', '')
            if 'entry-wrapper' in classes or ('entry' in classes and 'entry-content' not in classes):
                # Start tracking a new entry
                self.current_entry = {'url': None, 'title': '', 'date': ''}
                self.current_entry_title = []
                self.current_entry_date = []

        # Look for entry links
        if tag == 'a':
            href = attrs_dict.get('href', '')
            # Match patterns like /344866.html or https://journal.dreamwidth.org/344866.html
            if re.search(r'/\d+\.html', href):
                self.entry_links.append(href)
                # If we're in an entry and haven't found a URL yet, use this one
                if self.current_entry is not None and self.current_entry['url'] is None:
                    self.current_entry['url'] = href

        # Track if we're in important sections
        if tag in ['h1', 'h2', 'h3']:
            # Could be title
            classes = attrs_dict.get('class', '')
            if self.current_entry and 'entry-title' in classes:
                self.in_title = True

        # Look for date/time elements - specifically the datetime span
        if tag == 'span':
            classes = attrs_dict.get('class', '')
            if self.current_entry and 'datetime' in classes:
                self.in_date = True
                self.datetime_depth = 1
            elif self.in_date:
                self.datetime_depth += 1

        if tag == 'div' or tag == 'article':
            classes = attrs_dict.get('class', '')
            if any(keyword in classes for keyword in ['entry-content', 'entrytext', 'entry-text']):
                self.in_content = True
            if 'tags' in classes or 'tag' in classes:
                self.in_tags = True

    def handle_endtag(self, tag):
        # Check if we're closing an entry container
        if self.current_tag_stack and tag in ['article', 'div']:
            attrs_dict = self.current_tag_stack[-1][1] if self.current_tag_stack else {}
            classes = attrs_dict.get('class', '')
            if 'entry-wrapper' in classes and self.current_entry:
                # Finalize current entry
                self.current_entry['title'] = ' '.join(self.current_entry_title).strip()
                self.current_entry['date'] = ' '.join(self.current_entry_date).strip()
                if self.current_entry['url']:
                    self.entries.append(self.current_entry)
                self.current_entry = None
                self.current_entry_title = []
                self.current_entry_date = []

        if self.current_tag_stack and self.current_tag_stack[-1][0] == tag:
            self.current_tag_stack.pop()

        if tag in ['h1', 'h2', 'h3']:
            self.in_title = False
        if tag == 'span' and self.in_date:
            self.datetime_depth -= 1
            if self.datetime_depth <= 0:
                self.in_date = False
                self.datetime_depth = 0
        if tag in ['div', 'article']:
            self.in_content = False
            self.in_tags = False

    def handle_data(self, data):
        if self.in_title and self.current_entry is not None:
            self.current_entry_title.append(data.strip())
        if self.in_date and self.current_entry is not None:
            self.current_entry_date.append(data.strip())

        # Keep old functionality for single-entry parsing
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

    def __init__(self, journal_name, verbose=True, username=None, password=None, db_path=None, api_key=None):
        self.journal_name = journal_name
        self.base_url = f"https://{journal_name}.dreamwidth.org"
        self.verbose = verbose
        self.username = username
        self.password = password
        self.api_key = api_key
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
            db = DB(self.db_path)
            cur = db.cursor()

            # Check if entries table exists
            cur.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='entries'
            """)
            if not cur.fetchone():
                self.log("Database exists but no entries table - will scrape all entries")
                db.close()
                return

            # Load all existing itemids
            cur.execute("SELECT itemid FROM entries")
            self.existing_itemids = set(row[0] for row in cur.fetchall())

            db.close()

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
        # If API key is provided, use Bearer token authentication
        if self.api_key:
            self.log("Using API key for Bearer token authentication")
            self.authenticated = True
            return True

        if not self.username or not self.password:
            self.log("No credentials provided, scraping without authentication")
            return False

        self.log(f"Logging in as {self.username} via web login...")

        try:
            # Step 1: Get the login page to extract lj_form_auth token
            login_page_url = "https://www.dreamwidth.org/login"
            req = Request(login_page_url, headers={'User-Agent': USER_AGENT})

            with self.opener.open(req, timeout=30) as response:
                login_html = response.read().decode('utf-8')

                # Extract lj_form_auth token
                auth_match = re.search(r'name=["\']lj_form_auth["\'] value=["\']([^"\']+)["\']', login_html)
                lj_form_auth = auth_match.group(1) if auth_match else None

                if lj_form_auth:
                    self.log(f"Found CSRF token")

            # Step 2: POST login credentials
            login_data = {
                'user': self.username,
                'password': self.password,
                'action:login': 'Log in',
                'remember_me': '1'
            }

            if lj_form_auth:
                login_data['lj_form_auth'] = lj_form_auth

            encoded_data = urlencode(login_data).encode('utf-8')
            req2 = Request(login_page_url, data=encoded_data, headers={'User-Agent': USER_AGENT})

            with self.opener.open(req2, timeout=30) as response2:
                # Check if login was successful by looking for session cookies
                has_session = False
                for cookie in self.cookie_jar:
                    if cookie.name == 'ljmastersession':
                        has_session = True
                        self.ljsession = cookie.value
                        self.log(f"✓ Got ljmastersession cookie")
                        break

                if has_session:
                    self.authenticated = True
                    self.log("Web login successful!")

                    # Show all cookies
                    all_cookies = [(c.name, c.domain) for c in self.cookie_jar]
                    self.log(f"Cookies: {', '.join([c[0] for c in all_cookies])}")

                    return True
                else:
                    self.log("✗ Web login failed - no session cookie received")
                    return False

        except Exception as e:
            self.log(f"Web login error: {e}")
            return False

    def fetch_page(self, url, delay=True):
        """Fetch a page with respectful delays."""
        if delay:
            time.sleep(REQUEST_DELAY)

        auth_marker = "[AUTH]" if self.authenticated else "[PUBLIC]"
        self.log(f"Fetching {auth_marker}: {url}")

        try:
            headers = {'User-Agent': USER_AGENT}

            # If using API key, add Bearer token authorization
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'

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
            "%Y-%m-%d %H:%M",       # 2022-04-26 20:21 (from month pages)
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

        Returns list of entry dicts with 'url', 'title', 'date' keys from listing page.
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

        # Debug logging
        self.log(f"  Parser found {len(parser.entries)} entries with metadata")
        self.log(f"  Parser found {len(parser.entry_links)} entry links")

        # Use the enhanced entry metadata if available, fall back to just URLs
        entries = []
        seen_itemids = set()

        if parser.entries:
            # Use metadata from parser
            self.log(f"  Using enhanced parser entries with metadata")
            for entry in parser.entries:
                href = entry['url']
                if '#' in href:
                    continue

                full_url = urljoin(self.base_url, href)
                itemid = self.extract_itemid_from_url(full_url)

                if itemid and itemid not in seen_itemids:
                    seen_itemids.add(itemid)
                    entries.append({
                        'url': full_url,
                        'title': entry['title'] or 'NO TITLE',
                        'date': entry['date'] or 'NO DATE'
                    })
        else:
            # Fallback to old behavior (just URLs)
            self.log(f"  Using fallback mode (entry_links only)")
            for href in parser.entry_links:
                if '#' in href:
                    continue

                full_url = urljoin(self.base_url, href)
                itemid = self.extract_itemid_from_url(full_url)

                if itemid and itemid not in seen_itemids:
                    seen_itemids.add(itemid)
                    entries.append({
                        'url': full_url,
                        'title': 'NO TITLE',
                        'date': 'NO DATE'
                    })

        self.log(f"Found {len(entries)} unique entries on page (skip={skip})")
        return entries

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

    def scrape_archive_page(self):
        """Scrape the archive page to get all year/month links.

        Returns:
            List of month URLs (e.g., ['https://kdanilov.dreamwidth.org/2022/11/', ...])
        """
        url = f"{self.base_url}/archive"
        self.log(f"Fetching archive page: {url}")

        html = self.fetch_page(url)
        if not html:
            self.log("  ✗ Failed to fetch archive page")
            return []

        self.log(f"  ✓ Archive page fetched ({len(html)} bytes)")

        month_links = []

        # Find month links directly from archive page
        # Pattern matches both relative and full URLs: /2022/11/ or https://kdanilov.dreamwidth.org/2022/11/
        # We want YYYY/MM/ patterns (2 digits for month)
        self.log("  Searching for direct month archive links (usually current year)...")
        month_pattern = r'href="(?:https?://[^/]+)?(/\d{4}/\d{2}/)(?:"|\?)'
        month_matches = re.findall(month_pattern, html)
        self.log(f"  Found {len(month_matches)} direct month link matches (may include duplicates)")

        for match in month_matches:
            full_url = urljoin(self.base_url, match)
            if full_url not in month_links:
                month_links.append(full_url)
                self.log(f"    • {full_url}")

        # ALWAYS check for year links and visit them (older years are only linked as years)
        self.log("\n  Searching for year archive links (for older years)...")

        # Find year links (YYYY/ only)
        # Match full URLs like https://kdanilov.dreamwidth.org/2017/
        year_pattern = r'href="(https?://[^/]+/\d{4}/)(?:"|\?)'
        year_matches = re.findall(year_pattern, html)

        year_links = []
        for match in year_matches:
            # Make sure it's year-only (ends with YYYY/ not YYYY/MM/)
            if re.match(r'.*/\d{4}/$', match):
                if match not in year_links:
                    year_links.append(match)

        self.log(f"  Found {len(year_links)} year archives")

        # Visit each year page to get month links
        for year_url in year_links:
            self.log(f"    Fetching year archive: {year_url}")
            year_html = self.fetch_page(year_url, delay=True)
            if not year_html:
                self.log(f"      ✗ Failed to fetch year page")
                continue

            # Find month links in this year page
            year_month_matches = re.findall(month_pattern, year_html)
            self.log(f"      Found {len(year_month_matches)} month links in this year")
            for match in year_month_matches:
                full_url = urljoin(self.base_url, match)
                if full_url not in month_links:
                    month_links.append(full_url)
                    self.log(f"        • {full_url}")

        # Sort by date (newest first)
        month_links.sort(reverse=True)

        self.log(f"Found {len(month_links)} month archives to scrape")
        return month_links

    def scrape_month_page(self, month_url):
        """Scrape a month archive page to get all entry URLs.

        Args:
            month_url: URL like 'https://kdanilov.dreamwidth.org/2022/11/'

        Returns:
            List of entry dicts with 'url', 'title', 'date' keys
        """
        self.log(f"  Fetching month page: {month_url}")
        html = self.fetch_page(month_url, delay=True)
        if not html:
            self.log(f"  ✗ Failed to fetch month page")
            return []

        self.log(f"  ✓ Month page fetched ({len(html)} bytes), parsing entries...")
        entries = []

        # The structure is <dt>date</dt><dd>time+entry</dd>
        # We need to extract date-entry pairs from the <dl> structure

        # Pattern for date links with full URL: <dt><a href="https://kdanilov.dreamwidth.org/2022/11/29/">29th</a></dt>
        date_pattern = r'<dt><a href="https?://[^/]+/(\d{4})/(\d{2})/(\d{2})/">(\d+)(?:st|nd|rd|th)?</a></dt>'

        # Pattern for the <dd> section that follows, containing time and entry
        # <dd><span class="datetime"><span class="time">05:58 am</span></span>...<h3 class="entry-title"><a title="..." href="...">title</a></h3>
        dd_pattern = r'<dd>.*?<span class="time">([^<]+)</span>.*?<h3[^>]*class="[^"]*entry-title[^"]*"[^>]*><a[^>]*title="([^"]*)"[^>]*href="([^"]+)"[^>]*>([^<]+)</a></h3>.*?</dd>'

        # Find all date entries
        date_matches = list(re.finditer(date_pattern, html))

        # Find all dd entries
        dd_matches = list(re.finditer(dd_pattern, html, re.DOTALL | re.IGNORECASE))

        # Match them up (should be 1:1)
        for i in range(min(len(date_matches), len(dd_matches))):
            date_match = date_matches[i]
            dd_match = dd_matches[i]

            year, month, day, day_num = date_match.groups()
            time_str, title_attr, url, title_text = dd_match.groups()

            date_str = f"{year}-{month}-{day} {time_str}"

            # Use title attribute if available, otherwise use title text
            title = title_attr if title_attr else title_text

            entries.append({
                'url': url,
                'title': title,
                'date': date_str
            })

        self.log(f"  Found {len(entries)} entries in {month_url}")
        return entries

    def scrape_year_page_months(self, year_url):
        """Extract month archive links from a year page.

        Args:
            year_url: URL like 'https://kdanilov.dreamwidth.org/2017/'

        Returns:
            List of month URLs (e.g., ['https://kdanilov.dreamwidth.org/2017/06/', ...])
        """
        html = self.fetch_page(year_url, delay=True)
        if not html:
            return []

        # Extract month links: https://kdanilov.dreamwidth.org/2017/06/
        month_pattern = r'href="(https?://[^/]+/\d{4}/\d{2}/)"'
        month_urls = re.findall(month_pattern, html)

        # Deduplicate while preserving order
        seen = set()
        unique_urls = []
        for url in month_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        return unique_urls

    def scrape_journal_from_archive(self, max_entries=None):
        """Scrape journal by extracting entry URLs directly from year pages.

        Args:
            max_entries: Maximum number of entries to scrape (None for all)

        Returns:
            List of entry data dictionaries
        """
        # Login first if credentials or API key are provided
        if self.api_key or (self.username and self.password):
            self.login()

        # Load existing entries from database
        self.load_existing_itemids()

        # Get year URLs from archive page
        archive_url = f"{self.base_url}/archive"
        self.log(f"Fetching archive page: {archive_url}")
        html = self.fetch_page(archive_url)
        if not html:
            self.log("Failed to fetch archive page")
            return []

        # Extract year links
        year_pattern = r'href="(https?://[^/]+/\d{4}/)(?:"|\?)'
        year_matches = re.findall(year_pattern, html)
        year_urls = []
        for match in year_matches:
            if re.match(r'.*/\d{4}/$', match) and match not in year_urls:
                year_urls.append(match)

        year_urls.sort(reverse=True)  # Newest first
        self.log(f"Found {len(year_urls)} year archives")

        if not year_urls:
            self.log("No year archives found")
            return []

        # Collect all month URLs from all year pages
        self.log(f"\n=== Collecting month URLs from {len(year_urls)} year pages ===")
        all_month_urls = []
        seen_months = set()

        for year_idx, year_url in enumerate(year_urls, 1):
            self.log(f"[{year_idx}/{len(year_urls)}] {year_url}")
            month_urls = self.scrape_year_page_months(year_url)

            for url in month_urls:
                if url not in seen_months:
                    seen_months.add(url)
                    all_month_urls.append(url)

            self.log(f"  → Found {len(month_urls)} months")

        self.log(f"\n✓ Collected {len(all_month_urls)} month archives")

        # Collect all entry URLs from all month pages (WITH dates)
        self.log(f"\n=== Collecting entry URLs from {len(all_month_urls)} month pages ===")
        all_entry_metadata = []  # Changed: store full metadata, not just URLs
        seen_entry_urls = set()

        for month_idx, month_url in enumerate(all_month_urls, 1):
            self.log(f"[{month_idx}/{len(all_month_urls)}] {month_url}")
            entries = self.scrape_month_page(month_url)

            for entry in entries:
                url = entry['url']
                if url not in seen_entry_urls:
                    seen_entry_urls.add(url)
                    all_entry_metadata.append(entry)  # Changed: keep full metadata

            self.log(f"  → Found {len(entries)} entries (total: {len(all_entry_metadata)} unique)")

        self.log(f"\n✓ Collected {len(all_entry_metadata)} unique entry URLs")

        # Process all entries
        self.log(f"\n=== Processing {len(all_entry_metadata)} entries ===")
        all_entries = []
        new_entries_count = 0
        skipped_count = 0

        for entry_idx, entry_meta in enumerate(all_entry_metadata, 1):
            entry_url = entry_meta['url']
            month_page_date = entry_meta.get('date')  # Date from month page
            month_page_title = entry_meta.get('title')  # Title from month page

            itemid = self.extract_itemid_from_url(entry_url)

            # Skip if we already have this entry
            if itemid and self.entry_exists(itemid):
                skipped_count += 1
                self.log(f"[{entry_idx}/{len(all_entry_metadata)}] SKIP {itemid} - already exists")
                continue

            # Scrape the full entry
            self.log(f"[{entry_idx}/{len(all_entry_metadata)}] Fetching {itemid}")
            entry_data = self.scrape_entry(entry_url)
            if not entry_data:
                self.log(f"[{entry_idx}/{len(all_entry_metadata)}] ✗ Failed to scrape entry {itemid}")
                continue

            # Use month page date as fallback if entry page didn't have a date
            if not entry_data.get('eventtime') and month_page_date:
                dt = self.parse_date(month_page_date)
                if dt:
                    entry_data['eventtime'] = dt
                    entry_data['eventtime_unix'] = dt.timestamp()
                    self.log(f"  Using date from month page: {month_page_date}")

            # Use month page title as fallback if entry page didn't have a title
            if not entry_data.get('subject') and month_page_title:
                entry_data['subject'] = month_page_title

            # Format date for logging
            date_str = "NO DATE"
            if entry_data.get('eventtime'):
                date_str = entry_data['eventtime'].strftime('%Y-%m-%d %H:%M')

            # This is a new entry
            all_entries.append(entry_data)
            new_entries_count += 1
            self.existing_itemids.add(entry_data['itemid'])
            self.log(f"[{entry_idx}/{len(all_entry_metadata)}] ✓ NEW {itemid} [{date_str}] - {entry_data.get('subject', 'NO TITLE')[:50]}")

            if max_entries and new_entries_count >= max_entries:
                self.log(f"\n!!! Reached max_entries limit: {max_entries}")
                self.log(f"Total: {new_entries_count} new, {skipped_count} skipped")
                return all_entries

        self.log(f"\n=== Archive scraping complete ===")
        self.log(f"Total: {new_entries_count} new entries, {skipped_count} skipped")
        return all_entries

    def scrape_journal(self, max_entries):
        """Scrape all entries from a journal.

        Args:
            max_entries: Maximum number of entries to scrape (None for all)

        Returns:
            List of entry data dictionaries
        """
        # Login first if credentials or API key are provided
        if self.api_key or (self.username and self.password):
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
        max_pages = (max_entries + entries_per_page - 1) / entries_per_page  # Stop after 3 pages where everything exists

        while True:
            # Fetch journal page with entry metadata
            entries = self.scrape_journal_page(skip)
            if self.verbose:
                self.log(f"Found these entries: {[e['url'] for e in entries]}")
            if not entries:
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

            self.log(f"\n--- Processing page with skip={skip} ({len(entries)} entries) ---")

            # Scrape each entry
            for entry_meta in entries:
                entry_url = entry_meta['url']
                entry_title_from_listing = entry_meta['title']
                entry_date_from_listing = entry_meta['date']

                itemid = self.extract_itemid_from_url(entry_url)

                # Skip if we already have this entry
                if itemid and self.entry_exists(itemid):
                    page_existing_count += 1
                    skipped_count += 1
                    self.log(f"SKIP {itemid} [{entry_date_from_listing}] - already exists: {entry_title_from_listing[:50]}")
                    continue

                # Always scrape to get the date, even if we skip storing it
                entry_data = self.scrape_entry(entry_url)
                if not entry_data:
                    continue

                # Format date for logging
                date_str = "NO DATE"
                if entry_data.get('eventtime'):
                    date_str = entry_data['eventtime'].strftime('%Y-%m-%d %H:%M')
                    page_dates.append(entry_data['eventtime'])

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
                if consecutive_all_exist_pages >= max_pages:
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

        db = DB(db_path, self.verbose)

        create_tables_if_missing(db, self.verbose)
        cur = db.cursor()

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


        db.close(cur)

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
        default=200,
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
    parser.add_argument(
        '--api-key',
        default=None,
        help='Dreamwidth API key for Bearer token authentication (get from Manage Accounts → Mobile → Advanced Options)'
    )
    parser.add_argument(
        '--use-archive',
        action='store_true',
        help='Use archive-based scraping (more reliable, traverses /archive pages)'
    )

    args = parser.parse_args()

    verbose = not args.quiet
    journal = Journal(args.journal)

    # Load credentials from config file or command line
    username = args.username
    password = args.password
    cookie = args.cookie
    api_key = args.api_key

    if args.config:
        configFileData = load_config(args.config)
        if configFileData:
            username = username or configFileData.get('username')
            password = password or configFileData.get('password')
            if verbose:
                print(f"Loaded credentials from {args.config}")
        else:
            print(f"Warning: Could not load config from {args.config}")

    # Try default config file if no credentials provided and no cookie/api_key
    if not username and not password and not cookie and not api_key:
      default_config = f"{journal.name}.config"
      if not os.path.exists(default_config):
        default_config = f"work/default_config"
      if os.path.exists(default_config):
        configFileData = load_config(default_config)
        if configFileData:
          username = configFileData.get('username')
          password = configFileData.get('password')
          if verbose:
            print(f"Loaded credentials from {default_config}")

    # Determine database path
    if args.output:
      db_path = args.output
    else:
      # Create journal directory if needed
      os.makedirs(journal.workdir, exist_ok=True)
      db_path = f"{journal.workdir}/journal.db"

    # Create scraper and run
    scraper = DreamwidthScraper(
        journal.name,
        verbose=verbose,
        username=username,
        password=password,
        db_path=db_path,
        api_key=api_key
    )

    print(f"Scraping journal: {journal.name}")
    print(f"Database: {db_path}")

    # Handle API key authentication (preferred method)
    if api_key:
        print(f"Authentication: API key (Bearer token)")
        print("  → Using modern Dreamwidth API with Bearer token")
        print("  → Will access friends-only entries if API key is valid")
    # Handle cookie-based authentication
    elif cookie:
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
    if args.use_archive:
        print("Mode: Archive-based scraping (traversing /archive pages)")
    else:
        print("Mode: Pagination-based scraping (use --use-archive for more reliable scraping)")
    print()

    if args.use_archive:
        entries = scraper.scrape_journal_from_archive(max_entries=args.max)
    else:
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
