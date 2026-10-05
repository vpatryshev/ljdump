#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# journal.py - functionality for Journal data
# Vlad Patryshev
# Version 1.8
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
# Copyright (c) 2026 Vlad Patryshev


import os, codecs, pprint, argparse, shutil, xml.dom.minidom
from getpass import getpass
import urllib
import html
import re
import calendar
from datetime import *
from xml.etree import ElementTree as ET
import time
import os
from utils import *
from config import *
from db import *

class Journal:
  def __init__(self, name):
    self.name = name
    self.workdir = f"work/{self.name}"

  def write_text(self, filename, content, timestamp = None):
    if timestamp is None:
      timestamp = time.time()
    path = f"{self.workdir}/{filename}"
    with codecs.open(path, "w", "UTF-8") as f:
      f.write(content)
    os.utime(path, (timestamp, timestamp))

