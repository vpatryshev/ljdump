#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update an existing Dreamwidth entry from an ljdump SQLite database.

Reads an entry from the database (by its local itemid) and overwrites the
matching entry on Dreamwidth via editevent. By default the entry edited on the
server is the one with the same itemid; use --target-itemid to point at a
different server-side entry.

The database is read from under the "work/" directory, so --db is given
relative to work/ (e.g. --db juan_gandhi/journal.db reads
work/juan_gandhi/journal.db).

Usage:
  python update_from_db.py --user USERNAME --password PASSWORD \
               --db juan_gandhi/journal.db --itemid 12345 \
               [--target-itemid 67890] [--server https://www.dreamwidth.org] \
               [--security friends] [--dry-run]
"""

import argparse
import datetime as dt
import sys

from utils import *
from db import *
from account import *


def main():
  ap = argparse.ArgumentParser(
    description="Update an existing Dreamwidth entry from an ljdump SQLite database"
  )
  ap.add_argument("--server", default=DREAMWIDTH,
                  help=f"Server url (default: {DREAMWIDTH})")
  ap.add_argument("--user", required=True, help="Dreamwidth username")
  ap.add_argument("--password", required=True, help="Dreamwidth password")
  ap.add_argument("--db", required=True,
                  help="Path to ljdump SQLite database, relative to work/")
  ap.add_argument("--itemid", required=True, type=int,
                  help="Entry itemid in the database (source of the new content)")
  ap.add_argument("--target-itemid", type=int, default=None,
                  help="Server-side itemid of the entry to edit "
                       "(default: same as --itemid)")
  ap.add_argument("--security", default="public",
                  choices=["public", "friends", "private"],
                  help="Post security level (default: public)")
  ap.add_argument("--dry-run", action="store_true",
                  help="Print the entry without updating it")
  args = ap.parse_args()

  target_itemid = args.target_itemid if args.target_itemid is not None else args.itemid

  db = DB(f"work/{args.db}")
  itemid = args.itemid
  entries = db.get(itemid)
  if not entries:
    print(f"0 records found for itemid={args.itemid}")
    return

  entry = dict(entries[0])

  try:
    post_date = dt.datetime.fromisoformat(entry["eventtime"])
  except (ValueError, TypeError) as e:
    print(f"Error parsing eventtime '{entry['eventtime']}': {e}", file=sys.stderr)
    sys.exit(1)

  subject = entry["subject"] or ""
  body = entry["event"]
  tags = entry["props_taglist"] or ""

  if args.dry_run:
    print(f"db itemid   : {itemid}")
    print(f"edit itemid : {target_itemid}")
    print(f"date        : {post_date}")
    print(f"subject     : {subject}")
    print(f"tags        : {tags}")
    print(f"security    : {args.security}")
    return

  try:
    account = Account.from_args(args)
    res = account.edit(
      itemid=target_itemid,
      subject=subject,
      body=body,
      tags=tags,
      security=args.security,
      post_date=post_date,
    )

    cleanup_updatetime=f"update entries set updatetime=null where itemid={itemid}"
    db.execute(cleanup_updatetime)

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
