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
               [--server https://www.dreamwidth.org] [--journal community] \
               [--color auto|always|never]

When they differ, the differing characters are highlighted in color (database
in blue, online in red) when writing to a terminal.

Exit status: 0 if identical, 1 if they differ, 2 if the entry is missing on
either side (or on error).
"""

import argparse
import difflib
import sys

from utils import *
from db import *
from ljdb import LJDB
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


# ANSI styling. The database side is blue, the online side is red.
_RESET = "\033[0m"
_BOLD = "\033[1m"
_BLUE = "\033[34m"   # database
_RED = "\033[31m"    # online
_CYAN = "\033[36m"   # hunk headers


def _paint(text, code) -> str:
  return f"{code}{text}{_RESET}" if text else text


def _highlight_pair(a: str, b: str):
  """Given a database line and an online line, return them with the characters
  unique to each side wrapped in that side's color (db blue, online red).
  Characters shared by both lines are left uncolored, so only the differing
  characters stand out."""
  matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
  a_parts, b_parts = [], []
  for tag, i1, i2, j1, j2 in matcher.get_opcodes():
    if tag == "equal":
      a_parts.append(a[i1:i2])
      b_parts.append(b[j1:j2])
    else:
      a_parts.append(_paint(a[i1:i2], _BLUE))
      b_parts.append(_paint(b[j1:j2], _RED))
  return "".join(a_parts), "".join(b_parts)


def _colorize(diff_lines: list) -> list:
  """Colorize a unified diff. Within each changed region, database (`-`) and
  online (`+`) lines are paired up and only their differing characters are
  highlighted; unpaired add/remove lines are colored whole."""
  out = []
  minus, plus = [], []

  def flush():
    paired = min(len(minus), len(plus))
    for i in range(paired):
      a_h, b_h = _highlight_pair(minus[i], plus[i])
      out.append(_paint("-", _BLUE) + a_h)
      out.append(_paint("+", _RED) + b_h)
    for line in minus[paired:]:
      out.append(_paint("-" + line, _BLUE))
    for line in plus[paired:]:
      out.append(_paint("+" + line, _RED))
    minus.clear()
    plus.clear()

  for idx, line in enumerate(diff_lines):
    if idx == 0 and line.startswith("---"):   # fromfile header
      out.append(_paint(line, _BOLD + _BLUE))
    elif idx == 1 and line.startswith("+++"):  # tofile header
      out.append(_paint(line, _BOLD + _RED))
    elif line.startswith("@@"):
      flush()
      out.append(_paint(line, _CYAN))
    elif line.startswith("-"):
      minus.append(line[1:])
    elif line.startswith("+"):
      plus.append(line[1:])
    else:  # context or blank line
      flush()
      out.append(line)
  flush()
  return out


def render_diff(itemid, db_values, online_values, differences, color=False) -> str:
  """Render a succinct, diff-style report comparing the two sides. When `color`
  is true, the characters that differ within each line are highlighted
  (database in blue, online in red)."""
  if not differences:
    return f"Entry {itemid}: database and online versions are identical."

  fields = ", ".join(d["field"] for d in differences)
  diff = list(difflib.unified_diff(
      _document(db_values), _document(online_values),
      fromfile=f"database:{itemid}", tofile=f"online:{itemid}", lineterm=""))
  header = f"database:{itemid} vs online:{itemid} — differs in {fields}"
  body = _colorize(diff) if color else diff
  return "\n".join([header, *body])


def compare_entry(db, account, itemid, journal=None, color=False) -> dict:
  """Compare the database copy of an entry with its live online version.

  :param db: a DB instance (open ljdump SQLite database)
  :param account: an authenticated Account instance
  :param itemid: entry itemid (the same id is used in the DB and on the server)
  :param journal: optional community/journal short name (usejournal)
  :param color: highlight differing characters with ANSI color in the report
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
                                  result["differences"], color=color)
  return result


def main():
  ap = argparse.ArgumentParser(
      description="Compare a database entry against its live version on Dreamwidth"
  )
  ap.add_argument("--server", default=DREAMWIDTH,
                  help=f"Server url (default: {DREAMWIDTH}")
  ap.add_argument("--user", required=True, help="Dreamwidth username")
  ap.add_argument("--password", required=True, help="Dreamwidth password")
  ap.add_argument("--verbose", default=False, help="Talk a lot about the process")
  ap.add_argument("--db", required=True,
                  help="ljdump SQLite database name, could be the same as username")
  ap.add_argument("--itemid", required=True, type=int,
                  help="Entry itemid (same id in the database and on the server)")
  ap.add_argument("--journal", default=None,
                  help="Optional community/journal short name (usejournal)")
  ap.add_argument("--color", choices=["auto", "always", "never"], default="auto",
                  help="Highlight differing characters in color "
                       "(default: auto = on when output is a terminal)")
  args = ap.parse_args()

  use_color = args.color == "always" or (
      args.color == "auto" and sys.stdout.isatty())

  db_path = f"work/{args.db}"
  db = LJDB(db_path, create=True)
  account = Account.from_args(args)

  result = compare_entry(db, account, args.itemid, args.journal, color=use_color)
  print(result["report"])

  if not result["in_db"] or not result["online"]:
    sys.exit(2)
  sys.exit(0 if result["identical"] else 1)


if __name__ == "__main__":
  main()
