#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# cache.py - caching layer
# Vlad Patryshev
# Version 0.1
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
# Copyright (c) 2026-2024 Vlad Patryshev and contributors

import argparse, codecs, os, pickle, pprint, re, shutil, sys
from pathlib import Path
from datetime import *
from utils import *

DIR="cache"
CACHEPATH = Path(DIR)
TTL=12*3600 # seconds, that is, 12 hours

if not os.path.exists(DIR):
    os.mkdir(DIR)

def path(name):
    return os.path.join(DIR, name)

def clear(name):
    p = path(name)
    if os.path.exists(p):
        os.remove(p)

def clearAll():
    for item in CACHEPATH.iterdir():
        item.unlink()

def isFresh(name):
    p = path(name)
    if os.path.exists(p):
        age_seconds = time.time() - os.path.getmtime(p)
        return age_seconds < TTL
    else:
        return FALSE

def get(name):
    p = path(name)
    if isFresh(name):
        with open(p, 'r', encoding='utf-8') as f:
            content = f.read()
            f.close()
            return content
    else:
        None

def put(name, value):
    p = path(name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(value)
        f.close()

if __name__ == "__main__":
# test the cache
    TTL = 3
    print("TESTING cache.py")
    clearAll()
    clear("non existent file")
    testvalue = "--test contents\nof file 'test1'--"
    put("test1", testvalue)
    fromfile = get("test1")
    assert fromfile == testvalue, f"Oops, bad input: {fromfile}"
    clear("test1")
    assert not os.path.exists("test"), "the file 'test' had to be deleted"

    put("test2", "this file gets expired soon")
    fromfile2a = get("test2")
    assert fromfile2a == "this file gets expired soon", "Oops, bad file test2"
    time.sleep(5)
    fromfile2b = get("test2")
    assert fromfile2b == None, "Oops, test2 still available?!"

    print("DONE TESTING cache.py")


#     args = argparse.ArgumentParser(description="Livejournal archive utility")
#     args.add_argument("--quiet", "-q", action='store_false', dest='verbose',
#                       help="reduce log output")
#     args.add_argument("--no_html", "-n", action='store_false', dest='make_pages',
#                       help="don't process the journal data into HTML files.")
#     args.add_argument('--max', type=int, default=400, dest='max_to_fetch',
#                       help='Maximum number of entries and comments to fetch at a time.  Default is 400.')
#     args.add_argument("--cache_images", "-i", action='store_true', dest='cache_images',
#                       help="build a cache of images referenced in entries")
#     args.add_argument("--dont_retry_images", "-d", action='store_false', dest='retry_images',
#                       help="don't retry images that failed to cache once already")
#     args.add_argument("--user", type=str, default='ljdump', dest='user_name', help="Name of config file dot config")
#     args = args.parse_args()
