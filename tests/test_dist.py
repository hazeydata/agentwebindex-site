"""Tests for the built site (dist/) and the helpers. Run by tests/run_dist.py (exact test count enforced there).

AC numbers refer to specs/awi-page-redo-001.md (rev 2 + R3-R6). SHIP gates live in tests/test_ship.py;
the headless-Chrome checks (AC16/AC17/AC14 served bytes, readability) live in tests/browser_check.py.
"""
import csv, hashlib, html, json, os, re, shutil, subprocess, sys, tempfile, unittest
from html.parser import HTMLParser
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / "dist"
sys.path.insert(0, str(R))
import copydoc, pins as pinmod, prices as P, render  # noqa: E402

PINS = pinmod.load(R)
LATEST = json.loads((R / "data/benchmarks/latest.json").read_text())
PRICING = P.load_pricing(R / "data/_upstream/pricing.yaml")
PROVIDERS = json.loads((R / "data/_upstream/providers.json").read_text())["providers"]
NAMES = {p["id"]: p["name"] for p in PROVIDERS}
CFG = json.loads((R / "site.config.json").read_text())
EXCL_PUBLIC = ("provider", "reason", "quote", "terms_url", "checked_at")
PAGES = {"/": "index.html", "/prices/": "prices", "/methodology/": "methodology", "/data/": "data", "/disclosures/": "disclosures",
         "/sponsors/": "sponsors", "/newsletter/": "newsletter", "/tell-us/": "tell-us"}
TEXT_SUFFIXES = (".html", ".css", ".js", ".json", ".csv", ".txt", ".xml", ".svg", ".jsonl", "")


def page(path):
    return (D / path.strip("/") / "index.html" if path != "/" else D / "index.html").read_text()


def dist_text_files(skip_data=False):
    out = [p for p in D.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES]
    return [p for p in out if not (skip_data and p.relative_to(D).parts[0] == "data")]


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


class TextOf(HTMLParser):
    """Visible text of an HTML fragment: inline tags join without spaces, block tags separate; script/style/noscript skipped."""
    INLINE = {"a", "b", "strong", "em", "i", "span", "code", "time", "small", "mark", "abbr"}
    SKIP = {"script", "style", "noscript", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag not in self.INLINE:
            self.out.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip -= 1
        elif tag not in self.INLINE:
            self.out.append(" ")

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)


def text_of(s):
    t = TextOf()
    t.feed(s)
    return norm("".join(t.out))


class Dom(HTMLParser):
    """Collects the elements the tests care about: nav.top links, footer links, imgs, h1, details, sections."""

    def __init__(self, s):
        super().__init__(convert_charrefs=True)
        self.stack, self.nav_links, self.footer_links, self.header_links, self.imgs, self.h1, self.details = [], [], [], [], [], [], []
        self.cur_h1 = None
        self.all_links = []
        self.in_nav_other = []
        self.feed(s)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.stack.append((tag, a))
        names = [t for t, _ in self.stack]
        if tag == "a" and a.get("href") is not None:
            self.all_links.append((a["href"], names[:]))
            if any(t == "nav" and "top" in (x.get("class") or "").split() for t, x in self.stack):
                self.nav_links.append(a["href"])
            if "footer" in names:
                self.footer_links.append(a["href"])
            if "nav" in names:
                self.in_nav_other.append(a["href"])
        if tag == "img":
            self.imgs.append(a)
        if tag == "h1":
            self.cur_h1 = []
        if tag == "details":
            self.details.append({"open": "open" in a, "summary": "", "id": a.get("id")})

    def handle_endtag(self, tag):
        if tag == "h1" and self.cur_h1 is not None:
            self.h1.append(norm("".join(self.cur_h1)))
            self.cur_h1 = None
        while self.stack:
            t, _ = self.stack.pop()
            if t == tag:
                break

    def handle_data(self, d):
        if self.cur_h1 is not None:
            self.cur_h1.append(d)
        if self.stack and self.stack[-1][0] == "summary" and self.details:
            self.details[-1]["summary"] += d


def copy_repo(dst):
    shutil.copytree(R, dst, ignore=shutil.ignore_patterns(".git", "dist", "__pycache__", "node_modules"))


def build_in(w):
    return subprocess.run([sys.executable, "build.py"], cwd=w, capture_output=True, text=True)


# ------------------------------------------------------------------ copy.md extraction (independent of copydoc.py)

def strip_md(s):
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    return norm(s.replace("**", ""))


def copy_strings():
    """{page: [verbatim strings]} from content/copy.md, excluding the file header, chart Shows/Data/File lines (and Chart 3,
    Subtitle), Notes, Open questions, field IDs and labels, and heading suffixes."""
    secs, cur = [], None
    for line in (R / "content/copy.md").read_text().splitlines():
        if line.startswith("## "):
            cur = [re.sub(r"\s*\((?:fact-cleared|collapsed)[^)]*\)", "", line[3:]).strip(), []]
            secs.append(cur)
        elif cur is not None and line.strip():
            cur[1].append(line.strip())
    out = {}

    def add(pg, s):
        out.setdefault(pg, []).append(strip_md(s))

    def body(line):   # drop a leading "**Label:**" / "**ID (Human label):**" field label
        return re.sub(r"^\*\*[A-Za-z0-9][^*]*?:\*\*\s*", "", line)

    for title, lines in secs:
        if title in ("Page title and nav", "Notes: layout review (screens/index.html and layout-spec.md @ 0dbe561)", "Open questions"):
            continue
        if title == "Home: hero":
            for l in lines:
                add("/", body(l))
        elif title in ("Home: findings",):
            for l in lines:
                add("/", l[2:] if l.startswith("- ") else l)
        elif title == "Home: section intros":
            for l in lines:
                add("/", l[4:] if l.startswith("### ") else l)
        elif title.startswith("Earlier runs"):
            for l in lines:
                add("/", body(l) if l.startswith("**Summary line") else (l[2:] if l.startswith("- ") else l))
        elif title == "Chart briefs":
            chart = None
            for l in lines:
                if l.startswith("### "):
                    chart = l[4:]
                elif chart and chart.startswith(("Chart 1", "Chart 2")) and re.match(r"\*\*(Title|Caption):\*\*", l):
                    add("/", body(l))
        elif title == "Methodology and limits":
            for l in lines:
                add("/methodology/", l[2:] if l.startswith("- ") else l)
        elif title == "About and tell us":
            for l in lines:
                add("/tell-us/", l)
        elif title == "Data page":
            for l in lines:
                add("/data/", l)
        elif title == "Footer":
            for l in lines:
                for pg in PAGES:
                    add(pg, l)
        elif title.startswith("Layout slot: newsletter"):
            for l in lines:
                add("/", l); add("/newsletter/", l)
        elif title.startswith("Layout slot: prices lede") or title == "Prices page: also priced":
            for l in lines:
                add("/prices/", l)
        elif title.startswith("Layout slot: methodology lede"):
            for l in lines:
                add("/methodology/", l)
        elif title in ("Disclosures page", "Sponsors page"):
            pg = "/disclosures/" if title.startswith("Disclosures") else "/sponsors/"
            for l in lines:
                add(pg, body(l))
    return out


def expected_numbers():
    """The nine headline values, derived here from latest.json through the helpers (no copy.md involved)."""
    t = {r["provider"]: r for r in LATEST["tables"]["search"] if r["run_date"] == LATEST["run_date"]}
    b = [r for r in LATEST["tables"]["scrape"] if r["run_date"] == LATEST["run_date"]][0]
    f = lambda r: P.fmt_pct(r["success_rate"]["v"])
    u = lambda x: P.fmt_usd(x["v"])
    return {"tavily pass": f(t["tavily"]), "exa pass": f(t["exa"]), "browserless pass": f(b),
            "tavily cost": u(t["tavily"]["entry_tier_cost_per_successful_1k"]), "exa cost": u(t["exa"]["entry_tier_cost_per_successful_1k"]),
            "browserless cost": u(b["entry_tier_cost_per_successful_1k"]),
            "exa list": u(t["exa"]["entry_tier_cost_per_1k"]), "tavily list": u(t["tavily"]["entry_tier_cost_per_1k"]),
            "browserless list": u(b["entry_tier_cost_per_1k"])}


