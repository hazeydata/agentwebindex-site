"""HTML renderers for the AgentWebIndex pages (stdlib only; called by build.py).

Static text comes from content/copy.md via copydoc.py and is therefore verbatim. Every number on Results and
Methodology is computed from data/benchmarks/latest.json (rows) and bench/pricing.yaml (prices) through the
prices.py helpers; nothing numeric is typed in here. Tests compare the computed strings with copy.md.

Public entry points (all take the build context `ctx`: latest, pricing, providers, doc, alt, pins, signup_form, charts):
  slots(ctx)       -> {slot name: html} used to fill src/*.html
  page_meta(ctx)   -> {page stem: (title, description)}
  footer_html(ctx), nav_html(path)
"""
import html, json, re
from pathlib import Path

import copydoc
import prices as P

e = html.escape
inline = copydoc.inline
NAV = [("/", "Results"), ("/prices/", "Prices"), ("/methodology/", "Methodology"), ("/data/", "Data")]
ISSUES = "https://github.com/hazeydata/agentwebindex-site/issues"
DATA_REPO = "https://github.com/hazeydata/agentwebindex"
CHART_WIDTHS = (720, 350)   # file variant -> displayed CSS width in px
SCHEMES = ("light", "dark")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def v(x):
    return x.get("v") if isinstance(x, dict) else x


