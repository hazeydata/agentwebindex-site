#!/usr/bin/env python3
"""Minimal static generator.
Site repo build: reads ONLY the vendored data/ copy (refresh with ./sync_data.sh) plus content/copy.md, content/chart-alt.md
and src/charts (vendored at the commits pinned in pins.json).
Guards first: pins.check() fails the build (non-zero exit) on the pre-Phase-0 data pin, a Tavily input date in the pinned pricing.yaml before pins.json phase0_date (R8),
or when the vendored data, copy or chart SVG bytes differ from pins.json.
src/*.html (slot templates filled by render.py) wrapped in src/_layout.html -> dist/<page>/index.html;
chart SVGs (byte-identical) -> dist/assets/charts and inlined into / (prolog removed, ids prefixed; build fails on duplicate ids), src/fonts (woff2 + OFL-*.txt) -> dist/assets/fonts; data/ (minus data/cache and data/_upstream) -> dist/data;
generates dist/data/prices.csv + prices.json from data/prices/history/*.jsonl and dist/data/benchmarks/latest.csv;
llms.txt, robots.txt, sitemap.xml; reads site.config.json."""
import csv, html, json, re, shutil, sys
from pathlib import Path
R=Path(__file__).resolve().parent; S=R/"src"; D=R/"dist"
sys.path.insert(0,str(R))
import copydoc, pins as pinmod, prices as P, render
errs=pinmod.check(R)
if errs:
    sys.exit("build failed: pin check\n  "+"\n  ".join(errs))
PINS=pinmod.load(R)
cfg=json.loads((R/"site.config.json").read_text()) if (R/"site.config.json").exists() else {}
SITE_URL=(cfg.get("site_url") or "https://agentwebindex.com").rstrip("/")
UP=R/"data"/"_upstream"   # vendored copies of agentwebindex collectors/providers.json, bench/tos_matrix.yaml, bench/pricing.yaml (see sync_data.sh)
PROVIDERS=UP/"providers.json"; PRICING=UP/"pricing.yaml"
EXCLUSION_PUBLIC=("provider","reason","quote","terms_url","checked_at")  # allowlist: only these exclusion fields are published

SIGNUP=cfg.get("signup") or {}

def signup_form(prefix, page):
    """First-party signup form (AWI-SIGNUP-FORM-001): same-origin POST to /api/subscribe (functions/api/subscribe.js).
    Works without JS (303 to /newsletter/thanks/<status>/); /signup.js upgrades it to an inline aria-live message.
    The honeypot `website` is off-screen, aria-hidden and tabindex=-1 (AC 4). No third-party script or iframe (AC 13)."""
    p = html.escape(prefix, quote=True)
    return (f'<form class="awi-signup" method="post" action="/api/subscribe" novalidate data-signup>'
            f'<label class="signup-label" for="{p}-email">Email address</label>'
            f'<div class="signup-row"><input id="{p}-email" name="email" type="email" autocomplete="email" inputmode="email" required maxlength="254" '
            f'aria-describedby="{p}-status"><button class="btn" type="submit">Subscribe</button></div>'
            f'<input type="hidden" name="page" value="{html.escape(page, quote=True)}">'
            f'<div class="signup-hp" aria-hidden="true"><label for="{p}-website">Website</label>'
            f'<input id="{p}-website" name="website" type="text" tabindex="-1" autocomplete="off" value=""></div>'
            f'<p id="{p}-status" class="signup-status" role="status" aria-live="polite"></p>'
            f'<p class="signup-privacy">{html.escape(SIGNUP.get("privacy") or "")}</p></form>')

def signup_js():
    """dist/signup.js: src/signup.js with the status copy from site.config.json "signup" (same copy as signup/config.js; AC 7 drift test)."""
    return (S/"signup.js").read_text().replace("/*MESSAGES*/{}", json.dumps(SIGNUP.get("messages") or {}, ensure_ascii=False))

def page_head(title, desc, path):
    u = html.escape(SITE_URL + path); t = html.escape(f"{title} · AgentWebIndex"); d = html.escape(desc)
    return (f'<meta name="description" content="{d}"><link rel="canonical" href="{u}"><link rel="icon" href="/favicon.svg" type="image/svg+xml">'
            f'<meta property="og:title" content="{t}"><meta property="og:description" content="{d}"><meta property="og:url" content="{u}"><meta property="og:type" content="website">')

