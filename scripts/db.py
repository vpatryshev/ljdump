#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
# Copyright (c) 2024 Garrett Birkel, Vlad Patryshev, et al.

import argparse
import datetime as dt
import os
import sqlite3
import sys
from pathlib import Path
from utils import *


class DB:
  def __init__(self, path: str, verbose=False, create=False):
    self.verbose = verbose
    parent = os.path.dirname(path)

    if not os.path.isfile(path):
      if not create:
        fail(f"Could not find the database file {Path(path).absolute()}")
      # Opening with create=True: make the parent directory and let sqlite
      # create the file. Callers should follow up with create_tables_if_missing.
      if parent:
        os.makedirs(parent, exist_ok=True)

    self.logfile = open(f"{parent}/db.log", "a", encoding="utf-8")
    self.logfile.write(f"========== {path} ===========\n")

    try:
      self.__connection = sqlite3.connect(path)
      self.__connection.row_factory = sqlite3.Row
    except Error as e:
      self.log(f"Failed to connect to database: {e}\n")
      fail(f"Failed to connect to db: {e}")

  def log(self, message):
    self.logfile.write(f"{dt.datetime.now()}: {message}\n")
    self.logfile.flush()

  def cursor(self):
    return self.__connection.cursor()

  def execute(self, sql: str):
    self.log(f" {sql}")
    cur = self.cursor()
    cur.execute(sql)
    cur.connection.commit()
    return cur

  def select(self, where: str) -> list:
    sql = f"SELECT itemid, subject, event, eventtime, props_taglist FROM entries WHERE {where}"
    rows = self.execute(sql).fetchall()
    return [dict(r) for r in rows]

  def get(self, itemid: int) -> list:
    return self.select(f"itemid = {itemid}")

  # Check if entries table exists
  def exists(self):
    cur = self.execute(self,
      "SELECT name FROM sqlite_master WHERE type='table' AND name='entries'")
    return cur.fetchone()

  def clear_update_time(self, itemid: int):
    self.execute(f"update entries set updatetime=null where itemid={itemid}")

  def set_sync_status(self, status):
    """ set values in the current status record
    :param cur: database cursor
    :param status: sync status record
    """
    self.cursor().execute("UPDATE status SET lastsync = ?, lastmaxcommentid = ?",
                          (status['last_sync'], status['last_max_comment_id']))

  def close(self, cursor = None):
    """ commit and close the cursor and database
    :param cursor: database cursor
`    """
    if cursor != None:
      cursor.close()
    self.__connection.commit()
    self.__connection.close()
    cursor = None
