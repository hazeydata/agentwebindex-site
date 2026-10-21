import html, json, math, re
from pathlib import Path

e = html.escape
CATS = [("search", "Search", "queries"), ("scrape", "Scrape", "URLs"), ("browser", "Browser", "pages")]
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


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def kn(r):
    return v(r.get("passed")), v(r.get("attempted"))


def ci(r):
    k, n = kn(r)
    return wilson(k, n) if isinstance(k, int) and isinstance(n, int) and n else None


def ci_text(r):
    w = ci(r)
    return f"95% CI {w[0] * 100:.1f}–{w[1] * 100:.1f}%" if w else ""


def frac(r, sep=" "):
    k, n = kn(r)
    s = v(r["success_rate"])
    p = int(s * 100 + 0.5) if s is not None else None
    return (f"{k}/{n}, {p}%" if sep == ", " else f"{k}/{n} ({p}%)") if s is not None else "n/a"


VERB = {"search": ("answered", "queries"), "scrape": ("fetched", "URLs"), "browser": ("loaded", "pages")}


def finding(cat, rows):
    verb, unit = VERB[cat]
    if not rows:
        return ""
    kind = "news " if all(str(r["set"]).startswith("news") for r in rows) else ""
    k0, n0 = kn(rows[0])
    ns = sorted({kn(r)[1] for r in rows})
    same = len(ns) == 1
    head = f"{rows[0]['_name']} {verb} {k0} of {n0} {kind}{unit}"
    rest = ", ".join(f"{r['_name']} {kn(r)[0]}" + ("" if same else f" of {kn(r)[1]}") for r in rows[1:])
    nlab = f"n={ns[0]}" if same else f"n={ns[0]}–{ns[-1]}"
    if len(rows) == 1:
        tail = f"one provider tested at {nlab}, so there is nothing to compare yet"
    else:
        pairs = [(a, b) for i, a in enumerate(rows) for b in rows[i + 1:]]
        sep = lambda a, b: ci(a) and ci(b) and (ci(a)[0] > ci(b)[1] or ci(b)[0] > ci(a)[1])
        clear = [(a, b) for a, b in pairs if sep(a, b)]
        if not clear:
            tail = f"at {nlab} no gap is clear"
        elif len(clear) == len(pairs):
            tail = f"at {nlab} every gap is clear"
        else:
            lab = ", ".join(f"{a['_name']}–{b['_name']}" for a, b in clear)
            tail = f"at {nlab} only the {lab} gap{'s are' if len(clear) > 1 else ' is'} clear"
    return head + (", " + rest if rest else "") + "; " + tail


def week_of(r):
    """(year, week) from the set name's trailing YYYY-WW (e.g. news_2026-43), else (0, 0)."""
    m = re.search(r"(\d{4})-(\d{1,2})$", str(r.get("set") or ""))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def latest_per_provider(rows):
    """Keep one row per provider: its latest week (by set week, then run_date), never file order."""
    best = {}
    for r in rows:
        k = (week_of(r), str(r.get("run_date") or ""))
        if r["provider"] not in best or k > best[r["provider"]][0]:
            best[r["provider"]] = (k, r)
    return [r for _, r in best.values()]


def week_label(rows):
    sets = sorted({r["set"] for r in rows}, key=lambda s: week_of({"set": s}))
    wks = sorted({"%d-%02d" % week_of(r) for r in rows if week_of(r) != (0, 0)})
    return ("Week " + ", ".join(wks) + " · " if wks else "") + "set " + ", ".join(sets)


