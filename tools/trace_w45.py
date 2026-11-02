#!/usr/bin/env python3
"""Trace every published week-45 cell on / back to content/w45-tables-regrade.json (AWI-W45-PUBLISH-001).

Usage: python3 tools/trace_w45.py [dist/index.html] [--evidence PATH/tables-regrade.json] [--json OUT]
Checks (exit 1 on any failure):
  1. the regrade file's sha256 equals content/w45-results.json regrade_sha256 (and, with --evidence, its bytes equal that file);
  2. section#latest-week has exactly one table row per week-45 regrade row (run_date == manifest run_date), none extra, none missing;
  3. every cell carries data-src naming the regrade fields of ITS column (fixed map below, not read from render.py),
     and its text equals that field formatted here (own half-up formatters, independent of prices.py);
  4. the Passed link points to the row's own run log at the manifest run_logs_commit;
  5. no number appears in the section outside a traced cell unless it is in the copy.md "Week 45 results" text;
  6. Apify has no week-45 row (cap reached, out until its Nov 16 cycle);
  7. each live provider in the manifest's live_not_held with no week-45 regrade row has exactly one '<Name>: not run this week' line, and no other.
"""
import hashlib, html, json, re, sys
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser
from pathlib import Path

R = Path(__file__).resolve().parent.parent
NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def pct(x):
    return f"{int((Decimal(repr(x)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))}%"


def day(iso):
    y, m, d = (int(t) for t in iso.split("-"))
    return f"{MONTHS[m - 1]} {d}, {y}"


# column -> (data-src suffixes, expected text from the regrade row)
COLUMNS = {
    "Provider": (["provider"], None),   # display name from data/_upstream/providers.json
    "Category": ([""], None),           # the regrade table key
    "Set": (["set"], lambda r: r["set"]),
    "Run date": (["run_date"], lambda r: r["run_date"]),
    "Passed / checks": (["passed.v", "attempted.v"], lambda r: f'{r["passed"]["v"]} of {r["attempted"]["v"]}'),
    "Failed / checks": (["failed.v"], lambda r: str(r["failed"]["v"])),
    "Pass rate": (["success_rate.v"], lambda r: pct(r["success_rate"]["v"])),
    "Per 1,000 passed checks": (["entry_tier_cost_per_successful_1k.display"], lambda r: r["entry_tier_cost_per_successful_1k"]["display"] or "n/a"),
    "List price per 1,000 calls": (["entry_tier_cost_per_1k.display"], lambda r: r["entry_tier_cost_per_1k"]["display"] or "n/a"),
    "Skipped (terms)": (["skipped_tos.count"], lambda r: "n/a" if (r.get("skipped_tos") or {}).get("count") is None else str(r["skipped_tos"]["count"])),
    "Flags": (["flags"], lambda r: ", ".join(r["flags"]) or "none"),
}


