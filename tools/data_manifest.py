#!/usr/bin/env python3
"""Write tests/data_pin_manifest.json: sha256 of the upstream bytes behind every vendored data file the site depends on.

Usage: python3 tools/data_manifest.py <agentwebindex-checkout> <full-40-hex-sha> [out.json]
Reads the files with `git show <sha>:<path>` (no working-tree state), so the manifest records what the commit contains.
Covered: data/benchmarks/latest.json and every file under data/_upstream/ except SOURCE (which records the sha itself).
The checkout path is not stored; the manifest names the public repo URL instead.
"""
import hashlib, json, re, subprocess, sys
from pathlib import Path

REPO_URL = "https://github.com/hazeydata/agentwebindex.git"
# vendored path (in this repo) -> path inside the agentwebindex repo (see sync_data.sh)
SOURCES = {
    "data/benchmarks/latest.json": "data/benchmarks/latest.json",
    "data/_upstream/providers.json": "collectors/providers.json",
    "data/_upstream/tos_matrix.yaml": "bench/tos_matrix.yaml",
    "data/_upstream/pricing.yaml": "bench/pricing.yaml",
}


def build(checkout, sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        sys.exit("sha must be a full 40-hex commit sha")
    files = {}
    for vendored, upstream in SOURCES.items():
        blob = subprocess.run(["git", "-C", str(checkout), "show", f"{sha}:{upstream}"], capture_output=True, check=True).stdout
        files[vendored] = hashlib.sha256(blob).hexdigest()
    return {"_doc": "sha256 of the upstream files at the pinned data sha; regenerate with tools/data_manifest.py (sync_data.sh does it).",
            "repo": REPO_URL, "sha": sha, "files": files}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).resolve().parent.parent / "tests/data_pin_manifest.json"
    out.write_text(json.dumps(build(sys.argv[1], sys.argv[2]), indent=1) + "\n")
    print("wrote", out.name)
