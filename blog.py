#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared library for posting entries to Dreamwidth via XML-RPC.
"""

import datetime as dt
import xmlrpc.client
import urllib.parse
from utils import *

DW_XMLRPC = "https://www.dreamwidth.org/interface/xmlrpc"

class Blog:
  def __init__(self, url: str, user: str, password: str):
    self.url = url
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
      fail(f"Error posting: {e}\n{message}")

  def startSession(self):
    """Log in with password and get session cookie."""
    d = dict(mode = "sessiongenerate",
             user = self.user,
             password = self.password,
             auth_method = "clear"
    )
    data = urllib.parse.urlencode(d).encode("utf-8")
    r = urllib.request.urlopen(self.url+"/interface/flat", data=data)
    response = {}
    while True:
      name = r.readline()
      if len(name) == 0:
        break
      value = r.readline()
      response[name.decode('utf-8').strip()] = value.decode('utf-8').strip()
    r.close()
    return response['ljsession']

