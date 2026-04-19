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
  def __init__(self, path: str, verbose=False):
    self.verbose = verbose
    self.log(f"Opening local database: {path}")

    if not os.path.isfile(path):
      fail(f"Could not find the database file {Path(path).absolute()}")

    try:
      self.__connection = sqlite3.connect(path)
      self.__connection.row_factory = sqlite3.Row
    except Error as e:
      fail(f"Failed to connect to db: {e}")

  def cursor(self):
    return self.__connection.cursor()

  def execute(self, sql: str):
    self.cursor().execute(sql)

  def select(self, where: str) -> list:
    #    check_sql(where)
    sql = f"SELECT itemid, subject, event, eventtime, props_taglist FROM entries WHERE {where}"
    print(sql)
    try:
      rows = self.execute(sql).fetchall()
    finally:
      self.__connection.close()

    return [dict(r) for r in rows]

  def get(self, itemid: int) -> list:
    return self.select(f"itemid = {itemid}")

  # Check if entries table exists
  def exists(self):
    cur = self.cursor()

    cur.execute(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='entries'")
    return cur.fetchone()

  def log(self, message):
    if self.verbose:
      print(message)

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
    """
    if cursor != None:
      cursor.close()
    self.__connection.commit()
    self.__connection.close()
