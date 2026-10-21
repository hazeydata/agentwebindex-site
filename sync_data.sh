#!/bin/bash
# Refresh the vendored data/ copy from a committed agentwebindex (bench/collectors/data) sha.
# Usage: ./sync_data.sh <agentwebindex-sha> [repo-url-or-path]
#   default repo: https://github.com/hazeydata/agentwebindex.git
# Fetches the repo into a temp dir, exports data/ + the upstream config files at exactly that sha
# with git archive (no working-tree state involved), and records the resolved sha in data/_upstream/SOURCE.
set -euo pipefail
SHA="${1:?usage: $0 <agentwebindex-sha> [repo-url-or-path]}"
REPO="${2:-https://github.com/hazeydata/agentwebindex.git}"
cd "$(dirname "$0")"
T="$(mktemp -d "${TMPDIR:-/tmp}/awi-sync.XXXXXX")"; trap 'rm -rf "$T"' EXIT
git init -q "$T/src"
git -C "$T/src" fetch -q --filter=blob:none "$REPO" '+refs/heads/*:refs/remotes/origin/*'
FULL="$(git -C "$T/src" rev-parse --verify --quiet "$SHA^{commit}")" || { echo "sha $SHA not found in $REPO"; exit 1; }
mkdir "$T/out"
git -C "$T/src" archive "$FULL" data collectors/providers.json bench/tos_matrix.yaml bench/pricing.yaml | tar -x -C "$T/out"
[ -f "$T/out/data/benchmarks/latest.json" ] || { echo "no data/benchmarks/latest.json at $FULL"; exit 1; }
rm -rf data && mv "$T/out/data" data && rm -rf data/cache   # page-text cache never vendored
mkdir -p data/_upstream
cp "$T/out/collectors/providers.json" "$T/out/bench/tos_matrix.yaml" "$T/out/bench/pricing.yaml" data/_upstream/
printf 'repo %s\nsha %s\n' "$REPO" "$FULL" > data/_upstream/SOURCE
echo "synced data/ from $REPO @ $FULL"
