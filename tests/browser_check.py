"""Headless-Chrome checks of the built dist/ (AC14 served bytes, AC16, AC17, R9.2-R9.5, mobile readability). Stdlib only.

Serves dist/ from a local HTTP server on a free port, starts Chrome with one throwaway --user-data-dir, and drives it
over the DevTools protocol with a minimal websocket client. Chrome, its profile directory and the server are always
cleaned up (try/finally). Screenshots (390 and 1440 wide, every page) go to a temp directory OUTSIDE the repo, which is
deleted on exit; with AWI_KEEP_SHOTS=1 it is kept and its path is printed for the human readability check. Prints SKIP and exits 0 when Chrome is not installed.

Run after `python3 build.py`:  python3 -m tests.browser_check
"""
import base64, hashlib, http.client, json, os, re, shutil, signal, socket, struct, subprocess, sys, tempfile, threading, time, urllib.request
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
        self.addr = (host, port, path)   # kept so Cdp can reconnect to the same page target once
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

    def call(self, method, **params):
        try:
            return self._call(method, **params)
        except ConnectionError as ex:   # seen once under load: "websocket closed" at captureScreenshot. Reconnect to the same target, retry once.
            print(f"browser_check: {method}: {ex}; reconnecting to the same page and retrying once", file=sys.stderr)
            self.ws.close()
            self.ws = WS(*self.ws.addr)
            self._call("Page.enable")
            self._call("Runtime.enable")
            return self._call(method, **params)

    def _call(self, method, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == mid:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})
            if "method" in m:
                self.events.append(m["method"])

    def wait_event(self, name, timeout=20):
        end = time.time() + timeout
        while name not in self.events:
            if time.time() > end:
                raise TimeoutError(name)
            self.ws.s.settimeout(max(0.1, end - time.time()))
            m = json.loads(self.ws.recv())
            if "method" in m:
                self.events.append(m["method"])
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


RETEST_MIN_PX = 13


def check_retest_chart_390(cdp, scheme, errs):
    """The Apify retest chart is an <img>, so its text is measured as (smallest font-size in the served SVG) x (rendered width / viewBox width)."""
    r = json.loads(cdp.js("""(async () => { const i = document.querySelector('.retest-fig img'); i.loading = 'eager'; i.scrollIntoView();
      for (let k = 0; k < 50 && !(i.complete && i.naturalWidth); k++) await new Promise(f => setTimeout(f, 100));
      return JSON.stringify({src: i.currentSrc, w: i.getBoundingClientRect().width,
        pill: parseFloat(getComputedStyle(document.querySelector('.retest .pill')).fontSize)}); })()"""))
    print(f"browser_check: retest 'Preliminary' pill @390 {scheme}: {r['pill']}px")
    if r["pill"] < RETEST_MIN_PX:
        errs.append(f"retest pill @390 {scheme}: {r['pill']}px < {RETEST_MIN_PX}px")
    name = r["src"].rsplit("/", 1)[-1]
    if not name.endswith("-350.svg"):
        errs.append(f"retest chart @390 {scheme}: served {name}, not the 350px variant")
        return
    svg = (D / "assets/retest" / name).read_text()
    vbw = float(re.search(r'viewBox="0 0 ([\d.]+) ', svg).group(1))
    px = min(float(x) for x in re.findall(r"font-size: ([\d.]+)px", svg)) * r["w"] / vbw
    print(f"browser_check: retest chart @390 {scheme}: {name} rendered {r['w']:.1f}px wide, smallest text {px:.2f}px")
    if px < RETEST_MIN_PX:
        errs.append(f"retest chart @390 {scheme}: smallest text {px:.2f}px < {RETEST_MIN_PX}px")


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
            if p == "/":
                check_retest_chart_390(cdp, scheme, errs)
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
const f = document.querySelector('iframe.beehiiv-embed'); const fb = r(f); const box = f ? r(f.parentElement) : null;
const pad = f ? parseFloat(getComputedStyle(f.parentElement).paddingLeft) + parseFloat(getComputedStyle(f.parentElement).paddingRight) : 0;
const cta = document.querySelector('.cta-hero');
const vals = [...document.querySelectorAll('.rows .row .mono')].map(e => ({h: r(e).height, f: getComputedStyle(e).fontSize, ff: getComputedStyle(e).fontFamily}));
const probe = document.createElement('span'); probe.style.cssText = 'position:absolute;visibility:hidden;width:68ch';
const pw = [...document.querySelectorAll('main p:not(.headline)')].filter(p => p.offsetParent).map(p => { p.appendChild(probe); probe.style.font = getComputedStyle(p).font;
  const want = probe.getBoundingClientRect().width; probe.remove(); return {mw: getComputedStyle(p).maxWidth, want, cls: p.className}; });
