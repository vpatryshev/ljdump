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

import xml.dom.minidom
import os
from account import Account
from utils import *
from config import *

class Config:
  def __init__(self, workdir, args):
    self.verbose = not hasattr(args, 'quiet')
    self.workdir = workdir
    if args.cache_images:
      self.unique = getpass("unique cookie (for Dreamwidth hosted image downloads, leave blank otherwise): ")
    self.cache_images=args.cache_images
    self.retry_images=args.retry_images

class ConfigPlain(Config):

  def __init__(self, workdir, journals, unique, args):
    super().__init__(workdir, args)
    self.account = Account.from_args(args)
    self.journals = journals
    self.unique = unique

class TUIConfig(Config):
  def __init__(self, name, args):
    super().__init__(".", args)
    print(f"{name} - livejournal (or Dreamwidth, etc) archive to html utility")
    print
    default_server = LIVEJOURNAL
    self.server = input(
      f"Alternative server to use (e.g. '{DREAMWIDTH}'), or hit return for '{default_server}': ") or default_server
    print
    print("Enter your Livejournal (or Dreamwidth, etc) username.")
    print
    username = raw_input("Username: ")
    print
    journal = raw_input("Journal to render (or hit return to render '%s'): " % username)
    password = getpass("Password: ")
    self.account = Account(server, username, password)
    print
    if journal:
      self.journals = [journal]
    else:
      self.journals = [username]
    self.unique = None
    print

class ConfigFromFile(Config):
  def __init__(self, workdir, path, args):
    super().__init__(workdir, args)
    configpath = f"{workdir}/{path}"
    if os.path.exists(configpath):
      config = xml.dom.minidom.parse(configpath)
      server = config.documentElement.getElementsByTagName("server")[0].childNodes[0].data
      username = config.documentElement.getElementsByTagName("username")[0].childNodes[0].data
      self.journals = [e.childNodes[0].data for e in config.documentElement.getElementsByTagName("journal")]
      if not self.journals:
        self.journals = [username]

      password_els = config.documentElement.getElementsByTagName("password")
      password = password_els[0].childNodes[0].data
      self.account = Account(server, username, password)

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
        [f"Oops, Could not open {configpath}",
        "need an xml config file, see as an example ljdump.config.sample"]))

def setup(config_file, args):
  if os.access(config_file, os.F_OK):
    return ConfigFromFile(".", config_file, args)
  elif os.access(f"work/{config_file}", os.F_OK):
    return ConfigFromFile("work", config_file, args)
  else:
    return TUIConfig("ljdump", args)