class Section(HTMLParser):
    """Collects section#latest-week: every data-src element's (src, label, text, hrefs), the row providers, and the full text."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0; self.on = False; self.stack = []; self.cells = []; self.text = []; self.untraced = []; self.rows = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "section" and a.get("id") == "latest-week":
            self.on = True; self.depth = 0
        if not self.on:
            return
        if tag == "section":
            self.depth += 1
        if tag == "tr" and "data-provider" in a:
            self.rows.append(a["data-provider"])
        if "data-src" in a:
            self.stack.append({"src": a["data-src"], "label": a.get("data-label"), "text": "", "hrefs": [], "tag": tag})
        if tag == "a" and self.stack:
            self.stack[-1]["hrefs"].append(a.get("href"))

    def handle_endtag(self, tag):
        if not self.on:
            return
        if self.stack and tag == self.stack[-1]["tag"]:
            self.cells.append(self.stack.pop())
        if tag == "section":
            self.depth -= 1
            if self.depth == 0:
                self.on = False

    def handle_data(self, data):
        if not self.on:
            return
        self.text.append(data)
        if self.stack:
            self.stack[-1]["text"] += data
        else:
            self.untraced.append(data)


def norm(s):
    return " ".join(s.split())


def trace(index_html, evidence=None):
    errs, ok = [], []
    man = json.loads((R / "content/w45-results.json").read_text())
    rpath = R / man["regrade_file"]
    raw = rpath.read_bytes()
    if hashlib.sha256(raw).hexdigest() != man["regrade_sha256"]:
        errs.append(f"{man['regrade_file']}: sha256 differs from manifest regrade_sha256")
    if evidence is not None:
        if Path(evidence).read_bytes() != raw:
            errs.append(f"{man['regrade_file']}: bytes differ from evidence {evidence}")
        else:
            ok.append(f"regrade file byte-identical to {evidence}")
    doc = json.loads(raw)
    names = {p["id"]: p["name"] for p in json.loads((R / "data/_upstream/providers.json").read_text())["providers"]}
    want = {f"tables.{c}.{i}": (c, r) for c, rows in doc["tables"].items() for i, r in enumerate(rows) if r.get("run_date") == man["run_date"]}
    if any(r["provider"] == "apify" for _, r in want.values()):
        errs.append("regrade has an Apify week-45 row; Apify should be out until its Nov 16 cycle")
    sec = Section(); sec.feed(Path(index_html).read_text())
    if not sec.text:
        return ["section#latest-week not found"], ok, 0
    if "apify" in sec.rows:
        errs.append("table shows an Apify week-45 row")
    by_row = {}
    for c in sec.cells:
        if c["label"] is None:
            continue
        key = ".".join(c["src"].split(",")[0].split(".")[:3])
        by_row.setdefault(key, {}).setdefault(c["label"], []).append(c)
    if sorted(by_row) != sorted(want):
        errs.append(f"rows on page {sorted(by_row)} != week-45 regrade rows {sorted(want)}")
    n = 0
    for key, (cat, r) in want.items():
        cells = by_row.get(key, {})
        if sorted(cells) != sorted(COLUMNS):
            errs.append(f"{key}: columns {sorted(cells)} != {sorted(COLUMNS)}")
        for col, (fields, fmt) in COLUMNS.items():
            for c in cells.get(col, []):
                n += 1
                exp_src = ",".join(f"{key}.{f}" if f else key for f in fields)
                exp = names.get(r["provider"], r["provider"]) if col == "Provider" else cat if col == "Category" else fmt(r)
                got = norm(c["text"])
                if c["src"] != exp_src:
                    errs.append(f"{key} {col}: data-src {c['src']!r} != {exp_src!r}")
                elif got != norm(exp):
                    errs.append(f"{key} {col}: page {got!r} != regrade {exp!r}")
                else:
                    ok.append(f"{exp_src} = {got}")
                if col == "Passed / checks":
                    files = [s.get("file") for s in r["passed"].get("src", [])]
                    url = f"https://github.com/hazeydata/agentwebindex/blob/{man['run_logs_commit']}/bench/{files[0]}" if files else None
                    if c["hrefs"] != [url]:
                        errs.append(f"{key} Passed link {c['hrefs']} != {url}")
    # header cells: run date and the ran-this-week list are derived from the same rows
    heads = {c["src"]: norm(c["text"]) for c in sec.cells if c["label"] is None and c["src"] != "not_run"}
    href = {c["src"]: c["hrefs"] for c in sec.cells if c["label"] is None}
    dates = sorted({r["run_date"] for _, r in want.values()})
    if heads.get("run_date") != (day(dates[0]) if len(dates) == 1 else None):
        errs.append(f"heading run date {heads.get('run_date')!r} != {dates}")
    else:
        ok.append(f"run_date = {heads['run_date']}")
    ran = []
    for _, r in want.values():
        nm = names.get(r["provider"], r["provider"])
        ran += [nm] if nm not in ran else []
    if heads.get("provider") != ", ".join(ran):
        errs.append(f"ran-this-week {heads.get('provider')!r} != {ran}")
    else:
        ok.append(f"provider (ran this week) = {heads['provider']}")
    # 'X: not run this week' lines: one per live provider (manifest live_not_held) with no week-45 regrade row, derived from the rows
    ran_ids = {r["provider"] for _, r in want.values()}
    if man.get("live_not_held") != {"keenable": "Keenable"}:   # Keenable-only ruling (Lucille 2, Nov 2 2026); independent of pins.py
        errs.append(f"manifest live_not_held {man.get('live_not_held')} is not exactly Keenable (Keenable-only ruling)")
    exp_nr = [nm for pid, nm in (man.get("live_not_held") or {}).items() if pid not in ran_ids]
    got_nr = [norm(c["text"]) for c in sec.cells if c["label"] is None and c["src"] == "not_run"]
    full = full_text = norm("".join(sec.text))
    if got_nr != exp_nr:
        errs.append(f"not-run lines {got_nr} != live providers with no week-45 row {exp_nr}")
    else:
        for nm in exp_nr:
            if f"{nm}: not run this week" not in full:
                errs.append(f"not-run line for {nm} is not '{nm}: not run this week'")
            else:
                ok.append(f"not_run = {nm} (no week-45 regrade row)")
    # sample clause: a week-45 search_evergreen row whose set_rows is below the full set's size. The total is the set_rows of a
    # regrade row (any week) on the same set_sha with no sample_note, i.e. a full-set run; the row's own sample_note must agree.
    exp_s = []
    for key, (c, r) in want.items():
        if r.get("set") != "search_evergreen":
            continue
        full = {x.get("set_rows") for rows in doc["tables"].values() for x in rows if x.get("set_sha") == r.get("set_sha") and not x.get("sample_note")}
        if len(full) == 1 and r.get("set_rows") < next(iter(full)):
            tot = next(iter(full))
            if f"first {r['set_rows']} of {tot} items" not in (r.get("sample_note") or ""):
                errs.append(f"{key}: sample_note {r.get('sample_note')!r} disagrees with full-set size {tot}")
            exp_s.append((key, names.get(r["provider"], r["provider"]), str(r["set_rows"]), str(tot)))
    got_s = [(k.split(":", 1)[1], heads.get(f"sample_provider:{k.split(':', 1)[1]}"), heads.get(f"sample_n:{k.split(':', 1)[1]}"), heads.get(k))
             for k in heads if k.startswith("sample_total:")]
    if sorted(got_s) != sorted(exp_s) or any(k.startswith(("sample_n:", "sample_provider:")) and k.split(":", 1)[1] not in [g[0] for g in got_s] for k in heads):
        errs.append(f"sample clause {got_s} != regrade-derived {exp_s}")
    else:
        for key, nm, a, t in exp_s:
            if f"{nm}'s evergreen run used {a} of the {t} evergreen questions." not in full_text:
                errs.append(f"sample clause for {key} not worded as copy")
            else:
                ok.append(f"sample = {nm} {a} of {t} ({key} set_rows; full-set size from same set_sha)")
    if "compare rows only within a run." not in full_text:
        errs.append("comparison line missing")
    # source line: the run-logs commit from the manifest, and the run date from the rows
    sha = man["run_logs_commit"]
    if heads.get("run_logs_commit") != sha[:7] or href.get("run_logs_commit") != [f"https://github.com/hazeydata/agentwebindex/commit/{sha}"]:
        errs.append(f"source sha {heads.get('run_logs_commit')!r} {href.get('run_logs_commit')} != manifest run_logs_commit {sha}")
    elif heads.get("source_date") != (day(dates[0]) if len(dates) == 1 else None):
        errs.append(f"source date {heads.get('source_date')!r} != {dates}")
    elif f"Source: tables.py regrade of the {heads['source_date']} run logs (agentwebindex {sha[:7]})" not in full_text:
        errs.append("source line not worded as copy")
    else:
        ok.append(f"source = agentwebindex {sha[:7]}, {heads['source_date']}")
    copy = "\n".join(_copy_section())
    allowed = set(NUM.findall(copy + " " + " ".join(COLUMNS)))   # copy text and the fixed column headers
    stray = sorted({t for t in NUM.findall(" ".join(sec.untraced)) if t not in allowed})
    if stray:
        errs.append(f"untraced numbers in section#latest-week: {stray}")
    return errs, ok, n


def _copy_section():
    out, on = [], False
    for line in (R / "content/copy.md").read_text().splitlines():
        if line.startswith("## "):
            on = line[3:].strip() == "Week 45 results"
        elif on and not line.startswith("<!--"):
            out.append(line)
    return out


def main(argv):
    args = list(argv); ev = js = None
    if "--evidence" in args:
        i = args.index("--evidence"); ev = args[i + 1]; del args[i:i + 2]
    if "--json" in args:
        i = args.index("--json"); js = args[i + 1]; del args[i:i + 2]
    idx = args[0] if args else str(R / "dist/index.html")
    errs, ok, n = trace(idx, ev)
    for line in ok:
        print("OK  ", line)
    for line in errs:
        print("FAIL", line)
    print(f"trace_w45: {n} table cells checked, {len(ok)} OK, {len(errs)} failures")
    if js:
        Path(js).write_text(json.dumps({"cells": n, "ok": ok, "failures": errs}, indent=1) + "\n")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
