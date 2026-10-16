#!/bin/bash
# Refresh the vendored data/ copy from a checkout of the agentwebindex (bench/collectors/data) repo.
# Usage: ./sync_data.sh ../agentwebindex
set -euo pipefail
SRC="${1:-../agentwebindex}"; cd "$(dirname "$0")"
[ -d "$SRC/data" ] || { echo "no $SRC/data"; exit 1; }
rm -rf data && mkdir -p data && cp -a "$SRC/data/." data/ && rm -rf data/cache   # mirror (no rsync on the box); page-text cache never vendored
mkdir -p data/_upstream
cp "$SRC/collectors/providers.json" "$SRC/bench/tos_matrix.yaml" "$SRC/bench/pricing.yaml" data/_upstream/
echo "synced data/ from $SRC"
