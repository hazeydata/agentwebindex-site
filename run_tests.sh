#!/bin/bash
set -e
cd "$(dirname "$0")"
nice -n 19 python3 build.py
nice -n 19 node tests/app_smoke.js
nice -n 19 python3 -m tests.run_dist
nice -n 19 python3 -m tests.test_dist
# headless Chrome: chart variants, stacking, 390px readability (prints SKIP when Chrome is missing)
if command -v google-chrome >/dev/null 2>&1; then
  nice -n 19 python3 -m tests.browser_check
else
  echo "browser_check: SKIP (google-chrome not found)"
fi
# SHIP gates (tests/test_ship.py) are run separately: python3 -m tests.test_ship
