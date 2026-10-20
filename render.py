import html, json
from pathlib import Path

e = html.escape
CATS = [("search", "Search", "queries"), ("scrape", "Scrape", "URLs"), ("browser", "Browser", "page loads")]
ICON = {
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L20 20"/>',
    "scrape": '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 11h6M9 14h6M9 17h3"/>',
    "browser": '<rect x="3" y="4" width="18" height="16" rx="1.5"/><path d="M3 8.5h18"/><path d="M11 12l5 2-2 .8-.8 2.2z" fill="currentColor"/>',
    "not_tested": '<circle cx="12" cy="12" r="8" stroke-dasharray="3 3"/>',
    "rate_limited": '<path d="M4 18h4v-4h4v-4h4V6h4"/>',
    "partial_run": '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" stroke="none"/>',
    "warn": '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 17.5v.5"/>',
    "empty": '<rect x="3" y="5" width="18" height="14" rx="1.5"/><path d="M3 10h18M9 10v9"/>',
}


def icon(name, cls=""):
    c = f' class="{cls}"' if cls else ""
    return (f'<svg{c} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" '
            f'stroke-linejoin="round" aria-hidden="true" focusable="false">{ICON[name]}</svg>')


def v(x):
    return x.get("v") if isinstance(x, dict) else x


def pct(x):
    y = v(x)
    return "n/a" if y is None else f"{y * 100:.1f}%"


def chip(label, title="", kind="warn", quiet=False):
    t = f' title="{e(title)}"' if title else ""
    sr = f'<span class="visually-hidden">. {e(title)}</span>' if title else ""
    return f'<span class="chip{" chip--quiet" if quiet else ""}"{t}>{icon(kind)}{e(label)}{sr}</span>'


def money(x):
    if not isinstance(x, dict):
        return "n/a"
    if x.get("v") is None and x.get("na_reason"):
        return e(x["na_reason"])
    out = e(x.get("display") or "n/a")
    if x.get("lower_bound"):
        out += f' <span class="flag" title="{e(x.get("lower_bound_reason") or "")}">lower bound</span>'
    return out


def cost(per, succ):
    tier = (per or {}).get("tier") or (succ or {}).get("tier")
    return (f'<span class="v">{money(per)}</span><span class="sub">{money(succ)} per 1k successful</span>'
            + (f'<span class="sub tier">{e(tier)}</span>' if tier else ""))


def names(providers_path):
    p = Path(providers_path)
    return json.loads(p.read_text())["providers"] if p.exists() else []


def untested(d, cat, tested_ids, provs):
    why = {}
    for s in d.get("skips") or []:
        if s.get("scope") == "provider" and s.get("category") == cat:
            why[s["provider"]] = s.get("reason") or s.get("status")
    for n in d.get("not_run_yet") or []:
        if cat in (n.get("categories") or []):
            why[n["provider"]] = n.get("reason") or "not run yet"
    excluded = {x["provider"] for x in d.get("exclusions") or []}
    out = []
    for p in provs:
        if cat in (p.get("categories") or []) and p["id"] not in tested_ids and p["id"] not in excluded:
            out.append((p["id"], p.get("name") or p["id"], why.get(p["id"]) or "no run in this result set"))
    return out


def initials(name):
    w = [x for x in "".join(c if c.isalnum() or c == " " else " " for c in name).split() if x]
    if not w:
        return "?"
    return (w[0][0] + (w[-1][0] if len(w) > 1 else (w[0][1:2] or ""))).upper()


def badge(name, pid):
    return (f'<span class="provider"><span class="provider__mono" aria-hidden="true">{e(initials(name))}</span>'
            f'<span class="provider__name">{e(name)}</span> <span class="sub">{e(pid)}</span></span>')


