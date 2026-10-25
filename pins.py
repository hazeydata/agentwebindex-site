"""pins.json: single source of truth for the pinned inputs (data sha, copy, charts), and the build-time guards.

check(root) returns a list of error strings; build.py exits non-zero if it is not empty.
Phase 0 guard (R8): the build reads bench/pricing.yaml at the pinned data sha (the vendored data/_upstream/pricing.yaml, whose SOURCE sha must equal
pins.json "data") and fails if the pin is STALE_DATA_SHA, or if any Tavily input date (every checked_at / verified_date anywhere under
providers.tavily) is before pins.json "phase0_date".
"""
import hashlib, json, os, re, subprocess
from pathlib import Path

STALE_DATA_SHA = "6b8bd87d778b3fe0fe049f9274796ab498928cc5"   # pre-Phase-0 data pin; never buildable
DATE_FIELDS = ("checked_at", "verified_date")


def load(root):
    return json.loads((Path(root) / "pins.json").read_text())


def source_sha(root):
    m = re.search(r"^sha ([0-9a-f]{40})$", (Path(root) / "data/_upstream/SOURCE").read_text(), re.M)
    return m.group(1) if m else None


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tavily_dates(pricing_path):
    """[(dotted path, value)] for every checked_at / verified_date at any depth under providers.tavily in pricing.yaml (JSON with # comment lines)."""
    doc = json.loads("\n".join(l for l in Path(pricing_path).read_text().splitlines() if not l.lstrip().startswith("#")))
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in DATE_FIELDS:
                    out.append((f"{path}.{k}", v))
                else:
                    walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(doc["providers"]["tavily"], "providers.tavily")
    return out


def check(root, pins=None, vendored_sha=None):
    """Errors for: stale data pin, Tavily input dated before phase0_date, vendored data not at the pinned sha, copy, chart alt text or chart bytes not at the pin."""
    root = Path(root)
    pins = pins if pins is not None else load(root)
    vendored = vendored_sha if vendored_sha is not None else source_sha(root)
    errs = []
    if pins["data"] == STALE_DATA_SHA:
        errs.append(f'pins.json: data pin {STALE_DATA_SHA[:7]} is the pre-Phase-0 sha; '
                    're-pin "data" to the data repo commit that carries the Tavily update and run ./sync_data.sh')
    try:
        dates = tavily_dates(root / "data/_upstream/pricing.yaml")
    except (OSError, ValueError, KeyError) as ex:
        dates = []
        errs.append(f"data/_upstream/pricing.yaml: cannot read Tavily input dates ({type(ex).__name__}: {ex})")
    else:
        if not dates:
            errs.append("data/_upstream/pricing.yaml: no checked_at / verified_date found under providers.tavily")
    for path, val in dates:
        if not isinstance(val, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
            errs.append(f"pricing.yaml {path} is {val!r}, not a YYYY-MM-DD date")
        elif val < pins["phase0_date"]:
            errs.append(f'pricing.yaml {path} is {val}, before the Phase 0 date {pins["phase0_date"]}; pin a data sha with the Tavily re-verification')
    repo = os.environ.get("AWI_DATA_REPO")
    if repo:   # optional cross-check: vendored pricing.yaml must be the bytes of bench/pricing.yaml at the pin in the data repo
        r = subprocess.run(["git", "-C", repo, "show", f'{pins["data"]}:bench/pricing.yaml'], capture_output=True)
        if r.returncode != 0:
            errs.append(f'AWI_DATA_REPO: cannot read bench/pricing.yaml at {pins["data"][:12]}')
        elif r.stdout != (root / "data/_upstream/pricing.yaml").read_bytes():
            errs.append(f'data/_upstream/pricing.yaml differs from bench/pricing.yaml at {pins["data"][:12]} in AWI_DATA_REPO; run ./sync_data.sh {pins["data"]}')
    if vendored != pins["data"]:
        errs.append(f'data/_upstream/SOURCE sha {vendored} != pins.json data {pins["data"]}; run ./sync_data.sh {pins["data"]}')
    if sha256(root / "content/copy.md") != pins["copy_sha256"]:
        errs.append("content/copy.md does not match pins.json copy_sha256")
    if "copy_cuts_sha256" in pins and sha256(root / "content/copy-cuts.md") != pins["copy_cuts_sha256"]:
        errs.append("content/copy-cuts.md does not match pins.json copy_cuts_sha256")
    if sha256(root / "content/chart-alt.md") != pins["chart_alt_sha256"]:
        errs.append("content/chart-alt.md does not match pins.json chart_alt_sha256")
    for name, meta in pins["charts_sha256"].items():
        p = root / "src/charts" / name
        if not p.exists() or sha256(p) != meta["sha256"]:
            errs.append(f"src/charts/{name} does not match pins.json charts_sha256")
    return errs
