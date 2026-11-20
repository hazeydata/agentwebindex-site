#!/usr/bin/env python3
"""One-off: render src/og-card.png (1200x630), the link-preview image served at /og-card.png.
Colors come from the dark :root in src/style.css, fonts from src/fonts via @font-face, the brand mark from src/_layout.html,
the tagline from content/copy.md. Needs google-chrome (and nothing else); build.py just copies the committed PNG.
Chrome is driven over DevTools (reusing the stdlib client in tests/browser_check.py).
Usage: python3 tools/render_og_card.py"""
import base64, http.client, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
R = Path(__file__).resolve().parent.parent
TAGLINE = "Same frozen questions and URLs for every search, scrape and browser API."   # verbatim fragment of the Home: hero lede in content/copy.md

css = (R / "src/style.css").read_text()
root = css[css.index(":root {"):]; root = root[:root.index("}")]
c = dict(re.findall(r"--([a-z-]+): (#[0-9A-Fa-f]{6})", root))
assert TAGLINE in (R / "content/copy.md").read_text(), "tagline no longer in copy.md"
svg = re.search(r'<a class="brand"[^>]*>(<svg.*?</svg>)', (R / "src/_layout.html").read_text(), re.S).group(1)
faces = "".join(m.group(0).replace("/assets/fonts/", (R / "src/fonts").as_uri() + "/") for m in re.finditer(r"@font-face \{[^}]*\}", css))
page = f"""<!doctype html><meta charset="utf-8"><style>{faces}
html,body{{margin:0;width:1200px;height:630px}}
body{{background:radial-gradient(circle,rgba(169,184,201,.09) 1px,transparent 1.2px) 0 0/22px 22px,linear-gradient(135deg,{c['bg']} 0%,{c['surface']} 100%);
 color:{c['text']};font-family:"Space Grotesk",sans-serif;box-sizing:border-box;padding:80px 90px;display:flex;flex-direction:column;justify-content:center;border-left:12px solid {c['acc-tint']}}}
.brand{{display:flex;align-items:center;gap:28px;font:600 112px/1 "Space Grotesk",sans-serif;letter-spacing:.012em}}
.brand svg{{width:112px;height:112px;color:{c['text']}}} .brand-dot{{fill:{c['acc-tint']}}} b{{color:{c['acc-tint']};font-weight:600}}
p{{margin:56px 0 0;font:400 44px/1.35 Inter,sans-serif;color:{c['muted']};max-width:960px}}
</style><div class="brand">{svg}<span>AgentWeb<b>Index</b></span></div><p>{TAGLINE}</p>"""
sys.path.insert(0, str(R))
from tests.browser_check import WS, Cdp   # stdlib CDP client; `chrome --screenshot` hangs on the build box, so drive Chrome over DevTools instead
tmp = Path(tempfile.mkdtemp()); proc = None
try:
    (tmp / "card.html").write_text(page)
    proc = subprocess.Popen(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--hide-scrollbars",
                             "--remote-debugging-port=0", f"--user-data-dir={tmp/'profile'}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, env=dict(os.environ, TMPDIR=str(tmp)))
    port_file = tmp / "profile/DevToolsActivePort"
    for _ in range(200):
        if port_file.exists() and len(port_file.read_text().split()) >= 2: break
        time.sleep(0.1)
    port = int(port_file.read_text().split()[0])
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("PUT", "/json/new?about:blank")
    ws = json.loads(c.getresponse().read())["webSocketDebuggerUrl"]
    cdp = Cdp(WS("127.0.0.1", port, ws.split(f":{port}", 1)[1]))
    cdp.call("Page.enable")
    cdp.call("Emulation.setDeviceMetricsOverride", width=1200, height=630, deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url=(tmp / "card.html").as_uri()); cdp.wait_event("Page.loadEventFired")
    cdp.js("document.fonts.ready.then(() => document.fonts.size)")
    (tmp / "card.png").write_bytes(base64.b64decode(cdp.call("Page.captureScreenshot", format="png")["data"]))
    try:
        from PIL import Image   # optional: palette-quantize to keep the file small
        Image.open(tmp / "card.png").convert("RGB").quantize(64).save(R / "src/og-card.png", optimize=True)
    except ImportError:
        shutil.copy(tmp / "card.png", R / "src/og-card.png")
finally:
    if proc:
        try: os.killpg(proc.pid, 9)   # Chrome helpers share the process group
        except ProcessLookupError: pass
    shutil.rmtree(tmp)
print("wrote src/og-card.png", (R / "src/og-card.png").stat().st_size, "bytes")
