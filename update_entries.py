#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_entries.py — apply a sed-style regex substitution to journal entries.

Usage:
    python3 update_entries.py <journal> <where_clause> <s/old/new/[g]>

Arguments:
    journal        Journal short name; database is expected at work/<journal>/journal.db
    where_clause   SQL WHERE clause used to pre-filter entries
    regex          Substitution in sed form: s/pattern/replacement/ or s/pattern/replacement/g

Example:
    python3 update_entries.py kdanilov "props_taglist LIKE '%music%'" "s/oldband/newband/g"
"""

import argparse
import calendar
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ljdumpdb import LJDB


def parse_sed(expr):
    """Parse a sed-style s/pattern/replacement/[g] expression.
    Returns (pattern, replacement, count) where count=0 means replace all.
    Raises ValueError on bad syntax.
    """
    if not expr.startswith("s"):
        raise ValueError(f"Regex must start with 's': {expr!r}")
    sep = expr[1]
    parts = expr[2:].split(sep)
    if len(parts) not in (2, 3):
        raise ValueError(f"Expected s{sep}pattern{sep}replacement{sep}[g], got: {expr!r}")
    pattern, replacement = parts[0], parts[1]
    flags_str = parts[2] if len(parts) == 3 else ""
    count = 0 if "g" in flags_str else 1
#    print(f"Pattern: {pattern!r}, replacement: {replacement!r}, count: {count}")
    return pattern, replacement, count


def main():
    parser = argparse.ArgumentParser(
        description="Apply a sed-style regex substitution to journal entries.")
    parser.add_argument("journal",
        help="Journal short name (database at work/<journal>/journal.db)")
    parser.add_argument("where_clause",
        help="SQL WHERE clause to select target entries")
    parser.add_argument("regex",
        help="Substitution expression: s/pattern/replacement/[g]")
    parser.add_argument("--dry-run", "-n", action="store_true",
        help="Show what would change without writing to the database")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    try:
        pattern, replacement, count = parse_sed(args.regex)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    db_path = os.path.join("work", args.journal, "journal.db")
    db = LJDB(db_path, verbose=args.verbose)

    cur = db.cursor()
    sql = f"SELECT itemid, event FROM entries WHERE {args.where_clause}"
    if args.verbose:
        print(f"Query: {sql}")
    cur.execute(sql)
    rows = cur.fetchall()

    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%d %H:%M:%S")
    now_unix = float(calendar.timegm(now.utctimetuple()))
    print(pattern)
    updated = 0
    for itemid, event in rows:
        if event is None:
            continue
        new_event = re.sub(pattern, replacement, event, count=count)
        if new_event == event:
            continue

        if args.dry_run:
            print(f"[dry-run] Would update itemid={itemid}")
            if args.verbose:
                # Show first differing line for context
                old_lines = event.splitlines()
                new_lines = new_event.splitlines()
                for old, new in zip(old_lines, new_lines):
                    if old != new:
                        print(f"  - {old!r}")
                        print(f"  + {new!r}")
        else:
            cur.execute("""
                UPDATE entries
                SET event = ?,
                    updatetime = ?,
                    updatetime_unix = ?
                WHERE itemid = ?
            """, (new_event, now_iso, now_unix, itemid))
            if args.verbose:
                print(f"Updated itemid={itemid}")

        updated += 1

    if args.dry_run:
        print(f"{updated} entr{'y' if updated == 1 else 'ies'} would be updated (dry run).")
        db.close(None)
    else:
        print(f"{updated} entr{'y' if updated == 1 else 'ies'} updated.")
        db.close(cur)


if __name__ == "__main__":
    main()
