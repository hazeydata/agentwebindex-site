"""Headless-Chrome checks of the built dist/ (AC14 served bytes, AC16, AC17, R9.2-R9.5, mobile readability). Stdlib only.

Serves dist/ from a local HTTP server on a free port, starts Chrome with one throwaway --user-data-dir, and drives it
over the DevTools protocol with a minimal websocket client. Chrome, its profile directory and the server are always
cleaned up (try/finally). Screenshots (390 and 1440 wide, every page) go to a temp directory OUTSIDE the repo, which is
deleted on exit; with AWI_KEEP_SHOTS=1 it is kept and its path is printed for the human readability check. Prints SKIP and exits 0 when Chrome is not installed.

Run after `python3 build.py`:  python3 -m tests.browser_check
"""
import base64, hashlib, http.client, json, os, re, shutil, signal, socket, struct, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / "dist"
CHROME = shutil.which("google-chrome") or "/usr/bin/google-chrome"
PINS = json.loads((R / "pins.json").read_text())
PAGES = ["/", "/prices/", "/methodology/", "/data/", "/disclosures/", "/sponsors/", "/newsletter/", "/tell-us/"]
CHARTS = {"chart-pass-rate": "pass-rate", "chart-cost": "cost-per-success"}
sys.path.insert(0, str(R))
import copydoc  # noqa: E402
ALTS = copydoc.alt_texts()
VIEWPORTS = [(390, 844), (720, 900), (1440, 900)]


