#!/bin/bash
set -e
cd "$(dirname "$0")"
nice -n 19 node tests/app_smoke.js
