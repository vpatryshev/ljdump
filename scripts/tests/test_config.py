#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for config.py.

Covers the importable configuration classes and helpers:
  - Config          (base: verbose flag, workdir, cache/retry flags, image cookie)
  - ConfigPlain     (config built directly from parsed args)
  - ConfigFromFile  (config parsed from an XML config file)
  - setup           (chooses a config source based on which files exist)

The interactive TUIConfig path and the cache_images cookie prompt call
input()/getpass(); those are exercised by patching input/getpass on the
module rather than by driving stdin live.
"""

import os
import sys
import unittest
import tempfile
from types import SimpleNamespace
from unittest import mock

# Ensure the scripts directory is on the path so `from config import ...` resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config, ConfigPlain, ConfigFromFile, setup
import config as config_mod


def make_args(cache_images=False, retry_images=False, quiet=None,
              server="https://www.dreamwidth.org", user="alice",
              password="secret"):
    """Build an argparse-like namespace accepted by the Config classes.

    `quiet` is special: Config sets verbose = not hasattr(args, 'quiet'),
    so we only attach the attribute when a value is explicitly provided.
    """
    kwargs = dict(
        cache_images=cache_images,
        retry_images=retry_images,
        server=server,
        user=user,
        password=password,
    )
    if quiet is not None:
        kwargs["quiet"] = quiet
    return SimpleNamespace(**kwargs)


SAMPLE_CONFIG = """<?xml version="1.0"?>
<ljdump>
  <server>https://www.dreamwidth.org</server>
  <username>alice</username>
  <password>hunter2</password>
  <journal>alice</journal>
  <journal>somecommunity</journal>
  <unique>cookie-value</unique>
</ljdump>
"""

CONFIG_NO_JOURNALS = """<?xml version="1.0"?>
<ljdump>
  <server>https://www.livejournal.com</server>
  <username>bob</username>
  <password>pw</password>
