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
# Copyright (c) 2026-2038 Vlad Patryshev and contributors

import os, time
from pathlib import Path

DIR="cache"
CACHEPATH = Path(DIR)
TTL=12*3600 # 12 hours

if not os.path.exists(DIR):
    os.mkdir(DIR)


def path(key: str) -> Path:
    return CACHEPATH / key


def clear(key: str):
    p = path(key)
    if p.exists():
        p.unlink()


def clearAll():
    for p in list(CACHEPATH.iterdir()): p.unlink()


def isFresh(key: str) -> bool:
    p = path(key)
    if p.exists():
        return time.time() < p.stat().st_mtime + TTL
    else:
        return False


def get(key: str) -> str:
    if isFresh(key): return path(key).read_text(encoding='utf-8')


def put(key: str, value: str):
    path(key).write_text(value)


def getOrCall(key: str, fun):
    value = get(key)
    if value == None:
        value = fun(key)
        put(key, value)
    return value


if __name__ == "__main__":
# test the cache
    TTL = 1
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
    time.sleep(2)
    fromfile2b = get("test2")
    assert fromfile2b == None, "Oops, test2 still available?!"

    value1 = getOrCall("test3", lambda key: f"<<{key}-1>>")
    assert value1 == "<<test3-1>>", "first call of test3, got {value1}"
    value2 = getOrCall("test3", lambda key: f"<<{key}-1>>")
    assert value2 == "<<test3-1>>", f"second call of test3, got {value2}"
    time.sleep(2)
    value3 = getOrCall("test3", lambda key: f"<<{key}-3>>")
    assert value3 == "<<test3-3>>", "third call of test3, got {value3}"

    put("url/", "somedata")
    fromfile4 = get("url/")
    assert fromfile4 == "somedata", "problem with url/"
    print("DONE TESTING cache.py")
