#!/bin/bash
set -e
cd "$(dirname "$0")"
nice -n 19 python3 build.py
nice -n 19 node tests/app_smoke.js
nice -n 19 python3 -m tests.run_dist
nice -n 19 python3 -m tests.test_dist
# signup (AWI-SIGNUP-FORM-001): endpoint/retry/export on mocks, SQL vs SQLite, secret scan, mutants on save-order + fallback
nice -n 19 node --test tests/signup/
nice -n 19 python3 tests/signup/sql_check.py
nice -n 19 bash tests/signup/secret_scan.sh
nice -n 19 python3 tests/signup/mutants.py
# headless Chrome: chart variants, stacking, 390px readability (prints SKIP when Chrome is missing)
if command -v google-chrome >/dev/null 2>&1; then
  nice -n 19 python3 -m tests.browser_check
else
  echo "browser_check: SKIP (google-chrome not found)"
fi
# SHIP gates (tests/test_ship.py) are run separately: python3 -m tests.test_ship