def plot(cat, label, rows, nt, W, narrow):
    L = 92 if narrow else 170
    R = 56 if narrow else 72
    rh = 34
    top = 26
    H = top + rh * (len(rows) + len(nt)) + 34
    X = lambda f: L + f * (W - L - R)
    pid = f"plot-{cat}-{'n' if narrow else 'w'}"
    lead = rows[0] if rows else None
    desc = (f'{len(rows)} provider{"s" if len(rows) != 1 else ""} with results. Highest success rate: {lead["_name"]} at {pct(lead["success_rate"])} '
            f'({lead.get("answered_display") or ""}). ' if lead else "No provider has results. ")
    if nt:
        desc += "Not tested: " + ", ".join(n for _, n, _ in nt) + ". "
    desc += "Full values are in the table below."
    g = [f'<title id="{pid}-t">Success rate by provider, {e(label)}</title><desc id="{pid}-d">{e(desc)}</desc>']
    for f in (0, .25, .5, .75, 1):
        x = X(f)
        g.append(f'<line class="ax-grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top - 6}" y2="{H - 30}"/>'
                 f'<text class="ax-tick" x="{x:.1f}" y="{H - 14}" text-anchor="middle">{int(f * 100)}%</text>')
    g.append(f'<text class="ax-title" x="{W - R}" y="12" text-anchor="end">success rate →</text>')
    y = top + rh / 2
    for r in rows:
        f = v(r["success_rate"]) or 0
        nm = r["_name"] if not narrow or len(r["_name"]) <= 12 else r["_name"][:11] + "…"
        part = " pt--partial" if r.get("partial") else ""
        g.append(f'<text class="pt-label" x="{L - 10}" y="{y + 4:.1f}" text-anchor="end">{e(nm)}</text>'
                 f'<line class="pt-bar" x1="{X(0):.1f}" x2="{X(f):.1f}" y1="{y:.1f}" y2="{y:.1f}"/>'
                 f'<g class="pt{part}"><circle class="pt-dot" cx="{X(f):.1f}" cy="{y:.1f}" r="6"/></g>'
                 f'<text class="pt-val" x="{X(f) + 12:.1f}" y="{y + 4:.1f}">{pct(r["success_rate"])}</text>')
        y += rh
    for _, n, _ in nt:
        nm = n if not narrow or len(n) <= 12 else n[:11] + "…"
        g.append(f'<text class="pt-label pt-label--muted" x="{L - 10}" y="{y + 4:.1f}" text-anchor="end">{e(nm)}</text>'
                 f'<circle class="pt-nt" cx="{X(0):.1f}" cy="{y:.1f}" r="5"/>'
                 f'<text class="pt-nt-label" x="{X(0) + 12:.1f}" y="{y + 4:.1f}">not tested</text>')
        y += rh
    cls = "plot--narrow" if narrow else "plot--wide"
    return (f'<svg class="{cls}" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="{pid}-t {pid}-d">'
            + "".join(g) + "</svg>")


def flags(r):
    return "".join(f'<span class="flag">{e(f)}</span>' for f in r.get("flags") or [])


