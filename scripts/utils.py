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
# Copyright (c) 2005-2026 Greg Hewgill, Vlad Patryshev and contributors

import sys
from datetime import *
import time
import xmlrpc.client
from xml.sax import saxutils

MimeExtensions = {
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

def fail(message):
  """Fail with a message."""
  print(f"\n❌ {message}", file=sys.stderr)
  exit(1)

def throttle():
  time.sleep(6)

def object_to_xml_string(accumulator, name, e):
    accumulator += ("<%s>\n" % name)
    for k in e.keys():
        if isinstance(e[k], {}.__class__):
            accumulator += object_to_xml_string("", k, e[k])
        else:
            try:
                s = str(e[k])
            except UnicodeDecodeError:
                # fall back to Latin-1 for old entries that aren't UTF-8
                s = e[k].decode('cp1252')
            accumulator += ("<%s>%s</%s>\n" % (k, saxutils.escape(s), k))
    accumulator += ("</%s>\n" % name)
    return accumulator


def possible_unicode_or_none(u):
    if u is None:
        return None
    if isinstance(u, xmlrpc.client.Binary):
        s = u.data.decode('utf-8')
    else:
        try:
            s = str(u)
        except UnicodeDecodeError:
            # fall back to Latin-1 for old entries that aren't UTF-8
            s = u.decode('cp1252')
    return s


# Subclass of tzinfo swiped mostly from dateutil
class fancytzoffset(tzinfo):
    def __init__(self, name, offset):
        self._name = name
        self._offset = timedelta(seconds=offset)
    def utcoffset(self, dt):
        return self._offset
    def dst(self, dt):
        return timedelta(0)
    def tzname(self, dt):
        return self._name
    def __eq__(self, other):
        return (isinstance(other, fancytzoffset) and self._offset == other._offset)
    def __ne__(self, other):
        return not self.__eq__(other)
    def __repr__(self):
        return "%s(%s, %s)" % (self.__class__.__name__,
                               repr(self._name),
                               self._offset.days*86400+self._offset.seconds)
    __reduce__ = object.__reduce__


# Variant tzinfo subclass for UTC
class fancytzutc(tzinfo):
    def utcoffset(self, dt):
        return timedelta(0)
    def dst(self, dt):
        return timedelta(0)
    def tzname(self, dt):
        return "UTC"
    def __eq__(self, other):
        return (isinstance(other, fancytzutc) or
                (isinstance(other, fancytzoffset) and other._offset == timedelta(0)))
    def __ne__(self, other):
        return not self.__eq__(other)
    def __repr__(self):
        return "%s()" % self.__class__.__name__
    __reduce__ = object.__reduce__

