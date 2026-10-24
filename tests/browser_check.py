"""Headless-Chrome checks of the built dist/ (AC14 served bytes, AC16, AC17, mobile readability). Stdlib only.

Serves dist/ from a local HTTP server on a free port, starts Chrome with one throwaway --user-data-dir, and drives it
over the DevTools protocol with a minimal websocket client. Chrome, its profile directory and the server are always
cleaned up (try/finally). Screenshots (390 and 1440 wide, every page) go to a temp directory OUTSIDE the repo; its path
is printed for the human readability check. Prints SKIP and exits 0 when Chrome is not installed.

Run after `python3 build.py`:  python3 -m tests.browser_check
"""
import base64, hashlib, http.client, json, os, shutil, signal, socket, struct, subprocess, sys, tempfile, threading, time, urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / "dist"
CHROME = shutil.which("google-chrome") or "/usr/bin/google-chrome"
PINS = json.loads((R / "pins.json").read_text())
PAGES = ["/", "/prices/", "/methodology/", "/data/", "/disclosures/", "/sponsors/", "/newsletter/", "/tell-us/"]
CHARTS = {"chart-pass-rate": "pass-rate", "chart-cost": "cost-per-success"}
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

    def call(self, method, **params):
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
  out[id] = [...fig.querySelectorAll('img')].map(i => { const cs = getComputedStyle(i), r = i.getBoundingClientRect();
    return {src: i.getAttribute('src'), currentSrc: i.currentSrc, display: cs.display, visible: cs.display !== 'none' && i.offsetParent !== null && r.width > 0,
            top: r.top + scrollY, bottom: r.bottom + scrollY, left: r.left, right: r.right, width: r.width, nw: i.naturalWidth}; }); }
return JSON.stringify(out); })()"""
REVEAL = """(() => { for (const i of document.querySelectorAll('.chart img')) { if (getComputedStyle(i).display !== 'none' && !(i.complete && i.naturalWidth > 0)) { i.scrollIntoView({block: 'center'}); return 0; } } return 1; })()"""
READ = """(() => { const sel = 'nav.top a, .site-footer a, button, summary, .btn';
const small = [...document.querySelectorAll(sel)].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.height < 43.99; }).map(e => e.tagName + ' ' + (e.textContent || '').trim().slice(0, 30) + ' h=' + e.getBoundingClientRect().height.toFixed(1));
return JSON.stringify({scrollWidth: document.documentElement.scrollWidth, bodyScrollWidth: document.body.scrollWidth, font: parseFloat(getComputedStyle(document.body).fontSize), small}); })()"""


def open_page(cdp, base, path, width, height, scheme, theme=None):
    cdp.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
    cdp.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": scheme}])
    cdp.events.clear()
    cdp.call("Page.navigate", url=base + path)
    cdp.wait_event("Page.loadEventFired")
    if theme:
        cdp.js(f"document.documentElement.setAttribute('data-theme','{theme}')")


def measure_charts(cdp):
    cdp.js(REVEAL)
    for _ in range(120):   # up to ~30 s: a loaded box can be slow to decode the SVGs
        data = json.loads(cdp.js(MEASURE % json.dumps(list(CHARTS))))
        if all(i["nw"] > 0 for imgs in data.values() for i in imgs if i["visible"]):
            return data
        cdp.js(REVEAL)
        time.sleep(0.25)
    return data


def check_charts(cdp, base, errs):
    n = 0
    cases = [(w, h, s, None) for (w, h) in VIEWPORTS for s in ("dark", "light")] + [(1440, 900, "dark", "light"), (1440, 900, "light", "dark"), (390, 844, "dark", "light")]
    for w, h, scheme, theme in cases:
        open_page(cdp, base, "/", w, h, scheme, theme)
        data = measure_charts(cdp)
        eff = theme or scheme
        size = 720 if w >= 768 else 350
        for cid, name in CHARTS.items():
            vis = [i for i in data[cid] if i["visible"]]
            tag = f"{cid} @{w} {scheme}{'+data-theme=' + theme if theme else ''}"
            if len(vis) != 1:
                errs.append(f"{tag}: {len(vis)} visible variants, expected 1")
                continue
            want = f"/assets/charts/awi-{name}-{size}-{eff}.svg"
            got = vis[0]["src"]
            if got != want:
                errs.append(f"{tag}: visible {got}, expected {want}")
            served = sha_of_url(base, got)
            pin = PINS["charts_sha256"][got.rsplit("/", 1)[1]]["sha256"]
            if served != pin:
                errs.append(f"{tag}: served bytes of {got} differ from pinned sha256")
            if vis[0]["nw"] <= 0:
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
            cdp.js("document.querySelectorAll('img').forEach(i=>{i.loading='eager'}); 1")
            time.sleep(0.4)
            shot = cdp.call("Page.captureScreenshot", format="png", captureBeyondViewport=True)
            name = ("index" if p == "/" else p.strip("/")) + f"-{w}.png"
            (shots / name).write_bytes(base64.b64decode(shot["data"]))


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
        check_readability(cdp, base, shots, errs)
        print(f"browser_check: {n} chart/viewport/scheme combinations checked; readability checked on {len(PAGES)} pages x 2 schemes at 390px")
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
    for m in errs:
        print("BROWSER FAIL:", m, file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
