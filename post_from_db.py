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

from utils import *
from db import *
from blog import *
from journal import *

def post(blog, entry, args):

  subject = entry['subject'] or ""
  body = entry["event"]
  tags = entry["props_taglist"] or ""

  if args.dry_run:
    print(f"itemid  : {entry['itemid']}")
    print(f"date  : {entry["eventtime"]}")
    print(f"subject : {subject}")
    print(f"tags  : {tags}")
    print(f"security: {args.security}")
#    print("--- body ---")
#    print(body)
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
    print("OK")
    print(f"URL: {res["url"]}")

  except Exception as e:
    print(f"Error in post_from_db.py: {e}", file=sys.stderr)

def main():
  ap = argparse.ArgumentParser(
    description="Post an entry from an ljdump SQLite database to Dreamwidth"
  )
  ap.add_argument("--server", default="https://dreamwidth.org", help="Server url")
  ap.add_argument("--user", required=True, help="Dreamwidth username")
  ap.add_argument("--password", required=True, help="Dreamwidth password")
  ap.add_argument("--db", required=True, help="Path to ljdump SQLite database")
  ap.add_argument("--itemid", required=False, type=int,
          help="Entry itemid in the database")
  ap.add_argument("--where", required=False, type=str,
          help="Filter for entries")
  ap.add_argument("--security", default="public",
          choices=["public", "friends", "private"],
          help="Post security level (default: public)")
  ap.add_argument("--dry-run", action="store_true",
          help="Print the entry without posting it")
  args = ap.parse_args()

  blog = Blog(args.server, args.user, args.password)
  journal = Journal(args.user)
  db = DB(f"work/{args.db}")
  if args.itemid != None:
    entries = db.get(args.itemid)
  elif args.where != None:
    entries = db.select(args.where)
  else:
    fail("Specify either --itemid or --where")

  if not entries or len(entries) == 0:
    print(f"0 records found for itemid={args.itemid}, {entries}")
    return
  print(f"Found {len(entries)} records")
  for i, entry_data in enumerate(entries):
    entry = dict(entry_data)
    print(f"{i}). #{entry['itemid']}, {entry['eventtime']}, {entry['subject']}, {entry['props_taglist']}, {len(entry['event'])} bytes")

    throttle()
    post(blog, entry, args)

if __name__ == "__main__":
  main()
