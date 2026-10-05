#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Post entries from an ljdump SQLite database to Dreamwidth.

The database is read from under the "work/" directory, so --db is given
relative to work/ (e.g. --db juan_gandhi/journal.db reads
work/juan_gandhi/journal.db).

Usage:
  # A single entry by itemid:
  python post_from_db.py --user USERNAME --password PASSWORD \
               --db juan_gandhi/journal.db --itemid 12345 \
               [--server https://www.dreamwidth.org] \
               [--security friends] [--dry-run]

  # Or a batch, by SQL WHERE clause against the entries table:
  python post_from_db.py --user USERNAME --password PASSWORD \
               --db juan_gandhi/journal.db --where "eventtime LIKE '2009-06%'"
"""

import argparse
import datetime as dt
import sys

from utils import *
from db import *
from account import *


def post(account, entry, args):
  subject = entry["subject"] or ""
  body = entry["event"]
  tags = entry["props_taglist"] or ""
  post_date = dt.datetime.fromisoformat(entry["eventtime"])

  if args.dry_run:
    print(f"itemid  : {entry['itemid']}")
    print(f"date    : {entry['eventtime']}")
    print(f"postdate: {post_date}")
    print(f"subject : {subject}")
    print(f"tags    : {tags}")
    print(f"security: {args.security}")
    return

  try:
    res = account.post(
      subject=subject,
      body=body,
      tags=tags,
      post_date=post_date,
      security=args.security,
    )
    print("OK")
    print(f"URL: {res['url']}")

  except Exception as e:
    print(f"Error in post_from_db.py: {e}", file=sys.stderr)


def main():
  ap = argparse.ArgumentParser(
    description="Post entries from an ljdump SQLite database to Dreamwidth"
  )
  ap.add_argument("--server", default=DREAMWIDTH,
                  help=f"Server url (default: {DREAMWIDTH})")
  ap.add_argument("--user", required=True, help="Dreamwidth username")
  ap.add_argument("--password", required=True, help="Dreamwidth password")
  ap.add_argument("--db", required=True,
                  help="Path to ljdump SQLite database, relative to work/")
  ap.add_argument("--itemid", required=False, type=int,
                  help="Entry itemid in the database")
  ap.add_argument("--where", required=False, type=str,
                  help="SQL WHERE filter selecting entries to post")
  ap.add_argument("--security", default="public",
                  choices=["public", "friends", "private"],
                  help="Post security level (default: public)")
  ap.add_argument("--dry-run", action="store_true",
                  help="Print the entries without posting them")
  args = ap.parse_args()

  account = Account.from_args(args)
  db = DB(f"work/{args.db}")
  if args.itemid is not None:
    entries = db.get(args.itemid)
  elif args.where is not None:
    entries = db.select(args.where)
  else:
    fail("Specify either --itemid or --where")

  if not entries:
    print(f"0 records found for itemid={args.itemid}, where={args.where}")
    return

  print(f"Found {len(entries)} records")
  for i, entry_data in enumerate(entries):
    entry = dict(entry_data)
    itemid = entry['itemid']
    print(f"{i}). #{itemid}, {entry['eventtime']}, "
          f"{entry['subject']}, {entry['props_taglist']}, "
          f"{len(entry['event'])} bytes")

    if not args.dry_run:
      throttle()
    res = post(account, entry, args)
    if (res is None):
      db.clear_update_time(itemid)


if __name__ == "__main__":
  main()
