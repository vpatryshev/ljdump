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

from db import *
from dw import *

def post(blog, entry, args):

    subject = entry["subject"] or ""
    body = entry["event"]
    tags = entry["props_taglist"] or ""

    if args.dry_run:
        print(f"itemid  : {entry['itemid']}")
        print(f"date    : {entry["eventtime"]}")
        print(f"subject : {subject}")
        print(f"tags    : {tags}")
        print(f"security: {args.security}")
        print("--- body ---")
        print(body)
        return

    try:
        post_date = dt.datetime.strptime(entry["eventtime"], "%Y-%m-%d %H:%M:%S")
        res = blog.post(
            subject=subject,
            body=body,
            tags=tags,
            post_date=post_date,
            security=args.security,
        )
    except Exception as e:
        print(f"Error in post_from_db.py: {e}", file=sys.stderr)
        return

    print("OK")
    for k in ("itemid", "anum", "url"):
        if k in res:
            print(f"{k}: {res[k]}")
    if not any(k in res for k in ("itemid", "anum", "url")):
        print(res)

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

    blog = Blog(args.user, args.password)
    db = DB(args.db)
    entries = db.get(args.itemid)
    if not entries:
        print(f"0 records found for itemid={args.itemid}")
        return

    entry = entries[0]
    post(blog, entry, args)

if __name__ == "__main__":
    main()