def table(cat, label, unit, rows, nt, n):
    th = ('<thead><tr><th scope="col" class="l c-rank">#</th><th scope="col" class="l">Provider</th><th scope="col">Success</th>'
          '<th scope="col">Latency p50</th><th scope="col">Entry tier $/1k</th><th scope="col">Volume tier $/1k</th><th scope="col" class="l c-notes">Notes</th></tr></thead>')
    body = []
    directional = any(str(f).startswith("below minimum") for r in rows for f in r.get("flags") or [])
    for i, r in enumerate(rows, 1):
        rl = r.get("rate_limited") or {}
        to = r.get("timed_out") or {}
        notes = [f'<span class="notes-stack">{flags(r)}'
                 + (chip(f'{rl["v"]} {rl.get("label") or "rate-limited"}', rl.get("note") or "", "rate_limited") if v(rl) else "")
                 + (chip("Partial run", "", "partial_run") if r.get("partial") else "") + "</span>",
                 f'<span class="note-text">Run {e(r.get("run_date") or "")} · set {e(r["set"])}</span>']
        if v(rl) and rl.get("note"):
            notes.append(f'<span class="note-text">{e(rl["note"])}</span>')
        if v(to) and to.get("note"):
            notes.append(f'<span class="note-text">{e(str(to["v"]))} timed out: {e(to["note"])}</span>')
        if r.get("free_quota_note"):
            notes.append(f'<span class="note-text">Free quota: {e(r["free_quota_note"])}</span>')
        if r.get("cost_units_note"):
            notes.append(f'<span class="note-text">{e(r["cost_units_note"])}</span>')
        p50 = v(r.get("p50_latency_ms"))
        tos = (r.get("skipped_tos") or {}).get("count", 0)
        body.append(
            f'<tr data-id="{e(r["provider"])}"><td class="c-rank">{"–" if directional else i}</td><td class="c-prov">{badge(r["_name"], r["provider"])}</td>'
            f'<td class="c-acc" data-label="Success"><span class="v">{pct(r["success_rate"])}</span><span class="sub">{e(r.get("answered_display") or "")}</span>'
            f'<span class="sub">n={v(r["attempted"])} · ToS-skipped {tos}</span></td>'
            f'<td class="c-lat" data-label="Latency p50">{"n/a" if p50 is None else f"{p50:.0f} ms"}</td>'
            f'<td class="c-cost" data-label="Entry tier $/1k">{cost(r.get("entry_tier_cost_per_1k"), r.get("entry_tier_cost_per_successful_1k"))}</td>'
            f'<td class="c-ci" data-label="Volume tier $/1k">{cost(r.get("volume_tier_cost_per_1k"), r.get("volume_tier_cost_per_successful_1k"))}</td>'
            f'<td class="c-notes">{"".join(notes)}</td></tr>')
    for pid, nm, why in nt:
        body.append(f'<tr class="is-untested" data-id="{e(pid)}"><td class="c-rank">—</td><td class="c-prov">{badge(nm, pid)}</td>'
                    f'<td class="c-nt" colspan="4"><span class="notes-stack">{chip("Not tested", "No result in this result set. The note says why.", "not_tested", True)}</span></td>'
                    f'<td class="c-notes"><span class="note-text">{e(why)}</span></td></tr>')
    cap = (f'<caption><strong>Table {n}</strong> {e(label)} results, ordered by success rate. Each row is one provider on one test set, '
           f'scored only from its run log.' + (' No row has 25 or more items yet, so the order is directional and no rank is shown.' if directional else '') + '</caption>')
    return f'<table class="lb" data-cat="{cat}" id="table-{cat}">{cap}{th}<tbody>{"".join(body)}</tbody></table>'


def freshness(d):
    fr = d.get("freshness") or []
    if not fr:
        return ""
    rows = "".join(
        f'<tr><td>{e(f["provider"])}</td><td data-label="Week">{e(f.get("week") or "")} {flags(f)}</td><td class="r num" data-label="n">{f.get("n")}</td>'
        f'<td class="r num" data-label="fresh_hit@10">{pct(f.get("fresh_hit_at_10"))}</td>'
        f'<td class="r num" data-label="median lag h">{"n/a" if v(f.get("median_lag_h")) is None else f"{v(f.get("median_lag_h")):.1f}"}</td>'
        f'<td class="r num" data-label="censored">{pct(f.get("censored_share"))}</td><td class="mono" data-label="set sha">{e((f.get("set_sha") or "")[:12])}</td></tr>'
        for f in fr)
    notes = "".join(f'<li class="muted">{e(n["provider"])}: {e(n["note"])}</li>' for n in d.get("freshness_notes") or [])
    return ('<h3 class="section-title">Freshness (weekly news set)</h3><table class="dt" id="freshness"><thead><tr><th>Provider</th><th>Week</th><th class="r">n</th>'
            '<th class="r">fresh_hit@10</th><th class="r">median lag h</th><th class="r">censored</th><th>set sha</th></tr></thead><tbody>'
            + rows + "</tbody></table>" + (f'<ul class="mt-4">{notes}</ul>' if notes else ""))


