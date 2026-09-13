#!/bin/bash
# Run the unit test suite. Run from anywhere — we cd to the project root first.
# `unittest discover` auto-collects every scripts/tests/test_*.py, so new test
# modules are picked up without editing this file. Exits non-zero on any failure.
# Extra args are forwarded to unittest (e.g. ./tests.sh -v).
cd "$(dirname "$0")"
python3 -m unittest discover -s scripts/tests -t scripts/tests -p "test_*.py" "$@"
