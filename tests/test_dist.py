import csv, html, json, re, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / "dist"
BENCH = json.loads((R / "data/benchmarks/latest.json").read_text())
import sys
sys.path.insert(0, str(R))
import render  # noqa: E402

PROVS = {x["id"]: x.get("name") or x["id"] for x in json.loads((R / "data/_upstream/providers.json").read_text())["providers"]}


def latest(cat):
    """Expected table rows for cat: latest week per provider from the JSON, named, ordered by success rate."""
    rows = [dict(r, _name=PROVS.get(r["provider"], r["provider"])) for r in BENCH["tables"].get(cat, []) if not r.get("mock")]
    return sorted(render.latest_per_provider(rows), key=lambda r: -(r["success_rate"]["v"] or 0))


def real_strings():
    out = []
    for cat in BENCH["tables"]:
        for r in latest(cat):
            out += [render.ci_text(r), render.frac(r), render.frac(r, ", ")]
    return out


TEXT = (".html", ".css", ".js", ".json", ".csv", ".txt", ".xml", ".svg", ".jsonl", "")


def files():
    return [p for p in D.rglob("*") if p.is_file() and p.suffix in TEXT]


def page(path):
    return (D / path.strip("/") / "index.html" if path != "/" else D / "index.html").read_text()


def section(h, start, end):
    i = h.index(start)
    return h[i:h.index(end, i)]


def rows_of(h, cat):
    t = section(h, f'id="table-{cat}"', "</table>")
    return re.findall(r"<tr[ >].*?</tr>", t.split("<tbody>", 1)[1], re.S)


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