const ctext = [...document.querySelectorAll('.ch svg text')].filter(t => t.getClientRects().length).map(t => parseFloat(getComputedStyle(t).fontSize) * t.getScreenCTM().a);
return JSON.stringify({pw, ctext, steps, vals, hpad: getComputedStyle(document.querySelector('.site-header .wrap')).paddingTop, header: r(document.querySelector('.site-header')).height, stepMin: ps.length ? Math.min(...ps) : null,
  iframe: f ? {w: fb.width, h: fb.height, inner: box.width - pad - 2, src: f.getAttribute('src'), loading: f.getAttribute('loading')} : null,
  ctaTop: cta ? r(cta).top + scrollY : null}); })()"""


def check_layout(cdp, base, errs):
    """AWI-PAGE-POLISH-001: header <= 88px at 390; Methodology paragraphs are not squeezed into the number column (P0);
    the signup iframe fills its box (width 100%, >= 240px tall) on /newsletter/ and at the end of Results (P0); hero CTA above the fold."""
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
            if p in ("/", "/newsletter/"):
                f = m["iframe"]
                if not f or f["h"] < 239.5 or abs(f["w"] - f["inner"]) > 1.5 or not f["src"] or f["loading"] == "lazy":
                    errs.append(f"{tag}: signup iframe not full-width / >=240px / eager: {f}")
            if p in ("/", "/prices/", "/methodology/", "/data/", "/disclosures/"):
                lim = 420 if w >= 768 else 560
                if m["ctaTop"] is None or m["ctaTop"] > lim:
                    errs.append(f"{tag}: hero CTA top {m['ctaTop']} > {lim}px")
            n += 1
    return n


CHROME_TMP_PREFIXES = ("com.google.Chrome.", ".com.google.Chrome.", ".org.chromium.", "scoped_dir")


def chrome_tmp_paths():
    """Existing Chrome scratch paths (com.google.Chrome.*, .com.google.Chrome.*, .org.chromium.*, scoped_dir*) in the
    system temp dirs. Read-only listing; never used to delete."""
    out = set()
    for d in {"/tmp", tempfile.gettempdir()}:
        try:
            out |= {os.path.join(d, n) for n in os.listdir(d) if n.startswith(CHROME_TMP_PREFIXES)}
        except OSError:
            pass
    return out


HYGIENE_OK = ("browser_check: temp hygiene OK: 0 new Chrome temp paths (com.google.Chrome.*, .com.google.Chrome.*, .org.chromium.*, "
              "scoped_dir*), no live Chrome process group; profile and Chrome TMPDIR removed")


def cleanup_errors(before, pgid, own_dirs):
    """All post-cleanup checks: new Chrome temp paths, a surviving Chrome process group, our own dirs still present."""
    errs = []
    left = sorted(chrome_tmp_paths() - before)
    if left:
        errs.append(f"run left {len(left)} new Chrome temp path(s) behind: {left}")
    if pgid is not None:
        try:
            os.killpg(pgid, 0)   # signal 0: existence probe only
            errs.append(f"Chrome process group {pgid} still alive after cleanup")
        except (ProcessLookupError, PermissionError):
            pass
    errs += [f"run left its own temp dir behind: {p}" for p in own_dirs if os.path.exists(p)]
    return errs


def report(errs):
    """Print BROWSER FAIL lines, or the hygiene OK line only when every check (cleanup included) passed."""
    for m in errs:
        print("BROWSER FAIL:", m, file=sys.stderr)
    if not errs:
        print(HYGIENE_OK)
    return 1 if errs else 0


def main():
    if not Path(CHROME).exists():
        print("browser_check: SKIP (google-chrome not installed)")
        return 0
    if not (D / "index.html").exists():
        print("browser_check: dist/ missing; run python3 build.py first", file=sys.stderr)
        return 2
    before = chrome_tmp_paths()
    # Every path this run creates is recorded here and only these exact paths are removed in finally.
    prof = tempfile.mkdtemp(prefix="awi-chrome.")
    ctmp = tempfile.mkdtemp(prefix="awi-chrome-tmp.")   # Chrome's own TMPDIR: its com.google.Chrome.* scratch lands here
    shots = Path(tempfile.mkdtemp(prefix="awi-shots."))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(D)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    chrome, ws, cdp, errs = None, None, None, []
    try:
        chrome = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                                   "--remote-debugging-port=0", "--remote-allow-origins=*", f"--user-data-dir={prof}", "about:blank"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
                                  env=dict(os.environ, TMPDIR=ctmp, TMP=ctmp, TEMP=ctmp))
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
        print(f"browser_check: {n} chart/viewport/scheme combinations checked; readability checked on {len(PAGES)} pages x 2 schemes at 390px")
        print(f"browser_check: one non-title Inter chart text element rendered with Inter (no fallback) in {nf} chart/viewport/scheme cases; id-rename text+geometry equal in {ng}")
        print(f"browser_check: layout (header <= 88px at 390, Methodology grid, signup iframe, hero CTA fold) checked on {nl} page/viewport cases")
        if os.environ.get("AWI_KEEP_SHOTS") == "1":
            print(f"browser_check: screenshots (390 and 1440) for a human readability check: {shots}")
    finally:
        if cdp:
            ws = cdp.ws   # the reconnect retry may have replaced it
        if ws:
            try:
                Cdp(ws)._call("Browser.close")   # graceful close first, so Chrome removes its own scratch (no reconnect here)
            except Exception:
                pass
            ws.close()
        if chrome:
            try:
                chrome.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
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
        shutil.rmtree(ctmp, ignore_errors=True)
        if os.environ.get("AWI_KEEP_SHOTS") != "1":
            shutil.rmtree(shots, ignore_errors=True)
    errs += cleanup_errors(before, chrome.pid if chrome else None, (prof, ctmp))
    return report(errs)


if __name__ == "__main__":
    sys.exit(main())
