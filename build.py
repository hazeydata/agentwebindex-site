#!/usr/bin/env python3
"""Minimal static generator.
Site repo build: reads ONLY the vendored data/ copy (refresh with ./sync_data.sh).
src/*.html wrapped in _layout.html -> dist/<page>/index.html; data/ (minus data/cache) -> dist/data;
generates dist/data/prices.csv + prices.json from data/prices/history/*.jsonl; reads site.config.json."""
import csv, html, json, re, shutil
from pathlib import Path
R=Path(__file__).resolve().parent; S=R/"src"; D=R/"dist"
UP=R/"data"/"_upstream"   # vendored copies of agentwebindex collectors/providers.json + bench/tos_matrix.yaml (see sync_data.sh)
cfg=json.loads((R/"site.config.json").read_text()) if (R/"site.config.json").exists() else {}

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
    names = {x["id"]: x["name"] for x in json.loads((UP / "providers.json").read_text())["providers"]}
    items = [(pid, t) for pid, t in sorted(tos.items()) if (t.get("benchmarking") or {}).get("status") == "forbidden"]
    if not items: return ""
    li = "".join(f'<li><b>{html.escape(names.get(pid, pid))}</b> is excluded from benchmark tables: its terms forbid benchmarking ('
                 f'{html.escape(t["benchmarking"].get("quote") or "")}; <a href="{html.escape(t.get("terms_url") or "")}">terms</a>, checked {html.escape(str(t.get("checked_at")))}). '
                 f'It still appears on the <a href="/prices/">price history</a> page.'
                 + (f' <span class="muted">Note: {html.escape(t["note"])}</span>' if t.get("note") else "") + '</li>' for pid, t in items)
    return f'<div id="exclusions" class="note"><h3>Excluded providers</h3><ul>{li}</ul></div>'

def price_exports():
    rows=[]; provs={p["id"]:p for p in json.loads((UP/"providers.json").read_text())["providers"]}
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

shutil.rmtree(D,ignore_errors=True); D.mkdir()
layout=(S/"_layout.html").read_text()
for f in S.glob("*.html"):
    if f.name.startswith("_"): continue
    body=f.read_text().replace("{{newsletter_slot}}",newsletter_slot()).replace("{{exclusions}}",exclusion_note()); m=re.match(r"<!--title:(.*?)-->",body); title=m.group(1) if m else f.stem
    out=D/"index.html" if f.stem=="index" else D/f.stem/"index.html"; out.parent.mkdir(exist_ok=True)
    out.write_text(layout.replace("{{title}}",title).replace("{{body}}",body))
for a in ("style.css","app.js"): shutil.copy(S/a,D/a)
if (R/"data").exists(): shutil.copytree(R/"data",D/"data",ignore=lambda d,n:[x for x in n if x=="cache"])
n=price_exports()
(D/"llms.txt").write_text("# AgentWebIndex\nMachine-readable data: /data/benchmarks/latest.json, /data/prices.json, /data/prices.csv, /data/prices/<provider>.json\n")
print("built",D,"price rows:",n)
