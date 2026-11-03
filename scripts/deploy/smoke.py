"""Post-deploy smoke check for agentwebindex (read-only GETs).

A route counts as served only when its status, content type AND body match what that route should return.
Pages answers every unknown path with 200 + the index.html (SPA fallback), so a bare 200 proves nothing.

Usage: python3 scripts/deploy/smoke.py https://agentwebindex.com [https://<deploy>.agentwebindex.pages.dev ...]
Exit 0 when every check passes, 1 otherwise. Prints one line per check; never prints response bodies.
"""
import re
import sys
import urllib.error
import urllib.request
import uuid

WORKER_MARKERS = (b"export default", b"addEventListener(", b"handleSubscribe", b"x-export-token", b"X-Export-Token")
_CF_EMAIL = re.compile(rb'(/cdn-cgi/l/email-protection#[0-9a-f]+|data-cfemail="[0-9a-f]+")')


def normalize(body: bytes) -> bytes:
    """Drop Cloudflare's per-request email-obfuscation tokens so two fetches of the same page compare equal."""
    return _CF_EMAIL.sub(b"", body)


def base_type(ctype: str) -> str:
    return (ctype or "").split(";")[0].strip().lower()


def is_fallback(status: int, ctype: str, body: bytes, fallback_body: bytes) -> bool:
    return status == 200 and base_type(ctype) == "text/html" and normalize(body) == normalize(fallback_body)


def check(path: str, status: int, ctype: str, body: bytes, fallback_body: bytes) -> tuple[bool, str]:
    """Return (ok, reason) for one GET response. fallback_body is the response to a random unknown path."""
    t = base_type(ctype)
    fb = is_fallback(status, ctype, body, fallback_body)
    if path == "/":
        ok = status == 200 and t == "text/html" and b"AgentWebIndex" in body
        return ok, f"home {status} {t}"
    if path == "/api/subscribe":
        ok = status == 405 and t != "text/html" and not fb
        return ok, f"subscribe GET expects 405 non-HTML, got {status} {t}{' (SPA fallback)' if fb else ''}"
    if path == "/api/signups/export.csv":
        ok = status == 401 and t != "text/html" and not fb and body.strip() == b"Unauthorized"
        return ok, f"export GET (no token) expects 401 'Unauthorized', got {status} {t}{' (SPA fallback)' if fb else ''}"
    if path.startswith("/_worker.js") or path == "/_routes.json":
        js = ("javascript" in t) or ("json" in t) or (status == 200 and t == "text/plain")  # any status
        leaked = any(m in body for m in WORKER_MARKERS)
        ok = not js and not leaked and (fb or status == 404)
        how = "SPA fallback" if fb else f"{status} {t}"
        return ok, f"{path} must not be served as an asset: {how}{' WORKER CODE' if leaked else ''}"
    raise ValueError(f"no expectation for {path}")


PATHS = ("/", "/api/subscribe", "/api/signups/export.csv", "/_worker.js", "/_worker.js/", "/_worker.js/index.js", "/_routes.json")


def fetch(url: str) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "awi-smoke"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def run(base: str) -> bool:
    base = base.rstrip("/")
    _, _, fallback = fetch(f"{base}/smoke-fallback-{uuid.uuid4().hex}")
    all_ok = True
    for p in PATHS:
        ok, why = check(p, *fetch(base + p), fallback)
        print(f"{'PASS' if ok else 'FAIL'} {base}{p}: {why}")
        all_ok &= ok
    return all_ok


if __name__ == "__main__":
    bases = sys.argv[1:] or ["https://agentwebindex.com"]
    sys.exit(0 if all([run(b) for b in bases]) else 1)
