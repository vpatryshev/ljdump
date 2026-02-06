#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime as dt
import xmlrpc.client
from pathlib import Path

DW_XMLRPC = "https://www.dreamwidth.org/interface/xmlrpc"


def read_post_file(path: Path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not lines:
        raise ValueError("File is empty")

    subject = lines[0].strip()
    body = "\n".join(lines[1:]).lstrip("\n")

    if not subject:
        raise ValueError("Subject (first line) missing")

    return subject, body


def post_to_dreamwidth(user: str, password: str, subject: str, body: str,
                       tags: str = "", security: str = "public",
                       post_date: dt.datetime = None):
    server = xmlrpc.client.ServerProxy(DW_XMLRPC, allow_none=True)

    # Use provided date or current time
    timestamp = post_date if post_date else dt.datetime.now()

    post = {
        "username": user,
        "password": password,
        "ver": 1,
        "lineendings": "unix",
        "subject": subject,
        "event": body,
        "year": timestamp.year,
        "mon": timestamp.month,
        "day": timestamp.day,
        "hour": timestamp.hour,
        "min": timestamp.minute,
        "props": {
            "taglist": tags,
            "opt_backdated": (post_date is not None)
        },
    }

    # Dreamwidth понимает public / friends / private (как в LJ)
    if security == "friends":
        post["security"] = "usemask"
        post["allowmask"] = 1
    elif security == "private":
        post["security"] = "private"
    else:
        post["security"] = "public"

    # Используем LJ.XMLRPC.postevent
    res = server.LJ.XMLRPC.postevent(post)
    return res  # обычно содержит itemid, url и т.п.


def main():
    ap = argparse.ArgumentParser(
        description="Post a text file to Dreamwidth via XML-RPC"
    )
    ap.add_argument(
        "file",
        help="Path to text file (UTF-8). First line is subject, rest is body."
    )
    ap.add_argument("--user", required=True, help="Dreamwidth username")
    ap.add_argument(
        "--password",
        required=True,
        help="Dreamwidth password"
    )
    ap.add_argument(
        "--tags",
        default="",
        help="Tags, comma-separated or space-separated"
    )
    ap.add_argument(
        "--security",
        default="public",
        choices=["public", "friends", "private"]
    )
    ap.add_argument(
        "--date",
        default=None,
        help="Post date in ISO format (e.g., 2021-11-17T09:19:00+00:00). If not provided, uses current time."
    )
    args = ap.parse_args()

    path = Path(args.file)
    subject, body = read_post_file(path)

    # Parse date if provided
    post_date = None
    if args.date:
        try:
            # Parse ISO format date
            post_date = dt.datetime.fromisoformat(args.date)
        except ValueError as e:
            print(f"Error parsing date '{args.date}': {e}")
            print("Expected format: 2021-11-17T09:19:00+00:00")
            return

    res = post_to_dreamwidth(
        user=args.user,
        password=args.password,
        subject=subject,
        body=body,
        tags=args.tags,
        security=args.security,
        post_date=post_date,
    )

    # Печатаем, что вернул сервер
    print("OK")
    for k in ("itemid", "anum", "url"):
        if k in res:
            print(f"{k}: {res[k]}")
    # На всякий случай покажем весь ответ, если там другое
    if not any(k in res for k in ("itemid", "anum", "url")):
        print(res)


if __name__ == "__main__":
    main()
