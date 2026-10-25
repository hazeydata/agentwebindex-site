"""Price helpers for the Prices and Results pages (stdlib only).

Reads the vendored bench/pricing.yaml (JSON-compatible) and data/benchmarks/latest.json shapes.
Dates on the Prices page come ONLY from pricing.yaml (never data/prices/<pid>.json fetched_at):
the "last checked" date of an entry-tier price is the oldest date among the inputs cost.py/tables.py
actually used for that row (CEO ruling Q4).
"""
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

PLACEHOLDER = "[[LINDSAY-PLACEHOLDER]]"
CATS = ("search", "scrape", "browser")   # tie-break order when a provider has rows in several categories


def load_pricing(path):
    """pricing.yaml is JSON with # comment lines."""
    return json.loads("\n".join(l for l in Path(path).read_text().splitlines() if not l.lstrip().startswith("#")))


def _v(x):
    return x.get("v") if isinstance(x, dict) else x


def _rows(latest):
    for cat, rows in (latest.get("tables") or {}).items():
        for r in rows:
            if not r.get("mock") and _v(r.get("attempted")) is not None:
                yield cat, r


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def priced_category(pid, latest):
    """Category whose rows this provider has in latest.json: the one with the newest run, ties by CATS order
    (exa/tavily/apify: search; browserless: scrape). None if the provider has no rows."""
    best = None
    for cat, r in _rows(latest):
        if r["provider"] != pid:
            continue
        k = (str(r.get("run_date") or ""), -CATS.index(cat) if cat in CATS else -len(CATS))
        if best is None or k > best[0]:
            best = (k, cat)
    return best[1] if best else None


def priced_inputs(pricing, pid, category, tier_key="entry"):
    """Dates (field path -> YYYY-MM-DD) of only the inputs cost.cost_columns()/tables.py use for this row:
    tier date (if the tier has one), credit-count date (only when credits_per_call_verified[category] is numeric),
    and the category's checked_at (date of the tier's price fields). Never data/prices/<pid>.json fetched_at."""
    c = ((pricing.get("providers") or {}).get(pid) or {}).get(category)
    if not isinstance(c, dict):
        return {}
    out = {}
    tier = (c.get("tiers") or {}).get(tier_key) or {}
    if tier.get("checked_at"):
        out[f"{category}.tiers.{tier_key}.checked_at"] = tier["checked_at"]
    ver = c.get("credits_per_call_verified") or {}
    if _num(ver.get(category)) and ver.get("checked_at"):
        out["credits_per_call_verified.checked_at"] = ver["checked_at"]
    if c.get("checked_at"):
        out[f"{category}.checked_at"] = c["checked_at"]
    return out


def priced_tier_checked_at(pricing, pid, category, tier_key="entry"):
    """min(priced_inputs(...).values()). Raises ValueError if there are no inputs."""
    ins = priced_inputs(pricing, pid, category, tier_key)
    if not ins:
        raise ValueError(f"no dated inputs for {pid}/{category}/{tier_key}")
    return min(ins.values())


def _D(x):
    return Decimal(str(x))


def fmt_pct(x):
    """Whole percent, ROUND_HALF_UP on Decimal(str(x))."""
    return f"{(_D(x) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)}%"


def fmt_usd(x):
    """>= $0.01: 2 dp; < $0.01: 2 significant figures; ROUND_HALF_UP; inf -> ∞; None -> n/a."""
    if x is None:
        return "n/a"
    if x == float("inf"):
        return "∞"
    d = _D(x)
    if d == 0 or abs(d) >= Decimal("0.01"):
        return f"${d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"
    q = d.quantize(Decimal(1).scaleb(d.adjusted() - 1), rounding=ROUND_HALF_UP)
    if q >= Decimal("0.01"):   # 0.00996 rounds up across the boundary
        return f"${q.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
    return f"${q:f}"


def fmt_ms(x):
    """Whole ms, ROUND_HALF_UP, thousands separator."""
    return f"{int(_D(x).quantize(Decimal(1), rounding=ROUND_HALF_UP)):,} ms"


def _display(pricing_cat, category):
    """(price_display, tier_name) for the entry tier, from pricing.yaml fields (same fields cost.py reads)."""
    t = (pricing_cat.get("tiers") or {}).get("entry") or {}
    name = t.get("name")
    if _num(t.get("unit_price")):
        return f"{fmt_usd(_D(t['unit_price']) * 1000)} per 1,000 calls", name
    if _num(t.get("usd_per_credit")):
        cpc = (pricing_cat.get("credits_per_call_verified") or {}).get(category)
        if not _num(cpc):
            cpc = (pricing_cat.get("credits_per_call") or {}).get(category)
        per_credit = f"${_D(t['usd_per_credit']):f} per credit"   # as written in pricing.yaml
        if _num(cpc):
            return f"{fmt_usd(_D(t['usd_per_credit']) * _D(cpc) * 1000)} per 1,000 calls ({per_credit})", name
        return per_credit, name
    if _num(t.get("plan_fee")) and _num(t.get("included_units")):
        return f"{fmt_usd(_D(t['plan_fee']) / _D(t['included_units']) * 1000)} per 1,000 calls (plan fee over included units)", name
    return "n/a (paid-tier price not captured)", name


def provider_names(providers):
    return {p["id"]: p.get("name") or p["id"] for p in providers}


def price_rows(pricing, latest, providers=()):
    """One PricedTier dict per provider that has published results in latest.json (exactly the 4 priced providers),
    sorted by provider id. `providers` (providers.json list) only supplies display names."""
    names = provider_names(providers)
    pids = sorted({r["provider"] for _, r in _rows(latest)})
    out = []
    for pid in pids:
        cat = priced_category(pid, latest)
        c = ((pricing.get("providers") or {}).get(pid) or {}).get(cat)
        if not cat or not isinstance(c, dict):
            continue
        shown, tier_name = _display(c, cat)
        inputs = priced_inputs(pricing, pid, cat)
        out.append({"provider": pid, "name": names.get(pid, pid), "category": cat, "tier_key": "entry", "tier_name": tier_name,
                    "price_display": shown, "checked_at": priced_tier_checked_at(pricing, pid, cat), "inputs": inputs,
                    "source_url": c.get("source_url") or c.get("pricing_url") or ""})
    return out


def untested_providers(pricing, latest, providers):
    """Display names (sorted) of providers in pricing.yaml that have no published results: the other 11.
    A providers.json entry with `exclude_from_also_priced: true` is left off (AWI-PROVIDER-CONTEXTDEV-001 R3; absent = false)."""
    names = provider_names(providers)
    tested = {r["provider"] for _, r in _rows(latest)}
    held = {p["id"] for p in providers if p.get("exclude_from_also_priced") is True}
    return sorted(names.get(pid, pid) for pid in (pricing.get("providers") or {}) if pid not in tested and pid not in held)