def price_exports():
    rows=[]; provs={p["id"]:p for p in json.loads(PROVIDERS.read_text())["providers"]}
    for f in sorted((R/"data/prices/history").glob("*.jsonl")) if (R/"data/prices/history").exists() else []:
        for line in f.read_text().splitlines():
            if not line.strip(): continue
            h=json.loads(line); pid=f.stem; p=provs.get(pid,{})
            base={"provider":pid,"name":p.get("name",pid),"pricing_url":p.get("pricing_url"),"fetched_at":h["fetched_at"],
                  "status":h["status"],"text_sha256":h.get("text_sha256"),"changed":h.get("changed")}
            rows.append(base|{"prices_found":h.get("prices_found",[]),"prices_added":h.get("prices_added",[]),"prices_removed":h.get("prices_removed",[]),"error":h.get("error")})
    (D/"data").mkdir(exist_ok=True)
    (D/"data/prices.json").write_text(json.dumps({"rows":rows,"note":"Amounts are raw strings as found on each pricing page; not normalized."},indent=1))
    with open(D/"data/prices.csv","w",newline="") as fh:
        w=csv.writer(fh); w.writerow(["provider","name","pricing_url","fetched_at","status","changed","text_sha256","price_on_page","error"])
        for r in rows:
            for amt in (r["prices_found"] or [""]):
                w.writerow([r["provider"],r["name"],r["pricing_url"],r["fetched_at"],r["status"],r["changed"],r["text_sha256"],amt,r["error"] or ""])
    return len(rows)

def bench_csv():
    """dist/data/benchmarks/latest.csv: the latest week's table rows, values copied from latest.json (which traces to run logs)."""
    src = R/"data/benchmarks/latest.json"
    if not src.exists(): return 0
    doc = json.loads(src.read_text()); v = lambda x: (x or {}).get("v") if isinstance(x, dict) else x
    cols = ["category","provider","run_date","set","set_sha","flags","attempted","passed","failed","rate_limited_free_tier","success_rate","p50_latency_ms",
            "entry_tier","entry_tier_cost_per_1k","entry_tier_cost_per_successful_1k","volume_tier","volume_tier_cost_per_1k","volume_tier_cost_per_successful_1k","free_quota_note"]
    out = D/"data/benchmarks/latest.csv"; out.parent.mkdir(parents=True, exist_ok=True); n = 0
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(cols)
        for cat, rows in (doc.get("tables") or {}).items():
            for r in rows:
                if r.get("mock") or v(r.get("attempted")) is None: continue
                w.writerow([cat, r["provider"], r.get("run_date",""), r["set"], r.get("set_sha",""), "; ".join(r.get("flags") or []),
                            v(r["attempted"]), v(r["passed"]), v(r["failed"]), v(r.get("rate_limited")) or 0, v(r["success_rate"]), v(r["p50_latency_ms"]),
                            (r.get("entry_tier_cost_per_1k") or {}).get("tier") or "", v(r.get("entry_tier_cost_per_1k")), v(r.get("entry_tier_cost_per_successful_1k")),
                            (r.get("volume_tier_cost_per_1k") or {}).get("tier") or "", v(r.get("volume_tier_cost_per_1k")), v(r.get("volume_tier_cost_per_successful_1k")),
                            r.get("free_quota_note") or ""]); n += 1
    return n