class Helpers(unittest.TestCase):
    def test_price_rows_exactly_four_priced_providers(self):  # AC4
        rows = P.price_rows(PRICING, LATEST, PROVIDERS)
        self.assertEqual(sorted(r["provider"] for r in rows), ["apify", "browserless", "exa", "tavily"])
        self.assertEqual(len(rows), 4)
        self.assertEqual({r["provider"]: r["category"] for r in rows}, {"exa": "search", "tavily": "search", "apify": "search", "browserless": "scrape"})

    def test_checked_at_is_min_of_inputs_and_inputs_are_only_used_fields(self):  # AC4
        mixed = {"providers": {"tavily": {"search": {"checked_at": "2026-10-24", "credits_per_call_verified": {"search": 1, "checked_at": "2026-10-15"},
                                                        "tiers": {"entry": {"usd_per_credit": 0.008, "checked_at": "2026-10-19"}}}}}}   # data may agree on one date; the rule must not depend on it
        self.assertEqual(P.priced_tier_checked_at(mixed, "tavily", "search"), "2026-10-15")
        for r in P.price_rows(PRICING, LATEST, PROVIDERS):
            self.assertEqual(r["checked_at"], min(r["inputs"].values()), r["provider"])
            c = PRICING["providers"][r["provider"]][r["category"]]
            want = {f"{r['category']}.checked_at"}
            if isinstance((c.get("credits_per_call_verified") or {}).get(r["category"]), (int, float)):
                want.add("credits_per_call_verified.checked_at")
            if (c.get("tiers") or {}).get("entry", {}).get("checked_at"):
                want.add(f"{r['category']}.tiers.entry.checked_at")
            self.assertEqual(set(r["inputs"]), want, r["provider"])
            self.assertEqual(r["tier_key"], "entry")

    def test_tavily_named_case_dates(self):  # AC4
        mixed = {"providers": {"tavily": {"search": {"checked_at": "2026-10-24", "credits_per_call_verified": {"search": 1, "checked_at": "2026-10-15"},
                                                        "tiers": {"entry": {"usd_per_credit": 0.008, "checked_at": "2026-10-19"}}}}}}   # data may agree on one date; the rule must not depend on it
        self.assertEqual(P.priced_tier_checked_at(mixed, "tavily", "search"), "2026-10-15")
        r = {x["provider"]: x for x in P.price_rows(PRICING, LATEST, PROVIDERS)}["tavily"]
        self.assertIn("credits_per_call_verified.checked_at", r["inputs"])
        self.assertIn("search.checked_at", r["inputs"])
        c = PRICING["providers"]["tavily"]["search"]
        self.assertEqual(r["inputs"]["credits_per_call_verified.checked_at"], c["credits_per_call_verified"]["checked_at"])
        self.assertEqual(r["inputs"]["search.checked_at"], c["checked_at"])
        self.assertEqual(P.priced_tier_checked_at(PRICING, "tavily", "search"), min(c["checked_at"], c["credits_per_call_verified"]["checked_at"]))
        # at the Phase 0 pin every Tavily input is dated 2026-10-24 (pricing.yaml), so the min of the inputs is that date
        self.assertEqual(set(r["inputs"].values()), {PINS["phase0_date"]})
        self.assertEqual(r["checked_at"], min(r["inputs"].values()))
        self.assertEqual(r["checked_at"], "2026-10-24")

    def test_priced_inputs_ignore_unrelated_fields_and_raise_when_empty(self):  # AC4
        pr = {"providers": {"x": {"search": {"checked_at": "2026-01-02", "verified_date": "2020-01-01",
                                              "credits_per_call_verified": {"search": "NOT CAPTURED", "checked_at": "2019-01-01"},
                                              "tiers": {"entry": {"checked_at": "2026-01-01"}, "volume": {"checked_at": "2000-01-01"}}}}}}
        self.assertEqual(P.priced_inputs(pr, "x", "search"), {"search.tiers.entry.checked_at": "2026-01-01", "search.checked_at": "2026-01-02"})
        self.assertEqual(P.priced_tier_checked_at(pr, "x", "search"), "2026-01-01")
        with self.assertRaises(ValueError):
            P.priced_tier_checked_at({"providers": {}}, "x", "search")

    def test_rounding_cases_half_up(self):  # AC6
        cases = [(P.fmt_pct(0.665), "67%"), (P.fmt_pct(0.685), "69%"), (P.fmt_pct(0.69), "69%"), (P.fmt_pct(0.6583333333333333), "66%"),
                 (P.fmt_usd(11.595), "$11.60"), (P.fmt_usd(11.5942), "$11.59"), (P.fmt_usd(0.00125), "$0.0013"), (P.fmt_usd(0.0075), "$0.0075"),
                 (P.fmt_usd(7.000000000000001), "$7.00"), (P.fmt_usd(float("inf")), "∞"), (P.fmt_usd(None), "n/a"),
                 (P.fmt_ms(1261.5), "1,262 ms"), (P.fmt_ms(1262.4), "1,262 ms"), (P.fmt_ms(999.5), "1,000 ms")]
        for got, want in cases:
            self.assertEqual(got, want)

    def test_untested_providers_are_the_other_eleven(self):  # AC21
        u = P.untested_providers(PRICING, LATEST, PROVIDERS)
        self.assertEqual(len(u), 11)
        self.assertEqual(u, sorted(u))
        priced = {r["name"] for r in P.price_rows(PRICING, LATEST, PROVIDERS)}
        self.assertFalse(priced & set(u))
        self.assertEqual(len(priced | set(u)), 15)

    def test_placeholder_constant(self):  # AC27 (constant kept)
        self.assertEqual(P.PLACEHOLDER, "[[LINDSAY-PLACEHOLDER]]")

    def test_sentinel_fetched_at_never_reaches_prices_page(self):  # AC5
        sentinel = "1999-01-01"
        with tempfile.TemporaryDirectory(prefix="awi-sentinel.") as t:
            w = Path(t) / "w"
            copy_repo(w)
            for f in ("data/prices/tavily.json",):
                p = w / f
                d = json.loads(p.read_text())
                self.assertIn("fetched_at", d)
                d["fetched_at"] = sentinel
                p.write_text(json.dumps(d))
            h = w / "data/prices/history/tavily.jsonl"
            lines = [json.loads(l) for l in h.read_text().splitlines() if l.strip()]
            lines[-1]["fetched_at"] = sentinel
            h.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
            b = build_in(w)
            self.assertEqual(b.returncode, 0, b.stderr[-400:])
            self.assertNotIn(sentinel, (w / "dist/prices/index.html").read_text())
            self.assertNotIn(sentinel, (w / "dist/index.html").read_text())
            self.assertIn(sentinel, (w / "dist/data/prices/tavily.json").read_text())   # the agent export still carries it