class Dist(unittest.TestCase):
    def test_no_pack_sample_values(self):
        vals = json.loads((R / "tests/pack_sample_values.json").read_text())["values"]
        self.assertGreater(len(vals), 100)
        real = " ".join(real_strings())
        vals = [v for v in vals if v not in real]  # a real computed value may coincide with a sample number
        hits = [(v, str(p.relative_to(D))) for p in files() for v in vals if v in p.read_text(errors="ignore")]
        self.assertEqual(hits, [])

    def test_no_sample_data_file(self):
        self.assertFalse((D / "data/latest.json").exists())
        self.assertFalse((D / "data/schema.json").exists())
        for p in files():
            self.assertNotIn('"sample": true', p.read_text(errors="ignore"), p)

    def test_no_external_fonts_or_cdn(self):
        allowed = {"https://subscribe-forms.beehiiv.com/v3/loader.js"}
        for p in D.rglob("*"):
            if p.suffix not in (".html", ".css", ".js"):
                continue
            s = p.read_text()
            self.assertNotRegex(s, r"@import", p)
            self.assertNotRegex(s, r"url\(\s*['\"]?(https?:)?//", p)
            self.assertNotRegex(s, r"(?i)fonts\.(googleapis|gstatic)|cdnjs|jsdelivr|unpkg|typekit|fontawesome", p)
            for tag, url in re.findall(r"<(link|script|img|source)\b[^>]*?(?:href|src)=\"([^\"]+)\"", s):
                if tag == "link" and re.search(r'rel="canonical"', s[s.find(url) - 200:s.find(url)]):
                    continue
                if url.startswith(("http:", "https:", "//")):
                    self.assertIn(url, allowed, (p, tag, url))

    def test_fonts_self_hosted_with_license(self):
        css = (D / "style.css").read_text()
        urls = re.findall(r"url\(\"(/assets/fonts/[^\"]+)\"\)", css)
        self.assertEqual(len(urls), 7)
        for u in urls:
            self.assertTrue((D / u.lstrip("/")).exists(), u)
        self.assertIn("SIL Open Font License, Version 1.1", (D / "assets/fonts/OFL.txt").read_text())

    def test_real_search_rows(self):
        h = page("/")
        tested = [r for r in rows_of(h, "search") if "is-untested" not in r]
        want = latest("search")
        self.assertEqual([re.search(r'data-id="([^"]+)"', r).group(1) for r in tested], [r["provider"] for r in want])
        for x, r in zip(want, tested):
            t = text(r)
            p50 = x["p50_latency_ms"]["v"]
            for w in (render.frac(x, ", "), render.ci_text(x), f"n={x['attempted']['v']}", f"Run {x['run_date']}", x["set"],
                      "n/a" if p50 is None else f"{p50:.0f} ms"):
                self.assertIn(w, t, (x["provider"], w))
            self.assertIn("<details", r)
            self.assertNotIn("Free quota", text(r.split("<details", 1)[0]))

    def test_real_browser_rows(self):
        tested = [r for r in rows_of(page("/"), "browser") if "is-untested" not in r]
        want = latest("browser")
        self.assertEqual(len(tested), len(want))
        for x, r in zip(want, tested):
            for w in (x["_name"], render.frac(x, ", "), render.ci_text(x), x["set"]):
                self.assertIn(w, text(r))

    def test_values_match_json(self):
        h = page("/")
        for cat, rows in BENCH["tables"].items():
            if not rows:
                continue
            got = {re.search(r'data-id="([^"]+)"', r).group(1): text(r) for r in rows_of(h, cat) if "is-untested" not in r}
            self.assertEqual(sorted(got), sorted({r["provider"] for r in rows if not r.get("mock")}))
            for r in latest(cat):
                self.assertIn(f'{r["passed"]["v"]}/{r["attempted"]["v"]}, {int(r["success_rate"]["v"] * 100 + 0.5)}%', got[r["provider"]])

    def test_untested_shows_not_tested_never_zero(self):
        h = page("/")
        provs = json.loads((R / "data/_upstream/providers.json").read_text())["providers"]
        excluded = {x["provider"] for x in BENCH["exclusions"]}
        for cat in ("search", "scrape", "browser"):
            have = {r["provider"] for r in BENCH["tables"][cat]}
            want = [p for p in provs if cat in p["categories"] and p["id"] not in have | excluded]
            panel = section(h, f'id="panel-{cat}"', 'class="lb-foot"')
            if not have:
                self.assertNotIn("<figure", panel)
                self.assertNotIn("<table", panel)
                self.assertIn(f'{cat.title()}: no providers tested yet this week ({len(want)} queued).', panel)
                self.assertEqual(text(section(panel, f'id="queued-{cat}"', "</p>")).split(">", 1)[1], ", ".join(p["name"] for p in want))
                continue
            un = [r for r in rows_of(h, cat) if "is-untested" in r]
            self.assertEqual(sorted(re.search(r'data-id="([^"]+)"', r).group(1) for r in un), sorted(p["id"] for p in want), cat)
            for r in un:
                self.assertIn("Not tested", r)
                self.assertNotRegex(text(r), r"\d%|\$\d")
            chart = section(h, f'id="chart-{cat}"', "</figure>")
            self.assertNotIn("(0%)", chart)
            self.assertEqual(chart.count(">not tested<"), 2 * len(want))

    def test_figures_no_legend_wilson_caption_title(self):
        h = page("/")
        figs = re.findall(r"<figure.*?</figure>", h, re.S)
        self.assertEqual(len(figs), sum(1 for v in BENCH["tables"].values() if v))
        for f in figs:
            self.assertNotIn("chart-card__key", f)
            self.assertNotIn("Not tested:", "".join(re.findall(r'<p class="chart-card__foot">.*?</p>', f)))
            self.assertNotIn("pt-bar", f)
            self.assertIn("Lines show 95% Wilson intervals; overlapping lines mean the order isn't settled.", html.unescape(f))
            self.assertIn("queries each" if 'data-cat="search"' in f else "each", f)
        for cat in BENCH["tables"]:
            rows = latest(cat)
            if not rows:
                continue
            s = html.unescape(section(h, f'id="chart-{cat}"', "</figcaption>"))
            self.assertIn(render.finding(cat, rows), s)
            self.assertIn(render.run_dates(rows), s)
            for r in rows:
                self.assertIn(f">{render.frac(r)}<", h)

    def test_narrow_labels_fit(self):
        h = page("/")
        for svg in re.findall(r'<svg class="plot--narrow".*?</svg>', h, re.S):
            W = float(re.search(r'viewBox="0 0 ([\d.]+)', svg).group(1))
            for x, a, w in re.findall(r'class="pt-val" x="([\d.]+)" y="[\d.]+" text-anchor="(\w+)" data-w="(\d+)"', svg):
                x, w = float(x), float(w)
                lo = x if a == "start" else x - w if a == "end" else x - w / 2
                self.assertGreaterEqual(lo, 92 - 10)
                self.assertLessEqual(lo + w, W)

    def test_excluded_provider_not_in_tables(self):
        h = page("/")
        for cat in ("search", "scrape", "browser"):
            self.assertNotIn('data-id="brave"', section(h, f'id="panel-{cat}"', 'class="lb-foot"'))
        self.assertIn('id="exclusions"', h)
        self.assertIn("Brave Search API", section(h, 'id="exclusions"', "</div>"))

    def test_status_flags_sets_valid_visible(self):
        h = page("/")
        rs = section(h, 'id="run-status"', "</section>")
        for s in BENCH["sets_valid"]:
            self.assertIn(s, section(rs, 'id="sets-valid"', "</p>"))
        for f in BENCH["flags"]:
            self.assertIn(f'{f["set"]}: {html.escape(f["flag"])}', rs)
        for k in BENCH["skips"]:
            self.assertIn(html.escape(k["reason"]), rs)
        self.assertIn("brightdata (scrape): not run yet", rs)
        self.assertIn(BENCH["freshness_notes"][0]["note"], h)
        for p in ("/", "/prices/", "/methodology/", "/data/"):
            s = page(p)
            self.assertIn(f'data-generated="{BENCH["generated_at"]}"', s)
            self.assertIn("Valid sets: " + ", ".join(BENCH["sets_valid"]), s)

    def test_freshness_table(self):
        t = text(section(page("/"), 'id="freshness"', "</table>"))
        for f in BENCH["freshness"]:
            for want in (PROVS.get(f["provider"], f["provider"]), render.count_pct(f["fresh_hit_at_10"], f["n"]), f["set_sha"][:12]):
                self.assertIn(want, t)
        self.assertIn("Fresh in top 10", t)
        self.assertNotIn("fresh_hit@10", t)

    def test_week_set_label_from_data(self):
        h = page("/")
        for cat in BENCH["tables"]:
            rows = latest(cat)
            if not rows:
                continue
            head = html.unescape(section(h, f'id="chart-{cat}"', "</figcaption>"))
            sets = sorted({r["set"] for r in rows})
            wks = sorted({"%d-%02d" % render.week_of(r) for r in rows})
            self.assertIn(f"Week {', '.join(wks)} · set {', '.join(sets)}", head)
            for svg in re.findall(r"<svg class=\"plot--.*?</title>", section(h, f'id="chart-{cat}"', "</figure>"), re.S):
                self.assertIn(f"set {', '.join(sets)}", html.unescape(svg))

    def test_run_status_plain_words(self):
        import render
        rs = section(page("/"), 'id="run-status"', "</section>")
        pub = sorted({r["set"] for v in BENCH["tables"].values() for r in v})
        p = text(section(rs, 'id="sets-published"', "</p>"))
        for s in pub:
            self.assertIn(s, p)
        skips = section(rs, 'id="skips"', "</table>")
        for k in BENCH["skips"]:
            self.assertIn(f'title="{k["status"]}">{html.escape(render.status_words(k["status"]))}<', skips)
            self.assertNotIn(f'>{k["status"]}<', skips)
        self.assertEqual(render.status_words("new_code_here"), "New code here")

    def test_freshness_counts(self):
        import render
        self.assertEqual(render.count_pct({"v": 0.9375}, 16), "15/16 (94%)")
        self.assertEqual(render.count_pct({"v": 0.3}, 16), "30%")
        self.assertEqual(render.count_pct(None, 16), "n/a")

    def test_narrow_labels_one_placement(self):
        h = page("/")
        for svg in re.findall(r'<svg class="plot--narrow".*?</svg>', h, re.S):
            self.assertEqual(set(re.findall(r'class="pt-val"[^>]*text-anchor="(\w+)"', svg)), {"middle"})

    def test_urls_preserved(self):
        old = (R / "tests/urls_baseline.txt").read_text().split()
        missing = [u for u in old if not (D / u.lstrip("/")).is_file()]
        self.assertEqual(missing, [])

    def test_internal_links_resolve(self):
        seen, missing = 0, []
        for p in D.rglob("*"):
            if p.suffix not in (".html", ".css", ".js", ".txt", ".xml"):
                continue
            s = p.read_text()
            refs = re.findall(r'(?:href|src)="(/[^"]*)"', s) + re.findall(r'url\("(/[^"]+)"\)', s)
            refs += re.findall(r"j\('(/[^'$`]+)'\)", s)
            refs += [u[len("https://agentwebindex.com"):] or "/" for u in re.findall(r"https://agentwebindex\.com(/[^\s<\"]*)", s)]
            for u in refs:
                if u.startswith("//"):
                    continue
                path = u.split("#", 1)[0].split("?", 1)[0]
                f = D / path.lstrip("/")
                if path.endswith("/"):
                    f = f / "index.html"
                seen += 1
                if not f.is_file():
                    missing.append((str(p.relative_to(D)), u))
        self.assertGreater(seen, 50)
        self.assertEqual(missing, [])

    def test_data_json_parses(self):
        for p in (D / "data").rglob("*.json"):
            json.loads(p.read_text())
        for p in (D / "data").rglob("*.jsonl"):
            for line in p.read_text().splitlines():
                if line.strip():
                    json.loads(line)
        idx = json.loads((D / "data/prices/index.json").read_text())
        self.assertTrue(idx["providers"])
        for x in idx["providers"]:
            self.assertTrue((D / f"data/prices/{x['provider']}.json").is_file(), x["provider"])

    def test_beehiiv_embed(self):
        cfg = json.loads((R / "site.config.json").read_text())
        fid = cfg["beehiiv_embed_url"].rstrip("/").rsplit("/", 1)[1]
        for p in ("/newsletter/", "/"):
            s = page(p)
            self.assertIn(f'data-beehiiv-form="{fid}"', s)
            self.assertIn('src="https://subscribe-forms.beehiiv.com/v3/loader.js"', s)
            self.assertIn(f'<noscript><a href="{cfg["beehiiv_embed_url"]}">', s)

    def test_downloads(self):
        rows = list(csv.reader((D / "data/benchmarks/latest.csv").read_text().splitlines()))
        self.assertEqual(len(rows) - 1, sum(len(v) for v in BENCH["tables"].values()))
        self.assertEqual(json.loads((D / "data/benchmarks/latest.json").read_text()), BENCH)
        self.assertGreater(len(json.loads((D / "data/prices.json").read_text())["rows"]), 0)
        self.assertTrue((D / "data/prices.csv").read_text().startswith("provider,name,pricing_url"))
        d = page("/data/")
        for u in ("/data/benchmarks/latest.csv", "/data/benchmarks/latest.json"):
            self.assertIn(f'href="{u}"', d)

    def test_page_content_kept(self):
        for name in ("methodology", "disclosures", "sponsors", "data", "newsletter", "prices"):
            src = (R / "src" / f"{name}.html").read_text()
            src = re.sub(r"<!--.*?-->|\{\{\w+\}\}", "", src)
            for chunk in re.findall(r"<(?:p|li|h1|h2)>(.*?)</(?:p|li|h1|h2)>", src, re.S):
                self.assertIn(text(chunk), text(page(f"/{name}/")), (name, chunk[:60]))

    def test_prices_page(self):
        p = page("/prices/")
        t = section(p, 'id="curated-prices"', "</table>")
        self.assertIn("Normalized $/1k requests", t)
        rows = re.findall(r"<tr><td>.*?</tr>", t)
        for r in rows:
            cell = text(re.search(r'data-label="Normalized \$/1k requests"[^>]*>(.*?)</td>', r).group(1))
            self.assertRegex(cell, r"^(\$[\d.]+( \(overage rate[^)]*\))?|n/a \(.+\))$")
        pricing = json.loads("\n".join(l for l in (R / "data/_upstream/pricing.yaml").read_text().splitlines() if not l.lstrip().startswith("#")))
        inc = pricing["providers"]["firecrawl"]["search"]["tiers"]["entry"]["included_units"]
        self.assertIn(f"overage rate after the plan's {inc:,} included units", text([r for r in rows if "Firecrawl" in r][0]))
        self.assertIn("$8", text([r for r in rows if "Tavily" in r][0]))
        self.assertNotRegex(p, r"NOT CAPTURED|Not captured|Not Captured")
        self.assertGreater(t.count("<tr>"), 10)
        self.assertIn("Checked", t)

    def test_nav_and_landmarks(self):
        for p in ("/", "/prices/", "/methodology/", "/disclosures/", "/newsletter/", "/data/", "/sponsors/"):
            s = page(p)
            self.assertEqual(s.count("<h1"), 1, p)
            self.assertIn(f'<a href="{p}" aria-current="page">', s)
            self.assertIn('<a class="skip-link" href="#main">', s)
            self.assertIn('<main id="main"', s)
            for img in re.findall(r"<img\b[^>]*>", s):
                self.assertIn("alt=", img, p)
            for svg in re.findall(r"<svg\b[^>]*>", s):
                self.assertTrue('aria-hidden="true"' in svg or "aria-labelledby=" in svg, (p, svg[:80]))