def run_dates(rows):
    by = {}
    for r in rows:
        by.setdefault(r.get("run_date") or "", []).append(r["_name"])
    if len(by) == 1:
        return f"Run {next(iter(by))}"
    return "Runs " + ", ".join(f"{d} ({', '.join(n)})" for d, n in sorted(by.items()))


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
    a, b = money(per), money(succ)
    return (f'<span class="v">{a}{" per 1k requests" if a != "n/a" else ""}</span><span class="sub">{b}{" per 1k successful requests" if b != "n/a" else " per successful request"}</span>'
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
    R = 12 if narrow else 40
    rh = 40 if narrow else 34
    top = 26
    H = top + rh * (len(rows) + len(nt)) + 34
    X = lambda f: L + f * (W - L - R)
    pid = f"plot-{cat}-{'n' if narrow else 'w'}"
    desc = finding(cat, rows) + ". " + "; ".join(f"{r['_name']} {frac(r)}, {ci_text(r)}" for r in rows) + "."
    if nt:
        desc += " Not tested: " + ", ".join(n for _, n, _ in nt) + "."
    g = [f'<title id="{pid}-t">{e(week_label(rows))}: {e(finding(cat, rows))}</title><desc id="{pid}-d">{e(desc)}</desc>']
    for f in (0, .25, .5, .75, 1):
        x = X(f)
        g.append(f'<line class="ax-grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top - 6}" y2="{H - 30}"/>'
                 f'<text class="ax-tick" x="{x:.1f}" y="{H - 14}" text-anchor="middle">{int(f * 100)}%</text>')
    g.append(f'<text class="ax-title" x="{W - R}" y="12" text-anchor="end">success rate →</text>')
    y = top + rh / 2
    cw = 7.2
    for r in rows:
        f = v(r["success_rate"]) or 0
        w = ci(r) or (f, f)
        nm = r["_name"] if not narrow or len(r["_name"]) <= 12 else r["_name"][:11] + "…"
        part = " pt--partial" if r.get("partial") else ""
        lab = frac(r)
        lw = len(lab) * cw
        if narrow:
            lx, anchor = min(max(X(f), L + lw / 2), W - 2 - lw / 2), "middle"
        elif X(w[1]) + 8 + lw <= W - 2:
            lx, anchor = X(w[1]) + 8, "start"
        elif X(w[0]) - 8 - lw >= L:
            lx, anchor = X(w[0]) - 8, "end"
        else:
            lx, anchor = X(f), "middle"
        ly = y + 4 if anchor != "middle" else y - 10
        g.append(f'<text class="pt-label" x="{L - 10}" y="{y + 4:.1f}" text-anchor="end">{e(nm)}</text>'
                 f'<line class="pt-ci-line" x1="{X(w[0]):.1f}" x2="{X(w[1]):.1f}" y1="{y:.1f}" y2="{y:.1f}"/>'
                 f'<g class="pt{part}"><circle class="pt-dot" cx="{X(f):.1f}" cy="{y:.1f}" r="5"/></g>'
                 f'<text class="pt-val" x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" data-w="{lw:.0f}">{e(lab)}</text>')
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


def flags(r, skip=()):
    return "".join(f'<span class="flag">{e(f)}</span>' for f in r.get("flags") or [] if f not in skip)


def table(cat, label, unit, rows, nt, n):
    th = ('<thead><tr><th scope="col" class="l c-rank">#</th><th scope="col" class="l">Provider</th><th scope="col">Success</th>'
          '<th scope="col">Latency p50</th><th scope="col">Entry tier $/1k</th><th scope="col">Volume tier $/1k</th><th scope="col" class="l c-notes">Notes</th></tr></thead>')
    body = []
    directional = any(str(f).startswith("below minimum") for r in rows for f in r.get("flags") or [])
    common = [f for f in (rows[0].get("flags") or []) if all(f in (r.get("flags") or []) for r in rows)] if rows else []
    for i, r in enumerate(rows, 1):
        rl = r.get("rate_limited") or {}
        to = r.get("timed_out") or {}
        notes = [f'<span class="notes-stack">{flags(r, common)}'
                 + (chip(f'{rl["v"]} {rl.get("label") or "rate-limited"}', rl.get("note") or "", "rate_limited") if v(rl) else "")
                 + (chip("Partial run", "", "partial_run") if r.get("partial") else "") + "</span>",
                 f'<span class="note-text">Run {e(r.get("run_date") or "")} · set {e(r["set"])}</span>']
        more = []
        if v(rl) and rl.get("note"):
            more.append(f'<span class="note-text">{e(rl["note"])}</span>')
        if v(to) and to.get("note"):
            more.append(f'<span class="note-text">{e(str(to["v"]))} timed out: {e(to["note"])}</span>')
        if r.get("free_quota_note"):
            more.append(f'<span class="note-text">Free quota: {e(r["free_quota_note"])}</span>')
        if r.get("cost_units_note"):
            more.append(f'<span class="note-text">{e(r["cost_units_note"])}</span>')
        if more:
            notes.append(f'<details class="row-notes"><summary>Quota and cost notes</summary>{"".join(more)}</details>')
        p50 = v(r.get("p50_latency_ms"))
        tos = (r.get("skipped_tos") or {}).get("count", 0)
        body.append(
            f'<tr data-id="{e(r["provider"])}"><td class="c-rank">{"–" if directional else i}</td><td class="c-prov">{badge(r["_name"], r["provider"])}</td>'
            f'<td class="c-acc" data-label="Success"><span class="v">{e(frac(r, ", "))}</span><span class="sub ci">{e(ci_text(r))}</span>'
            + (f'<span class="sub">{e(r["answered_display"])}</span>' if "(" in (r.get("answered_display") or "") else "") +
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
           f'scored only from its run log.' + (f' Every row: {e(", ".join(common))}.' if common else '') + (' No row has 25 or more items yet, so the order is directional and no rank is shown.' if directional else '') + '</caption>')
    return f'<table class="lb" data-cat="{cat}" id="table-{cat}">{cap}{th}<tbody>{"".join(body)}</tbody></table>'


STATUS_WORDS = {
    "excluded_tos_benchmarking": "Excluded: terms forbid benchmarking",
    "not_implemented": "Not implemented yet",
    "skipped_invalid_set": "Skipped: test set missing",
    "skipped_no_key": "Skipped: no API key",
    "skipped_not_month1": "Skipped: not on this month's free-tier list",
}


def status_words(code):
    return STATUS_WORDS.get(code) or str(code or "").replace("_", " ").capitalize()


def count_pct(share, n):
    s = v(share)
    if s is None:
        return "n/a"
    p = int(s * 100 + 0.5)
    x = s * n if isinstance(n, int) else None
    return f"{round(x)}/{n} ({p}%)" if x is not None and abs(x - round(x)) < 1e-9 else f"{p}%"


def freshness(d, names=None):
    fr = d.get("freshness") or []
    if not fr:
        return ""
    rows = "".join(
        f'<tr><td>{e((names or {}).get(f["provider"], f["provider"]))}</td><td data-label="Week">{e(f.get("week") or "")} {flags(f)}</td><td class="r num" data-label="n">{f.get("n")}</td>'
        f'<td class="r num" data-label="Fresh in top 10">{count_pct(f.get("fresh_hit_at_10"), f.get("n"))}</td>'
        f'<td class="r num" data-label="median lag h">{"n/a" if v(f.get("median_lag_h")) is None else f"{v(f.get("median_lag_h")):.1f}"}</td>'
        f'<td class="r num" data-label="censored">{count_pct(f.get("censored_share"), f.get("n"))}</td><td class="mono" data-label="set sha">{e((f.get("set_sha") or "")[:12])}</td></tr>'
        for f in fr)
    notes = "".join(f'<li class="muted">{e((names or {}).get(n["provider"], n["provider"]))}: {e(n["note"])}</li>' for n in d.get("freshness_notes") or [])
    return ('<h3 class="section-title">Freshness (weekly news set)</h3><table class="dt" id="freshness"><thead><tr><th>Provider</th><th>Week</th><th class="r">n</th>'
            '<th class="r">Fresh in top 10</th><th class="r">median lag h</th><th class="r">censored</th><th>set sha</th></tr></thead><tbody>'
            + rows + "</tbody></table>" + (f'<ul class="mt-4">{notes}</ul>' if notes else ""))


def run_status(d):
    fl = d.get("flags") or []
    sk = d.get("skips") or []
    sv = d.get("sets_valid") or []
    nr = d.get("not_run_yet") or []
    pub = sorted({r["set"] for rows in (d.get("tables") or {}).values() for r in rows if not r.get("mock")})
    out = [f'<section class="run-status" id="run-status" aria-labelledby="run-status-h"><h2 id="run-status-h">Run status {e(d.get("run_date") or "")}</h2>',
           f'<p class="muted">Generated <span class="mono">{e(d.get("generated_at") or "")}</span> from run logs. '
           f'<span data-stale-note data-generated="{e(d.get("generated_at") or "")}"></span></p>',
           f'<p id="sets-valid"><b>Valid sets this run:</b> {", ".join(f"<code>{e(s)}</code>" for s in sv) if sv else "none"}</p>',
           f'<p id="sets-published"><b>Published tables use:</b> {", ".join(f"<code>{e(s)}</code>" for s in pub) if pub else "no set"}'
           + (f'. {"These are" if len(pub) > 1 else "This is"} not among this run\'s valid sets, so the tables show the latest set with results.' if pub and not set(pub) & set(sv) else "") + '</p>']
    if fl:
        out.append('<ul id="run-flags">' + "".join(f'<li class="flag">{e(f["set"])}: {e(f["flag"])}</li>' for f in fl) + "</ul>")
    if nr:
        out.append('<h3>Not run yet</h3><ul>' + "".join(f'<li>{e(n["provider"])} ({e(", ".join(n["categories"]))}): not run yet. <span class="muted">{e(n.get("reason") or "")}</span></li>' for n in nr) + "</ul>")
    if sk:
        out.append('<table class="dt" id="skips"><caption>Skipped</caption><thead><tr><th>Skipped</th><th>Status</th><th>Reason</th></tr></thead><tbody>'
                   + "".join(f'<tr><td>{e(k.get("set") or " / ".join(x for x in (k.get("provider"), k.get("category")) if x) or k.get("scope"))}</td>'
                             f'<td data-label="Status" title="{e(k.get("status"))}">{e(status_words(k.get("status")))}</td><td data-label="Reason" class="muted wide">{e(status_words(k["reason"]) if k.get("reason") in STATUS_WORDS else k.get("reason"))}</td></tr>' for k in sk)
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
        rows = latest_per_provider(rows)
        rows.sort(key=lambda r: -(v(r["success_rate"]) or 0))
        nt = untested(d or {}, cat, {r["provider"] for r in rows}, provs)
        sel = n == 1
        tabs.append(f'<button class="tab" role="tab" type="button" id="tab-{cat}" aria-controls="panel-{cat}" data-tab="{cat}" data-cat="{cat}" '
                    f'aria-selected="{"true" if sel else "false"}"{"" if sel else " tabindex=\"-1\""}>{icon(cat, "tab__icon")}{label} '
                    f'<span class="tab__count">{len(rows)}/{len(rows) + len(nt)}</span></button>')
        sets = sorted({r["set"] for r in rows})
        ns = [kn(r)[1] for r in rows]
        meta = ((f"n = {ns[0]} {unit} each" if len(set(ns)) == 1 else f"n = {', '.join(map(str, ns))} {unit}") + " · " + ", ".join(sets)) if rows else ""
        if rows:
            fig = (f'<figure class="chart-card" data-cat="{cat}" id="chart-{cat}"><figcaption class="chart-card__head"><span><strong>Fig. {n}</strong> '
                   f'<span class="fig-week" data-sets="{e(" ".join(sorted({r["set"] for r in rows})))}">{e(week_label(rows))}</span> <span class="fig-title">{e(finding(cat, rows))}</span><span class="sub fig-sub">{e(label)} · {e(run_dates(rows))}</span></span>'
                   f'<span class="chart-card__meta">{e(meta)}</span></figcaption><div class="chart-card__plot">'
                   + plot(cat, label, rows, nt, 720, False) + plot(cat, label, rows, nt, 340, True) + "</div>"
                   "<p class=\"chart-card__foot\">Lines show 95% Wilson intervals; overlapping lines mean the order isn't settled.</p></figure>")
            lead = rows[0]
            call = (f'<aside class="callouts" aria-label="{label} summary"><div class="callout callout--lead"><p class="eyebrow">Highest success rate</p>'
                    f'<p class="callout__value">{e(lead["_name"])}</p><p class="callout__sub">{e(frac(lead))} · {e(ci_text(lead))}</p></div>'
                    f'<div class="callout"><p class="eyebrow">Run dates</p><p class="callout__sub">{e(run_dates(rows))}</p></div>'
                    '<div class="callout howto"><strong>How to read this</strong><p>Dots are success rates; the line through each dot is its 95% Wilson interval. '
                    'Rows on fewer than 25 items are early and directional, not a ranking. Dashed rows have no result yet.</p></div></aside>')
            body = f'<div class="board">{fig}{call}</div>{table(cat, label, unit, rows, nt, n)}'
        else:
            body = (f'<p class="empty-cat" id="empty-{cat}">{e(label)}: no providers tested yet this week ({len(nt)} queued).</p>'
                    f'<p class="muted" id="queued-{cat}">{e(", ".join(x for _, x, _ in nt))}</p>')
        panel = (f'<div class="tabpanel" role="tabpanel" id="panel-{cat}" aria-labelledby="tab-{cat}" data-cat="{cat}" tabindex="0">'
                 f'<h2 class="visually-hidden">{label}</h2>{body}'
                 + (freshness(d, nm) if cat == "search" and d else "")
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
