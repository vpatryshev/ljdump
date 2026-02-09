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
