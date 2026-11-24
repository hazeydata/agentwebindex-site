#!/usr/bin/env python3
"""AWI-W48-BASE-RUN-001: check every numeric claim in the built #latest-week against the staged Week 48 regrade.

Usage: python3 tools/check_w48_numbers.py [dist-dir]   (default: ./dist)
Exit 0 only if every assertion passes. Prints "matched M / total N".
Hard bans checked over every dist HTML file: no Bright Data 69/120 score, no parked evergreen regrade numbers (Tavily 87, Exa 59).
"""
import hashlib, html, json, re, sys
from pathlib import Path

R = Path(__file__).resolve().parent.parent
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
results = []


def chk(name, ok, detail=""):
    results.append((bool(ok), name, detail))


def day(iso):
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{MONTHS[m - 1]} {d}, {y}"


def text(s):
    t = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ").split())
    return re.sub(r"\s+([.,;:)])", r"\1", t).replace("( ", "(")


N1, N2 = r"(?<![\d$.,])", r"(?!\d|,\d|\.\d)"   # standalone number: not part of $11.59, 1,087 or 87.5


def main(argv):
    dist = Path(argv[0]) if argv else R / "dist"
    raw = (R / "content/w45-tables-regrade.json").read_bytes()
    chk("regrade file sha256 starts 8772701b", hashlib.sha256(raw).hexdigest().startswith("8772701b"))
    staged = R / "data/benchmarks/staged/latest-2026-48.json"
    chk("regrade file is byte-identical to staged/latest-2026-48.json", staged.read_bytes() == raw)
    doc = json.loads(raw)
    man = json.loads((R / "content/w45-results.json").read_text())
    chk("manifest week 2026-48, run 2026-11-24, extra_rows only browserless@2026-10-23",
        man["week"] == "2026-48" and man["run_date"] == "2026-11-24" and man["extra_rows"] == {"browserless": "2026-10-23"})
    rows = [(c, r) for c in ("search", "scrape", "browser") for r in doc["tables"].get(c, [])
            if r["run_date"] == man["run_date"] or man["extra_rows"].get(r["provider"]) == r["run_date"]]
    want = [(c, r["provider"], f"{r['passed']['v']} of {r['attempted']['v']}", day(r["run_date"])) for c, r in rows]
    exp = [("search", "apify", "1 of 9", "Nov 24, 2026"), ("search", "exa", "15 of 16", "Nov 24, 2026"),
           ("search", "firecrawl", "13 of 16", "Nov 24, 2026"), ("search", "tavily", "15 of 16", "Nov 24, 2026"),
           ("search", "tinyfish", "13 of 16", "Nov 24, 2026"), ("scrape", "browserless", "79 of 120", "Oct 23, 2026"),
           ("browser", "apify", "12 of 12", "Nov 24, 2026"), ("browser", "browserless", "12 of 12", "Nov 24, 2026"),
           ("browser", "tinyfish", "8 of 12", "Nov 24, 2026")]
    chk("regrade rows (+extra) are the expected nine, in order", want == exp, str(want))

    page = (dist / "index.html").read_text()
    m = re.search(r'<section id="latest-week">.*?</section>', page, re.S)
    chk("#latest-week present", m)
    sec = m.group(0) if m else ""
    trs = re.findall(r'<tr data-provider="([^"]+)">(.*?)</tr>', sec, re.S)
    got = []
    for prov, body in trs:
        cells = dict(re.findall(r'data-label="([^"]+)"[^>]*>(.*?)</t[dh]>', body, re.S))
        got.append((text(cells.get("Category", "")), prov, text(cells.get("Passed / checks", "")), text(cells.get("Run date", "")), cells))
    chk("page table rows match the regrade rows (category, provider, passed of checked, run date), in order",
        [g[:4] for g in got] == exp, str([g[:4] for g in got]))
    for (c, r), g in zip(rows, got):
        cells = g[4]
        chk(f"{c}/{r['provider']}: failed, set, skipped cells", text(cells.get("Failed / checks", "")) == str(r["failed"]["v"])
            and text(cells.get("Set", "")) == r["set"] and text(cells.get("Skipped (terms)", "")) == str((r.get("skipped_tos") or {}).get("count", "n/a")))
    chk("no Bright Data table row", 'data-provider="brightdata"' not in sec)

    t = text(sec)
    for claim in ("Ran Nov 24, 2026:", "Week 48 results, Nov 24, 2026 run", "16 items, under the 25 we want", "first 9 of this week's 16 news items",
                  "passed 1.", "Exa and Tavily each passed 15 of 16", "Firecrawl and TinyFish each passed 13",
                  "TinyFish passed 8 of 12 fetch checks, up from 4 of 14 last week", "Apify and Browserless passed all 12",
                  "Browserless's scrape row is from the Oct 23, 2026 run", "Its fetch row above is from the Nov 24, 2026 run",
                  "Its last complete scrape run is Nov 2, 2026", "Source: tables.py regrade of the Nov 24, 2026 run logs (agentwebindex 1c36065)",
                  'href="https://agentwebindex.com/methodology/"'):
        chk(f"section says: {claim}", claim in (sec if claim.startswith("href") else t))
    ran = re.search(r"Ran Nov 24, 2026: (.*?)\.", t)
    chk("Ran list excludes the Oct 23 scrape row's extras (Browserless listed only via its Nov 24 fetch row; no Bright Data)",
        ran and "Bright Data" not in ran.group(1) and ran.group(1) == "Apify, Exa, Firecrawl, Tavily, TinyFish, Browserless")
    chk("no 'Week 48' label next to Browserless scrape note / Bright Data note",
        not re.search(r"Week 48[^.]*(scrape row|Bright Data)|(scrape row|Bright Data)[^.]*Week 48", t))
    chk("Bright Data note is a paragraph, not a row", 'data-copy="brightdata-note"' in sec and 'data-provider="brightdata"' not in sec)
    chk("browserless scrape row-note follows the scrape row",
        re.search(r'data-provider="browserless">(?:(?!</tr>).)*Oct 23, 2026.*?</tr><tr class="row-note">.*?browserless-scrape-note', sec, re.S))
    chk("Nov 24, 2026 count: 8 rows + heading + source date + Ran line + coverage/notes >= 10", len(re.findall(r"Nov 24, 2026", sec)) >= 10)

    # chart
    fig = re.search(r'<figure class="chart" id="chart-week48-pass-rate">(.*?)</figure>', sec, re.S)
    chk("W48 chart figure inside #latest-week", fig)
    labels = set(html.unescape(x) for x in re.findall(r'aria-label="([^"]*)"', fig.group(1))) if fig else set()
    alt = ("Week 48 news search: 4 providers passed 13 to 15 of 16 checks, with overlapping intervals; "
           "TinyFish fetch passed 8 of 12, up from 4 of 14 a week earlier")
    chk("W48 chart aria-label is the approved alt (one value, all variants)", labels == {alt}, str(labels))
    chk("W48 chart has 4 variants (350/720 x light/dark)", fig and len(re.findall(r'class="ch ch-(?:350|720) ch-(?:light|dark)"', fig.group(1))) == 4)
    nums = {"15 of 16": 2, "13 of 16": 2}
    chk("alt numbers match regrade: search passed counts 13..15 of 16 for 4 non-Apify providers",
        sorted(r["passed"]["v"] for c, r in rows if c == "search" and r["provider"] != "apify") == [13, 15, 15, 13][:0] or
        sorted(r["passed"]["v"] for c, r in rows if c == "search" and r["provider"] != "apify") == [13, 13, 15, 15])
    tf = next(r for c, r in rows if c == "browser" and r["provider"] == "tinyfish")
    chk("alt TinyFish fetch 8 of 12 matches regrade", (tf["passed"]["v"], tf["attempted"]["v"]) == (8, 12))
    chk("copy alt equals chart-alt.md", f'"{alt}"' in (R / "content/chart-alt.md").read_text())

    # bans over every built html
    files = sorted(dist.rglob("*.html"))
    bad69 = [str(f.relative_to(dist)) for f in files if re.search(r"69\s*(?:/|of|\s)\s*120", text(f.read_text()))
             or re.search(r"69/120|69 of 120", f.read_text())]
    chk(f"69/120 (Bright Data score) absent from all {len(files)} dist HTML files", not bad69, str(bad69))
    ban = []
    for f in files:
        s = html.unescape(f.read_text())
        if re.search(r"(?i)\btavily\b[^<>]{0,40}%s87%s|%s87%s[^<>]{0,40}\btavily\b|\bexa\b[^<>]{0,40}%s59%s|%s59%s[^<>]{0,40}\bexa\b" % ((N1, N2) * 4), s):
            ban.append(str(f.relative_to(dist)))
    chk("Tavily 87 / Exa 59 (parked evergreen regrade) absent from all dist HTML", not ban, str(ban))
    chk("those numbers absent from the W48 chart alt and SVG text",
        not re.search(r"\b(87|59)\b", alt) and not (fig and re.search(r"(?i)\btavily\b[^<>]{0,40}%s87%s|\bexa\b[^<>]{0,40}%s59%s" % ((N1, N2) * 2), fig.group(1))))

    ok = sum(1 for r in results if r[0])
    for good, name, detail in results:
        print(("OK   " if good else "FAIL ") + name + ("" if good or not detail else f"  [{detail[:300]}]"))
    print(f"check_w48_numbers: matched {ok} / total {len(results)}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