</ljdump>
"""


class TestConfigBase(unittest.TestCase):
    def test_verbose_true_when_no_quiet_attr(self):
        cfg = Config("/tmp/work", make_args())
        self.assertTrue(cfg.verbose)

    def test_verbose_false_when_quiet_attr_present(self):
        # Any value for `quiet` makes hasattr true -> verbose False.
        cfg = Config("/tmp/work", make_args(quiet=True))
        self.assertFalse(cfg.verbose)
        cfg2 = Config("/tmp/work", make_args(quiet=False))
        self.assertFalse(cfg2.verbose)

    def test_workdir_stored(self):
        cfg = Config("/some/dir", make_args())
        self.assertEqual(cfg.workdir, "/some/dir")

    def test_cache_and_retry_flags_copied(self):
        cfg = Config("/tmp/work", make_args(cache_images=False, retry_images=True))
        self.assertFalse(cfg.cache_images)
        self.assertTrue(cfg.retry_images)

    def test_no_cookie_prompt_when_cache_images_false(self):
        # getpass is NOT called, so no `unique` attribute is set by the base.
        cfg = Config("/tmp/work", make_args(cache_images=False))
        self.assertFalse(hasattr(cfg, "unique"))

    def test_cache_images_prompts_for_cookie(self):
        # The cookie prompt uses getpass(), a name not present in the config
        # module namespace, so we inject it via patch to exercise the branch.
        with mock.patch.object(config_mod, "getpass", create=True,
                               return_value="my-cookie") as gp:
            cfg = Config("/tmp/work", make_args(cache_images=True))
        gp.assert_called_once()
        self.assertEqual(cfg.unique, "my-cookie")
        self.assertTrue(cfg.cache_images)


class TestConfigPlain(unittest.TestCase):
    def test_fields_populated(self):
        journals = ["alice", "community"]
        cfg = ConfigPlain("/tmp/work", journals, "the-cookie", make_args())
        self.assertEqual(cfg.journals, journals)
        self.assertEqual(cfg.unique, "the-cookie")
        self.assertEqual(cfg.workdir, "/tmp/work")

    def test_account_built_from_args(self):
        cfg = ConfigPlain("/tmp/work", ["alice"], None,
                          make_args(server="https://s", user="u", password="p"))
        self.assertEqual(cfg.account.url, "https://s")
        self.assertEqual(cfg.account.user, "u")
        self.assertEqual(cfg.account.password, "p")

    def test_unique_overrides_after_super_init(self):
        # cache_images path in base would set unique, but ConfigPlain assigns
        # its own `unique` argument last, so that value wins.
        with mock.patch.object(config_mod, "getpass", create=True,
                               return_value="base-cookie"):
            cfg = ConfigPlain("/tmp/work", ["alice"], "plain-cookie",
                              make_args(cache_images=True))
        self.assertEqual(cfg.unique, "plain-cookie")


class TestConfigFromFile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        for root, dirs, files in os.walk(self.tmpdir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self.tmpdir)

    def _write(self, name, contents):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(contents)
        return path

    def test_parses_server_user_password_and_account(self):
        self._write("ljdump.config", SAMPLE_CONFIG)
        cfg = ConfigFromFile(self.tmpdir, "ljdump.config", make_args())
        self.assertEqual(cfg.account.url, "https://www.dreamwidth.org")
        self.assertEqual(cfg.account.user, "alice")
        self.assertEqual(cfg.account.password, "hunter2")

    def test_parses_multiple_journals(self):
        self._write("ljdump.config", SAMPLE_CONFIG)
        cfg = ConfigFromFile(self.tmpdir, "ljdump.config", make_args())
        self.assertEqual(cfg.journals, ["alice", "somecommunity"])

    def test_journals_default_to_username_when_absent(self):
        self._write("ljdump.config", CONFIG_NO_JOURNALS)
        cfg = ConfigFromFile(self.tmpdir, "ljdump.config", make_args())
        self.assertEqual(cfg.journals, ["bob"])

    def test_unique_is_none_without_cache_images(self):
        # Even though the file has a <unique> element, it is only read when
        # cache_images is enabled.
        self._write("ljdump.config", SAMPLE_CONFIG)
        cfg = ConfigFromFile(self.tmpdir, "ljdump.config",
                             make_args(cache_images=False))
        self.assertIsNone(cfg.unique)

    def test_unique_read_from_file_when_cache_images(self):
        # With cache_images the base Config.__init__ runs getpass() first
        # (a name absent from the module namespace), then ConfigFromFile reads
        # <unique> from the file and overwrites it. Patch getpass to reach that.
        self._write("ljdump.config", SAMPLE_CONFIG)
        with mock.patch.object(config_mod, "getpass", create=True,
                               return_value="ignored"):
            cfg = ConfigFromFile(self.tmpdir, "ljdump.config",
                                 make_args(cache_images=True))
        self.assertEqual(cfg.unique, "cookie-value")

    def test_unique_none_when_cache_images_but_no_element(self):
        self._write("ljdump.config", CONFIG_NO_JOURNALS)
        with mock.patch.object(config_mod, "getpass", create=True,
                               return_value="ignored"):
            cfg = ConfigFromFile(self.tmpdir, "ljdump.config",
                                 make_args(cache_images=True))
        self.assertIsNone(cfg.unique)

    def test_missing_file_calls_fail_and_exits(self):
        # fail() prints and calls exit(1) -> SystemExit. Silence stderr.
        with mock.patch.object(config_mod.sys, "stderr"):
            with self.assertRaises(SystemExit):
                ConfigFromFile(self.tmpdir, "does_not_exist.config",
                               make_args())


class TestSetup(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_cwd = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self._orig_cwd)
        for root, dirs, files in os.walk(self.tmpdir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self.tmpdir)

    def test_uses_config_file_in_cwd(self):
        with open("ljdump.config", "w", encoding="utf-8") as fh:
            fh.write(SAMPLE_CONFIG)
        cfg = setup("ljdump.config", make_args())
        self.assertIsInstance(cfg, ConfigFromFile)
        self.assertEqual(cfg.account.user, "alice")

    def test_uses_config_file_in_work_subdir(self):
        os.mkdir("work")
        with open(os.path.join("work", "ljdump.config"), "w",
                  encoding="utf-8") as fh:
            fh.write(CONFIG_NO_JOURNALS)
        cfg = setup("ljdump.config", make_args())
        self.assertIsInstance(cfg, ConfigFromFile)
        self.assertEqual(cfg.account.user, "bob")
        self.assertEqual(cfg.workdir, "work")

    def test_falls_back_to_tui_when_no_file(self):
        # No config file exists; setup() prints a notice then constructs a
        # TUIConfig, driving the interactive prompts. We inject input()/getpass
        # so nothing blocks on real stdin.
        inputs = iter([
            "",       # server -> defaults to LIVEJOURNAL
            "carol",  # username
            "",       # journal -> defaults to username
        ])
        with mock.patch.object(config_mod, "print"), \
             mock.patch.object(config_mod, "input", create=True,
                               side_effect=lambda prompt="": next(inputs)), \
             mock.patch.object(config_mod, "getpass", return_value="pw"):
            cfg = setup("ljdump.config", make_args())

        self.assertIsInstance(cfg, config_mod.TUIConfig)
        self.assertEqual(cfg.server, config_mod.LIVEJOURNAL)
        self.assertEqual(cfg.account.user, "carol")
        self.assertEqual(cfg.account.password, "pw")
        # An empty journal answer falls back to the username.
        self.assertEqual(cfg.journals, ["carol"])
        self.assertIsNone(cfg.unique)


if __name__ == "__main__":
    unittest.main()
