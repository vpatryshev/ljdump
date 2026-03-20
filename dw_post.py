#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared library for posting entries to Dreamwidth via XML-RPC.
"""

import datetime as dt
import xmlrpc.client

DW_XMLRPC = "https://www.dreamwidth.org/interface/xmlrpc"


def post_to_dreamwidth(user: str, password: str, subject: str, body: str,
                       tags: str = "", security: str = "public",
                       post_date: dt.datetime = None) -> dict:
    """Post an entry to Dreamwidth. Returns the server response dict."""
    server = xmlrpc.client.ServerProxy(DW_XMLRPC, allow_none=True)

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
            "opt_backdated": (post_date is not None),
        },
    }

    if security == "friends":
        post["security"] = "usemask"
        post["allowmask"] = 1
    elif security == "private":
        post["security"] = "private"
    else:
        post["security"] = "public"

    return server.LJ.XMLRPC.postevent(post)