class WS:
    def __init__(self, host, port, path):
        self.s = socket.create_connection((host, port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.s.recv(4096)
        head, self.buf = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise RuntimeError("websocket handshake failed: " + head.decode(errors="replace")[:200])

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(1 << 20)
            if not chunk:
                raise ConnectionError("websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        data = text.encode()
        n = len(data)
        hdr = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", n))
        mask = os.urandom(4)
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        msg = b""
        while True:
            b0, b1 = self._read(2)
            op, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if op == 8:
                raise ConnectionError("websocket closed by peer")
            if op == 9:   # ping -> pong
                self.s.sendall(bytes([0x8A, 0x80 | len(payload)]) + b"\0\0\0\0" + payload) if len(payload) < 126 else None
                continue
            msg += payload
            if b0 & 0x80:
                return msg.decode()

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


class Cdp:
    def __init__(self, ws):
        self.ws, self.n, self.events = ws, 0, []

    hook = None   # optional fn(cdp, message) for events that need an answer (Fetch.requestPaused)

    def _dispatch(self, m):
        if "id" in m:
            sent = getattr(self, "pending_ids", {}).pop(m["id"], None)
            if sent:
                if "error" in m:
                    self.send_errors = getattr(self, "send_errors", []) + [f"{sent}: {m['error']}"]
                return
            self.responses[m["id"]] = m
        elif "method" in m:
            self.events.append(m["method"])
            if self.hook:
                self.hook(self, m)

    def send(self, method, **params):
        """Fire-and-forget command (used from hooks, which must not block on a reply). Errors are kept in self.send_errors."""
        self.n += 1
        self.pending_ids = getattr(self, "pending_ids", {}); self.pending_ids[self.n] = method
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))

    def call(self, method, **params):
        self.n += 1
        mid = self.n
        self.responses = getattr(self, "responses", {})
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while mid not in self.responses:
            self._dispatch(json.loads(self.ws.recv()))
        m = self.responses.pop(mid)
        if "error" in m:
            raise RuntimeError(f"{method}: {m['error']}")
        return m.get("result", {})

    def wait_event(self, name, timeout=20):
        self.responses = getattr(self, "responses", {})
        end = time.time() + timeout
        while name not in self.events:
            if time.time() > end:
                raise TimeoutError(name)
            self.ws.s.settimeout(max(0.1, end - time.time()))
            self._dispatch(json.loads(self.ws.recv()))
        self.ws.s.settimeout(30)

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise RuntimeError(str(r["exceptionDetails"])[:300])
        return r["result"].get("value")


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def sha_of_url(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return hashlib.sha256(r.read()).hexdigest()


MEASURE = """(() => { const out = {};
for (const id of %s) { const fig = document.getElementById(id);
  out[id] = [...fig.querySelectorAll('.ch')].map(i => { const cs = getComputedStyle(i), r = i.getBoundingClientRect(), svg = i.querySelector('svg');
    return {file: i.dataset.file, display: cs.display, visible: cs.display !== 'none' && r.width > 0 && r.height > 0,
            role: i.getAttribute('role'), label: i.getAttribute('aria-label'),
            top: r.top + scrollY, bottom: r.bottom + scrollY, left: r.left, right: r.right, width: r.width, svgw: svg ? svg.getBoundingClientRect().width : 0}; }); }
return JSON.stringify(out); })()"""
# page ready = load fired, the site stylesheet is applied (its .ch rule hides variants) and fonts settled; the 390px flake was
# measuring before style.css applied (all 4 <img> variants visible) plus lazy <img> decode races. Inline SVGs remove the decode wait.
READY = """(async () => { for (let k = 0; k < 200; k++) { const sheet = [...document.styleSheets].find(s => s.href && s.href.endsWith('/style.css'));
  let ok = false; try { ok = !!sheet && sheet.cssRules.length > 0; } catch (e) {}
  if (ok && document.readyState === 'complete') { await document.fonts.ready; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))); return true; }
  await new Promise(r => setTimeout(r, 50)); } return false; })()"""
# R9.3 geometry/text equality: snapshot every drawn element of the visible variant, then swap in the ORIGINAL file markup
# (prolog removed, ids not renamed) with every other chart removed so its ids are unique, and snapshot again.
SNAP = """(() => { const vis = [...document.querySelectorAll('#%s .ch')].find(e => getComputedStyle(e).display !== 'none');
  const root = vis.querySelector('svg'), o = root.getBoundingClientRect();
  return JSON.stringify([[o.width, o.height]].concat([...root.querySelectorAll('*')].filter(e => e.getBBox && !e.closest('defs, metadata, clipPath')).map(e => { const b = e.getBBox(), r = e.getBoundingClientRect();
    return [e.tagName, e.tagName === 'text' ? e.textContent : '', +b.x.toFixed(2), +b.y.toFixed(2), +b.width.toFixed(2), +b.height.toFixed(2),
            +(r.left - o.left).toFixed(2), +(r.top - o.top).toFixed(2), +r.width.toFixed(2), +r.height.toFixed(2)]; }))); })()"""
SWAP = """(async () => { const vis = [...document.querySelectorAll('#%s .ch')].find(e => getComputedStyle(e).display !== 'none');
  const txt = await (await fetch('/assets/charts/' + vis.dataset.file)).text();
  const i = txt.indexOf('<svg'); document.querySelectorAll('.ch').forEach(e => { if (e !== vis) e.remove(); });
  vis.innerHTML = txt.slice(i); await document.fonts.ready; await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const seen = new Set(), dup = new Set(); document.querySelectorAll('[id]').forEach(e => (seen.has(e.id) ? dup : seen).add(e.id));
  return JSON.stringify([vis.dataset.file, [...dup]]); })()"""
FONT = """(() => { const vis = [...document.querySelectorAll('#%s .ch')].find(e => getComputedStyle(e).display !== 'none');
  const t = [...vis.querySelectorAll('text')].find(e => /Inter/.test(e.getAttribute('style') || '') && e.textContent.trim());
  t.setAttribute('data-font-probe', '1'); const cs = getComputedStyle(t);
  const face = [...document.fonts].find(f => f.family.replace(/"/g, '') === 'Inter' && f.weight === '400');
  return JSON.stringify({family: cs.fontFamily, weight: cs.fontWeight, check: document.fonts.check(cs.fontSize + ' Inter'),
                         face: face ? face.status : 'missing', text: t.textContent}); })()"""
READ = """(() => { const sel = 'nav.top a, .site-footer a, button, summary, .btn';
const small = [...document.querySelectorAll(sel)].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.height < 43.99; }).map(e => e.tagName + ' ' + (e.textContent || '').trim().slice(0, 30) + ' h=' + e.getBoundingClientRect().height.toFixed(1));
return JSON.stringify({scrollWidth: document.documentElement.scrollWidth, bodyScrollWidth: document.body.scrollWidth, font: parseFloat(getComputedStyle(document.body).fontSize), small}); })()"""


def open_page(cdp, base, path, width, height, scheme, theme=None):
    cdp.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
    cdp.call("Emulation.setScrollbarsHidden", hidden=width < 768)   # phones overlay scrollbars; a 15px desktop gutter would shrink the 390 layout to 375
    cdp.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": scheme}])
    for attempt in range(3):
        cdp.events.clear()
        cdp.call("Page.navigate", url=base + path)
        cdp.wait_event("Page.loadEventFired")
        if cdp.js(READY):
            break
    else:
        raise RuntimeError(f"{path}: style.css never applied after 3 loads")
    if theme:
        cdp.js(f"document.documentElement.setAttribute('data-theme','{theme}')")
        cdp.js("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")


def check_charts(cdp, base, errs):
    """AC16/AC17/R9.5: at every viewport x scheme (and data-theme override) exactly one of the 4 inlined variants per chart is
    visible, the rest display:none; it is the right file; it fits 390px; C2 is stacked under C1. R9.4: role=img + alt-text name."""
    n = 0
    cases = [(w, h, s, None) for (w, h) in VIEWPORTS for s in ("dark", "light")] + [(1440, 900, "dark", "light"), (1440, 900, "light", "dark"), (390, 844, "dark", "light")]
    for w, h, scheme, theme in cases:
        open_page(cdp, base, "/", w, h, scheme, theme)
        data = json.loads(cdp.js(MEASURE % json.dumps(list(CHARTS))))
        eff = theme or scheme
        size = 720 if w >= 768 else 350
        for cid, name in CHARTS.items():
            vis = [i for i in data[cid] if i["visible"]]
            tag = f"{cid} @{w} {scheme}{'+data-theme=' + theme if theme else ''}"
            hidden = [i for i in data[cid] if not i["visible"]]
            if len(data[cid]) != 4 or any(i["display"] != "none" for i in hidden):
                errs.append(f"{tag}: expected 4 variants with the hidden ones display:none, got {[(i['file'], i['display']) for i in data[cid]]}")
            if len(vis) != 1:
                errs.append(f"{tag}: {len(vis)} visible variants, expected 1")
                continue
            want = f"awi-{name}-{size}-{eff}.svg"
            got = vis[0]["file"]
            if got != want:
                errs.append(f"{tag}: visible {got}, expected {want}")
            if vis[0]["role"] != "img" or vis[0]["label"] != ALTS[name]:
                errs.append(f"{tag}: visible chart role/name {vis[0]['role']!r}/{vis[0]['label']!r} != img/QUERIES.md alt")
            served = sha_of_url(base, "/assets/charts/" + got)
            if served != PINS["charts_sha256"][got]["sha256"]:
                errs.append(f"{tag}: served bytes of {got} differ from pinned sha256")
            if vis[0]["svgw"] <= 0:
                errs.append(f"{tag}: {got} did not render")
            if w == 390 and vis[0]["right"] > 390 + 0.5:
                errs.append(f"{tag}: chart overflows the 390px viewport (right={vis[0]['right']})")
            n += 1
        a, b = [[i for i in data[c] if i["visible"]] for c in CHARTS]
        if a and b:
            if b[0]["top"] < a[0]["bottom"] - 0.5:
                errs.append(f"@{w}: C2 top {b[0]['top']} above C1 bottom {a[0]['bottom']} (not stacked)")
            if abs(b[0]["left"] - a[0]["left"]) > 0.5:
                errs.append(f"@{w}: C1 and C2 left edges differ ({a[0]['left']} vs {b[0]['left']})")
    return n


def check_fonts(cdp, base, errs):
    """R9.2: per chart, ONE non-title chart <text> styled Inter resolves to Inter (computed style + document.fonts) and Chrome renders that element in Inter with no fallback font. Chart titles are Space Grotesk 600 and are not checked here."""
    cdp.call("DOM.enable")
    cdp.call("CSS.enable")
    n = 0
    for w, h in ((390, 844), (1440, 900)):
        for scheme in ("dark", "light"):
            open_page(cdp, base, "/", w, h, scheme)
            for cid in CHARTS:
                tag = f"{cid} @{w} {scheme}"
                r = json.loads(cdp.js(FONT % cid))
                if not r["family"].replace('"', "").replace("'", "").startswith("Inter") or not r["check"] or r["face"] != "loaded":
                    errs.append(f"{tag}: chart text font {r}")
                doc = cdp.call("DOM.getDocument", depth=0)["root"]["nodeId"]
                node = cdp.call("DOM.querySelector", nodeId=doc, selector="[data-font-probe]")["nodeId"]
                fonts = [f["familyName"] for f in cdp.call("CSS.getPlatformFontsForNode", nodeId=node)["fonts"]]
                if fonts != ["Inter"]:
                    errs.append(f"{tag}: chart text {r['text']!r} rendered with {fonts}, expected only Inter")
                cdp.js("document.querySelector('[data-font-probe]').removeAttribute('data-font-probe'); 1")
                n += 1
    return n


def file_dup_ids(path):
    ids = re.findall(r'\bid="([^"]*)"', path.read_text())
    return {i for i in ids if ids.count(i) > 1}


def same_drawing(a, b, tol=0.05):
    """Equal tag, text and SVG bbox; client-rect offsets within tol px (sub-pixel rounding of the page offset only)."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if len(x) == 2:   # svg root size
            if any(abs(p - q) > tol for p, q in zip(x, y)):
                return False
            continue
        if x[:6] != y[:6] or any(abs(p - q) > tol for p, q in zip(x[6:], y[6:])):
            return False
    return True


def check_rename_geometry(cdp, base, errs):
    """R9.3: the build-time id rename changes nothing drawn: every element's text and box match the original file markup."""
    n = 0
    for w, h in ((390, 844), (1440, 900)):
        for scheme in ("dark", "light"):
            for cid in CHARTS:
                open_page(cdp, base, "/", w, h, scheme)
                before = json.loads(cdp.js(SNAP % cid))
                f, dup = json.loads(cdp.js(SWAP % cid))
                own = file_dup_ids(D / "assets/charts" / f)   # ids the source file itself repeats (matplotlib gid), allowed only here
                if set(dup) - own:
                    errs.append(f"{cid} @{w} {scheme}: ids {sorted(set(dup) - own)} collide after swapping in the original markup")
                after = json.loads(cdp.js(SNAP % cid))
                if not before or not same_drawing(before, after):
                    diff = next((i for i, (x, y) in enumerate(zip(before, after)) if not same_drawing([x], [y])), min(len(before), len(after)))
                    errs.append(f"{cid} @{w} {scheme}: renamed vs original differ ({len(before)} vs {len(after)} elements; first diff #{diff}: "
                                f"{before[diff] if diff < len(before) else None} vs {after[diff] if diff < len(after) else None})")
                n += 1
    return n


def check_readability(cdp, base, shots, errs):
    for scheme in ("dark", "light"):
        for p in PAGES:
            open_page(cdp, base, p, 390, 844, scheme)
            r = json.loads(cdp.js(READ))
            if r["scrollWidth"] > 390 or r["bodyScrollWidth"] > 390:
                errs.append(f"{p} {scheme}: horizontal overflow at 390px (scrollWidth {r['scrollWidth']})")
            if r["font"] < 16:
                errs.append(f"{p} {scheme}: body font {r['font']}px < 16px")
            if r["small"]:
                errs.append(f"{p} {scheme}: tap targets under 44px: {r['small'][:4]}")
    for w, h in ((390, 844), (1440, 900)):
        for p in PAGES:
            open_page(cdp, base, p, w, h, "dark")
            time.sleep(0.4)
            shot = cdp.call("Page.captureScreenshot", format="png", captureBeyondViewport=True)
            name = ("index" if p == "/" else p.strip("/")) + f"-{w}.png"
            (shots / name).write_bytes(base64.b64decode(shot["data"]))


LAYOUT = """(() => { const r = e => e ? e.getBoundingClientRect() : null;
const ps = [...document.querySelectorAll('.steps li > p')].map(e => r(e).width);
const steps = [...document.querySelectorAll('.steps li')].map(li => { const cs = getComputedStyle(li), b = getComputedStyle(li, '::before'), lr = r(li);
  const inner = lr.width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight); const h2 = li.querySelector('h2');
  return {beforeRow: b.gridRowStart, h2Row: getComputedStyle(h2).gridRowStart, h2Top: r(h2).top - lr.top - parseFloat(cs.paddingTop), h2Left: r(h2).left - lr.left,
          pw: [...li.querySelectorAll(':scope > p')].map(p => r(p).width), inner}; });
const cta = document.querySelector('.cta-hero');
const vals = [...document.querySelectorAll('.rows .row .mono')].map(e => ({h: r(e).height, f: getComputedStyle(e).fontSize, ff: getComputedStyle(e).fontFamily}));
const probe = document.createElement('span'); probe.style.cssText = 'position:absolute;visibility:hidden;width:68ch';
const pw = [...document.querySelectorAll('main p:not(.headline)')].filter(p => p.offsetParent).map(p => { p.appendChild(probe); probe.style.font = getComputedStyle(p).font;
  const want = probe.getBoundingClientRect().width; probe.remove(); return {mw: getComputedStyle(p).maxWidth, want, cls: p.className}; });
const ctext = [...document.querySelectorAll('.ch svg text')].filter(t => t.getClientRects().length).map(t => parseFloat(getComputedStyle(t).fontSize) * t.getScreenCTM().a);
return JSON.stringify({pw, ctext, steps, vals, hpad: getComputedStyle(document.querySelector('.site-header .wrap')).paddingTop, header: r(document.querySelector('.site-header')).height, stepMin: ps.length ? Math.min(...ps) : null,
  ctaTop: cta ? r(cta).top + scrollY : null}); })()"""


def check_layout(cdp, base, errs):
    """AWI-PAGE-POLISH-001: header <= 88px at 390; Methodology paragraphs are not squeezed into the number column (P0);
    hero CTA above the fold. (The signup form itself is checked by check_signup.)"""
    n = 0
    for w, h in ((390, 844), (1440, 900)):
        for p in PAGES:
            open_page(cdp, base, p, w, h, "dark")
            m = json.loads(cdp.js(LAYOUT))
            tag = f"{p} @{w}"
            if w == 390 and m["header"] > 88.5:
                errs.append(f"{tag}: header {m['header']}px > 88px")
            if w == 390 and m["hpad"] != "8px":
                errs.append(f"{tag}: header vertical padding {m['hpad']} != 8px")
            if w == 390 and p == "/":
                for v in m["vals"]:
                    if v["f"] != "13px" or "Plex Mono" not in v["ff"] or v["h"] > 40.5:
                        errs.append(f"{tag}: run-row value not a Plex Mono 13px label:value line (<= 2 lines): {v}")
            if p == "/methodology/" and (m["stepMin"] is None or m["stepMin"] < (480 if w >= 768 else 300)):
                errs.append(f"{tag}: Methodology step paragraph only {m['stepMin']}px wide")
            for q in m["pw"]:   # AC-20: every visible body paragraph is capped at 68ch of its own font
                if not q["mw"].endswith("px") or abs(float(q["mw"][:-2]) - q["want"]) > 1:
                    errs.append(f"{tag}: paragraph .{q['cls']} max-width {q['mw']} != 68ch ({q['want']:.1f}px)")
                    break
            if w == 390 and p == "/":   # AC-25/39: every rendered chart text element >= 12px at 390
                small = [round(x, 2) for x in m["ctext"] if x < 11.995]
                if not m["ctext"] or small:
                    errs.append(f"{tag}: chart text below 12px: {small[:5]} ({len(small)} of {len(m['ctext'])})")
            if p == "/methodology/" and w == 390:   # AC-5 at 390: number and h2 on one line; every paragraph full content width (+-1px)
                for i, st in enumerate(m["steps"]):
                    if st["beforeRow"] != "1" or abs(st["h2Top"]) > 1 or st["h2Left"] < 8:
                        errs.append(f"{tag}: step {i + 1} number and h2 not on one line: {st}")
                    if not st["pw"] or any(abs(x - st["inner"]) > 1 for x in st["pw"]):
                        errs.append(f"{tag}: step {i + 1} paragraph width {st['pw']} != content width {st['inner']}")
            if p in ("/", "/prices/", "/methodology/", "/data/", "/disclosures/"):
                lim = 420 if w >= 768 else 560
                if m["ctaTop"] is None or m["ctaTop"] > lim:
                    errs.append(f"{tag}: hero CTA top {m['ctaTop']} > {lim}px")
            n += 1
    return n


SIGNUP = """(() => { const f = document.querySelector('form.awi-signup'); if (!f) return 'null';
const r = e => e.getBoundingClientRect(), lab = f.querySelector('label.signup-label'), inp = f.querySelector('input[name=email]'), b = f.querySelector('button[type=submit]');
const hp = f.querySelector('.signup-hp'), hr = r(hp), cs = getComputedStyle(b);
const vis = e => { const x = r(e); return x.width > 0 && x.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
return JSON.stringify({bottom: Math.max(r(lab).bottom, r(inp).bottom, r(b).bottom) + scrollY, labelVisible: vis(lab), labelText: lab.textContent,
  button: b.textContent, bg: cs.backgroundColor, fg: cs.color, hpOff: hr.right <= 0 || hr.left >= innerWidth, inputH: r(inp).height, buttonH: r(b).height}); })()"""


def _lum(rgb):
    v = [int(x) / 255 for x in re.findall(r"\d+", rgb)[:3]]
    v = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in v]
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]