def run_status(d):
    fl = d.get("flags") or []
    sk = d.get("skips") or []
    sv = d.get("sets_valid") or []
    nr = d.get("not_run_yet") or []
    out = [f'<section class="run-status" id="run-status" aria-labelledby="run-status-h"><h2 id="run-status-h">Run status {e(d.get("run_date") or "")}</h2>',
           f'<p class="muted">Generated <span class="mono">{e(d.get("generated_at") or "")}</span> from run logs. '
           f'<span data-stale-note data-generated="{e(d.get("generated_at") or "")}"></span></p>',
           f'<p id="sets-valid"><b>Valid sets this run:</b> {", ".join(f"<code>{e(s)}</code>" for s in sv) if sv else "none"}</p>']
    if fl:
        out.append('<ul id="run-flags">' + "".join(f'<li class="flag">{e(f["set"])}: {e(f["flag"])}</li>' for f in fl) + "</ul>")
    if nr:
        out.append('<h3>Not run yet</h3><ul>' + "".join(f'<li>{e(n["provider"])} ({e(", ".join(n["categories"]))}): not run yet. <span class="muted">{e(n.get("reason") or "")}</span></li>' for n in nr) + "</ul>")
    if sk:
        out.append('<table class="dt" id="skips"><caption>Skipped</caption><thead><tr><th>Skipped</th><th>Status</th><th>Reason</th></tr></thead><tbody>'
                   + "".join(f'<tr><td>{e(k.get("set") or " / ".join(x for x in (k.get("provider"), k.get("category")) if x) or k.get("scope"))}</td>'
                             f'<td data-label="Status" class="mono">{e(k.get("status"))}</td><td data-label="Reason" class="muted wide">{e(k.get("reason"))}</td></tr>' for k in sk)
                   + "</tbody></table>")
    out.append("</section>")
    return "".join(out)


