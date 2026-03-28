#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import datetime as dt
from pathlib import Path
from utils import *
from blog import *

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

    if not path.is_file():
        fail(f"Could not find the input file {path.absolute()}")

    subject, body = read_post_file(path)
    assert subject, "Please provide subject"
    assert body, "Please provide body"

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

    blog = Blog("https://www.dreamwidth.org", args.user, args.password)

    res = blog.post(
        subject,
        body,
        args.tags,
        args.security,
        post_date,
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