def contrast(a, b):
    x, y = sorted((_lum(a), _lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def press_tab(cdp):
    for t in ("rawKeyDown", "keyUp"):
        cdp.call("Input.dispatchKeyEvent", type=t, key="Tab", code="Tab", windowsVirtualKeyCode=9, nativeVirtualKeyCode=9)


def press_enter(cdp):
    cdp.call("Input.dispatchKeyEvent", type="rawKeyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, nativeVirtualKeyCode=13)
    cdp.call("Input.dispatchKeyEvent", type="char", text="\r", key="Enter")
    cdp.call("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13, nativeVirtualKeyCode=13)


def check_signup(cdp, base, errs):
    """AWI-SIGNUP-FORM-001 AC 14: the first form's label, input and Subscribe button end inside the top 800px at 1280x800
    (and 844px at 390x844) on / and /newsletter/, label visible, honeypot off-screen. AC 16: button text/background contrast
    >= 4.5:1 (the site's standard, same --acc/--on-acc pair as every .btn) in both schemes; keyboard only: Tab reaches the
    email input then the Subscribe button and never the honeypot; Enter on an invalid address announces the error in the
    aria-live status (client-side, no request is sent)."""
    n = 0
    for w, h in ((1280, 800), (390, 844)):
        for scheme in ("dark", "light"):
            for p in ("/", "/newsletter/"):
                open_page(cdp, base, p, w, h, scheme)
                m = json.loads(cdp.js(SIGNUP)); tag = f"{p} @{w}x{h} {scheme}"
                if not m:
                    errs.append(f"{tag}: no signup form"); continue
                if m["bottom"] > min(h, 800) + 0.5:
                    errs.append(f"{tag}: signup form ends at {m['bottom']:.0f}px, below the first screenful")
                if not m["labelVisible"] or m["labelText"] != "Email address" or m["button"] != "Subscribe":
                    errs.append(f"{tag}: label/button wrong: {m}")
                if not m["hpOff"]:
                    errs.append(f"{tag}: honeypot is on screen")
                if m["inputH"] < 43.5 or m["buttonH"] < 43.5:
                    errs.append(f"{tag}: input/button below the 44px tap target")
                c = contrast(m["bg"], m["fg"])
                if c < 4.5:
                    errs.append(f"{tag}: Subscribe contrast {c:.2f} < 4.5")
                n += 1
    for p in ("/", "/newsletter/"):
        open_page(cdp, base, p, 1280, 800, "dark")
        seq = []
        for _ in range(40):
            press_tab(cdp)
            seq.append(cdp.js("(() => { const a = document.activeElement; return (a.name || a.tagName) + '|' + (a.closest('form.awi-signup') ? 'f' : '') })()"))
            if seq[-1] == "BUTTON|f":
                break
        if "website|f" in seq or "email|f" not in seq or seq[-1] != "BUTTON|f" or seq.index("email|f") != len(seq) - 2:
            errs.append(f"{p}: keyboard order to the form wrong: {seq[-4:]}")
        cdp.js("(() => { const i = document.querySelector('form.awi-signup input[name=email]'); i.value = 'a@b'; i.focus(); return 1 })()")
        press_enter(cdp)
        time.sleep(0.2)
        st = json.loads(cdp.js("(() => { const f = document.querySelector('form.awi-signup'); const s = f.querySelector('.signup-status'); return JSON.stringify({t: s.textContent, live: s.getAttribute('aria-live'), inv: f.querySelector('input[name=email]').getAttribute('aria-invalid'), url: location.pathname}); })()"))
        if st["t"] != "That email doesn't look right. Check it and try again." or st["live"] != "polite" or st["inv"] != "true" or st["url"] != p:
            errs.append(f"{p}: invalid email not announced inline: {st}")
        n += 1
    return n


# Stand-in for gc.zgo.at/count.js (the box has no network): it beacons a superset of what GoatCounter sends -- the
# path through the page's own window.goatcounter.path, plus search, hash, referrer and title -- to the data-goatcounter endpoint.
GC_STUB = """(function(){var g=window.goatcounter||{};var p=location.pathname+location.search+location.hash;if(typeof g.path==='function')p=g.path(p);
var s=document.querySelector('script[data-goatcounter]');var ep=(s&&s.getAttribute('data-goatcounter'))||'https://gc.zgo.at/count';
new Image().src=ep+'?p='+encodeURIComponent(p)+'&r='+encodeURIComponent(document.referrer)+'&t='+encodeURIComponent(document.title)+'&u='+encodeURIComponent(location.href);})();"""


def check_signup_goatcounter(cdp, errs):
    """AWI-SIGNUP-FORM-001 R3 (AC 13 / AC 15 locally): with tests/signup/dev_server.mjs (dist/ + the real /api/subscribe on mocks),
    (a) with gc.zgo.at blocked the form still submits, with JS on (inline status) and with JS off (303 to /newsletter/thanks/<status>/),
    and a row is stored for each; (b) with GoatCounter allowed (stub count.js), no request to any non-local host carries the email
    (raw, URL-encoded or lowercased) in its URL, path, query, Referer or body, while beacons do fire (incl. the thanks page)."""
    proc = subprocess.Popen(["node", str(R / "tests/signup/dev_server.mjs")], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, start_new_session=True)
    seen, mode = [], {"block": True}

    def hook(c, m):
        if m.get("method") != "Fetch.requestPaused":
            return
        p = m["params"]; rq = p["request"]; url = rq["url"]; rid = p["requestId"]
        if url.startswith(base) or not url.startswith(("http:", "https:")):   # local server, chrome-extension:// internals
            c.send("Fetch.continueRequest", requestId=rid)
            return
        seen.append({"url": url, "referer": rq.get("headers", {}).get("Referer", ""), "body": rq.get("postData", ""), "blocked": mode["block"]})
        if mode["block"]:
            c.send("Fetch.failRequest", requestId=rid, errorReason="BlockedByClient")
        else:
            body = GC_STUB if url.endswith("count.js") else ""
            c.send("Fetch.fulfillRequest", requestId=rid, responseCode=200,
                   responseHeaders=[{"name": "Content-Type", "value": "text/javascript" if body else "image/gif"}], body=base64.b64encode(body.encode()).decode())

    def rows():
        with urllib.request.urlopen(base + "/__rows", timeout=10) as r:
            return json.loads(r.read())["rows"]

    def submit(path, email, js_on):
        cdp.call("Emulation.setScriptExecutionDisabled", value=not js_on)
        cdp.events.clear()
        cdp.call("Page.navigate", url=base + path)
        try:
            cdp.wait_event("Page.loadEventFired")
        except (TimeoutError, OSError) as ex:
            raise RuntimeError(f"R3 {path}: no load; events={cdp.events[-20:]} paused={len(seen)} send_errors={getattr(cdp, 'send_errors', [])}") from ex
        root = cdp.call("DOM.getDocument")["root"]["nodeId"]
        node = cdp.call("DOM.querySelector", nodeId=root, selector="form.awi-signup input[name=email]")["nodeId"]
        cdp.call("DOM.focus", nodeId=node)
        cdp.call("Input.insertText", text=email)
        cdp.events.clear()
        press_enter(cdp)
        if not js_on:
            cdp.wait_event("Page.loadEventFired")
            # reload the landing page with JS on, so GoatCounter (when allowed) runs there with the real document.referrer
            cdp.call("Emulation.setScriptExecutionDisabled", value=False)
            cdp.events.clear(); cdp.call("Page.reload"); cdp.wait_event("Page.loadEventFired")
        else:
            cdp.js("new Promise(r => { const t0 = Date.now(); (function w() { const s = document.querySelector('.signup-status');"
                   " if ((s && s.textContent.trim()) || Date.now() - t0 > 8000) r(); else setTimeout(w, 100); })(); })")
        time.sleep(0.6)
        hist = cdp.call("Page.getNavigationHistory"); url = hist["entries"][hist["currentIndex"]]["url"]
        cdp.call("Emulation.setScriptExecutionDisabled", value=False)
        txt = cdp.js("(() => { const s = document.querySelector('.signup-status, .signup-result'); return s ? s.textContent : '' })()")
        return url, txt

    n = 0
    try:
        line = proc.stdout.readline()
        base = f"http://127.0.0.1:{int(line.split()[1])}"
        cdp.hook = hook
        cdp.call("Fetch.enable", patterns=[{"urlPattern": "*"}])
        cdp.call("Emulation.setDeviceMetricsOverride", width=1280, height=800, deviceScaleFactor=1, mobile=False)
        ok_msg = "Check your inbox to confirm your subscription."
        flows = [("/", "Kitty.Blocked+js@Example.COM", True, True), ("/newsletter/", "kitty.blocked.nojs@example.com", False, True),
                 ("/", "Kitty.Leak+js@Example.COM", True, False), ("/newsletter/", "kitty.leak.nojs@example.com", False, False)]
        for path, email, js_on, block in flows:
            mode["block"] = block
            before = len(rows())
            url, txt = submit(path, email, js_on)
            tag = f"{path} js={'on' if js_on else 'off'} gc={'blocked' if block else 'stubbed'}"
            want_url = base + path if js_on else base + "/newsletter/thanks/pending_confirmation/"
            if url != want_url or txt.strip() != ok_msg:
                errs.append(f"{tag}: signup did not complete: url={url} text={txt!r}")
            if len(rows()) != before + 1:
                errs.append(f"{tag}: no row stored")
            if js_on is False:   # no-JS: the landing page must also load GoatCounter normally (when allowed), so the leak check covers it
                time.sleep(0.4)
            n += 1
        gc = [x for x in seen if not x["blocked"]]
        if not any("goatcounter" in x["url"] and "thanks" in x["url"] for x in gc) or not any(x["url"].endswith("count.js") for x in gc):
            errs.append(f"GoatCounter beacons did not fire with gc allowed (test would be vacuous): {[x['url'][:80] for x in gc]}")
        if not any(x["blocked"] and "gc.zgo.at" in x["url"] for x in seen):
            errs.append("gc.zgo.at was never requested while blocked (block test vacuous)")
        for _, email, _, _ in flows:
            forms = {email, email.lower(), email.split("@")[0] + "@" + email.split("@")[1].lower()}
            forms |= {urllib.parse.quote(f, safe="") for f in list(forms)} | {urllib.parse.quote_plus(f) for f in list(forms)} | {email.split("@")[0]}
            for x in seen:
                blob = urllib.parse.unquote(x["url"]) + " " + x["url"] + " " + x["referer"] + " " + x["body"]
                hit = [f for f in forms if f and f in blob]
                if hit:
                    errs.append(f"third-party request carries the email: {x['url'][:120]} (matched {hit[0]!r})")
        others = sorted({urllib.parse.urlsplit(x["url"]).hostname for x in seen} - {"gc.zgo.at", "openmillage.goatcounter.com"})
        if others:
            errs.append(f"unexpected third-party hosts requested: {others}")
        print(f"browser_check: GoatCounter (R3): {n} submits ok with gc.zgo.at blocked/stubbed, JS on/off; {len(seen)} third-party requests, 0 carry the email"
              if not errs else "browser_check: GoatCounter (R3): see failures")
    finally:
        cdp.hook = None
        try:
            cdp.call("Fetch.disable")
        except Exception:
            pass
        try:
            os.killpg(proc.pid, signal.SIGTERM); proc.wait(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(proc.pid, signal.SIGKILL); proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                pass
    return n


def main():
    if not Path(CHROME).exists():
        print("browser_check: SKIP (google-chrome not installed)")
        return 0
    if not (D / "index.html").exists():
        print("browser_check: dist/ missing; run python3 build.py first", file=sys.stderr)
        return 2
    prof = tempfile.mkdtemp(prefix="awi-chrome.")
    shots = Path(tempfile.mkdtemp(prefix="awi-shots."))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(D)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    chrome, ws, errs = None, None, []
    try:
        chrome = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                                   "--remote-debugging-port=0", "--remote-allow-origins=*", f"--user-data-dir={prof}", "about:blank"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        port_file = Path(prof) / "DevToolsActivePort"
        for _ in range(100):
            if port_file.exists() and len(port_file.read_text().split()) >= 2:
                break
            time.sleep(0.1)
        port = int(port_file.read_text().split()[0])
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("PUT", "/json/new?about:blank")
        target = json.loads(c.getresponse().read())
        ws = WS("127.0.0.1", port, target["webSocketDebuggerUrl"].split(f":{port}", 1)[1])
        cdp = Cdp(ws)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        n = check_charts(cdp, base, errs)
        nf = check_fonts(cdp, base, errs)
        ng = check_rename_geometry(cdp, base, errs)
        check_readability(cdp, base, shots, errs)
        nl = check_layout(cdp, base, errs)
        nsu = check_signup(cdp, base, errs)
        check_signup_goatcounter(cdp, errs)
        print(f"browser_check: {n} chart/viewport/scheme combinations checked; readability checked on {len(PAGES)} pages x 2 schemes at 390px")
        print(f"browser_check: one non-title Inter chart text element rendered with Inter (no fallback) in {nf} chart/viewport/scheme cases; id-rename text+geometry equal in {ng}")
        print(f"browser_check: layout (header <= 88px at 390, Methodology grid, hero CTA fold) checked on {nl} page/viewport cases")
        print(f"browser_check: signup form (first screenful, label, Subscribe, honeypot off-screen, contrast, keyboard, aria-live error) checked in {nsu} cases")
        if os.environ.get("AWI_KEEP_SHOTS") == "1":
            print(f"browser_check: screenshots (390 and 1440) for a human readability check: {shots}")
    finally:
        if ws:
            ws.close()
        if chrome:
            try:
                os.killpg(chrome.pid, signal.SIGTERM)
                chrome.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(chrome.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(prof, ignore_errors=True)
        if os.environ.get("AWI_KEEP_SHOTS") != "1":
            shutil.rmtree(shots, ignore_errors=True)
    for m in errs:
        print("BROWSER FAIL:", m, file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