def leaderboard(bench_path, providers_path):
    p = Path(bench_path)
    d = json.loads(p.read_text()) if p.exists() else None
    provs = names(providers_path)
    nm = {x["id"]: x.get("name") or x["id"] for x in provs}
    tabs, panels = [], []
    for n, (cat, label, unit) in enumerate(CATS, 1):
        rows = [dict(r, _name=nm.get(r["provider"], r["provider"])) for r in ((d or {}).get("tables") or {}).get(cat, [])
                if d and d.get("has_results") and not r.get("mock") and v(r.get("attempted")) is not None]
        rows.sort(key=lambda r: -(v(r["success_rate"]) or 0))
        nt = untested(d or {}, cat, {r["provider"] for r in rows}, provs)
        sel = n == 1
        tabs.append(f'<button class="tab" role="tab" type="button" id="tab-{cat}" aria-controls="panel-{cat}" data-tab="{cat}" data-cat="{cat}" '
                    f'aria-selected="{"true" if sel else "false"}"{"" if sel else " tabindex=\"-1\""}>{icon(cat, "tab__icon")}{label} '
                    f'<span class="tab__count">{len(rows)}/{len(rows) + len(nt)}</span></button>')
        sets = sorted({r["set"] for r in rows})
        meta = (f'n = {", ".join(str(v(r["attempted"])) for r in rows)} {unit} · ' + ", ".join(sets)) if rows else "no results"
        fig = (f'<figure class="chart-card" data-cat="{cat}" id="chart-{cat}"><figcaption class="chart-card__head"><span><strong>Fig. {n}</strong> Success rate by provider, {label}</span>'
               f'<span class="chart-card__meta">{e(meta)}</span></figcaption><div class="chart-card__plot">'
               + plot(cat, label, rows, nt, 720, False) + plot(cat, label, rows, nt, 340, True) + "</div>"
               '<div class="chart-card__key" aria-hidden="true"><span><svg viewBox="0 0 18 12" aria-hidden="true"><circle cx="9" cy="6" r="4.5" fill="var(--cat)"/></svg>full run</span>'
               '<span><svg viewBox="0 0 18 12" aria-hidden="true"><circle cx="9" cy="6" r="4" fill="none" stroke="var(--cat)" stroke-width="2"/></svg>partial run</span>'
               '<span><svg viewBox="0 0 18 12" aria-hidden="true"><circle cx="9" cy="6" r="4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 3"/></svg>not tested</span></div>'
               + (f'<p class="chart-card__foot">Not tested: {e(", ".join(x for _, x, _ in nt))}.</p>' if nt else "") + "</figure>")
        if not rows:
            msg = f'<p class="nodata">No data yet for {cat}.</p>' + (f'<p class="muted">Last run {e(d.get("generated_at") or "")}: no provider produced results.</p>' if d else "")
        else:
            msg = ""
        lead = rows[0] if rows else None
        call = ('<aside class="callouts" aria-label="' + label + ' summary">'
                + (f'<div class="callout callout--lead"><p class="eyebrow">Highest success rate</p><p class="callout__value">{e(lead["_name"])}</p>'
                   f'<p class="callout__sub">{pct(lead["success_rate"])} · {e(lead.get("answered_display") or "")}</p></div>' if lead else
                   f'<div class="empty" role="status">{icon("empty")}<h3>No results yet</h3><p>Every {label.lower()} provider is untested in this result set.</p></div>')
                + (f'<div class="callout"><p class="eyebrow">Run dates</p><p class="callout__sub">{e(", ".join(sorted({r.get("run_date") or "" for r in rows})))}</p></div>' if rows else "")
                + '<div class="callout howto"><strong>How to read this</strong><p>Longer is better. Rows marked <span class="flag">below minimum (n=X)</span> ran on fewer than 25 items: treat them as early and directional, not a ranking. Dashed rows have no result yet.</p></div></aside>')
        panel = (f'<div class="tabpanel" role="tabpanel" id="panel-{cat}" aria-labelledby="tab-{cat}" data-cat="{cat}" tabindex="0">'
                 f'<h2 class="visually-hidden">{label}</h2>{msg}<div class="board">{fig}{call}</div>{table(cat, label, unit, rows, nt, n)}'
                 + (freshness(d) if cat == "search" and d else "")
                 + '<p class="lb-foot"><a href="/methodology/">Method</a> · <a href="/data/benchmarks/latest.csv">CSV</a> · <a href="/data/benchmarks/latest.json">JSON</a> · <a href="/disclosures/">Disclosures</a></p></div>')
        panels.append(panel)
    head = (f'<p class="muted mt-4">Run date{"s" if len((d or {}).get("run_dates") or []) > 1 else ""} {e(", ".join((d or {}).get("run_dates") or [(d or {}).get("run_date") or ""]))}. '
            f'Generated {e((d or {}).get("generated_at") or "")} from run logs. Free tier is a note, never a cost.</p>' if d else '<p class="nodata">No data yet.</p>')
    return (head + '<div class="tabs mt-6" role="tablist" aria-label="Benchmark category" data-tabs>' + "".join(tabs) + "</div>"
            + "".join(panels) + (run_status(d) if d else ""))


def status_strip(bench_path):
    p = Path(bench_path)
    if not p.exists():
        return "<span>No result set yet</span>"
    d = json.loads(p.read_text())
    g = d.get("generated_at") or ""
    sv = ", ".join(d.get("sets_valid") or []) or "none"
    return (f'<span><span class="fresh-dot" data-fresh-dot aria-hidden="true"></span>Run <strong>{e(d.get("run_date") or "")}</strong> · generated {e(g[:16].replace("T", " "))} UTC'
            f'<span data-stale-note data-generated="{e(g)}"></span></span><span>Valid sets: {e(sv)} · <a href="/#run-status">run status</a></span>')