def tokens(block):
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", block))


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


TEXT_PAIRS = [("ink", "bg"), ("ink", "surface"), ("ink", "surface-2"), ("ink-2", "bg"), ("ink-2", "surface"), ("ink-2", "surface-2"),
              ("ink-3", "bg"), ("ink-3", "surface"), ("accent-ink", "bg"), ("accent-ink", "surface-2"), ("on-accent", "accent"), ("bg", "ink")]
MARK_PAIRS = [("focus", "bg"), ("field-border", "bg"), ("cat-search", "bg"), ("cat-scrape", "bg"), ("cat-browser", "bg")]


def themes():
    css = (D / "style.css").read_text()
    light = tokens(css[css.index(":root {"):css.index("}", css.index(":root {"))])
    dark = dict(light, **tokens(css[css.index(':root[data-theme="dark"]'):]))
    return {"light": light, "dark": dark}


class Wilson(unittest.TestCase):
    def test_reference_values(self):
        import render
        for k, n, lo, hi in ((12, 16, 50.5, 89.8), (8, 16, 28.0, 72.0), (2, 16, 3.5, 36.0), (11, 16, 44.4, 85.8)):
            w = render.wilson(k, n)
            self.assertEqual((round(w[0] * 100, 1), round(w[1] * 100, 1)), (lo, hi))

    def test_finding_phrases(self):
        import render
        row = lambda name, k, n: {"_name": name, "set": "news_x", "passed": {"v": k}, "attempted": {"v": n}, "success_rate": {"v": k / n}}
        self.assertEqual(render.finding("search", [row("A", 40, 40), row("B", 0, 40)]), "A answered 40 of 40 news queries, B 0; at n=40 every gap is clear")
        self.assertEqual(render.finding("search", [row("A", 5, 10), row("B", 4, 10)]), "A answered 5 of 10 news queries, B 4; at n=10 no gap is clear")
        self.assertEqual(render.finding("search", [row("A", 9, 10), row("B", 1, 20)]), "A answered 9 of 10 news queries, B 1 of 20; at n=10–20 every gap is clear")


