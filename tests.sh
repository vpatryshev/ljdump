#!/bin/bash
# Run the unit test suite. Run from anywhere — we cd to the project root first
# so the `scripts.*` module names resolve. A single `unittest` invocation
# aggregates all modules and exits non-zero if any test fails.
cd "$(dirname "$0")"
python3 -m unittest \
  scripts.test_db \
  scripts.test_ljdumpdb \
  scripts.test_utils \
  scripts.test_account \
  scripts.test_compare_from_db \
  scripts.test_update_from_db \
  scripts.test_dwscrape