def day_label(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{MONTHS[m - 1]} {d}, {y}"


# ---------------------------------------------------------------- data selection

def names(ctx):
    return P.provider_names(ctx.providers)


def run_rows(ctx):
    """Rows of the latest run (run_date == latest.json run_date): search rows by provider name, then scrape, then browser."""
    L = ctx.latest
    nm = names(ctx)
    out = []
    for cat in P.CATS:
        rows = [r for r in (L.get("tables") or {}).get(cat, [])
                if r.get("run_date") == L.get("run_date") and not r.get("mock") and v(r.get("attempted")) is not None]
        for r in sorted(rows, key=lambda r: nm.get(r["provider"], r["provider"])):
            out.append(dict(r, _cat=cat, _name=nm.get(r["provider"], r["provider"])))
    return out


def run_log_url(ctx, row, key="passed"):
    """GitHub link (at the pinned data sha) to the run log this value was counted from."""
    src = (row.get(key) or {}).get("src") or []
    f = src[0]["file"] if src and src[0].get("file") else None
    return f"{DATA_REPO}/blob/{ctx.pins['data']}/bench/{f}" if f else ""


def price_source(ctx, row):
    for pr in P.price_rows(ctx.pricing, ctx.latest, ctx.providers):
        if pr["provider"] == row["provider"]:
            return pr["source_url"]
    return ""


def link(url, text):
    return f'<a href="{e(url)}">{text}</a>' if url else text


def sublabel(r):
    n = r.get("set_rows")
    if str(r["set"]).startswith("search_evergreen"):
        return f"{r['_cat']} · {n} evergreen questions"
    skip = (r.get("skipped_tos") or {}).get("count") or 0
    return f"{r['_cat']} · {n} URLs" + (f"; {skip} skipped by design under its terms" if skip else "")


def kn(r):
    return v(r["passed"]), v(r["attempted"])


def cost1k(r):
    return v(r.get("entry_tier_cost_per_successful_1k"))


def list1k(r):
    return v(r.get("entry_tier_cost_per_1k"))


# ---------------------------------------------------------------- computed copy strings (checked against copy.md by tests)

def search_rows(ctx):
    return sorted([r for r in run_rows(ctx) if r["_cat"] == "search"], key=lambda r: -(v(r["success_rate"]) or 0))


def scrape_rows(ctx):
    return [r for r in run_rows(ctx) if r["_cat"] == "scrape"]


def headline_sentence(ctx):
    """'<Top search> passed <pct> of our <n> evergreen checks, <other> <pct>; <scrape provider> passed <pct> of <n> scrape checks'"""
    s, sc = search_rows(ctx), scrape_rows(ctx)
    first = f"{s[0]['_name']} passed {P.fmt_pct(v(s[0]['success_rate']))} of our {v(s[0]['attempted'])} evergreen checks"
    rest = "".join(f", {r['_name']} {P.fmt_pct(v(r['success_rate']))}" for r in s[1:])
    scrape = "".join(f"; {r['_name']} passed {P.fmt_pct(v(r['success_rate']))} of {v(r['attempted'])} scrape checks" for r in sc)
    return first + rest + scrape


def intro_sentence(ctx):
    return f"Our first $0 free-tier run, on {day_label(ctx.latest['run_date'])}, used frozen test sets."


def findings(ctx):
    """The three findings bullets as (bold lead, rest) text pairs."""
    s, sc = search_rows(ctx), scrape_rows(ctx)
    n = v(s[0]["attempted"])
    b1 = (f"Search, {n} evergreen questions.", "")   # pass-rate claim cut as a repeat (copy-cuts item 2); stated once in the #run line
    by_cost = sorted(s, key=cost1k)
    costs = ", ".join(f"{r['_name']} {P.fmt_usd(cost1k(r))}" for r in by_cost) + "."
    cheaper_list = min(s, key=list1k)
    lead = by_cost[0]
    tail = ""
    if len(s) == 2 and cheaper_list is not lead:
        tail = (f" {cheaper_list['_name']} lists lower ({P.fmt_usd(list1k(cheaper_list))} vs {P.fmt_usd(list1k(lead))} per 1,000 calls) "
                "but passed fewer, so each pass costs more.")
    b2 = ("Cost per 1,000 passed checks, entry-tier list price:", costs + tail)
    out = [b1, b2]
    for r in sc:
        skip = (r.get("skipped_tos") or {}).get("count") or 0
        out.append((f"Scrape, {r['_name']}:", f"{kn(r)[0]} of {kn(r)[1]} tested passed ({P.fmt_pct(v(r['success_rate']))}), {P.fmt_usd(cost1k(r))} per 1,000 successful calls. "
                    f"{r.get('set_rows')} URLs; {skip} skipped by design under its terms."))
    return out


def cost_title(ctx):
    """'<A> lists cheaper than <B> (<list> vs <list> per 1,000 calls) but costs more per 1,000 passed checks (<cost> vs <cost>)'"""
    s = search_rows(ctx)
    cheap, dear = min(s, key=list1k), min(s, key=cost1k)
    return (f"{cheap['_name']} lists cheaper than {dear['_name']} ({P.fmt_usd(list1k(cheap))} vs {P.fmt_usd(list1k(dear))} per 1,000 calls) "
            f"but costs more per 1,000 passed checks ({P.fmt_usd(cost1k(cheap))} vs {P.fmt_usd(cost1k(dear))})")


def pass_caption(ctx):
    # values cut as a repeat (copy-cuts item 5): the chart's data labels and the #run line carry them
    return f"Pass rate on our test set, {day_label(ctx.latest['run_date'])} run. Values in the chart."


def latency_sentence(ctx):
    """'<Provider> <category> <n> ms, ...' for each row of the run (p50, whole ms, half up), comma-joined, ending in '.'"""
    return ", ".join(f"{r['_name']} {r['_cat']} {P.fmt_ms(v(r['p50_latency_ms']))}" for r in run_rows(ctx) if v(r.get("p50_latency_ms")) is not None) + "."


# ---------------------------------------------------------------- CTA boxes (AWI-PAGE-POLISH-001)
# Lead-ins and the single button label come from copy.md "CTA boxes" (Lindsay). The button links to the signup:
# on Results to the on-page form (#signup-end), elsewhere to /newsletter/.

def cta_label(ctx):
    return ctx.doc.field("CTA boxes", "Button")


def cta_btn(ctx, href="/newsletter/"):
    return f'<a class="btn cta-btn" href="{href}">{e(cta_label(ctx))}</a>'


def cta_card(ctx, key=None, href="/newsletter/"):
    """Compact hero card: right column at >=768px, one lead+button row under the lede below it."""
    lead = f'<p class="cta-lead">{e(ctx.doc.field("CTA boxes", key))}</p>' if key else ""
    return f'<aside class="cta cta-hero" aria-label="Newsletter">{lead}{cta_btn(ctx, href)}</aside>'


def signup_card(ctx, key, prefix, page):
    """Hero card holding the first-party signup form itself, so it sits in the first screenful (AWI-SIGNUP-FORM-001 AC 14)."""
    return (f'<aside class="cta cta-hero cta-form" id="signup-top" aria-label="Newsletter"><p class="cta-lead">{e(ctx.doc.field("CTA boxes", key))}</p>'
            f'{ctx.signup_form(prefix, page)}</aside>')


def info_card(ctx, key, body, label):
    """Hero card that is not a newsletter signup (Data downloads, Disclosures corrections): one lead-in from copy-cuts "Hero card lead-ins"."""
    return f'<aside class="cta cta-hero cta-info" aria-label="{e(label)}"><p class="cta-lead">{e(ctx.doc.field("CTA boxes", key))}</p>{body}</aside>'


def cta_end(ctx, key, form=False):
    """Full-width repeat at the end of a page; `form` embeds the signup itself instead of a button."""
    body = ctx.signup_form("end", "/") if form else cta_btn(ctx)
    return (f'<section class="cta-end-wrap"><div class="wrap"><div class="cta cta-end"{' id="signup-end"' if form else ''}>'
            f'<p class="cta-lead">{e(ctx.doc.field("CTA boxes", key))}</p>{body}</div></div></section>')


def hero(top, rest="", aside=""):
    """Hero grid: areas top/cta/rest. >=768px: [top rest] left (max 560px), cta right; below: top, cta, rest."""
    return (f'<section class="hero"><div class="wrap"><div class="hero-grid{" has-cta" if aside else ""}">'
            f'<div class="hero-top">{top}</div>{aside}{f"<div class=\"hero-rest\">{rest}</div>" if rest else ""}</div></div></section>')


# ---------------------------------------------------------------- Results

def hero_results(ctx):
    d = ctx.doc
    top = ('<p class="kicker">Logged runs, cited prices</p><h1>Results</h1>'
           f'<p class="headline">{inline(d.field("Home: hero", "Headline"))}</p>')
    rest = (f'<p class="lede body-lede">{inline(d.field("Home: hero", "Lede"))}</p>'
            f'<p class="byline">{inline(d.para("Home: hero", "Built by"))}</p>'
            '<ul class="meta"><li class="chip">Data CC BY 4.0</li><li class="chip">No paid placement</li></ul>')
    return hero(top, rest, signup_card(ctx, "Results top", "top", "/"))


def results_row(ctx, r):
    # The sub-label is verbatim copy and one ends in "terms"; AC19 forbids the literal "ms</" in index.html. The trailing newline inside the
    # span (whitespace, invisible, text unchanged after whitespace collapse) is the least intrusive way to keep both. See README "AC19".
    k, n = kn(r)
    passed = link(run_log_url(ctx, r), f"{k} of {n} passed ({P.fmt_pct(v(r['success_rate']))})")
    cost = link(price_source(ctx, r), P.fmt_usd(cost1k(r)))
    return (f'<div class="row" role="listitem" data-provider="{e(r["provider"])}"><div class="who"><b>{e(r["_name"])}</b> <span>{e(sublabel(r))}\n</span></div>'
            f'<div class="mono val-pass">{passed}</div>'
            f'<div class="mono val-cost">{cost} per 1,000 passed checks · list {e(P.fmt_usd(list1k(r)))} per 1,000 calls</div></div>')


def section_run(ctx):
    d = ctx.doc
    rows = "".join(results_row(ctx, r) for r in run_rows(ctx))
    bullets = "".join(f"<li><b>{e(a)}</b>{' ' + e(b) if b else ''}</li>" for a, b in findings(ctx))
    return ('<section id="run"><div class="wrap"><div class="col">'
            f'<h2>Results, {e(day_label(ctx.latest["run_date"]))} run</h2>'
            f'<p class="lcopy">{e(intro_sentence(ctx))}</p><p class="lcopy strong">{e(headline_sentence(ctx))}.</p></div>'
            f'<div class="rows" role="list">{rows}</div>'
            f'<div class="col"><ul class="findings">{bullets}</ul>'
            f'<p class="lcopy">{inline(d.para("Home: findings", "One run."))}</p></div></div></section>')


PROLOG_RE = re.compile(r"\A<\?xml[^>]*\?>\s*(?:<!DOCTYPE[^>]*>\s*)?")
ID_RE = re.compile(r'(\bid="|\bhref="#|url\(#)([^"\)]+)')


def strip_prolog(svg):
    """The SVG file minus its XML declaration and doctype (R9.1); everything from <svg on is kept byte for byte."""
    m = PROLOG_RE.match(svg)
    if not m or not svg[m.end():].startswith("<svg"):
        raise ValueError("chart SVG does not start with an XML prolog followed by <svg")
    return svg[m.end():]


def id_prefix(name, width, scheme):
    return f"{name}-{width}-{scheme}--"


DUP_SUFFIX = re.compile(r"--dup\d+$")


def prefix_ids(svg, prefix):
    """Build-time id rename (R9.3): id="x", href="#x" (incl. xlink:href) and url(#x) -> prefix + x. An id repeated inside one file
    (matplotlib writes gid "wilson-ci" three times per pass-rate SVG) gets "--dupN" on its 2nd+ use; such ids must be unreferenced."""
    counts, refs = {}, set(re.findall(r'(?:\bhref="#|url\(#)([^"\)]+)', svg))

    def sub(m):
        kind, x = m.groups()
        if kind != 'id="':
            return kind + prefix + x
        n = counts[x] = counts.get(x, 0) + 1
        if n > 1 and x in refs:
            raise ValueError(f"chart id {x!r} is repeated and referenced; cannot rename safely")
        return kind + prefix + x + (f"--dup{n}" if n > 1 else "")
    return ID_RE.sub(sub, svg)


def unprefix_ids(svg, prefix):
    """Inverse of prefix_ids (used by the R9.1 equality test)."""
    def sub(m):
        kind, x = m.groups()
        if not x.startswith(prefix):
            return m.group(0)
        x = x[len(prefix):]
        return kind + (DUP_SUFFIX.sub("", x) if kind == 'id="' else x)
    return ID_RE.sub(sub, svg)


def duplicate_ids(page):
    seen, dups = set(), set()
    for i in re.findall(r'\bid="([^"]*)"', page):
        (dups if i in seen else seen).add(i)
    return sorted(dups)


def chart_svgs(ctx, name):
    """Four inlined SVGs (720/350 x light/dark), each in a role=img wrapper named by the QUERIES.md alt text; CSS shows exactly one.
    The served files in /assets/charts stay byte-identical; inlined markup = file minus prolog, with ids prefixed per variant."""
    alt = e(ctx.alt[name], quote=True)
    out = []
    for width in CHART_WIDTHS:
        for scheme in SCHEMES:
            f = f"awi-{name}-{width}-{scheme}.svg"
            svg = prefix_ids(strip_prolog((ctx.charts / f).read_text()), id_prefix(name, width, scheme))
            out.append(f'<div class="ch ch-{width} ch-{scheme}" role="img" aria-label="{alt}" data-file="{f}" data-prefix="{id_prefix(name, width, scheme)}">{svg}</div>')
    return "".join(out)


def section_chart(ctx, sid, intro_key, name, title):
    intro = ctx.doc.blocks("Home: section intros", intro_key)[0][1]
    return (f'<section id="{sid}"><div class="wrap"><div class="col"><h2>{e(intro_key)}</h2><p class="lcopy">{inline(intro)}</p></div>'
            f'<figure class="chart" id="chart-{sid}"><h3>{e(title)}</h3>{chart_svgs(ctx, name)}</figure>'
            '</div></section>')


def section_not_tested(ctx):
    """One Notes <details> (addendum 9, CEO R-5): the chart footnotes and "Not tested"."""
    t = ctx.doc.blocks("Home: section intros", "Not tested")[0][1]
    foot = "".join(f'<p class="footnote" data-chart="{sid}">{e(c)}</p>' for sid, c in
                   (("pass-rate", pass_caption(ctx)), ("cost", ctx.doc.field("Chart briefs", "Caption", sub="Chart 2"))))
    return ('<section id="not-tested" class="notes"><div class="wrap"><details id="notes"><summary>Notes</summary>'
            f'{foot}<h3>Not tested</h3><p>{inline(t)}</p><p><a href="/methodology/">Methodology and limits</a></p></details></div></section>')


RETEST = "retest-apify-2026-10-26"


def section_retest(ctx):
    """Apify retest (preliminary): own section after the weekly results (layout.md). Copy from copy.md; alt text and
    counts from content/retest-apify-2026-10-26.json; the SVG is served byte-identical from /assets/retest/ as an <img>, with a 350px <source> below 960px (chart text >= 13px at 320-959px). The caption is a <p>, not a <figcaption> (CEO R-5: no figcaption on the page)."""
    meta = json.loads((ctx.content / f"{RETEST}.json").read_text())
    title = "Apify retest (preliminary)"
    para = [t for k, t in ctx.doc.blocks(title) if k == "p" and not t.startswith(("**", "<!--"))][0]
    cap = ctx.doc.field(title, "Caption")
    src = "/assets/retest/" + Path(meta["chart"]).name
    src350 = "/assets/retest/" + Path(meta["chart_350"]).name   # 350px variant like the weekly charts (252-unit viewBox shown at 350px)
    return (f'<section id="apify-retest" class="retest"><div class="wrap"><div class="col"><h3>{e(title)} <span class="pill">Preliminary</span></h3>'
            f'<p>{inline(para)}</p></div><figure class="retest-fig"><picture><source media="(max-width: 959.98px)" srcset="{src350}">'
            f'<img src="{src}" alt="{e(meta["alt"], quote=True)}" width="768" height="432" loading="lazy"></picture>'
            f'<p class="retest-caption">{e(cap)}</p></figure></div></section>')


def earlier_runs(ctx):
    bl = ctx.doc.blocks("Earlier runs")
    summary = next(t for k, t in bl if t.startswith("**Summary line:**")).split(":**", 1)[1].strip()
    out, ul = [], False
    for kind, t in bl:
        if t.startswith("**Summary line:**"):
            continue
        if kind == "li":
            out.append("" if ul else "<ul>")
            ul = True
            out.append(f"<li>{inline(t)}</li>")
            continue
        if ul:
            out.append("</ul>")
            ul = False
        out.append(f"<h4>{e(t.strip('*'))}</h4>" if t.startswith("**Week") else f"<p>{inline(t)}</p>")
    if ul:
        out.append("</ul>")
    return f'<details id="earlier-runs"><summary>{e(summary)}</summary>{"".join(out)}</details>'


def every_row(ctx):
    """Full results table (every non-mock row in latest.json), collapsed. No latency column."""
    nm = names(ctx)
    body = []
    for cat in P.CATS:
        for r in (ctx.latest.get("tables") or {}).get(cat, []):
            if r.get("mock") or v(r.get("attempted")) is None:
                continue
            r = dict(r, _cat=cat, _name=nm.get(r["provider"], r["provider"]))
            k, n = kn(r)
            c = (r.get("entry_tier_cost_per_successful_1k") or {}).get("display") or "n/a"
            lp = (r.get("entry_tier_cost_per_1k") or {}).get("display") or "n/a"
            body.append(
                f'<tr><th scope="row" data-label="Provider">{e(r["_name"])}</th><td data-label="Category">{e(cat)}</td>'
                f'<td data-label="Set">{e(r["set"])}</td><td data-label="Run date">{e(r.get("run_date") or "")}</td>'
                f'<td data-label="Passed" class="mono">{link(run_log_url(ctx, r), f"{k} of {n} ({P.fmt_pct(v(r["success_rate"]))})")}</td>'
                f'<td data-label="Per 1,000 passed checks" class="mono">{e(c)}</td><td data-label="List price per 1,000 calls" class="mono">{e(lp)}</td>'
                f'<td data-label="Flags">{e(", ".join(r.get("flags") or []))}</td></tr>')
    return ('<details id="every-row"><summary>Every row</summary><div class="tablewrap"><table class="dt"><thead><tr><th scope="col">Provider</th>'
            '<th scope="col">Category</th><th scope="col">Set</th><th scope="col">Run date</th><th scope="col">Passed</th>'
            '<th scope="col">Per 1,000 passed checks</th><th scope="col">List price per 1,000 calls</th><th scope="col">Flags</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div></details>')


def section_details(ctx):
    return f'<section id="details"><div class="wrap"><div class="col"><h2>Details</h2></div>{earlier_runs(ctx)}{every_row(ctx)}</div></section>'


def section_sponsor(ctx):
    one = ctx.doc.lines("Layout slot: newsletter")
    line = next(l.strip() for l in one if l.strip())
    return ('<section id="sponsor-newsletter"><div class="wrap">'
            '<aside id="sponsor-banner" class="sponsor"><b>Sponsored</b> <a href="/sponsors/">No sponsors yet</a></aside>'
            f'<h2>Newsletter</h2><p class="lcopy">{inline(line)}</p>'
            f'<div class="cta cta-end" id="signup-end"><p class="cta-lead">{e(ctx.doc.field("CTA boxes", "Results end"))}</p>{ctx.signup_form("end", "/")}</div>'
            '</div></section>')


# ---------------------------------------------------------------- Prices

def prices_body(ctx):
    d = ctx.doc
    lede = next(l.strip() for l in d.lines("Layout slot: prices lede") if l.strip())
    rows = []
    for r in P.price_rows(ctx.pricing, ctx.latest, ctx.providers):
        sub = f'<span class="sub">{e(r["tier_name"])}</span>' if r.get("tier_name") else ""
        rows.append(f'<div class="row price-row" role="listitem" data-provider="{e(r["provider"])}">'
                    f'<div class="who"><b>{e(r["name"])}</b> <span>{e(r["category"])}</span></div>'
                    f'<div class="mono price">{e(r["price_display"])}{sub}</div>'
                    f'<div class="mono checked">Last checked <time datetime="{e(r["checked_at"])}">{e(r["checked_at"])}</time> · '
                    f'<a href="{e(r["source_url"])}">pricing page</a></div></div>')
    also = next(l.strip() for l in d.lines("Prices page: also priced") if l.strip())
    return (hero(f'<p class="kicker">Entry-tier list price</p><h1>Prices</h1><p class="lede">{inline(lede)}</p>', "", cta_card(ctx, "Prices top"))
            + f'<section><div class="wrap"><div class="rows" role="list" id="price-rows">{"".join(rows)}</div>'
            f'<div class="col"><p class="lcopy" id="also-priced">{inline(also)}</p></div></div></section>' + cta_end(ctx, "Prices end"))


# ---------------------------------------------------------------- Methodology

def methodology_body(ctx):
    d = ctx.doc
    lede = next(l.strip() for l in d.lines("Layout slot: methodology lede") if l.strip())
    steps, limits, tail, toc, mode = [], [], [], [], "steps"
    for kind, t in d.blocks("Methodology and limits"):
        if t.startswith("**Limits, plainly.**"):
            mode = "limits"
        elif mode == "steps":
            if t.startswith("**Latency (p50)"):
                t = f"**Latency (p50), {day_label(ctx.latest['run_date'])} run:** {latency_sentence(ctx)} Yours will differ."
            m = re.match(r"^\*\*(.+?)\*\*\s*(.*)$", t)
            label, rest = (m.group(1), m.group(2)) if m else ("", t)
            sid = "m-" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
            toc.append(f'<li><a href="#{sid}">{e(label.rstrip(".:"))}</a></li>')
            steps.append(f'<li id="{sid}"><h2>{inline(label)}</h2>\n<p>{inline(rest)}</p></li>')
        elif kind == "li":
            limits.append(f"<li>{inline(t)}</li>")
        else:
            tail.append(f"<p>{inline(t)}</p>")
    toc.append('<li><a href="#limits">Limits, plainly</a></li>')
    return (hero(f'<p class="kicker">Methodology and limits</p><h1>Methodology</h1><p class="lede">{inline(lede)}</p>', "", cta_card(ctx, "Methodology top"))
            + '<section class="major"><div class="wrap mlayout">'
            f'<nav class="toc" aria-label="On this page"><ul>{"".join(toc)}</ul></nav>'
            f'<div class="mbody"><ol class="steps">{"".join(steps)}</ol>'
            f'<div class="limits" id="limits"><h2>Limits, plainly.</h2><ul>{"".join(limits)}</ul>{"".join(tail)}</div></div></div></section>'
            + cta_end(ctx, "Methodology end"))


# ---------------------------------------------------------------- Data, Tell us, Disclosures, Sponsors, Newsletter

DATA_FILES = [("latest.json", "/data/benchmarks/latest.json"), ("latest.csv", "/data/benchmarks/latest.csv"),
              ("prices.json", "/data/prices.json"), ("prices.csv", "/data/prices.csv"),
              ("prices/<provider>.json", "/data/prices/index.json"), ("LICENSE", "/data/LICENSE")]


def data_body(ctx):
    lede = next(l.strip() for l in ctx.doc.lines("Data page") if l.strip())
    items = "".join(f'<li><a class="mono" href="{u}">{e(n)}</a></li>' for n, u in DATA_FILES[2:])
    dl = (f'<p class="actions"><a class="btn" href="{DATA_FILES[0][1]}">Download latest.json</a>'
          f'<a class="btn ghost" href="{DATA_FILES[1][1]}">or latest.csv</a></p>')   # labels: Lindsay copy-cuts, Data
    return (hero(f'<p class="kicker">CC BY 4.0</p><h1>Data</h1><p class="lede">{inline(lede)}</p>', "", info_card(ctx, "Data top", dl, "Data files"))
            + f'<section><div class="wrap"><div class="col"><div class="card"><h2 class="card-h">Other files</h2><ul class="files">{items}</ul></div></div></div></section>'
            + cta_end(ctx, "Data end"))


def tell_us_body(ctx):
    bl = ctx.doc.blocks("About and tell us")
    about, tell = bl[0][1], next(t for _, t in bl if t.startswith("Spot a wrong number"))
    return ('<section class="hero"><div class="wrap"><div class="col"><h1>Tell us</h1>'
            f'<p class="lede">{inline(about)}</p><p class="lcopy">{inline(tell)}</p>'
            f'<p class="actions"><a class="btn" href="{ISSUES}">Open an issue</a><a class="btn ghost" href="mailto:fred@hazeydata.ai">Email Fred</a></p>'
            '</div></div></section>' + cta_end(ctx, "Tell us end"))


def field_page(ctx, prefix, aside="", hero_extra="", end_key=None, after_first=""):
    """Kicker, Title (h1), Intro, then each (ID) field as a label|text row; the ID is structure only and never rendered."""
    d = ctx.doc
    top = f'<p class="kicker">{e(d.field(prefix, "Kicker"))}</p><h1>{e(d.field(prefix, "Title"))}</h1>'
    bl = d.blocks(prefix)
    intro = [t for _, t in bl if t.startswith("**Intro:**")]
    if intro:
        top += f'<p class="lede">{inline(intro[0].split(":**", 1)[1].strip())}</p>'
    out = [hero(top + hero_extra, "", aside), '<section><div class="wrap"><div class="prose fields">']
    for kind, t in bl:
        m = re.match(r"^\*\*([A-Za-z][A-Za-z -]*?)(?: \(([^)]*)\))?:\*\*\s*(.*)$", t)
        if m and m.group(1) in ("Kicker", "Title", "Intro"):
            continue
        if m:
            label = m.group(2) or (None if re.fullmatch(r"[A-Z]+-[A-Z]+", m.group(1)) else m.group(1))   # IDs are structure only
            out.append(f'<div class="field">{f"<h2>{e(label)}</h2>" if label else ""}<p>{inline(m.group(3))}</p></div>')
        else:
            out.append(f'<div class="field"><p>{inline(t)}</p></div>')
    if after_first and len(out) > 2:
        out.insert(3, after_first)
    out.append("</div></div></section>")
    if end_key:
        out.append(cta_end(ctx, end_key))
    return "".join(out)


def newsletter_body(ctx):
    line = next(l.strip() for l in ctx.doc.lines("Layout slot: newsletter") if l.strip())
    return ('<section class="hero"><div class="wrap"><div class="col"><p class="kicker">Newsletter</p><h1>Newsletter</h1>'
            f'<p class="lede">{inline(line)}</p><div class="cta cta-news" id="signup">'
            f'<p class="cta-lead">{e(ctx.doc.field("CTA boxes", "Newsletter box"))}</p>{ctx.signup_form("news", "/newsletter/")}</div></div></div></section>')


# ---------------------------------------------------------------- shell

def nav_html(path):
    return "".join(f'<li><a href="{u}"{" aria-current=\"page\"" if u == path else ""}>{n}</a></li>' for u, n in NAV)


def footer_html(ctx):
    d = ctx.doc
    foot = next(l.strip() for l in d.lines("Footer") if l.strip())
    pages = [("/disclosures/", "Disclosures"), ("/sponsors/", "Sponsors"), ("/newsletter/", "Newsletter"), ("/tell-us/", "Tell us")]
    agents = [("/data/benchmarks/latest.json", "latest.json"), ("/data/prices/index.json", "prices"), ("/llms.txt", "llms.txt")]
    li = lambda xs: "".join(f'<li><a href="{u}">{n}</a></li>' for u, n in xs)
    return ('<footer class="site-footer"><div class="wrap">'
            f'<div class="foot-main"><p class="foot-line">{inline(foot)}</p></div>'
            f'<div class="foot-links"><p class="eyebrow">About</p><ul>{li(pages)}</ul></div>'
            f'<div class="foot-links"><p class="eyebrow">For agents</p><ul>{li(agents)}</ul></div>'
            '</div></footer>')


def page_meta(ctx):
    d = ctx.doc
    first = lambda prefix: next(l.strip() for l in d.lines(prefix) if l.strip())
    return {
        "index": ("Results", d.field("Home: hero", "Lede")),
        "prices": ("Prices", first("Layout slot: prices lede")),
        "methodology": ("Methodology", first("Layout slot: methodology lede")),
        "data": ("Data", first("Data page")),
        "disclosures": ("Disclosures", d.field("Disclosures page", "Intro")),
        "sponsors": ("Sponsors", d.field("Sponsors page", "SPON-WHO")),
        "tell-us": ("Tell us", d.blocks("About and tell us")[0][1]),
        "newsletter": ("Newsletter", first("Layout slot: newsletter")),
    }


def slots(ctx):
    d = ctx.doc
    return {
        "hero_results": hero_results(ctx), "run": section_run(ctx),
        "pass_rate": section_chart(ctx, "pass-rate", "Pass rate", "pass-rate", headline_sentence(ctx)),
        "cost": section_chart(ctx, "cost", "Cost per passed check", "cost-per-success", cost_title(ctx)),
        "not_tested": section_not_tested(ctx), "retest": section_retest(ctx), "details": section_details(ctx), "sponsor": section_sponsor(ctx),
        "prices_body": prices_body(ctx), "methodology_body": methodology_body(ctx), "data_body": data_body(ctx),
        "tell_us_body": tell_us_body(ctx), "newsletter_body": newsletter_body(ctx),
        "disclosures_body": field_page(ctx, "Disclosures page", end_key="Disclosures end",
                                       aside=info_card(ctx, "Disclosures top", f'<p class="inline-links"><a href="{ISSUES}">Open an issue</a><span class="sep"> · </span>'
                                                       '<a href="mailto:fred@hazeydata.ai">Email fred@hazeydata.ai</a></p>', "Corrections")),
        "sponsors_body": field_page(ctx, "Sponsors page", end_key="Sponsors end",
                                    after_first=f'<div class="cta cta-inline"><p class="cta-lead">{e(d.field("CTA boxes", "Sponsors top"))}</p>'
                                               '<a class="btn" href="mailto:fred@hazeydata.ai">Email Fred</a></div>'),
    }
