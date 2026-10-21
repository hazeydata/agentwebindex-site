#!/bin/bash
set -e
cd "$(dirname "$0")"
nice -n 19 python3 build.py
nice -n 19 node tests/app_smoke.js
nice -n 19 python3 -m tests.run_dist
nice -n 19 python3 -m tests.test_dist
