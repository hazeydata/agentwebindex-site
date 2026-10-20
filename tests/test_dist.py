import csv, html, json, re, unittest
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / "dist"
BENCH = json.loads((R / "data/benchmarks/latest.json").read_text())
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
        rows = rows_of(h, "search")
        tested = [r for r in rows if "is-untested" not in r]
        self.assertEqual([re.search(r'data-id="([^"]+)"', r).group(1) for r in tested], ["exa", "tavily", "apify"])
        for pid, pc, ans, p50, rd in [("exa", "75.0%", "12/16 answered", "2980 ms", "2026-10-15"),
                                      ("tavily", "50.0%", "8/16 answered", "1400 ms", "2026-10-15"),
                                      ("apify", "12.5%", "2/16 answered (12 of the fails timed out)", "60452 ms", "2026-10-19")]:
            r = text(next(x for x in tested if f'data-id="{pid}"' in x))
            for want in (pc, ans, p50, "n=16", "ToS-skipped 0", f"Run {rd}", "news_2026-42", "below minimum (n=16)"):
                self.assertIn(want, r, (pid, want))
        self.assertIn("$7.00", text(tested[0]))
        self.assertIn("$9.33", text(tested[0]))
        self.assertIn("$7.50", text(tested[1]))

    def test_real_browser_rows(self):
        r = text(rows_of(page("/"), "browser")[0])
        for want in ("Browserless", "68.8%", "11/16 answered", "2681 ms", "$1.25", "$1.82", "$0.70", "$1.02", "newsfetch_2026-42", "below minimum (n=16)"):
            self.assertIn(want, r)

    def test_values_match_json(self):
        h = page("/")
        for cat, rows in BENCH["tables"].items():
            got = {re.search(r'data-id="([^"]+)"', r).group(1): text(r) for r in rows_of(h, cat) if "is-untested" not in r}
            self.assertEqual(sorted(got), sorted(r["provider"] for r in rows if not r.get("mock")))
            for r in rows:
                self.assertIn(f'{r["success_rate"]["v"] * 100:.1f}%', got[r["provider"]])
                self.assertIn(r["answered_display"], got[r["provider"]])

    def test_untested_shows_not_tested_never_zero(self):
        h = page("/")
        provs = json.loads((R / "data/_upstream/providers.json").read_text())["providers"]
        excluded = {x["provider"] for x in BENCH["exclusions"]}
        for cat in ("search", "scrape", "browser"):
            have = {r["provider"] for r in BENCH["tables"][cat]}
            want = sorted(p["id"] for p in provs if cat in p["categories"] and p["id"] not in have | excluded)
            un = [r for r in rows_of(h, cat) if "is-untested" in r]
            self.assertEqual(sorted(re.search(r'data-id="([^"]+)"', r).group(1) for r in un), want, cat)
            for r in un:
                self.assertIn("Not tested", r)
                self.assertNotRegex(text(r), r"\d%|\$\d")
            chart = section(h, f'id="chart-{cat}"', "</figure>")
            self.assertNotIn(">0.0%<", chart)
            plot = section(chart, "chart-card__plot", "chart-card__key")
            self.assertEqual(plot.count(">not tested<"), 2 * len(want))
        self.assertIn("No data yet for scrape.", h)

    def test_excluded_provider_not_in_tables(self):
        h = page("/")
        for cat in ("search", "scrape", "browser"):
            self.assertNotIn('data-id="brave"', section(h, f'id="table-{cat}"', "</table>"))
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
        for want in ("exa", "93.8%", "tavily", "50.0%", "3e516ca796e2"):
            self.assertIn(want, t)

    def test_urls_preserved(self):
        old = (R / "tests/urls_baseline.txt").read_text().split()
        missing = [u for u in old if not (D / u.lstrip("/")).is_file()]
        self.assertEqual(missing, [])

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
        t = section(page("/prices/"), 'id="curated-prices"', "</table>")
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
