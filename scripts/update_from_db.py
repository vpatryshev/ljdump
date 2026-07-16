#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update an existing Dreamwidth entry from an ljdump SQLite database.

Reads one or more entries from the database and overwrites the matching entries
on Dreamwidth via editevent. The entries to update are chosen with either
--itemid (a single itemid or a comma-separated list) or --where (a SQL WHERE
clause; the script resolves it to the list of matching itemids and updates
those). By default the entry edited on the server is the one with the same
itemid; use --target-itemid (single itemid only) to point at a different
server-side entry.

The database is read from under the "work/" directory, so --db is given
relative to work/ (e.g. --db juan_gandhi/journal.db reads
work/juan_gandhi/journal.db).

Usage:
  python update_from_db.py --user USERNAME --password PASSWORD \
               --db juan_gandhi/journal.db \
               (--itemid 12345[,12346,...] | --where "SQL WHERE clause") \
               [--target-itemid 67890] [--server https://www.dreamwidth.org] \
               [--security friends] [--dry-run]
"""

import argparse
import datetime as dt
import sys

from utils import *
from db import *
from account import *


def parse_itemids(spec: str) -> list:
  """Parse a single itemid or a comma-separated list into a list of ints."""
  ids = []
  for part in spec.split(","):
    part = part.strip()
    if not part:
      continue
    try:
      ids.append(int(part))
    except ValueError:
      fail(f"Invalid itemid: {part!r}")
  if not ids:
    fail("No itemids given")
  return ids


def select_itemids(db, where: str) -> list:
  """Return the itemids of entries matching a SQL WHERE clause, sorted."""
  rows = db.select(where)
  return sorted(row["itemid"] for row in rows)


def update_one(db, account, itemid, target_itemid=None,
               security="public", dry_run=False):
  """Update a single server entry from its database row, via editevent.

  :param db: a DB instance (open ljdump SQLite database)
  :param account: an authenticated Account instance
  :param itemid: itemid of the database row holding the new content
  :param target_itemid: server-side itemid to edit (default: same as itemid)
  :param security: post security level (public/friends/private)
  :param dry_run: print what would happen instead of editing
  :returns: the server response dict, or None if the entry is not in the
            database (or when dry_run is set)
  """
  target_itemid = target_itemid if target_itemid is not None else itemid

  entries = db.get(itemid)
  if not entries:
    print(f"0 records found for itemid={itemid}")
    return None

  entry = dict(entries[0])
  try:
    post_date = dt.datetime.fromisoformat(entry["eventtime"])
  except (ValueError, TypeError) as e:
    fail(f"Error parsing eventtime '{entry['eventtime']}' for itemid {itemid}: {e}")

  subject = entry["subject"] or ""
  body = entry["event"]
  tags = entry["props_taglist"] or ""

  if dry_run:
    print(f"db itemid   : {itemid}")
    print(f"edit itemid : {target_itemid}")
    print(f"date        : {post_date}")
    print(f"subject     : {subject}")
    print(f"tags        : {tags}")
    print(f"security    : {security}")
    return None

  res = account.edit(
      itemid=target_itemid,
      subject=subject,
      body=body,
      tags=tags,
      security=security,
      post_date=post_date,
  )
  db.execute(f"update entries set updatetime=null where itemid={itemid}")
  return res


def main():
  ap = argparse.ArgumentParser(
    description="Update existing Dreamwidth entries from an ljdump SQLite database"
  )
  ap.add_argument("--server", default=DREAMWIDTH,
                  help=f"Server url (default: {DREAMWIDTH})")
  ap.add_argument("--user", required=True, help="Dreamwidth username")
  ap.add_argument("--password", required=True, help="Dreamwidth password")
  ap.add_argument("--db", required=True,
                  help="Path to ljdump SQLite database, relative to work/")
  ap.add_argument("--itemid", default=None,
                  help="Entry itemid, or a comma-separated list of itemids "
                       "(source of the new content)")
  ap.add_argument("--where", default=None,
                  help="SQL WHERE clause selecting entries to update "
                       "(alternative to --itemid)")
  ap.add_argument("--target-itemid", type=int, default=None,
                  help="Server-side itemid of the entry to edit; only valid "
                       "with a single --itemid (default: same as the itemid)")
  ap.add_argument("--security", default="public",
                  choices=["public", "friends", "private"],
                  help="Post security level (default: public)")
  ap.add_argument("--dry-run", action="store_true",
                  help="Print the entries without updating them")
  args = ap.parse_args()

  if bool(args.itemid) == bool(args.where):
    fail("Specify exactly one of --itemid or --where")
  if args.target_itemid is not None and args.where is not None:
    fail("--target-itemid cannot be combined with --where")

  db = DB(f"work/{args.db}")
  account = Account.from_args(args)

  if args.where is not None:
    itemids = select_itemids(db, args.where)
    if not itemids:
      print(f"0 records match: {args.where}")
      return
    print(f"{len(itemids)} entries match the filter")
  else:
    itemids = parse_itemids(args.itemid)
    if args.target_itemid is not None and len(itemids) > 1:
      fail("--target-itemid can only be used with a single --itemid")

  for i, itemid in enumerate(itemids):
    if i > 0:
      print()
      if not args.dry_run:
        throttle()

    res = update_one(db, account, itemid,
                     target_itemid=args.target_itemid,
                     security=args.security, dry_run=args.dry_run)
    if res is None:
      continue

    print(f"OK (itemid {itemid})")
    for k in ("itemid", "anum", "url"):
      if k in res:
        print(f"  {k}: {res[k]}")
    if not any(k in res for k in ("itemid", "anum", "url")):
      print(f"  {res}")


if __name__ == "__main__":
  main()
