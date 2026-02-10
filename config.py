#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# config.py - config for lj/dw API
# Vlad Patryshev
# Version 1.0
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
# Copyright (c) 2026-eternity Vlad Patryshev and contributors

import os, codecs, pprint, argparse, shutil, xml.dom.minidom
from getpass import getpass
import urllib
import html
import re
import calendar
from datetime import *
from utils import *
from config import *
import json
import time

class Config:
    def __init__(self, args):
        self.verbose = not hasattr(args, 'quiet')
        if args.cache_images:
            self.unique = getpass("unique cookie (for Dreamwidth hosted image downloads, leave blank otherwise): ")
        self.cache_images=args.cache_images,
        self.retry_images=args.retry_images

class ConfigPlain(Config):

    def __init__(self, server, username, password, journals, unique, args):
        super().__init__(args)
        self.server = server
        self.username = username
        self.password = password
        self.journals = journals
        self.unique = unique

class TUIConfig(Config):
    def __init__(self, name, args):
        super().__init__(args)
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
        password = getpass("Password: ")
        print
        if journal:
            self.journals = [journal]
        else:
            self.journals = [username]
        self.unique = None
        print

class ConfigFromFile(Config):
    def __init__(self, path, args, cache_images = False):
        super().__init__(args)
        if os.path.exists(path):
            config = xml.dom.minidom.parse(path)
            self.server = config.documentElement.getElementsByTagName("server")[0].childNodes[0].data
            self.username = config.documentElement.getElementsByTagName("username")[0].childNodes[0].data
            self.journals = [e.childNodes[0].data for e in config.documentElement.getElementsByTagName("journal")]
            if not self.journals:
                self.journals = [self.username]

            password_els = config.documentElement.getElementsByTagName("password")
            self.password = password_els[0].childNodes[0].data

            # If a user is hosting images on Dreamwidth and using a config file, they will
            # put their cookie in the config file.  Asking for it every time would annoy users
            # who are not hosting images on Dreamwidth.
            self.unique = None
            if self.cache_images:
                unique_els = config.documentElement.getElementsByTagName("unique")
                if len(unique_els) > 0:
                    self.unique = unique_els[0].childNodes[0].data
        else:
            fail("\n".join(
                [f"Could not open {path}",
                "need an xml config file, see as an example ljdump.config.sample"]))

def setup(config_file, args):
  if os.access(config_file, os.F_OK):
      return ConfigFromFile(config_file, args)
  else:
      return TUIConfig("ljdump", args)
