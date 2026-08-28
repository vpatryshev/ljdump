#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for LJDB class in ljdb.py
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ljdb import LJDB, TABLES, INDEXES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_db_path():
    """Return the path to a freshly created empty SQLite file."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


def _make_ljdb(verbose=False):
    """Create a temp LJDB with all tables initialised. Returns (db, path)."""
    path = _empty_db_path()
    db = LJDB(path, verbose=verbose)
    db.create_tables_if_missing()
    return db, path


def _raw_fetch(path, sql, params=()):
    """Run a query on the DB file via a fresh connection and return all rows."""
    conn = sqlite3.connect(path)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


# Minimal valid event dict as the server would return it
def _make_event(itemid=1, subject="Hello", event="Body text",
                eventtime="2024-03-15 10:00:00", logtime="2024-03-15 10:01:00",
                taglist="music, life", url="https://example.com/1"):
    return {
        "itemid": itemid,
        "anum": itemid * 256,
        "eventtime": eventtime,
        "logtime": logtime,
        "subject": subject,
        "event": event,
        "url": url,
        "props": {
            "taglist": taglist,
            "current_music": "Song",
            "commentalter": None,
            "current_moodid": None,
            "import_source": None,
            "interface": "web",
            "opt_backdated": None,
            "picture_keyword": None,
            "picture_mapid": None,
        },
    }


def _make_comment(id=1, entryid=1, date="2024-03-15T11:00:00Z",
                  user="reader", subject="Re: Hello", body="Nice post",
                  parentid="0", posterid="42", state="S"):
    return {
        "id": id,
        "entryid": entryid,
        "date": date,
        "parentid": parentid,
        "posterid": posterid,
        "user": user,
        "subject": subject,
        "body": body,
        "state": state,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateTablesIfMissing(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def _table_names(self):
        rows = _raw_fetch(self.path, "SELECT name FROM sqlite_master WHERE type='table'")
        return {r[0] for r in rows}

    def _index_names(self):
        rows = _raw_fetch(self.path, "SELECT name FROM sqlite_master WHERE type='index'")
        return {r[0] for r in rows}

    def test_all_tables_created(self):
        expected = {"status", "user", "entries", "comments", "moods",
                    "tags", "icons", "users_map", "cached_images"}
        self.assertTrue(expected.issubset(self._table_names()))

    def test_all_indexes_created(self):
        expected = {"entries_eventtime_unix", "entries_logtime_unix",
                    "comments_date_unix", "comments_entryid"}
        self.assertTrue(expected.issubset(self._index_names()))

    def test_idempotent(self):
        # Calling again must not raise
        self.db.create_tables_if_missing()
        self._table_names()  # would raise if DB is broken


class TestGetSyncStatusOrDefaults(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def test_returns_defaults_when_table_empty(self):
        status = self.db.get_sync_status_or_defaults("2024-01-01", 0)
        self.assertEqual(status["last_sync"], "2024-01-01")
        self.assertEqual(status["last_max_comment_id"], 0)

    def test_inserts_row_when_table_empty(self):
        self.db.get_sync_status_or_defaults("2024-01-01", 0)
        cur = self.db.cursor()
        cur.execute("SELECT lastsync, lastmaxcommentid FROM status")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "2024-01-01")

    def test_returns_existing_values_when_row_present(self):
        conn = sqlite3.connect(self.path)
        conn.execute("INSERT INTO status VALUES ('2023-06-01', 99)")
        conn.commit()
        conn.close()

        status = self.db.get_sync_status_or_defaults("ignored", -1)
        self.assertEqual(status["last_sync"], "2023-06-01")
        self.assertEqual(status["last_max_comment_id"], 99)

    def test_returns_latest_when_multiple_rows_present(self):
        # Regression: a broken read used to leave stray empty status rows and
        # always report an empty sync point (causing a full re-sync every run).
        # get() must return the row with the real (latest) sync point.
        conn = sqlite3.connect(self.path)
        conn.execute("INSERT INTO status VALUES ('2025-05-05 10:00:00', 500)")
        conn.execute("INSERT INTO status VALUES ('', 0)")
        conn.execute("INSERT INTO status VALUES ('', 0)")
        conn.commit()
        conn.close()
        status = self.db.get_sync_status_or_defaults("ignored", -1)
        self.assertEqual(status["last_sync"], "2025-05-05 10:00:00")
        self.assertEqual(status["last_max_comment_id"], 500)


class TestSetSyncStatus(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def test_set_then_get_roundtrip(self):
        # The core of the sync bug: after storing a sync point, reading it back
        # must return that value (not defaults), so the next run is incremental.
        self.db.set_sync_status({"last_sync": "2025-07-01 00:00:00",
                                 "last_max_comment_id": 42})
        status = self.db.get_sync_status_or_defaults("x", -1)
        self.assertEqual(status["last_sync"], "2025-07-01 00:00:00")
        self.assertEqual(status["last_max_comment_id"], 42)

    def test_collapses_to_single_row(self):
        conn = sqlite3.connect(self.path)
        conn.execute("INSERT INTO status VALUES ('', 0)")
        conn.execute("INSERT INTO status VALUES ('', 0)")
        conn.commit()
        conn.close()
        self.db.set_sync_status({"last_sync": "2025-07-01 00:00:00",
                                 "last_max_comment_id": 42})
        cur = self.db.cursor()
        cur.execute("SELECT lastsync, lastmaxcommentid FROM status")
        rows = cur.fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0][0], rows[0][1]), ("2025-07-01 00:00:00", 42))


class TestUserInfo(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def test_get_user_info_returns_none_when_empty(self):
        self.assertIsNone(self.db.get_user_info())

    def test_insert_user_info(self):
        data = {"journal_short_name": "testuser", "defaultpicurl": "http://pic",
                "fullname": "Test User", "userid": 123}
        self.db.insert_or_update_user_info(data)
        result = self.db.get_user_info()
        self.assertEqual(result["journal_short_name"], "testuser")
        self.assertEqual(result["userid"], 123)

    def test_update_user_info(self):
        data = {"journal_short_name": "testuser", "defaultpicurl": "http://pic",
                "fullname": "Test User", "userid": 123}
        self.db.insert_or_update_user_info(data)
        data["fullname"] = "Updated Name"
        self.db.insert_or_update_user_info(data)
        result = self.db.get_user_info()
        self.assertEqual(result["fullname"], "Updated Name")
        cur = self.db.cursor()
        cur.execute("SELECT COUNT(*) FROM user")
        self.assertEqual(cur.fetchone()[0], 1)


class TestEvents(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def test_get_all_events_empty(self):
        self.assertEqual(self.db.get_all_events(), [])

    def test_insert_event_and_retrieve(self):
        ev = _make_event(itemid=1, subject="First")
        self.db.insert_or_update_event(ev)
        events = self.db.get_all_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["subject"], "First")
        self.assertEqual(events[0]["itemid"], 1)

    def test_insert_multiple_events_ordered_by_itemid(self):
        self.db.insert_or_update_event(_make_event(itemid=3, subject="Third",
            eventtime="2024-05-01 00:00:00", logtime="2024-05-01 00:00:00"))
        self.db.insert_or_update_event(_make_event(itemid=1, subject="First",
            eventtime="2024-03-01 00:00:00", logtime="2024-03-01 00:00:00"))
        self.db.insert_or_update_event(_make_event(itemid=2, subject="Second",
            eventtime="2024-04-01 00:00:00", logtime="2024-04-01 00:00:00"))
        events = self.db.get_all_events()
        self.assertEqual([e["itemid"] for e in events], [1, 2, 3])

    def test_update_event(self):
        ev = _make_event(itemid=1, subject="Original")
        self.db.insert_or_update_event(ev)
        ev["subject"] = "Updated"
        self.db.insert_or_update_event(ev)
        events = self.db.get_all_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["subject"], "Updated")

    def test_event_taglist_stored(self):
        ev = _make_event(itemid=1, taglist="music, travel")
        self.db.insert_or_update_event(ev)
        events = self.db.get_all_events()
        self.assertEqual(events[0]["props_taglist"], "music, travel")

    def test_event_no_subject_defaults_to_no_subject(self):
        ev = _make_event(itemid=1)
        del ev["subject"]
        self.db.insert_or_update_event(ev)
        events = self.db.get_all_events()
        self.assertEqual(events[0]["subject"], "(no subject)")

    def test_eventtime_unix_is_numeric(self):
        ev = _make_event(itemid=1, eventtime="2024-06-15 12:00:00",
                         logtime="2024-06-15 12:00:00")
        self.db.insert_or_update_event(ev)
        events = self.db.get_all_events()
        self.assertIsInstance(events[0]["eventtime_unix"], float)


class TestComments(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()
        # Insert a parent entry so FK-like checks don't block us
        self.db.insert_or_update_event(_make_event(itemid=1))

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def test_get_all_comments_empty(self):
        self.assertEqual(self.db.get_all_comments(), [])

    def test_insert_comment_and_retrieve(self):
        c = _make_comment(id=1, entryid=1, user="alice")
        self.db.insert_or_update_comment(c)
        comments = self.db.get_all_comments()
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["user"], "alice")

    def test_insert_returns_true_for_new(self):
        c = _make_comment(id=1, entryid=1)
        self.assertTrue(self.db.insert_or_update_comment(c))

    def test_update_returns_false_for_existing(self):
        self.db.insert_or_update_comment(_make_comment(id=1, entryid=1))
        c2 = _make_comment(id=1, entryid=1, body="Edited body")
        self.assertFalse(self.db.insert_or_update_comment(c2))

    def test_update_comment_body(self):
        self.db.insert_or_update_comment(_make_comment(id=1, entryid=1, body="Original"))
        self.db.insert_or_update_comment(_make_comment(id=1, entryid=1, body="Revised"))
        comments = self.db.get_all_comments()
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["body"], "Revised")

    def test_comment_with_empty_date(self):
        c = _make_comment(id=2, entryid=1, date="")
        self.db.insert_or_update_comment(c)
        comments = self.db.get_all_comments()
        self.assertIsNone(comments[0]["date"])
        self.assertIsNone(comments[0]["date_unix"])

    def test_comment_date_unix_is_numeric(self):
        c = _make_comment(id=3, entryid=1, date="2024-03-15T11:00:00Z")
        self.db.insert_or_update_comment(c)
        comments = self.db.get_all_comments()
        self.assertIsInstance(comments[0]["date_unix"], float)


class TestMoods(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def test_get_all_moods_empty(self):
        self.assertEqual(self.db.get_all_moods(), [])

    def test_insert_mood_and_retrieve(self):
        self.db.insert_or_update_mood({"id": 1, "name": "happy", "parent": 0})
        moods = self.db.get_all_moods()
        self.assertEqual(len(moods), 1)
        self.assertEqual(moods[0]["name"], "happy")

    def test_update_mood(self):
        self.db.insert_or_update_mood({"id": 1, "name": "happy", "parent": 0})
        self.db.insert_or_update_mood({"id": 1, "name": "ecstatic", "parent": 0})
        moods = self.db.get_all_moods()
        self.assertEqual(len(moods), 1)
        self.assertEqual(moods[0]["name"], "ecstatic")


class TestTags(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def _tag(self, name="music", uses=5):
        return {"name": name, "display": 1,
                "security_private": 0, "security_protected": 0,
                "security_public": 1, "security_level": "public",
                "uses": uses}

    def test_get_all_tags_empty(self):
        self.assertEqual(self.db.get_all_tags(), [])

    def test_insert_tag_and_retrieve(self):
        self.db.insert_or_update_tag(self._tag("music"))
        tags = self.db.get_all_tags()
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["name"], "music")

    def test_update_tag_uses(self):
        self.db.insert_or_update_tag(self._tag("music", uses=5))
        self.db.insert_or_update_tag(self._tag("music", uses=10))
        tags = self.db.get_all_tags()
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["uses"], 10)


class TestIcons(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def _icon(self, keywords="default", filename="default.png", url="http://u"):
        return {"keywords": keywords, "filename": filename, "url": url}

    def test_get_all_icons_empty(self):
        self.assertEqual(self.db.get_all_icons(), [])

    def test_insert_icon_and_retrieve(self):
        self.db.insert_or_update_icon(self._icon("default"))
        icons = self.db.get_all_icons()
        self.assertEqual(len(icons), 1)
        self.assertEqual(icons[0]["keywords"], "default")

    def test_update_icon_filename(self):
        self.db.insert_or_update_icon(self._icon("default", filename="old.png"))
        self.db.insert_or_update_icon(self._icon("default", filename="new.png"))
        icons = self.db.get_all_icons()
        self.assertEqual(len(icons), 1)
        self.assertEqual(icons[0]["filename"], "new.png")


class TestUsersMap(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def test_get_users_map_empty(self):
        self.assertEqual(self.db.get_users_map(), {})

    def test_insert_and_retrieve(self):
        self.db.insert_or_update_user_in_map(42, "alice")
        result = self.db.get_users_map()
        self.assertEqual(result[42], "alice")

    def test_update_username(self):
        self.db.insert_or_update_user_in_map(42, "alice")
        self.db.insert_or_update_user_in_map(42, "alice2")
        result = self.db.get_users_map()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[42], "alice2")

    def test_multiple_users(self):
        self.db.insert_or_update_user_in_map(1, "alice")
        self.db.insert_or_update_user_in_map(2, "bob")
        result = self.db.get_users_map()
        self.assertEqual(len(result), 2)


class TestCachedImages(unittest.TestCase):
    def setUp(self):
        self.db, self.path = _make_ljdb()
        self.url = "https://example.com/image.png"
        self.entry_date = datetime(2024, 3, 15, tzinfo=timezone.utc)

    def tearDown(self):
        self.db.close(None)
        os.unlink(self.path)

    def test_get_or_create_returns_new_record(self):
        rec = self.db.get_or_create_cached_image_record(self.url)
        self.assertEqual(rec["url"], self.url)
        self.assertEqual(rec["cached"], 0)
        self.assertIsNone(rec["filename"])
        self.assertIsNotNone(rec["id"])

    def test_get_or_create_returns_existing_record(self):
        rec1 = self.db.get_or_create_cached_image_record(self.url)
        rec2 = self.db.get_or_create_cached_image_record(self.url)
        self.assertEqual(rec1["id"], rec2["id"])

    def test_get_or_create_stores_date_first_seen(self):
        rec = self.db.get_or_create_cached_image_record(self.url, self.entry_date)
        self.assertIsNotNone(rec["date_first_seen"])

    def test_report_image_as_cached(self):
        rec = self.db.get_or_create_cached_image_record(self.url, self.entry_date)
        self.db.report_image_as_cached(rec["id"], "local_image.png", self.entry_date)
        cur = self.db.cursor()
        cur.execute("SELECT cached, filename FROM cached_images WHERE id = ?", (rec["id"],))
        row = cur.fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], "local_image.png")

    def test_report_image_as_attempted_sets_timestamp(self):
        rec = self.db.get_or_create_cached_image_record(self.url)
        self.db.report_image_as_attempted(rec["id"])
        cur = self.db.cursor()
        cur.execute("SELECT date_last_attempted FROM cached_images WHERE id = ?", (rec["id"],))
        self.assertIsNotNone(cur.fetchone()[0])

    def test_get_all_successfully_cached_empty(self):
        self.db.get_or_create_cached_image_record(self.url)
        self.assertEqual(self.db.get_all_successfully_cached_image_records(), [])

    def test_get_all_successfully_cached_after_report(self):
        rec = self.db.get_or_create_cached_image_record(self.url, self.entry_date)
        self.db.report_image_as_cached(rec["id"], "local_image.png", self.entry_date)
        cached = self.db.get_all_successfully_cached_image_records()
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached[0]["url"], self.url)
        self.assertEqual(cached[0]["filename"], "local_image.png")

    def test_attempted_image_not_in_successfully_cached(self):
        rec = self.db.get_or_create_cached_image_record(self.url)
        self.db.report_image_as_attempted(rec["id"])
        self.assertEqual(self.db.get_all_successfully_cached_image_records(), [])


if __name__ == "__main__":
    unittest.main()
