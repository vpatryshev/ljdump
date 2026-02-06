#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# utils.py - utilities for lj/dw API
# Greg Hewgill, Garrett Birkel, et al
# Version 2.0
#
# LICENSE
#
# This software is provided 'as-is', without any express or implied
# warranty.  In no event will the author be held liable for any damages
# arising from the use of this software.
#
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely, subject to the following restrictions:
#
# 1. The origin of this software must not be misrepresented; you must not
#    claim that you wrote the original software. If you use this software
#    in a product, an acknowledgment in the product documentation would be
#    appreciated but is not required.
# 2. Altered source versions must be plainly marked as such, and must not be
#    misrepresented as being the original software.
# 3. This notice may not be removed or altered from any source distribution.
#
# Copyright (c) 2005-2026 Greg Hewgill and contributors

import os, codecs, pprint, argparse, shutil, xml.dom.minidom
from getpass import getpass
import urllib
import html
import re
import calendar
from datetime import *
import json
import time

MimeExtensions = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

def fail(message):
    """Fail with a message."""
    print(message)
    exit(1)

class Config:

    def __init__(self, server, username, password, unique, args):
        default_server = "https://livejournal.com"
        self.server = raw_input("Alternative server to use (e.g. 'https://www.dreamwidth.org'), or hit return for '%s': " % default_server) or default_server

        self.server = server
        self.username = username
        self.password = password
        self.unique = unique,
        self.verbose = not args.quiet
        self.cache_images=args.cache_images,
        self.retry_images=args.retry_images

class TUIConfig:
    def __init__(self, name, args):
        print("{name} - livejournal (or Dreamwidth, etc) archive to html utility")
        print
        default_server = "https://livejournal.com"
        self.server = raw_input("Alternative server to use (e.g. 'https://www.dreamwidth.org'), or hit return for '%s': " % default_server) or default_server
        print
        print("Enter your Livejournal (or Dreamwidth, etc) username.")
        print
        self.username = raw_input("Username: ")
        print
        journal = raw_input("Journal to render (or hit return to render '%s'): " % username)
        self.password = getpass("Password: ")
        print
        if journal:
            self.journals = [journal]
        else:
            self.journals = [username]
        self.ljuniq = None
        if args.cache_images:
            self.ljuniq = getpass("ljuniq cookie (for Dreamwidth hosted image downloads, leave blank otherwise): ")
        print
        self.verbose = not args.quiet
        self.cache_images=args.cache_images,
        self.retry_images=args.retry_images

class ConfigFromFile:
    def __init__(self, path, args, cache_images = False):
        """Load configuration from XML file."""
        if os.path.exists(path):
            config = xml.dom.minidom.parse(path)
            self.server = config.documentElement.getElementsByTagName("server")[0].childNodes[0].data
            self.username = config.documentElement.getElementsByTagName("username")[0].childNodes[0].data
            self.journals = [e.childNodes[0].data for e in config.documentElement.getElementsByTagName("journal")]
            if not self.journals:
                self.journals = [self.username]

            password_els = config.documentElement.getElementsByTagName("password")
            self.password = password_els[0].childNodes[0].data

            self.ljuniq = None
            # If a user is hosting images on Dreamwidth and using a config file, they will
            # put their cookie in the config file.  Asking for it every time would annoy users
            # who are not hosting images on Dreamwidth.
            if cache_images:
                ljuniq_els = config.documentElement.getElementsByTagName("ljuniq")
                if len(ljuniq_els) > 0:
                    self.ljuniq = ljuniq_els[0].childNodes[0].data
            self.verbose = not hasattr(args, 'quiet')
            self.cache_images=args.cache_images,
            self.retry_images=args.retry_images
        else:
            fail("\n".join(
                [f"Could not open {path}",
                "need an xml config file, see as an example ljdump.config.sample"]))


def startSession(journal_server, username, password):
    """Log in with password and get session cookie."""
    d = dict(   mode="sessiongenerate",
                user=username,
                auth_method="clear",
                password=password
    )
    data = urllib.parse.urlencode(d).encode("utf-8")
    r = urllib.request.urlopen(journal_server+"/interface/flat", data=data)
    response = {}
    while True:
        name = r.readline()
        if len(name) == 0:
            break
        value = r.readline()
        response[name.decode('utf-8').strip()] = value.decode('utf-8').strip()
    r.close()
    return response['ljsession']
