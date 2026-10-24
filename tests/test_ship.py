"""SHIP gates (not part of run_tests.sh; run: python3 -m tests.test_ship after ./run_tests.sh built dist/).

Any failure blocks SHIP. The Tavily data PR (hazeydata/agentwebindex#25, 8ab7ccc) is pinned in pins.json, so R3 (rendered
Tavily date == Phase 0 date) and R4 (data pin moved, phase0_landed) are ordinary gates now.
"""
import json, re, sys, unittest
from decimal import Decimal
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / "dist"
sys.path.insert(0, str(R))
import copydoc, pins as pinmod, prices as P  # noqa: E402

PINS = pinmod.load(R)
PRICING = P.load_pricing(R / "data/_upstream/pricing.yaml")
LATEST = json.loads((R / "data/benchmarks/latest.json").read_text())
PROVIDERS = json.loads((R / "data/_upstream/providers.json").read_text())["providers"]


def page(path):
    return (D / path.strip("/") / "index.html" if path != "/" else D / "index.html").read_text()


def dist_text():
    return {p: p.read_text(errors="ignore") for p in D.rglob("*") if p.is_file() and p.suffix in (".html", ".css", ".js", ".json", ".csv", ".txt", ".xml", ".svg", ".jsonl", "")}


class Ship(unittest.TestCase):
    def test_no_placeholders(self):  # AC27: no [[LINDSAY-PLACEHOLDER]] may reach dist/
        hits = [str(p.relative_to(D)) for p, s in dist_text().items() if P.PLACEHOLDER in s or "LINDSAY-PLACEHOLDER" in s]
        self.assertEqual(hits, [], "placeholder text in dist/")

    def test_tavily_date_is_phase0(self):  # R3: every Tavily input is dated 2026-10-24 at the data pin
        expected = PINS["phase0_date"]
        self.assertEqual(expected, "2026-10-24")
        computed = P.priced_tier_checked_at(PRICING, "tavily", "search")
        s = page("/prices/")
        row = re.search(r'data-provider="tavily">.*?</div></div>', s, re.S).group(0)
        rendered = re.search(r'<time datetime="([0-9-]+)"', row).group(1)
        self.assertEqual(rendered, computed, "rendered date must be wired to pricing.yaml")
        self.assertEqual(rendered, expected, f"Tavily last-checked is {rendered}, Phase 0 date is {expected}")

    def test_tavily_price_matches_pricing_yaml(self):  # AC2: rendered Tavily price == pricing.yaml on Results, Prices and the chart alt text
        c = PRICING["providers"]["tavily"]["search"]
        per_credit = Decimal(str(c["tiers"]["entry"]["usd_per_credit"]))
        cpc = Decimal(str(c["credits_per_call_verified"]["search"]))
        list1k = P.fmt_usd(per_credit * cpc * 1000)
        passed_cost = P.fmt_usd(per_credit * cpc * 1000 * 100 / next(r for r in LATEST["tables"]["search"] if r["provider"] == "tavily" and r["run_date"] == LATEST["run_date"])["passed"]["v"])
        prices = page("/prices/")
        self.assertIn(f"{list1k} per 1,000 calls (${per_credit:f} per credit)", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", prices)))
        home = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page("/")))
        self.assertIn("Tavily search · 100 evergreen questions", home)
        self.assertIn(f"{passed_cost} per 1,000 passed checks · list {list1k} per 1,000 calls", home)
        alt = copydoc.alt_texts()["cost-per-success"]
        self.assertIn(f"Tavily {passed_cost}", alt)
        self.assertIn(f"Tavily {list1k}", alt)
        self.assertEqual(page("/").count(f'alt="{alt}"'), 4)
        row = next(r for r in LATEST["tables"]["search"] if r["provider"] == "tavily" and r["run_date"] == LATEST["run_date"])
        self.assertEqual(Decimal(str(row["entry_tier_cost_per_1k"]["v"])), per_credit * cpc * 1000)   # latest.json cost input == pricing.yaml

    def test_data_pin_moved(self):  # R4/AC2
        self.assertTrue(PINS["phase0_landed"], "phase0_landed is false: the Tavily data PR has not landed")
        self.assertNotEqual(PINS["data"], PINS["data_stale_after_phase0"], "data pin is still the pre-Phase-0 sha")
        self.assertEqual(pinmod.check(R), [])


def main():
    res = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Ship))
    bad = {t.id().rsplit(".", 1)[1] for t, _ in res.failures + res.errors}
    if bad:
        print("SHIP GATE FAILURES: " + ", ".join(sorted(bad)))
    if not bad:
        print("SHIP gates: all passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