shutil.rmtree(D,ignore_errors=True); D.mkdir()
layout=(S/"_layout.html").read_text(); pages=[]
ctx=type("Ctx",(),{})()
ctx.latest=json.loads((R/"data/benchmarks/latest.json").read_text()); ctx.pricing=P.load_pricing(PRICING)
ctx.providers=json.loads(PROVIDERS.read_text())["providers"]; ctx.doc=copydoc.load(); ctx.alt=copydoc.alt_texts()
ctx.pins=PINS; ctx.signup_form=signup_form; ctx.charts=S/"charts"; ctx.content=R/"content"
SLOTS=render.slots(ctx); META=render.page_meta(ctx); FOOTER=render.footer_html(ctx)
for f in sorted(S.glob("*.html")):
    if f.name.startswith("_"): continue
    body=f.read_text()
    for k,val in SLOTS.items(): body=body.replace("{{%s}}"%k,val)
    assert "{{" not in body, f"unfilled slot in {f.name}"
    title,desc=META[f.stem]
    path="/" if f.stem=="index" else f"/{f.stem}/"; pages.append(path)
    out=D/"index.html" if f.stem=="index" else D/f.stem/"index.html"; out.parent.mkdir(exist_ok=True)
    page=layout.replace("{{title}}",html.escape(title)).replace("{{head}}",page_head(title,desc,path)).replace("{{nav}}",render.nav_html(path)).replace("{{footer}}",FOOTER).replace("{{body}}",body)
    dups=render.duplicate_ids(page)
    if dups: sys.exit(f"build failed: duplicate id attributes on {path}: {dups[:10]}")   # R9.3
    out.write_text(page)
pages.sort(key=lambda p:(p!="/",p))
(D/"robots.txt").write_text("User-agent: *\nAllow: /\n"+"".join(f"Allow: {p}\n" for p in pages if p!="/")+f"Sitemap: {SITE_URL}/sitemap.xml\n")
(D/"sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+"".join(f"<url><loc>{SITE_URL}{p}</loc></url>\n" for p in pages)+"</urlset>\n")
for a in ("style.css","app.js","favicon.svg"): shutil.copy(S/a,D/a)
(D/"signup.js").write_text(signup_js())
def thanks_pages():
    """dist/newsletter/thanks/<status>/: the no-JS landing page per /api/subscribe status (noindex, not in the sitemap)."""
    back=html.escape(SIGNUP.get("thanks_back") or "Back")
    for st,msg in (SIGNUP.get("messages") or {}).items():
        path=f"/newsletter/thanks/{st}/"; out=D/"newsletter"/"thanks"/st/"index.html"; out.parent.mkdir(parents=True,exist_ok=True)
        body=(f'<section class="hero"><div class="wrap"><div class="col"><p class="kicker">Newsletter</p><h1>Newsletter</h1>'
              f'<p class="lede signup-result" role="status" data-status="{st}">{html.escape(msg)}</p><p><a href="/newsletter/">{back}</a></p></div></div></section>')
        out.write_text(layout.replace("{{title}}","Newsletter").replace("{{head}}",page_head("Newsletter",msg,path)+'<meta name="robots" content="noindex">')
                       .replace("{{nav}}",render.nav_html(path)).replace("{{footer}}",FOOTER).replace("{{body}}",body))
thanks_pages()
shutil.copytree(S/"fonts",D/"assets"/"fonts")
shutil.copytree(S/"retest",D/"assets"/"retest")   # Apify retest chart, byte-identical (pinned by content/retest-apify-2026-10-26.json)
shutil.copytree(S/"charts",D/"assets"/"charts")   # byte-identical copies of the 8 pinned chart SVGs only (fonts live in assets/fonts)
if (R/"data").exists(): shutil.copytree(R/"data",D/"data",ignore=lambda d,n:[x for x in n if x in ("cache","_upstream")],dirs_exist_ok=True)
def public_bench():
    """Published latest.json: exclusions reduced to EXCLUSION_PUBLIC; the vendored data/ copy is left unchanged."""
    p=D/"data/benchmarks/latest.json"
    if not p.exists(): return
    d=json.loads(p.read_text()); d["exclusions"]=[{k:x[k] for k in EXCLUSION_PUBLIC if k in x} for x in d.get("exclusions") or []]
    p.write_text(json.dumps(d,indent=1))
public_bench()
n=price_exports(); nb=bench_csv()
(D/"llms.txt").write_text("# AgentWebIndex\nMachine-readable data: /data/benchmarks/latest.json, /data/benchmarks/latest.csv (CC BY 4.0), /data/prices.json, /data/prices.csv, /data/prices/<provider>.json\nPages: /, /prices/, /methodology/, /data/, /sponsors/, /disclosures/, /newsletter/, /tell-us/\n")
print("built",D,"price rows:",n,"benchmark csv rows:",nb)
