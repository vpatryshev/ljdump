#!/bin/bash
# Run the unit test suite. Run from anywhere — we cd to the project root first
# so the `scripts.*` module names resolve. A single `unittest` invocation
# aggregates all modules and exits non-zero if any test fails.
cd "$(dirname "$0")"
python3 -m unittest \
  scripts.tests.test_db \
  scripts.tests.test_ljdumpdb \
  scripts.tests.test_utils \
  scripts.tests.test_account \
  scripts.tests.test_compare_from_db \
  scripts.tests.test_update_from_db \
  scripts.tests.test_dwscrape \
  scripts.tests.test_fix_latex_chars \
  scripts.tests.test_ljdumptomd \
  scripts.tests.test_combine_clean_md \
  scripts.tests.test_cache \
  scripts.tests.test_update_entries \
  scripts.tests.test_ljdumptohtml \
  scripts.tests.test_config \
  scripts.tests.test_ljdumpops \
  scripts.tests.test_journal
