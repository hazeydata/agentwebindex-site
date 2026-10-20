#!/usr/bin/env python3
"""Minimal static generator.
Site repo build: reads ONLY the vendored data/ copy (refresh with ./sync_data.sh).
src/*.html wrapped in _layout.html -> dist/<page>/index.html; data/ (minus data/cache) -> dist/data;
generates dist/data/prices.csv + prices.json from data/prices/history/*.jsonl; reads site.config.json."""
import csv, html, json, re, shutil
import render
from pathlib import Path
R=Path(__file__).resolve().parent; S=R/"src"; D=R/"dist"
cfg=json.loads((R/"site.config.json").read_text()) if (R/"site.config.json").exists() else {}
SITE_URL=(cfg.get("site_url") or "https://agentwebindex.com").rstrip("/")
UP=R/"data"/"_upstream"   # vendored copies of agentwebindex collectors/providers.json, bench/tos_matrix.yaml, bench/pricing.yaml (see sync_data.sh)
PROVIDERS=UP/"providers.json"; PRICING=UP/"pricing.yaml"

def newsletter_slot():
    url=(cfg.get("beehiiv_embed_url") or "").strip()
    m=re.match(r"https://subscribe-forms\.beehiiv\.com/([0-9a-f-]{36})/?$",url)
    if m:   # official beehiiv script embed, plain link fallback without JS
        fid=m.group(1); u=html.escape(url)
        return (f'<div id="beehiiv-embed" data-test-id="beehiiv-embed"><script async src="https://subscribe-forms.beehiiv.com/v3/loader.js" '
                f'data-beehiiv-form="{fid}"></script><noscript><a href="{u}">Subscribe to the newsletter</a></noscript></div>')
    if url.startswith("https://"):
        return (f'<iframe id="beehiiv-embed" src="{html.escape(url)}" data-test-id="beehiiv-embed" '
                'width="100%" height="320" frameborder="0" scrolling="no" style="border:0;max-width:100%"></iframe>')
    return ('<form id="signup" onsubmit="return false" aria-disabled="true"><input type="email" placeholder="you@example.com" disabled>'
            '<button disabled>Coming soon</button></form><p class="muted">Placeholder: no form endpoint is connected and nothing is submitted.</p>')

def exclusion_note():
    """Static note (rendered at build time from bench/tos_matrix.yaml) for providers whose terms forbid benchmarking."""
    p = UP / "tos_matrix.yaml"
    if not p.exists(): return ""
    txt = p.read_text(); tos = json.loads("\n".join(l for l in txt.splitlines() if not l.lstrip().startswith("#")))["providers"]
    names = {x["id"]: x["name"] for x in json.loads(PROVIDERS.read_text())["providers"]}
    items = [(pid, t) for pid, t in sorted(tos.items()) if (t.get("benchmarking") or {}).get("status") == "forbidden"]
    if not items: return ""
    li = "".join(f'<li><b>{html.escape(names.get(pid, pid))}</b> is excluded from benchmark tables: its terms forbid benchmarking ('
                 f'{html.escape(t["benchmarking"].get("quote") or "")}; <a href="{html.escape(t.get("terms_url") or "")}">terms</a>, checked {html.escape(str(t.get("checked_at")))}). '
                 f'It still appears on the <a href="/prices/">prices</a> page.'
                 + (f' <span class="muted">Note: {html.escape(t["note"])}</span>' if t.get("note") else "") + '</li>' for pid, t in items)
    return f'<div id="exclusions" class="note"><h3>Excluded providers</h3><ul>{li}</ul></div>'

def _money(x): return f"${x:,.4f}".rstrip("0").rstrip(".") if isinstance(x,(int,float)) else None

def price_label(t):
    if _money(t.get("unit_price")): return f"{_money(t['unit_price']*1000)} per 1k requests"
    if _money(t.get("usd_per_credit")): return f"{_money(t['usd_per_credit'])} per credit"
    if _money(t.get("usd_per_hour")): return f"{_money(t['usd_per_hour'])} per browser-hour"
    if _money(t.get("plan_fee")): return f"{_money(t['plan_fee'])}/month" + (f", {t['included_units']:,} units included" if isinstance(t.get("included_units"),int) else "")
    return None

def per_1k(c, cat, e):
    num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
    cpc = (c.get("credits_per_call") or {}).get(cat)
    if not num(cpc): cpc = (c.get("credits_per_call_verified") or {}).get(cat)
    if num(e.get("unit_price")): return _money(e["unit_price"] * 1000), None
    if e.get("usd_per_hour") is not None: return None, "billed per browser-hour; a request's duration is not part of the price"
    if num(e.get("usd_per_credit")):
        return (_money(e["usd_per_credit"] * cpc * 1000), None) if num(cpc) else (None, "credits per request not published")
    if num(e.get("plan_fee")):
        if num(e.get("overage_per_unit")) and num(cpc):
            inc = f" after the plan's {e['included_units']:,} included units" if num(e.get("included_units")) else ""
            return _money(e["overage_per_unit"] * cpc * 1000) + f" (overage rate{inc})", None
        return None, "plan fee; units per request not published" if num(e.get("overage_per_unit")) else "plan fee; overage rate not published"
    return None, "price not captured"

