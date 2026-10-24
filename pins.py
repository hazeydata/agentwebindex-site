"""pins.json: single source of truth for the pinned inputs (data sha, copy, charts), and the build-time guards.

check(root) returns a list of error strings; build.py exits non-zero if it is not empty.
R4 guard: the build fails if pins.json "data" equals "data_stale_after_phase0" while "phase0_landed" is true
(the Tavily price re-verification landed in the data repo but the site still pins the old data sha).
"""
import hashlib, json, re
from pathlib import Path


def load(root):
    return json.loads((Path(root) / "pins.json").read_text())


def source_sha(root):
    m = re.search(r"^sha ([0-9a-f]{40})$", (Path(root) / "data/_upstream/SOURCE").read_text(), re.M)
    return m.group(1) if m else None


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(root, pins=None, vendored_sha=None):
    """Errors for: stale data pin after Phase 0 (R4), vendored data not at the pinned sha, copy, chart alt text or chart bytes not at the pin."""
    root = Path(root)
    pins = pins if pins is not None else load(root)
    vendored = vendored_sha if vendored_sha is not None else source_sha(root)
    errs = []
    if pins.get("phase0_landed") and pins["data"] == pins.get("data_stale_after_phase0"):
        errs.append(f'pins.json: data pin {pins["data"][:7]} is still the pre-Phase-0 sha while phase0_landed is true; '
                    're-pin "data" to the data repo commit that carries the Tavily update and run ./sync_data.sh')
    if vendored != pins["data"]:
        errs.append(f'data/_upstream/SOURCE sha {vendored} != pins.json data {pins["data"]}; run ./sync_data.sh {pins["data"]}')
    if sha256(root / "content/copy.md") != pins["copy_sha256"]:
        errs.append("content/copy.md does not match pins.json copy_sha256")
    if sha256(root / "content/chart-alt.md") != pins["chart_alt_sha256"]:
        errs.append("content/chart-alt.md does not match pins.json chart_alt_sha256")
    for name, meta in pins["charts_sha256"].items():
        p = root / "src/charts" / name
        if not p.exists() or sha256(p) != meta["sha256"]:
            errs.append(f"src/charts/{name} does not match pins.json charts_sha256")
    return errs