class Pins(unittest.TestCase):
    def test_data_pin_matches_upstream_bytes(self):  # AC7
        man = json.loads((R / "tests/data_pin_manifest.json").read_text())
        self.assertEqual(man["sha"], PINS["data"])
        self.assertEqual(man["repo"], "https://github.com/hazeydata/agentwebindex.git")
        self.assertEqual(pinmod.source_sha(R), PINS["data"])
        upstream = {p.relative_to(R).as_posix() for p in (R / "data/_upstream").iterdir() if p.name != "SOURCE"} | {"data/benchmarks/latest.json"}
        self.assertEqual(set(man["files"]), upstream, "every file under data/_upstream/ (except SOURCE) and latest.json must be in the manifest")
        for rel, sha in man["files"].items():
            self.assertEqual(hashlib.sha256((R / rel).read_bytes()).hexdigest(), sha, f"{rel} differs from the pinned upstream bytes")
        self.assertNotRegex(json.dumps(man), "/work" + "space|/home/")

    def test_pin_check_function_cases(self):  # R8
        saved = os.environ.pop("AWI_DATA_REPO", None)   # the data-repo cross-check has its own test; these cases use fake shas
        self.addCleanup(lambda: saved is not None and os.environ.__setitem__("AWI_DATA_REPO", saved))
        base = dict(PINS)
        self.assertEqual(pinmod.check(R, pins=base), [])
        self.assertEqual(pinmod.STALE_DATA_SHA, "6b8bd87d778b3fe0fe049f9274796ab498928cc5")
        stale = dict(base, data=pinmod.STALE_DATA_SHA)
        errs = pinmod.check(R, pins=stale, vendored_sha=pinmod.STALE_DATA_SHA)
        self.assertTrue(any("pre-Phase-0" in e for e in errs), errs)
        moved = dict(base, data="a" * 40)   # re-pinned: the vendored SOURCE no longer matches the pin
        errs = pinmod.check(R, pins=moved)
        self.assertFalse(any("pre-Phase-0" in e for e in errs))
        self.assertTrue(any("SOURCE" in e for e in errs))
        self.assertEqual(pinmod.check(R, pins=moved, vendored_sha="a" * 40), [])
        self.assertTrue(any("before the Phase 0 date" in e for e in pinmod.check(R, pins=dict(base, phase0_date="2026-10-25"))))

    def test_tavily_dates_walk_every_depth_and_only_tavily(self):  # R8
        dates = dict(pinmod.tavily_dates(R / "data/_upstream/pricing.yaml"))
        self.assertIn("providers.tavily.search.checked_at", dates)
        self.assertIn("providers.tavily.search.credits_per_call_verified.checked_at", dates)
        self.assertGreaterEqual(len(dates), 3)
        self.assertTrue(all(k.startswith("providers.tavily.") for k in dates))
        self.assertTrue(all(v >= PINS["phase0_date"] for v in dates.values()), dates)

    def test_build_fails_if_pin_is_pre_phase0_sha(self):  # R8 (a)
        stale = pinmod.STALE_DATA_SHA
        with tempfile.TemporaryDirectory(prefix="awi-pin.") as t:
            w = Path(t) / "w"
            copy_repo(w)
            p = json.loads((w / "pins.json").read_text())
            p["data"] = stale
            (w / "pins.json").write_text(json.dumps(p))
            data_repo = os.environ.get("AWI_DATA_REPO")
            if data_repo:   # real 6b8bd87 tree, re-vendored in the temp copy only
                s = subprocess.run(["bash", "sync_data.sh", stale, data_repo], cwd=w, capture_output=True, text=True)
                self.assertEqual(s.returncode, 0, s.stderr[-400:])
            else:   # no local clone: keep SOURCE consistent with the pin so only the stale-sha rule can fire
                (w / "data/_upstream/SOURCE").write_text(f"repo https://github.com/hazeydata/agentwebindex.git\nsha {stale}\n")
            self.assertEqual(pinmod.source_sha(w), stale)
            b = build_in(w)
            self.assertNotEqual(b.returncode, 0)
            self.assertIn("pre-Phase-0", b.stderr)
            self.assertNotIn("SOURCE", b.stderr)
            self.assertFalse((w / "dist/index.html").exists())

    def test_build_fails_if_tavily_input_dated_before_phase0(self):  # R8 (b)
        with tempfile.TemporaryDirectory(prefix="awi-pin.") as t:
            w = Path(t) / "w"
            copy_repo(w)
            y = w / "data/_upstream/pricing.yaml"
            old = '"verified_date": "2026-10-24"'
            raw = y.read_text()
            self.assertIn(old, raw)
            i = raw.index(old)   # first 2026-10-24 verified_date: confirm it sits under tavily before editing
            y.write_text(raw[:i] + '"verified_date": "2026-10-23"' + raw[i + len(old):])
            self.assertEqual([k for k, v in pinmod.tavily_dates(y) if v == "2026-10-23"], [k for k, v in pinmod.tavily_dates(y) if v == "2026-10-23" and k.startswith("providers.tavily.")])
            self.assertTrue(any(v == "2026-10-23" for _, v in pinmod.tavily_dates(y)))   # the edited field is under providers.tavily
            self.assertNotEqual(PINS["data"], pinmod.STALE_DATA_SHA)
            self.assertEqual(pinmod.source_sha(w), PINS["data"])
            b = build_in(w)
            self.assertNotEqual(b.returncode, 0)
            self.assertIn("2026-10-23", b.stderr)
            self.assertIn("before the Phase 0 date 2026-10-24", b.stderr)
            self.assertNotIn("pre-Phase-0", b.stderr)
            self.assertFalse((w / "dist/index.html").exists())

    def test_vendored_pricing_cross_checked_against_data_repo(self):  # R8 optional: needs AWI_DATA_REPO
        repo = os.environ.get("AWI_DATA_REPO")
        self.assertEqual(pinmod.check(R), [])
        with tempfile.TemporaryDirectory(prefix="awi-pin.") as t:
            w = Path(t) / "w"
            copy_repo(w)
            p = w / "data/_upstream/pricing.yaml"
            p.write_text(p.read_text() + "# drift\n")
            errs = pinmod.check(w)
            if not repo:   # without the data repo the cross-check is off (documented in the README)
                self.assertFalse(any("differs from bench/pricing.yaml" in e for e in errs), errs)
                return
            self.assertTrue(any("differs from bench/pricing.yaml" in e for e in errs), errs)
            self.assertNotEqual(build_in(w).returncode, 0)

    def test_proof_map_names_only_existing_tests(self):  # S15: PR body map is generated from test names
        sys.path.insert(0, str(R / "tools"))
        import proof_map
        text, missing = proof_map.render()
        self.assertEqual(missing, [])
        self.assertIn(f"tests/test_dist.py:{proof_map.defs('tests/test_dist.py')['test_nav_top_exactly_four_links']}", text)

    def test_real_repo_at_303efdf4_builds_and_check_is_ok(self):  # R8 pass case
        self.assertEqual(PINS["data"], "303efdf4fa955e81697a92906d32d6ac125e3882")
        self.assertEqual(pinmod.source_sha(R), PINS["data"])
        self.assertEqual(pinmod.check(R), [])
        with tempfile.TemporaryDirectory(prefix="awi-pin.") as t:
            w = Path(t) / "w"
            copy_repo(w)
            b = build_in(w)
            self.assertEqual(b.returncode, 0, b.stderr[-400:])
            self.assertTrue((w / "dist/index.html").exists())

    def test_build_fails_if_vendored_data_sha_differs_from_pin(self):  # R4
        with tempfile.TemporaryDirectory(prefix="awi-pin.") as t:
            w = Path(t) / "w"
            copy_repo(w)
            p = json.loads((w / "pins.json").read_text())
            p["data"] = "b" * 40
            (w / "pins.json").write_text(json.dumps(p))
            b = build_in(w)
            self.assertNotEqual(b.returncode, 0)
            self.assertIn("SOURCE", b.stderr)

    def test_chart_alt_vendored_section_only(self):  # content/chart-alt.md is the pinned "## Alt text" section of QUERIES.md, not the whole file
        raw = (R / "content/chart-alt.md").read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), PINS["chart_alt_sha256"])
        head, _, rest = raw.decode().partition("\n")
        self.assertTrue(head.startswith("<!--") and head.endswith("-->") and "agentwebindex-meta 2c28c0a cycles/2026-10-24-page-redo/her/QUERIES.md" in head)
        self.assertTrue(rest.startswith("## Alt text"))
        self.assertEqual([l for l in rest.splitlines() if l.startswith("#")], [rest.splitlines()[0]])   # a single section
        self.assertRegex(PINS["queries_sha256"], r"^[0-9a-f]{64}$")   # sha256 of the full original QUERIES.md at 2c28c0a
        self.assertEqual(set(copydoc.alt_texts()), {"pass-rate", "cost-per-success"})
        self.assertFalse((R / "content/QUERIES.md").exists())

    def test_charts_byte_identical_to_pin(self):  # AC14 (R8): the 8 chart SVGs only; fonts are not byte-checked
        want = PINS["charts_sha256"]
        self.assertEqual(len(want), 8)
        self.assertTrue(all(n.endswith(".svg") and "/" not in n for n in want), sorted(want))
        for name, meta in want.items():
            for base in (R / "src/charts", D / "assets/charts"):
                self.assertEqual(hashlib.sha256((base / name).read_bytes()).hexdigest(), meta["sha256"], f"{base.name}/{name}")
        self.assertEqual(hashlib.sha256((R / "content/copy.md").read_bytes()).hexdigest(), PINS["copy_sha256"])

    def test_no_font_over_100kb_and_charts_dir_is_exactly_the_8_svgs(self):  # R8
        names = set(PINS["charts_sha256"])
        for base in (R / "src/charts", D / "assets/charts"):
            self.assertEqual({p.name for p in base.iterdir()}, names, base)
            self.assertTrue(all(p.is_file() for p in base.iterdir()), base)
        g = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=R, capture_output=True, text=True)
        if g.returncode == 0:
            files = [R / f for f in g.stdout.splitlines() if (R / f).is_file()]
        else:   # copy of the repo without .git (canary / temp copies)
            files = [p for p in R.rglob("*") if p.is_file() and not {".git", "dist", "node_modules", "__pycache__"} & set(p.relative_to(R).parts)]
        files += [p for p in D.rglob("*") if p.is_file()]
        magic = (b"wOFF", b"wOF2", b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")
        font_ext = (".ttf", ".otf", ".woff", ".woff2", ".eot", ".ttc")
        fonts = [p for p in files if p.suffix.lower() in font_ext or p.read_bytes()[:4] in magic]
        self.assertGreaterEqual(len(fonts), 7)   # 3 IBM Plex Mono + 4 Inter / Space Grotesk, in the repo and in dist
        for p in fonts:
            self.assertLessEqual(p.stat().st_size, 100 * 1024, f"font over 100 KB: {p}")
            self.assertFalse(p.suffix.lower() in (".ttf", ".otf", ".eot", ".ttc"), f"unsubsetted font format: {p}")

class Shell(unittest.TestCase):
    def test_nav_top_exactly_four_links(self):  # AC8
        for p in PAGES:
            dom = Dom(page(p))
            self.assertEqual(dom.nav_links, ["/", "/prices/", "/methodology/", "/data/"], p)

    def test_secondary_links_in_footer_never_nav(self):  # AC9
        for p in PAGES:
            dom = Dom(page(p))
            for u in ("/disclosures/", "/sponsors/", "/newsletter/", "/tell-us/"):
                self.assertIn(u, dom.footer_links, (p, u))
                self.assertNotIn(u, dom.in_nav_other, (p, u))
            for u in ("/data/benchmarks/latest.json", "/data/prices/index.json", "/llms.txt"):
                self.assertIn(u, dom.footer_links, (p, u))

    def test_results_title_h1_and_no_leaderboard_anywhere(self):  # AC10
        s = page("/")
        self.assertEqual(Dom(s).h1, ["Results"])
        self.assertEqual(re.search(r"<title>(.*?)</title>", s).group(1), "Results · AgentWebIndex")
        hits = [str(p.relative_to(D)) for p in D.rglob("*") if "leaderboard" in p.name.lower()]
        for p in D.rglob("*"):
            if p.is_file():
                hits += [str(p.relative_to(D))] if re.search(rb"(?i)leaderboard", p.read_bytes()) else []
        self.assertEqual(hits, [])
        for f in ("render.py", "build.py", "prices.py", "copydoc.py", "pins.py", "src/style.css", "src/app.js"):
            self.assertNotRegex((R / f).read_text(), r"(?i)leaderboard", f)   # no function, class or id of that name either

    def test_every_contact_address_is_fred(self):  # AC11
        found = set()
        for p in dist_text_files():
            found |= set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", p.read_text(errors="ignore")))
        found -= {"fred@hazeydata.ai"}
        self.assertEqual(found, set())
        self.assertNotIn("sponsors@agentwebindex.com", "".join(p.read_text(errors="ignore") for p in dist_text_files()))
        self.assertIn("mailto:fred@hazeydata.ai", page("/tell-us/"))

    def test_one_h1_skip_link_main_and_img_alts(self):
        for p in PAGES:
            s = page(p)
            self.assertEqual(s.count("<h1"), 1, p)
            self.assertIn(f'<a href="{p}" aria-current="page">', s) if p in ("/", "/prices/", "/methodology/", "/data/") else None
            self.assertIn('<a class="skip-link" href="#main">', s)
            self.assertIn('<main id="main">', s)
            for img in Dom(s).imgs:
                self.assertTrue(img.get("alt"), p)
            for lab in re.findall(r'role="img"([^>]*)>', s):   # inlined charts (R9.4): role=img needs a non-empty name
                self.assertRegex(lab, r'aria-label="[^"]+"', p)

    def test_canonical_robots_sitemap_goatcounter(self):  # AC24, AC26
        base = json.loads((R / "tests/agent_surface_baseline.json").read_text())
        site = CFG["site_url"].rstrip("/")
        robots, sitemap = (D / "robots.txt").read_text(), (D / "sitemap.xml").read_text()
        for p in PAGES:
            s = page(p)
            self.assertEqual(s.count(f'<link rel="canonical" href="{site}{p}">'), 1, p)
            self.assertEqual(s.count(base["goatcounter_snippet"]), 1, p)
            self.assertLess(s.index(base["goatcounter_snippet"]), s.index("</head>"), p)
            self.assertIn(f"<loc>{site}{p}</loc>", sitemap, p)
            if p != "/":
                self.assertIn(f"Allow: {p}\n", robots, p)
        self.assertTrue(robots.startswith("User-agent: *\nAllow: /\n"))
        self.assertTrue(robots.endswith(f"Sitemap: {site}/sitemap.xml\n"))

    def test_signup_form_markup(self):  # AWI-SIGNUP-FORM-001 AC 4, 14, 16 (static part): first-party form on / (hero + end) and /newsletter/
        for p, n in (("/", 2), ("/newsletter/", 1)):
            s = page(p)
            forms = re.findall(r'<form class="awi-signup"[^>]*>.*?</form>', s, re.S)
            self.assertEqual(len(forms), n, p)
            for f in forms:
                self.assertIn('method="post" action="/api/subscribe"', f)
                pid = re.search(r'<input id="([a-z]+)-email" name="email" type="email"', f).group(1)
                self.assertIn(f'<label class="signup-label" for="{pid}-email">Email address</label>', f)   # visible label
                self.assertIn('<button class="btn" type="submit">Subscribe</button>', f)
                self.assertIn(f'<p id="{pid}-status" class="signup-status" role="status" aria-live="polite">', f)
                self.assertIn(f'aria-describedby="{pid}-status"', f)
                hp = re.search(r'<div class="signup-hp" aria-hidden="true">(.*?)</div>', f).group(1)
                self.assertIn('name="website" type="text" tabindex="-1" autocomplete="off"', hp)
                self.assertRegex(f, r'<input type="hidden" name="page" value="/(newsletter/)?">')
        top = page("/")
        self.assertLess(top.index('class="awi-signup"'), top.index('id="run"'))   # hero form precedes the results (AC 14; geometry in browser_check)
        css = (D / "style.css").read_text()
        self.assertRegex(css, r"\.signup-hp \{ position: absolute; left: -10000px;")
        self.assertIn('<script src="/signup.js" defer></script>', top)

    def test_signup_no_beehiiv_iframe_or_third_party_script(self):  # AC 13 (R3: form and /api/subscribe only; GoatCounter left as is)
        for p in ("/", "/newsletter/"):
            s = page(p)
            # the email only ever travels in a same-origin POST body, never in a URL that analytics could see (R3)
            for f in re.findall(r'<form\b[^>]*class="awi-signup"[^>]*>', s):
                self.assertIn('method="post"', f, p); self.assertIn('action="/api/subscribe"', f, p)
            self.assertNotIn("beehiiv.com", s, p)
            self.assertNotRegex(s, r"(?i)<iframe", p)
            ext = re.findall(r'<script\b[^>]*\bsrc="((?:https?:)?//[^"]+)"', s)
            # goatcounter is the site's pre-existing analytics (out of scope for this spec); nothing else, and no Turnstile (R2)
            self.assertEqual(ext, ["https://gc.zgo.at/count.js"], p)
        for f in D.rglob("*"):
            if f.suffix in (".html", ".js", ".css"):
                self.assertNotIn("beehiiv", f.read_text().lower(), f)
                self.assertNotIn("challenges.cloudflare.com", f.read_text(), f)
        js = (D / "signup.js").read_text()
        self.assertNotRegex(js, r"https?://")   # same-origin fetch only

    def test_signup_thanks_pages_match_config(self):  # AC 7 / AC 8 / AC 15 no-JS landing pages; copy == site.config.json == signup/config.js (node test)
        sc = CFG["signup"]
        self.assertTrue(sc["double_opt_in"])
        for st, msg in sc["messages"].items():
            s = (D / "newsletter/thanks" / st / "index.html").read_text()
            self.assertIn(f'data-status="{st}">{html.escape(msg)}</p>', s)
            self.assertIn('<meta name="robots" content="noindex">', s)
        self.assertEqual(sc["messages"]["pending_confirmation"], "Check your inbox to confirm your subscription.")
        self.assertEqual(sc["messages"]["queued"], "Thanks, you're on the list. We'll send a confirmation email soon.")
        self.assertEqual(sc["messages"]["rate_limited"], "Too many tries, please wait a few minutes.")
        self.assertNotIn("/newsletter/thanks/", (D / "sitemap.xml").read_text())
        js = (D / "signup.js").read_text()
        self.assertIn(json.dumps(sc["messages"], ensure_ascii=False), js)

    def test_signup_no_secret_names_or_values_in_dist(self):  # AC 12 (repo-wide value scan is tests/signup/secret_scan.sh)
        for f in dist_text_files():
            t = f.read_text(errors="ignore")
            for name in ("BEEHIIV_API_KEY", "IP_SALT", "EXPORT_TOKEN", "Authorization", "api.beehiiv.com"):
                self.assertNotIn(name, t, f)

    def test_no_external_fonts_or_cdn(self):
        allowed = {"https://gc.zgo.at/count.js"}
        for p in D.rglob("*"):
            if p.suffix not in (".html", ".css", ".js"):
                continue
            s = p.read_text()
            self.assertNotRegex(s, r"@import", p)
            self.assertNotRegex(s, r"url\(\s*['\"]?(https?:)?//", p)
            self.assertNotRegex(s, r"(?i)fonts\.(googleapis|gstatic)|cdnjs|jsdelivr|unpkg|typekit|fontawesome", p)
            for tag, attrs in re.findall(r"<(link|script|img|source)\b([^>]*)>", s):
                if tag == "link" and 'rel="canonical"' in attrs:
                    continue
                for url in re.findall(r"(?<![\w-])(?:href|src)=\"([^\"]*)\"", attrs):
                    if url.startswith(("http:", "https:", "//")):
                        self.assertIn(url, allowed, (p, tag, url))

    def test_fonts_self_hosted(self):
        css = (D / "style.css").read_text()
        urls = re.findall(r"url\(\"(/assets/[^\"]+)\"\)", css)
        self.assertGreaterEqual(len(urls), 6)
        for u in urls:
            self.assertTrue((D / u.lstrip("/")).exists(), u)
        for n, who in (("Inter", "Inter Project Authors"), ("SpaceGrotesk", "Space Grotesk Project Authors"), ("IBMPlexMono", "2017 IBM Corp")):
            txt = (D / f"assets/fonts/OFL-{n}.txt").read_text()
            self.assertIn("SIL Open Font License, Version 1.1", txt)
            self.assertIn(who, txt.splitlines()[0])
        self.assertFalse((D / "assets/fonts/OFL.txt").exists())
        self.assertNotIn("IBMPlexSans", "".join(p.read_text() for p in (D / "assets/fonts").glob("*.txt")))
        self.assertNotIn("truetype", css)
        self.assertEqual(sorted(re.findall(r"/assets/fonts/([\w.-]+)\"", css)), sorted(p.name for p in (D / "assets/fonts").glob("*.woff2")))   # no unused font files

    def test_theme_tokens_and_toggle(self):  # brand: two-variable swap; dark default, light by media query and data-theme
        css = (D / "style.css").read_text()
        for tok in ("--cyan: #5FC4D6", "--acc: #616512", "--acc-tint: #8B901A", "--font-head:", "--font-body:", "--font-mono:"):
            self.assertIn(tok, css)
        self.assertIn("Space Grotesk", css)
        self.assertIn("prefers-color-scheme: light", css)
        self.assertIn(":root[data-theme=light]", css)
        self.assertLess(css.index("color-scheme: dark"), css.index("prefers-color-scheme: light"))   # dark is the default
        self.assertIn("data-theme-toggle", page("/"))
        self.assertIn("setAttribute('data-theme'", (D / "app.js").read_text())

    def test_internal_links_resolve(self):
        seen, missing = 0, []
        for p in D.rglob("*"):
            if p.suffix not in (".html", ".css", ".js", ".txt", ".xml"):
                continue
            s = p.read_text()
            refs = re.findall(r'(?:href|src)="(/[^"]*)"', s) + re.findall(r'url\("(/[^"]+)"\)', s)
            refs += [u or "/" for u in re.findall(r"https://agentwebindex\.com(/[^\s<\"]*)", s)]
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


class Results(unittest.TestCase):
    def setUp(self):
        self.s = page("/")

    def test_section_order(self):  # AC12
        ids = re.findall(r'<(?:section|footer)\b[^>]*?(?:id="([a-z-]+)"|class="(site-footer)")', self.s)
        order = [a or b for a, b in ids]
        self.assertEqual([x for x in order if x != ""], ["run", "pass-rate", "cost", "not-tested", "details", "sponsor-newsletter", "site-footer"])
        self.assertTrue(self.s.index('class="hero"') < self.s.index('id="run"'))
        self.assertIn('<aside id="sponsor-banner" class="sponsor"><b>Sponsored</b>', self.s)
        run = self.s[self.s.index('id="run"'):self.s.index('id="pass-rate"')]
        rows = re.findall(r'<div class="row"[^>]*data-provider="([a-z]+)"', run)
        self.assertEqual(rows, ["exa", "tavily", "browserless"])
        subs = re.findall(r'<div class="who"><b>([^<]+)</b>\s*<span>([^<]*)</span>', run)
        self.assertEqual([(a, norm(b)) for a, b in subs], [("Exa", "search · 100 evergreen questions"), ("Tavily", "search · 100 evergreen questions"),
                         ("Browserless", "scrape · 150 URLs; 30 skipped by design under its terms")])

    def test_values_computed_from_latest_json_and_linked(self):  # AC13
        ex, text = expected_numbers(), text_of(self.s)
        for k, val in ex.items():
            self.assertIn(val, text, k)
        run = self.s[self.s.index('id="run"'):self.s.index('id="pass-rate"')]
        pin = PINS["data"]
        for pid in ("exa", "tavily", "browserless"):
            row = re.search(rf'<div class="row"[^>]*data-provider="{pid}">.*?</div></div>', run, re.S).group(0)
            logs = re.findall(r'href="(https://github\.com/hazeydata/agentwebindex/blob/[^"]+)"', row)
            self.assertEqual(len(logs), 1, pid)
            self.assertTrue(logs[0].startswith(f"https://github.com/hazeydata/agentwebindex/blob/{pin}/bench/runs/{LATEST['run_date']}/{pid}/"), logs[0])
            src = PRICING["providers"][pid]["scrape" if pid == "browserless" else "search"]["source_url"]
            self.assertIn(f'href="{src}"', row)

    def test_no_hardcoded_values_in_code_or_templates(self):  # AC13
        literals = ["69%", "40%", "66%", "$11.59", "$17.50", "$1.90", "$7.00", "$8.00", "$1.25"] + list(expected_numbers().values())
        files = [R / "render.py", R / "build.py", R / "prices.py", R / "copydoc.py"] + sorted((R / "src").glob("*.html"))
        for f in files:
            src = f.read_text()
            for lit in literals:
                self.assertFalse(lit in src, f"{lit} hard-coded in {f.name}")

    def test_charts_alt_title_caption(self):  # AC15
        alts, doc = copydoc.alt_texts(), copydoc.load()
        queries = (R / "content/chart-alt.md").read_text()
        for name, sub, sid in (("pass-rate", "Chart 1", "pass-rate"), ("cost-per-success", "Chart 2", "cost")):
            alt = alts[name]
            self.assertIn(f'"{alt}"', queries)
            sec = self.s[self.s.index(f'id="{sid}"'):]
            sec = sec[:sec.index("</section>")]
            labels = re.findall(r'<div class="ch [^"]*" role="img" aria-label="([^"]*)"', sec)   # R9.4
            self.assertEqual(len(labels), 4)
            for lab in labels:
                self.assertEqual(html.unescape(lab), alt)
            fig = sec[sec.index("<figure"):]
            self.assertEqual(text_of(re.search(r"<h3>(.*?)</h3>", fig).group(1)), doc.field("Chart briefs", "Title", sub=sub))
            self.assertNotIn("<figcaption", fig)   # footnotes moved into Notes (addendum 9, CEO R-5)
            notes = self.s[self.s.index('<details id="notes">'):]
            notes = notes[:notes.index("</details>")]
            foot = re.search(rf'<p class="footnote" data-chart="{sid}">(.*?)</p>', notes).group(1)
            if sub == "Chart 2":
                self.assertEqual(text_of(foot), doc.field("Chart briefs", "Caption", sub=sub))
            self.assertIn(f'<h3>', fig)

    def test_chart_variants_and_css(self):  # AC16 / R9.5 (static half; real rendering in browser_check.py)
        for name in ("pass-rate", "cost-per-success"):
            wraps = re.findall(r'<div class="(ch ch-(\d+) ch-(\w+))" role="img"[^>]*data-file="([^"]+)"', self.s)
            mine = [w for w in wraps if w[3].startswith(f"awi-{name}-")]
            self.assertEqual(sorted(w[3] for w in mine), sorted(f"awi-{name}-{w}-{c}.svg" for w in (720, 350) for c in ("light", "dark")))
            for cls, width, scheme, f in mine:
                self.assertEqual(f, f"awi-{name}-{width}-{scheme}.svg")
        self.assertNotIn("<img", self.s[self.s.index('id="chart-pass-rate"'):self.s.index('id="chart-cost"') + 20000].split("</section>")[0])
        css = (D / "style.css").read_text()
        self.assertIn(".ch { display: none;", css)
        self.assertIn("@media (min-width: 768px) { .ch-720.ch-dark { display: block; } }", css)
        self.assertIn("@media (max-width: 767.98px) { .ch-350.ch-dark { display: block; } }", css)
        self.assertIn("@media (prefers-color-scheme: light)", css)
        self.assertIn("max-width: 100%", css[css.index(".ch {"):css.index(".ch {") + 80])

    def test_inlined_svg_is_file_minus_prolog_with_only_ids_renamed(self):  # R9.1
        n = 0
        for f, meta in PINS["charts_sha256"].items():
            raw = (R / "src/charts" / f).read_text()
            self.assertEqual(hashlib.sha256((R / "src/charts" / f).read_bytes()).hexdigest(), meta["sha256"])
            name, width, scheme = f[4:-4].rsplit("-", 2)
            pre = render.id_prefix(name, int(width), scheme)
            m = re.search(r'<div class="ch ch-%s ch-%s" role="img" aria-label="[^"]*" data-file="%s" data-prefix="%s">(<svg.*?</svg>\s*)</div>' % (width, scheme, re.escape(f), re.escape(pre)), self.s, re.S)
            self.assertIsNotNone(m, f)
            body = raw[raw.index("<svg"):]
            self.assertTrue(raw[:raw.index("<svg")].startswith("<?xml"))
            self.assertNotIn("<svg", raw[:raw.index("<svg")])
            self.assertEqual(render.unprefix_ids(m.group(1), pre), body, f)   # only ids/refs differ ...
            self.assertEqual(re.sub(r'(\bid="|href="#|url\(#)[^"\)]*', "", m.group(1)), re.sub(r'(\bid="|href="#|url\(#)[^"\)]*', "", body))   # ... nothing else
            n += 1
        self.assertEqual(n, 8)

    def test_no_duplicate_ids_on_any_page_and_build_fails_on_one(self):  # R9.3
        for p in PAGES:
            ids = re.findall(r'\bid="([^"]*)"', page(p))
            self.assertEqual(len(ids), len(set(ids)), (p, sorted({i for i in ids if ids.count(i) > 1})))
        self.assertGreaterEqual(page("/").count("<svg"), 8)
        with tempfile.TemporaryDirectory(prefix="awi-dup.") as t:
            w = Path(t) / "w"
            copy_repo(w)
            r = w / "render.py"
            r.write_text(r.read_text().replace('return f"{name}-{width}-{scheme}--"', 'return f"{name}--"'))   # rename that collides
            b = build_in(w)
            self.assertNotEqual(b.returncode, 0)
            self.assertIn("duplicate id attributes", b.stderr)

    def test_fonts_cover_chart_text_and_page(self):  # R9.2 (static half; browser_check proves the rendered font)
        css = (D / "style.css").read_text()
        faces = set(re.findall(r'@font-face \{ font-family: "([^"]+)"; font-style: normal; font-weight: (\d+);[^}]*url\("/assets/fonts/[^"]+\.woff2"\)', css))
        svgs = "".join((R / "src/charts" / f).read_text() for f in PINS["charts_sha256"])
        for fam in set(re.findall(r"font-family: '([^']+)'", svgs)):
            self.assertTrue(any(f == fam for f, _ in faces), fam)
        self.assertIn(("Inter", "400"), faces)
        self.assertFalse(list((D / "assets").rglob("*.ttf")))

    def test_charts_stacked_in_one_column_markup(self):  # AC17 (static half)
        self.assertLess(self.s.index('id="chart-pass-rate"'), self.s.index('id="chart-cost"'))
        css = (D / "style.css").read_text()
        self.assertNotRegex(css[css.index(".chart {"):css.index("/* details */")], r"float|grid-template-columns|display: flex")

    def test_earlier_runs_details(self):  # AC18
        dom = Dom(self.s)
        er = [d for d in dom.details if d["id"] == "earlier-runs"][0]
        self.assertFalse(er["open"])
        self.assertTrue(all(not d["open"] for d in dom.details))
        doc = copydoc.load()
        self.assertEqual(norm(er["summary"]), doc.field("Earlier runs", "Summary line"))
        body = self.s[self.s.index('id="earlier-runs"'):]
        body = text_of(body[:body.index("</details>")])
        for kind, t in doc.blocks("Earlier runs"):
            if kind in ("li", "h3") or t.startswith("**Week"):
                self.assertIn(strip_md(t), body, t)
        self.assertEqual(len(re.findall(r"<li>", self.s[self.s.index('id="earlier-runs"'):self.s.index('id="every-row"')])), 8)

    def test_index_forbidden_words(self):  # AC19
        for w in ("p50", "latency", "ms</", "freshness"):
            self.assertNotIn(w, self.s.lower(), w)

    def test_every_row_table_has_all_rows_without_latency(self):
        t = self.s[self.s.index('id="every-row"'):]
        t = t[:t.index("</details>")]
        want = sum(len([r for r in rows if not r.get("mock")]) for rows in LATEST["tables"].values())
        self.assertEqual(t.count('<th scope="row"'), want)
        self.assertNotRegex(t, r"(?i)p50|latency")


class OtherPages(unittest.TestCase):
    def test_prices_rows_dates_and_links(self):  # AC20
        s = page("/prices/")
        rows = re.findall(r'<div class="row price-row".*?</div></div>', s, re.S)
        want = P.price_rows(PRICING, LATEST, PROVIDERS)
        self.assertEqual(len(rows), len(want))
        for r, w in zip(rows, want):
            t = text_of(r)
            self.assertIn(f"{w['name']} {w['category']}", t)
            self.assertIn(w["price_display"], t)
            self.assertIn(f"Last checked {w['checked_at']} · pricing page", t)
            self.assertIn(f'<a href="{html.escape(w["source_url"])}">pricing page</a>', r)
            self.assertEqual(w["checked_at"], P.priced_tier_checked_at(PRICING, w["provider"], w["category"]))
        self.assertEqual(len(re.findall(r"\bimg\b|<svg|<canvas", s[s.index("<main"):s.index("<footer")])), 0)   # no chart

    def test_no_cheapest_tier_100k_claim_anywhere(self):  # R7: nothing in dist/ (any file type) makes the 'cheapest tier covering 100k/month' claim
        pat = re.compile(r"cheapest\s+tier|100\s*k\s*(?:/|per|a)\s*mo(?:nth)?|100,?000\s*(?:/|per|a)\s*mo(?:nth)?|100\s*k\s*(?:requests|calls|credits)?\s*(?:/|per|a)\s*mo(?:nth)?", re.I)
        files = [p for p in D.rglob("*") if p.is_file()]
        self.assertGreater(len(files), 50)
        hits = [(str(p.relative_to(D)), m.group(0)) for p in files for m in pat.finditer(p.read_bytes().decode("utf-8", "ignore"))]
        self.assertEqual(hits, [])
        for ok in ("Cheapest tier covering 100K/month", "cheapest  tier", "100,000/month", "100k per month", "100000 / month"):
            self.assertTrue(pat.search(ok), ok)   # the pattern itself catches the variants

    def test_prices_shows_only_tavily_entry_tier(self):  # R6/R7: Bootstrap/Startup/Growth and the volume (Project) tier are not on the page
        tiers = PRICING["providers"]["tavily"]["search"]["tiers"]
        row = text_of(re.search(r'<div class="row price-row"[^>]*data-provider="tavily">.*?</div></div>', page("/prices/"), re.S).group(0))
        self.assertIn(tiers["entry"]["name"], row)
        self.assertIn(f"${tiers['entry']['usd_per_credit']} per credit", row)
        for word in ("Bootstrap", "Startup", "Growth", "Project", "volume", "slider", str(tiers["volume"]["usd_per_credit"]), "$30"):
            self.assertNotIn(word, row, word)
            self.assertNotIn(word, text_of(page("/prices/")), word)

    def test_no_daily_anywhere(self):  # AC20
        self.assertEqual([str(p.relative_to(D)) for p in dist_text_files() if re.search(r"(?i)daily", p.read_text(errors="ignore"))], [])
        for f in ("render.py", "build.py", "src/style.css", "src/app.js"):
            self.assertNotRegex((R / f).read_text(), r"(?i)daily")

    def test_also_priced_line_names_all_eleven_none_has_a_row(self):  # AC21
        s = page("/prices/")
        line = text_of(re.search(r'<p class="lcopy" id="also-priced">(.*?)</p>', s, re.S).group(1))
        self.assertEqual(s.count('id="also-priced"'), 1)
        self.assertTrue(line.startswith("Priced, not yet tested: "))
        listed = {n.strip() for n in line.split(": ", 1)[1].rstrip(".").split(", ")}
        un = P.untested_providers(PRICING, LATEST, PROVIDERS)
        self.assertEqual(listed, set(un))
        rows = text_of("".join(re.findall(r'<div class="row price-row".*?</div></div>', s, re.S)))
        for n in un:
            self.assertNotIn(n, rows)

    def test_methodology_latency_uses_fmt_ms(self):  # AC22
        s = text_of(page("/methodology/"))
        rows = {(r["provider"], c): r for c, rr in LATEST["tables"].items() for r in rr if r["run_date"] == LATEST["run_date"]}
        for (pid, cat) in (("exa", "search"), ("tavily", "search"), ("browserless", "scrape")):
            self.assertRegex(s, re.escape(f"{NAMES[pid]} {cat} {P.fmt_ms(rows[(pid, cat)]['p50_latency_ms']['v'])}") + r"[,.]")
        self.assertIn("Freshness: not measured yet", s)   # the single copy line; no chart, table or id
        self.assertIn("Latency (p50)", s)

    def test_pro_waitlist_and_freshness_blocks_gone(self):  # AC23
        for p in dist_text_files(skip_data=True):
            self.assertNotRegex(p.read_text(errors="ignore"), r"(?i)AWI Pro|\$29|29/mo|29/month|waitlist", p)
        for p in PAGES:
            self.assertNotIn('id="freshness"', page(p))
        self.assertNotRegex((R / "render.py").read_text(), r"(?i)def freshness|id=\"freshness\"")

    def test_tell_us_page(self):  # AC24
        s = page("/tell-us/")
        self.assertIn('href="https://github.com/hazeydata/agentwebindex-site/issues"', s)
        self.assertIn('href="mailto:fred@hazeydata.ai"', s)
        self.assertIn("<loc>https://agentwebindex.com/tell-us/</loc>", (D / "sitemap.xml").read_text())
        self.assertIn("Allow: /tell-us/", (D / "robots.txt").read_text())
        self.assertEqual(Dom(s).h1, ["Tell us"])

    def test_disclosures_and_sponsors_structure(self):  # AC25
        for p in PAGES:
            s = page(p)
            self.assertNotRegex(s, r"\b(?:DISC|SPON)-[A-Z]+\b")
            self.assertNotIn("**", s)
            self.assertNotRegex(text_of(s), r"\b(?:Kicker|Title|Intro):")
        d = text_of(page("/disclosures/"))
        for h in ("Current and past sponsors", "Affiliate relationships", "Free credits received", "Who pays for testing", "Corrections changelog"):
            self.assertIn(h, page("/disclosures/"))
        self.assertIn("No corrections yet. If we get one wrong, we'll fix it and log it here.", d)
        self.assertEqual(Dom(page("/sponsors/")).h1, ["Sponsors"])
        self.assertEqual(Dom(page("/disclosures/")).h1, ["Disclosures"])

    def test_data_page_file_list(self):
        s = page("/data/")
        for u in ("/data/benchmarks/latest.json", "/data/benchmarks/latest.csv", "/data/prices.json", "/data/prices.csv", "/data/prices/index.json", "/data/LICENSE"):
            self.assertIn(f'href="{u}"', s)
        self.assertIn("prices/&lt;provider&gt;.json", s)


class CopyAndGreps(unittest.TestCase):
    def test_copy_diff_verbatim(self):  # AC28
        strings = copy_strings()
        self.assertGreater(sum(len(v) for v in strings.values()), 60)
        self.assertEqual(set(strings), set(PAGES))
        for pg, items in strings.items():
            text = text_of(page(pg))
            for s in items:
                self.assertIn(norm(s), text, f"{pg}: {s[:70]}")
        # copy.md has not been edited: the verbatim target is the pinned file
        self.assertEqual(hashlib.sha256((R / "content/copy.md").read_bytes()).hexdigest(), PINS["copy_sha256"])
        alts = copydoc.alt_texts()
        for key in ("pass-rate", "cost-per-success"):
            self.assertIn(f"Alt text:** {alts[key]}", (R / "content/copy.md").read_text())   # chart-alt.md alt == copy.md alt

    def test_no_fact_cleared_text(self):  # AC29
        self.assertEqual([p.name for p in dist_text_files() if "(fact-cleared" in p.read_text(errors="ignore")], [])

    def test_no_draft_or_pending_case_sensitive(self):  # AC30
        hits = [(p.name, w) for p in dist_text_files() for w in ("DRAFT", "PENDING") if w in p.read_text(errors="ignore")]
        self.assertEqual(hits, [])

    def test_no_absolute_local_paths_in_repo_files(self):
        bad = []
        for f in R.rglob("*"):
            if f.is_file() and ".git" not in f.parts and "dist" not in f.parts and "__pycache__" not in f.parts and f.suffix in (".py", ".md", ".sh", ".js", ".json", ".html", ".css", ".txt", ".yaml") and f.parts[len(R.parts)] != "data":
                s = f.read_text(errors="ignore")
                if f.name == "SOURCE":
                    continue
                if re.search("/work" + "space|/home/" + "box", s):
                    bad.append(str(f.relative_to(R)))
        self.assertEqual(bad, [], "local absolute paths in committed files")

    def test_no_pack_sample_values(self):
        vals = json.loads((R / "tests/pack_sample_values.json").read_text())["values"]
        self.assertGreater(len(vals), 100)
        hits = [(v, str(p.relative_to(D))) for p in dist_text_files() for v in vals if v in p.read_text(errors="ignore")]
        self.assertEqual(hits, [])


class AgentSurfaces(unittest.TestCase):
    def test_agent_surfaces_unchanged(self):  # AC26
        base = json.loads((R / "tests/agent_surface_baseline.json").read_text())
        # invariants that hold for any data pin: the vendored data is served as-is
        skip = {"cache", "_upstream"}
        for p in (R / "data").rglob("*"):
            rel = p.relative_to(R / "data")
            if p.is_file() and not (set(rel.parts) & skip) and rel.as_posix() != "benchmarks/latest.json":
                self.assertEqual((D / "data" / rel).read_bytes(), p.read_bytes(), rel.as_posix())
        pub = json.loads((D / "data/benchmarks/latest.json").read_text())
        self.assertEqual({k: v for k, v in pub.items() if k != "exclusions"}, {k: v for k, v in LATEST.items() if k != "exclusions"})
        self.assertEqual(pub["exclusions"], [{k: x[k] for k in EXCL_PUBLIC if k in x} for x in LATEST["exclusions"]])
        llms = (D / "llms.txt").read_text()
        self.assertIn("Machine-readable data: /data/benchmarks/latest.json, /data/benchmarks/latest.csv (CC BY 4.0), /data/prices.json, /data/prices.csv, /data/prices/<provider>.json\n", llms)
        self.assertTrue(llms.endswith("/newsletter/, /tell-us/\n"))   # only addition: the new page
        rows = list(csv.reader((D / "data/benchmarks/latest.csv").read_text().splitlines()))
        self.assertEqual(len(rows) - 1, sum(len(v) for v in LATEST["tables"].values()))
        for p in (D / "data").rglob("*.json"):
            json.loads(p.read_text())
        # byte comparison with what main (60a8f4b) built from the same data, while the data pin is the one it was built from
        if base["data_sha"] == PINS["data"]:
            for rel, sha in base["files"].items():
                if rel == "data/index.html":   # the Data page itself (redesigned), not an agent surface
                    continue
                self.assertEqual(hashlib.sha256((D / rel).read_bytes()).hexdigest(), sha, rel)
            self.assertEqual(hashlib.sha256(llms.replace(", /tell-us/\n", "\n").encode()).hexdigest(), base["llms_txt_sha256"])

    def test_urls_preserved(self):
        old = (R / "tests/urls_baseline.txt").read_text().split()
        self.assertEqual([u for u in old if not (D / u.lstrip("/")).is_file()], [])

    def test_no_internal_exclusion_fields(self):
        """Only allowlisted exclusion fields reach any built output; internal notes (ToS "note") never do."""
        public = set(EXCL_PUBLIC)
        internal = [x[k] for x in LATEST["exclusions"] for k in x if k not in public and isinstance(x[k], str)]
        self.assertTrue(internal, "fixture lost its internal note; this test would be hollow")
        needles = ["needs legal review", "treated as forbidden"] + internal + [html.escape(t) for t in internal]
        files = [f for f in D.rglob("*") if f.is_file() and f.suffix in (".html", ".txt", ".json", ".csv", ".xml")]
        self.assertTrue(any(f.name == "llms.txt" for f in files))
        for f in files:
            t = f.read_text()
            for n in needles:
                self.assertNotIn(n, t, f"{n!r} leaked into {f.relative_to(D)}")

    def test_unknown_exclusion_key_never_published(self):
        """Allowlist, not denylist: an unknown internal key added to a tmp copy of the data never reaches dist."""
        marker = "AWI-INTERNAL-MARKER-q7zk"
        with tempfile.TemporaryDirectory(prefix="awi-excl.") as t:
            w = Path(t) / "w"
            copy_repo(w)
            p = w / "data/benchmarks/latest.json"
            d = json.loads(p.read_text())
            d["exclusions"][0]["internal_x"] = marker
            p.write_text(json.dumps(d, indent=1))
            b = build_in(w)
            self.assertEqual(b.returncode, 0, b.stderr[-300:])
            for f in (w / "dist").rglob("*"):
                if f.is_file() and f.suffix in (".html", ".txt", ".json", ".csv", ".xml"):
                    t2 = f.read_text()
                    self.assertNotIn(marker, t2, f"marker leaked into {f.name}")
                    self.assertNotIn("internal_x", t2, f"key leaked into {f.name}")



def repo_files():
    """Tracked files (git ls-files); in a canary's temp copy without .git, every file outside .git/ and dist/."""
    r = subprocess.run(["git", "ls-files", "-z"], cwd=R, capture_output=True)
    if r.returncode == 0 and r.stdout:
        out = [R / t for t in r.stdout.decode().split("\0") if t]
    else:
        out = [f for f in R.rglob("*") if f.is_file() and not {".git", "dist", "__pycache__"} & set(f.relative_to(R).parts)]
    assert len(out) > 20, len(out)
    return [f for f in out if f.is_file()]


class Polish(unittest.TestCase):
    """AWI-PAGE-POLISH-001 guards: numbers, ranking, row count, banned names, repeated claims, CTA label, chart titles, Methodology grid."""
    NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")
    CLAIM_TAVILY = "Tavily passed 69% of our 100 evergreen checks, Exa 40%; Browserless passed 66% of 120 scrape checks"

    def test_no_number_added_or_changed(self):
        base = json.loads((R / "tests/numbers_baseline.json").read_text())["pages"]
        for p in PAGES:
            now = set(self.NUM.findall(text_of(re.sub(r"<svg\b.*?</svg>", " ", page(p), flags=re.S))))   # chart SVGs: pinned by sha256
            self.assertEqual(sorted(now - set(base[p])), [], p)
        home = text_of(page("/"))
        for k, val in expected_numbers().items():
            self.assertIn(val, home, k)

    def test_results_rows_match_pinned_data_unranked(self):  # AC-2 (spec R-9) / AC-3
        """Rows = every non-mock, attempted row of latest.json's run_date at the data pin, grouped by table (search, scrape, browser) and by
        provider name inside a table; that list and its order must equal main's build at the same pin. No ranking words, badges or sorting by score."""
        base = json.loads((R / "tests/results_rows_baseline.json").read_text())
        self.assertEqual(base["data"], PINS["data"])
        L = json.loads((D / "data/benchmarks/latest.json").read_text())
        names = {p["id"]: p.get("name", p["id"]) for p in json.loads((R / "data/_upstream/providers.json").read_text()).get("providers", [])} \
            if (R / "data/_upstream/providers.json").exists() else {}
        want = []
        for cat in ("search", "scrape", "browser"):
            rows = [r for r in L.get("tables", {}).get(cat, []) if r.get("run_date") == L["run_date"] and not r.get("mock")
                    and (r.get("attempted") or {}).get("v") is not None]
            want += [r["provider"] for r in sorted(rows, key=lambda r: names.get(r["provider"], r["provider"]))]
        s = page("/")
        run = s[s.index('id="run"'):]
        run = run[:run.index("</section>")]
        got = re.findall(r'<div class="row" role="listitem" data-provider="([^"]+)"', run)
        self.assertEqual(got, want)
        self.assertEqual(got, base["rows"])
        self.assertEqual(len(got), 3)   # what 303efdf4 produces; update with the baseline if the pin moves
        # Full "Every row" table: every non-mock attempted row in latest.json (all run dates), in latest.json order per table.
        want_t = []
        for cat in ("search", "scrape", "browser"):
            for r in L.get("tables", {}).get(cat, []):
                if not r.get("mock") and (r.get("attempted") or {}).get("v") is not None:
                    want_t.append([names.get(r["provider"], r["provider"]), cat, r["set"], r.get("run_date") or ""])
        t = s[s.index('id="every-row"'):]
        t = t[:t.index("</table>")]
        got_t = [[text_of(x) for x in tr] for tr in re.findall(
            r'<tr><th scope="row"[^>]*>(.*?)</th><td[^>]*>(.*?)</td><td[^>]*>(.*?)</td><td[^>]*>(.*?)</td>', t)]
        self.assertEqual(got_t, want_t)
        self.assertEqual(got_t, base["table"])
        self.assertEqual((len(got_t), len({r[0] for r in got_t}), sum(r[0] == "Apify" for r in got_t)), (11, 4, 2))   # R-9 at 303efdf4
        for p in PAGES:
            self.assertNotRegex(text_of(page(p)), r"(?i)\b(rank(ed|ing)?|winner|best|top pick|#1|1st place|leader)\b", p)
        self.assertNotRegex(run, r'(?i)class="[^"]*\b(badge|rank|winner|highlight)\b')
        self.assertNotRegex((R / "render.py").read_text().split("def run_rows")[1].split("\ndef ")[0], r"success_rate|cost")

    def test_cyan_only_charts_and_focus(self):  # AC-15: --cyan appears only in focus styles (charts carry their own colours)
        css = re.sub(r"/\*.*?\*/", "", (D / "style.css").read_text(), flags=re.S)
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            if "var(--cyan)" in body:
                self.assertRegex(sel.strip(), r"^[^,]*:focus(-visible)?(\s*,\s*[^,]*:focus(-visible)?)*$", sel)

    def test_prose_max_width_68ch(self):  # AC-20: no body-text rule below or above 68ch (the 40ch headline and 45ch chart h3 are headings)
        css = re.sub(r"/\*.*?\*/", "", (D / "style.css").read_text(), flags=re.S)
        for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            for m in re.findall(r"max-width:\s*(\d+)ch", body):
                if m != "68":
                    self.assertRegex(sel.strip(), r"^\.(headline|chart h3)$", (sel, m))

    def test_no_raw_hex_in_button_rules(self):  # AC-15 (Tobias): buttons take colours from tokens only
        css = (D / "style.css").read_text()
        rules = re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S))
        btn = [(sel.strip(), body) for sel, body in rules if re.search(r"\.btn\b|\bbutton\b|cta-btn", sel)]
        self.assertTrue(btn)
        for sel, body in btn:
            self.assertNotRegex(body, r"#[0-9a-fA-F]{3,8}\b", sel)
            self.assertNotRegex(body, r"\b(rgb|hsl)a?\(", sel)
        self.assertRegex(re.search(r"\.btn \{([^}]*)\}", css).group(1), r"color: var\(--on-acc\)")
        roots = [body for sel, body in rules if "--on-cyan:" in body]
        self.assertGreaterEqual(len(roots), 2)   # dark :root plus the light blocks
        for body in roots:
            self.assertIn("--on-acc: #FFFFFF;", body)

    # Pattern is assembled from parts so this file itself never contains the names: AC-4 requires
    # the repo-wide case-insensitive grep for the two names (dotted or not) to return nothing, guard included.
    BANNED = re.compile(("keen" + "able|context" + r"\.?" + "dev").encode(), re.I)

    def test_banned_names_absent(self):  # AC-4: every tracked file in the repo AND every file in dist/
        files = repo_files() + [f for f in D.rglob("*") if f.is_file()]
        hits = sorted({str(f.relative_to(R)) for f in files if f.is_file() and self.BANNED.search(f.read_bytes())})
        self.assertEqual(hits, [])

    def test_each_claim_once(self):
        site = " ".join(text_of(page(p)) for p in PAGES)
        self.assertEqual(site.count(self.CLAIM_TAVILY + "."), 1)          # the #run line; the chart h3 carries it as a title (no period)
        self.assertEqual(text_of(page("/")).count(self.CLAIM_TAVILY), 2)   # sentence + chart h3, nothing else
        self.assertEqual(text_of(page("/disclosures/")).count("No provider pays us"), 1)
        for p in PAGES:
            if p != "/disclosures/":
                self.assertNotIn("No provider pays us", text_of(page(p)), p)

    def test_cta_label_same_on_every_page(self):
        want = copydoc.load().field("CTA boxes", "Button")
        self.assertEqual(want, "Get the results by email")
        for p in PAGES:
            s = page(p)
            labels = [text_of(x) for x in re.findall(r'<a class="btn cta-btn"[^>]*>(.*?)</a>', s)]
            self.assertTrue(set(labels) <= {want}, (p, labels))
            if p not in ("/newsletter/", "/"):   # Newsletter and Results carry the signup form itself (AWI-SIGNUP-FORM-001)
                self.assertGreaterEqual(len(labels), 1, p)
        retired = "Get price " + "updates by email"   # AC-29: retired label; assembled so the repo-wide grep stays clean
        self.assertEqual([str(f.relative_to(R)) for f in repo_files() if retired.lower().encode() in f.read_bytes().lower()], [])
        for f in D.rglob("*.html"):
            self.assertNotIn(retired.lower(), f.read_text().lower(), f)

    def test_chart_h3_equals_svg_aria_label(self):
        s = page("/")
        for sid in ("pass-rate", "cost"):
            fig = s[s.index(f'id="chart-{sid}"'):]
            fig = fig[:fig.index("</figure>")]
            h3 = text_of(re.search(r"<h3>(.*?)</h3>", fig).group(1))
            labels = [html.unescape(x) for x in re.findall(r'<svg role="img" aria-label="([^"]*)"', fig)]
            self.assertEqual(len(labels), 4, sid)
            for lab in labels:
                self.assertEqual(lab, h3, sid)
                self.assertFalse(lab.endswith("."), sid)

    def test_methodology_steps_grid(self):  # P0: a bare text node in .steps li became its own grid item in the 48px number column
        s = page("/methodology/")
        steps = re.findall(r'<li id="m-[^"]+">(.*?)</li>', s[s.index('<ol class="steps">'):s.index("</ol>")], re.S)
        self.assertEqual(len(steps), 8)
        for li in steps:
            self.assertRegex(li, r"^<h2>.*?</h2>\s*<p>.*</p>$")   # only element children: h2 then p
        css = (D / "style.css").read_text()
        self.assertIn("grid-template-columns: 56px minmax(0, 68ch)", css)
        self.assertIn(".steps li > * { grid-column: 2; }", css)

    def test_hero_button_target(self):  # AC-8, updated by AWI-SIGNUP-FORM-001: Results' hero holds the form itself; other hero buttons go to /newsletter/
        for p in PAGES:
            heroes = re.findall(r'<aside class="cta cta-hero"[^>]*>(.*?)</aside>', page(p), re.S)
            for h in heroes:
                for href in re.findall(r'<a class="btn cta-btn" href="([^"]+)"', h):
                    self.assertEqual(href, "/newsletter/", p)
        s = page("/")
        self.assertIn('<aside class="cta cta-hero cta-form" id="signup-top" aria-label="Newsletter">', s)
        self.assertIn('id="signup-end"', s)

    def test_hero_lead_ins_from_copy_cuts(self):  # AC-29 / AC-40 / AC-28
        self.assertRegex(PINS["copy_cuts_sha256"], r"^[0-9a-f]{64}$")   # copy-cuts.md is recorded, not vendored (see pins.json copy_cuts)
        want = {"/data/": "The raw results behind these pages. Grab them and check our work.",
                "/disclosures/": "Spot something off? Tell us.", "/prices/": "Want the next run?"}
        for p, lead in want.items():
            card = re.findall(r'<aside class="cta cta-hero[^"]*"[^>]*>(.*?)</aside>', page(p), re.S)
            self.assertEqual(len(card), 1, p)
            leads = re.findall(r'<p class="cta-lead">(.*?)</p>', card[0])
            self.assertEqual([text_of(x) for x in leads], [lead], p)
        self.assertIn("Download latest.json", page("/data/").split('class="cta cta-hero')[1].split("</aside>")[0])
        self.assertIn("Open an issue", page("/disclosures/").split('class="cta cta-hero')[1].split("</aside>")[0])
        doc = copydoc.load()
        for k in ("Results top", "Results end", "Prices top", "Prices end", "Methodology top", "Methodology end", "Data top", "Data end",
                  "Disclosures top", "Disclosures end", "Newsletter box", "Sponsors top", "Sponsors end", "Tell us end", "Button"):
            self.assertTrue(doc.field("CTA boxes", k), k)

    def test_chart_source_line_names_data_pin(self):  # AC-10: Her?'s source line must name the pinned data sha, not a stale one
        for f in sorted((R / "src/charts").glob("*.svg")):
            s = f.read_text()
            shas = re.findall(r"latest\.json @ ([0-9a-f]{7,40})", s)
            self.assertEqual(len(shas), 1, f.name)
            self.assertTrue(PINS["data"].startswith(shas[0]), (f.name, shas[0]))
            for other in re.findall(r"@ ([0-9a-f]{7,40})\b", s):
                self.assertTrue(PINS["data"].startswith(other), (f.name, other))

    def test_notes_hold_footnotes(self):  # AC-22: footnotes + Not tested in one Notes <details>, none outside
        s = page("/")
        notes = s[s.index('<details id="notes">'):]
        notes = notes[:notes.index("</details>")]
        self.assertIn("<summary>Notes</summary>", notes)
        self.assertEqual(len(re.findall(r'class="footnote"', notes)), 2)
        self.assertIn("<h3>Not tested</h3>", notes)
        self.assertEqual(s.count('class="footnote"'), 2)
        self.assertNotIn("<figcaption", s)
        outside = text_of(s.replace(notes, ""))   # AC-22: zero caption paragraphs outside Notes
        for foot in re.findall(r'<p class="footnote"[^>]*>(.*?)</p>', notes):
            self.assertNotIn(text_of(foot), outside)

if __name__ == "__main__":
    unittest.main()