def lc(s): return re.sub(r"(?i)not captured", "not captured", s or "")

def curated_prices(path):
    if not path.exists(): return '<p class="nodata">No data yet.</p>'
    doc = json.loads("\n".join(l for l in path.read_text().splitlines() if not l.lstrip().startswith("#")))
    names = {x["id"]: x["name"] for x in json.loads(PROVIDERS.read_text())["providers"]} if PROVIDERS.exists() else {}
    rows = []
    for pid, cats in sorted(doc.get("providers", {}).items()):
        for cat, c in cats.items():
            if not isinstance(c, dict): continue
            e = (c.get("tiers") or {}).get("entry") or {}; lab = price_label(e); src = c.get("source_url") or c.get("pricing_url") or ""
            price = html.escape(lab) if lab else '<span class="muted">not captured</span>'
            nv, why = per_1k(c, cat, e)
            norm = html.escape(nv) if nv else f'n/a <span class="muted">({html.escape(why)})</span>'
            rows.append(f'<tr><td><a href="{html.escape(src)}">{html.escape(names.get(pid, pid))}</a></td><td data-label="Category">{html.escape(cat)}</td><td data-label="Entry tier">{html.escape(lc(e.get("name")))}</td>'
                        f'<td data-label="Price">{price}</td><td data-label="Normalized $/1k requests" class="num">{norm}</td><td class="muted mono" data-label="Checked">{html.escape(str(c.get("checked_at") or ""))}</td></tr>')
    return ('<table id="curated-prices" class="dt"><thead><tr><th>Provider</th><th>Category</th><th>Entry tier</th><th>Price</th><th>Normalized $/1k requests</th><th>Checked</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
            '<p class="muted">Each price is read by hand from the linked vendor pricing page on the date shown.</p>')

def history_slot():
    if not (cfg.get("pricing") or {}).get("show_history"): return ""
    return '<h2>Price history</h2><div id="prices" data-page="prices"><p class="nodata">No data yet.</p></div>'

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
NAV=[("/","Leaderboard"),("/prices/","Prices"),("/methodology/","Methodology"),("/data/","Data"),("/disclosures/","Disclosures"),("/newsletter/","Newsletter"),("/sponsors/","Sponsors")]
BENCH=R/"data/benchmarks/latest.json"; status=render.status_strip(BENCH)
for f in S.glob("*.html"):
    if f.name.startswith("_"): continue
    body=(f.read_text().replace("{{newsletter_slot}}",newsletter_slot()).replace("{{exclusions}}",exclusion_note())
          .replace("{{curated_prices}}",curated_prices(PRICING)).replace("{{price_history}}",history_slot())
          .replace("{{leaderboard}}",render.leaderboard(BENCH,PROVIDERS) if "{{leaderboard}}" in f.read_text() else ""))
    m=re.match(r"<!--title:(.*?)-->",body); title=m.group(1) if m else f.stem
    dm=re.search(r"<!--desc:(.*?)-->",body); desc=dm.group(1) if dm else "AgentWebIndex: cited prices and benchmarks for agent web APIs."; body=re.sub(r"<!--desc:.*?-->\n?","",body)
    body=re.sub(r"<!--title:.*?-->\n?","",body)
    path="/" if f.stem=="index" else f"/{f.stem}/"; pages.append(path)
    if f.stem!="index": body=f'<div class="prose">{body}</div>'
    nav="".join(f'<li><a href="{u}"{' aria-current="page"' if u==path else ""}>{n}</a></li>' for u,n in NAV)
    out=D/"index.html" if f.stem=="index" else D/f.stem/"index.html"; out.parent.mkdir(exist_ok=True)
    out.write_text(layout.replace("{{title}}",title).replace("{{head}}",page_head(title,desc,path)).replace("{{status}}",status).replace("{{nav}}",nav).replace("{{body}}",body))
pages.sort(key=lambda p:(p!="/",p))
(D/"robots.txt").write_text("User-agent: *\nAllow: /\n"+"".join(f"Allow: {p}\n" for p in pages if p!="/")+f"Sitemap: {SITE_URL}/sitemap.xml\n")
(D/"sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+"".join(f"<url><loc>{SITE_URL}{p}</loc></url>\n" for p in pages)+"</urlset>\n")
for a in ("style.css","app.js","favicon.svg"): shutil.copy(S/a,D/a)
shutil.copytree(S/"fonts",D/"assets"/"fonts")
if (R/"data").exists(): shutil.copytree(R/"data",D/"data",ignore=lambda d,n:[x for x in n if x in ("cache","_upstream")],dirs_exist_ok=True)
n=price_exports(); nb=bench_csv()
(D/"llms.txt").write_text("# AgentWebIndex\nMachine-readable data: /data/benchmarks/latest.json, /data/benchmarks/latest.csv (CC BY 4.0), /data/prices.json, /data/prices.csv, /data/prices/<provider>.json\nPages: /, /prices/, /methodology/, /data/, /sponsors/, /disclosures/, /newsletter/\n")
print("built",D,"price rows:",n,"benchmark csv rows:",nb)
