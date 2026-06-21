#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare a stored entry against its live version on Dreamwidth.

Given an ljdump SQLite database and an entry itemid, this fetches the same
entry from the server and reports whether the content (subject, tags, body)
matches what is stored locally. If they differ, it prints a readable diff.

The database is read from under the "work/" directory, so --db is given
relative to work/ (e.g. --db juan_gandhi/journal.db reads
work/juan_gandhi/journal.db).

Usage:
  python compare_from_db.py --user USERNAME --password PASSWORD \
               --db juan_gandhi/journal.db --itemid 4066 \
               [--server https://www.dreamwidth.org] [--journal community]

Exit status: 0 if identical, 1 if they differ, 2 if the entry is missing on
either side (or on error).
"""

import difflib
from db import *
from account import *

# Fields that make up the editable "content" of an entry, as (label, db key,
# online accessor). The online value is read from the raw getevents dict.
_FIELDS = (
    ("subject", lambda db_entry: db_entry.get("subject"),
                lambda ev: ev.get("subject")),
    ("tags",    lambda db_entry: db_entry.get("props_taglist"),
                lambda ev: (ev.get("props") or {}).get("taglist")),
    ("event",   lambda db_entry: db_entry.get("event"),
                lambda ev: ev.get("event")),
)


def _norm(value) -> str:
  """Normalize a field for comparison: decode XML-RPC Binary the same way the
  database does, treat None as empty, and unify line endings so that CRLF/CR
  vs LF differences don't show up as spurious changes."""
  s = possible_unicode_or_none(value)
  if s is None:
    return ""
  return s.replace("\r\n", "\n").replace("\r", "\n")


def _document(values) -> list:
  """A canonical, line-oriented representation of an entry's content, so the
  whole thing can be rendered as a single unified diff (like `diff`)."""
  return [f"Subject: {values['subject']}",
          f"Tags: {values['tags']}",
          ""] + values["event"].split("\n")


def render_diff(itemid, db_values, online_values, differences) -> str:
  """Render a succinct, diff-style report comparing the two sides."""
  if not differences:
    return f"Entry {itemid}: database and online versions are identical."

  fields = ", ".join(d["field"] for d in differences)
  diff = difflib.unified_diff(
      _document(db_values), _document(online_values),
      fromfile=f"database:{itemid}", tofile=f"online:{itemid}", lineterm="")
  return "\n".join([f"database:{itemid} vs online:{itemid} — differs in {fields}",
                    *diff])


def compare_entry(db, account, itemid, journal=None) -> dict:
  """Compare the database copy of an entry with its live online version.

  :param db: a DB instance (open ljdump SQLite database)
  :param account: an authenticated Account instance
  :param itemid: entry itemid (the same id is used in the DB and on the server)
  :param journal: optional community/journal short name (usejournal)
  :returns: a dict with keys:
      itemid       - the itemid compared
      in_db        - bool, whether the entry exists locally
      online       - bool, whether the entry exists on the server
      identical    - bool when both sides exist (None otherwise)
      differences  - list of {field, db, online} for each differing field
      report       - human-readable summary / diff (str)
  """
  db_rows = db.get(itemid)
  db_entry = dict(db_rows[0]) if db_rows else None
  online_ev = account.get(itemid, journal)

  result = {
      "itemid": itemid,
      "in_db": db_entry is not None,
      "online": online_ev is not None,
      "identical": None,
      "differences": [],
      "report": "",
  }

  if not db_entry and not online_ev:
    result["report"] = f"Entry {itemid} not found in the database or online."
    return result
  if not db_entry:
    result["report"] = f"Entry {itemid} exists online but not in the database."
    return result
  if not online_ev:
    result["report"] = f"Entry {itemid} exists in the database but not online."
    return result

  db_values = {}
  online_values = {}
  for label, db_get, online_get in _FIELDS:
    db_values[label] = _norm(db_get(db_entry))
    online_values[label] = _norm(online_get(online_ev))
    if db_values[label] != online_values[label]:
      result["differences"].append(
          {"field": label, "db": db_values[label], "online": online_values[label]})

  result["identical"] = not result["differences"]
  result["report"] = render_diff(itemid, db_values, online_values,
                                  result["differences"])
  return result


def main():
  ap = argparse.ArgumentParser(
      description="Compare a database entry against its live version on Dreamwidth"
  )
  ap.add_argument("--server", default=DREAMWIDTH,
                  help=f"Server url (default: {DREAMWIDTH}")
  ap.add_argument("--user", required=True, help="Dreamwidth username")
  ap.add_argument("--password", required=True, help="Dreamwidth password")
  ap.add_argument("--db", required=True,
                  help="Path to ljdump SQLite database, relative to work/")
  ap.add_argument("--itemid", required=True, type=int,
                  help="Entry itemid (same id in the database and on the server)")
  ap.add_argument("--journal", default=None,
                  help="Optional community/journal short name (usejournal)")
  args = ap.parse_args()

  db = DB(f"work/{args.db}")
  account = Account.from_args(args)

  result = compare_entry(db, account, args.itemid, args.journal)
  print(result["report"])

  if not result["in_db"] or not result["online"]:
    sys.exit(2)
  sys.exit(0 if result["identical"] else 1)


if __name__ == "__main__":
  main()
