#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared library for posting entries to Dreamwidth via XML-RPC.
"""

import datetime as dt
import xmlrpc.client
from utils import *
from utils import *

DW_XMLRPC = "https://www.dreamwidth.org/interface/xmlrpc"

class Blog:
  def __init__(self, user: str, password: str):
    self.user = user
    self.password = password
    self.server = xmlrpc.client.ServerProxy(DW_XMLRPC, allow_none=True)

  def post(self, subject: str, body: str,
           tags: str = "", security: str = "public",
           post_date: dt.datetime = None) -> dict:
    """Post an entry to Dreamwidth. Returns the server response dict."""

    assert body, "Empty content is not allowed"
    timestamp = post_date if post_date else dt.datetime.now()
    message = {
        "username": self.user,
        "password": self.password,
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
        message["security"] = "usemask"
        message["allowmask"] = 1
    elif security == "private":
        message["security"] = "private"
    else:
        message["security"] = "public"

    try:
        return self.server.LJ.XMLRPC.postevent(message)
    except Exception as e:
        print(f"Error posting: {e}\n{message}")
        fail("bad...")

