#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Post a single entry from an ljdump SQLite database to Dreamwidth.

Usage:
    python post_from_db.py --user USERNAME --password PASSWORD \
                           --db path/to/journal.db --itemid 12345 [--security friends] [--dry-run]
"""

import argparse
import datetime as dt
import sqlite3
import sys
from pathlib import Path

# dw_post.py lives in the ljdump project
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ljdump" / "ljdump"))
from dw_post import post_to_dreamwidth


def fetch_entry(db_path: str, itemid: int) -> list:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT itemid, subject, event, eventtime, props_taglist "
            "FROM entries WHERE itemid = ?",
            (itemid,)
        ).fetchall()
    finally:
        con.close()

    return [dict(r) for r in rows]


def main():
    ap = argparse.ArgumentParser(
        description="Post an entry from an ljdump SQLite database to Dreamwidth"
    )
    ap.add_argument("--user", required=True, help="Dreamwidth username")
    ap.add_argument("--password", required=True, help="Dreamwidth password")
    ap.add_argument("--db", required=True, help="Path to ljdump SQLite database")
    ap.add_argument("--itemid", required=True, type=int,
                    help="Entry itemid in the database")
    ap.add_argument("--security", default="public",
                    choices=["public", "friends", "private"],
                    help="Post security level (default: public)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the entry without posting it")
    args = ap.parse_args()

    entries = fetch_entry(args.db, args.itemid)
    if not entries:
        print(f"0 records found for itemid={args.itemid}")
        return

    entry = entries[0]

    try:
        post_date = dt.datetime.strptime(entry["eventtime"], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError) as e:
        print(f"Error parsing eventtime '{entry['eventtime']}': {e}", file=sys.stderr)
        sys.exit(1)

    subject = entry["subject"] or ""
    body = entry["event"]
    tags = entry["props_taglist"] or ""

    if args.dry_run:
        print(f"itemid  : {entry['itemid']}")
        print(f"date    : {post_date}")
        print(f"subject : {subject}")
        print(f"tags    : {tags}")
        print(f"security: {args.security}")
        print("--- body ---")
        print(body)
        return

    try:
        res = post_to_dreamwidth(
            user=args.user,
            password=args.password,
            subject=subject,
            body=body,
            tags=tags,
            post_date=post_date,
            security=args.security,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("OK")
    for k in ("itemid", "anum", "url"):
        if k in res:
            print(f"{k}: {res[k]}")
    if not any(k in res for k in ("itemid", "anum", "url")):
        print(res)


if __name__ == "__main__":
    main()