class TwoWeeks(unittest.TestCase):
    FIX = {"has_results": True, "tables": {"search": [
        {"provider": p, "set": f"news_2026-{w}", "run_date": d, "passed": {"v": k}, "attempted": {"v": n}, "success_rate": {"v": k / n},
         "p50_latency_ms": {"v": 100}, "flags": []}
        # file order deliberately puts the newer week first for exa
        for p, w, d, k, n in (("exa", 43, "2026-10-20", 37, 40), ("exa", 42, "2026-10-15", 15, 16),
                              ("tavily", 42, "2026-10-15", 12, 16), ("tavily", 43, "2026-10-20", 29, 40))]}, "scrape": [], "browser": []}

    def test_one_row_per_provider_single_week_title(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            b = Path(td) / "b.json"
            b.write_text(json.dumps(self.FIX))
            pv = Path(td) / "p.json"
            pv.write_text(json.dumps({"providers": [{"id": "exa", "name": "Exa", "categories": ["search"]},
                                                    {"id": "tavily", "name": "Tavily", "categories": ["search"]}]}))
            h = render.leaderboard(b, pv)
        ids = re.findall(r'<tr data-id="([^"]+)"', section(h, 'id="table-search"', "</table>"))
        self.assertEqual(ids, ["exa", "tavily"])
        head = html.unescape(section(h, 'id="chart-search"', "</figcaption>"))
        self.assertIn("Week 2026-43 · set news_2026-43", head)
        self.assertNotIn("2026-42", head)
        self.assertIn("Exa answered 37 of 40 news queries, Tavily 29;", head)
        self.assertNotIn("of 16", h)


class Colours(unittest.TestCase):
    def test_category_colours_only_via_data_cat(self):
        css = (D / "style.css").read_text()
        uses = [l.strip() for l in css.splitlines() if "var(--cat-" in l]
        for l in uses:
            self.assertRegex(l, r'^(--cat: var\(--cat-search\);|\[data-cat="(search|scrape|browser)"\]\s*\{ --cat: var\(--cat-\2\); \}|\.diagram \.d-search)', l)


class Contrast(unittest.TestCase):
    def test_text_pairs_aa(self):
        for name, tk in themes().items():
            for f, b in TEXT_PAIRS:
                self.assertGreaterEqual(ratio(tk[f], tk[b]), 4.5, (name, f, b))

    def test_marks_3_to_1(self):
        for name, tk in themes().items():
            for f, b in MARK_PAIRS:
                self.assertGreaterEqual(ratio(tk[f], tk[b]), 3.0, (name, f, b))


if __name__ == "__main__":
    for name, tk in themes().items():
        for f, b in TEXT_PAIRS + MARK_PAIRS:
            print(name, f, b, round(ratio(tk[f], tk[b]), 2))
