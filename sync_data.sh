#!/bin/bash
# Refresh the vendored data/ copy from a committed agentwebindex (bench/collectors/data) sha.
# Usage: ./sync_data.sh <full-40-hex-agentwebindex-sha> [repo-url-or-path] [recorded-url]
#   default repo: https://github.com/hazeydata/agentwebindex.git
#   The repo recorded in data/_upstream/SOURCE is never a local path: for a remote URL it is that URL; for a local clone
#   it is [recorded-url], else $AWI_RECORD_URL, else the canonical https://github.com/hazeydata/agentwebindex.git.
# Fetches the repo into a temp dir, exports data/ + the upstream config files at exactly that sha
# with git archive (no working-tree state involved), and records the resolved sha in data/_upstream/SOURCE.
# Also regenerates tests/data_pin_manifest.json (tools/data_manifest.py). After re-pinning, edit pins.json "data" to the same sha.
set -euo pipefail
SHA="${1:?usage: $0 <full-40-hex-agentwebindex-sha> [repo-url-or-path]}"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "sha must be exactly 40 lowercase hex characters (a full commit sha, not a branch, ref or short sha): $SHA" >&2; exit 2; }
CANON="https://github.com/hazeydata/agentwebindex.git"
REPO="${2:-$CANON}"
if [ -n "${3:-}" ]; then RECORD="$3"
elif [ -n "${AWI_RECORD_URL:-}" ]; then RECORD="$AWI_RECORD_URL"
elif [[ "$REPO" == *://* || "$REPO" == git@* ]]; then RECORD="$REPO"
else RECORD="$CANON"; fi
[[ "$RECORD" == *://* || "$RECORD" == git@* ]] || { echo "recorded repo must be a URL, not a path: $RECORD" >&2; exit 2; }
cd "$(dirname "$0")"
T="$(mktemp -d "${TMPDIR:-/tmp}/awi-sync.XXXXXX")"; trap 'rm -rf "$T"' EXIT
git init -q "$T/src"
git -C "$T/src" fetch -q --filter=blob:none "$REPO" '+refs/heads/*:refs/remotes/origin/*'
git -C "$T/src" cat-file -e "$SHA^{commit}" 2>/dev/null || git -C "$T/src" fetch -q "$REPO" "$SHA" 2>/dev/null || true   # e.g. a PR head that is on no branch
FULL="$(git -C "$T/src" rev-parse --verify --quiet "$SHA^{commit}")" && [ "$FULL" = "$SHA" ] || { echo "commit $SHA not found in $REPO" >&2; exit 1; }
mkdir "$T/out"
git -C "$T/src" archive "$FULL" data collectors/providers.json bench/tos_matrix.yaml bench/pricing.yaml | tar -x -C "$T/out"
[ -f "$T/out/data/benchmarks/latest.json" ] || { echo "no data/benchmarks/latest.json at $FULL"; exit 1; }
rm -rf data && mv "$T/out/data" data && rm -rf data/cache   # page-text cache never vendored
mkdir -p data/_upstream
cp "$T/out/collectors/providers.json" "$T/out/bench/tos_matrix.yaml" "$T/out/bench/pricing.yaml" data/_upstream/
printf 'repo %s\nsha %s\n' "$RECORD" "$FULL" > data/_upstream/SOURCE
python3 tools/data_manifest.py "$T/src" "$FULL" tests/data_pin_manifest.json   # AC7: hashes of the upstream bytes at this sha
echo "synced data/ from $REPO @ $FULL (recorded repo: $RECORD)"
