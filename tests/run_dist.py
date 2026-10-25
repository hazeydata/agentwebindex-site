"""Run tests.test_dist and fail if it was hollowed out.

1. The real run must pass with exactly EXPECTED tests and no skips (skip-all, deleted tests, emptied class all fail).
2. Canaries: a scratch copy of the repo gets a known real defect injected into render.py, is rebuilt and re-tested,
   and the named tests MUST fail. Tests that return early, swallow assertions, or stop checking the behavior they
   name let a canary survive, which fails this runner.
"""
import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

EXPECTED = 65  # exact number of tests in tests.test_dist; update deliberately when adding or removing tests

R = Path(__file__).resolve().parent.parent
# name -> (exact text in the file, defect replacement, tests that must fail[, file])
CANARIES = {
    # the priced date must be the OLDEST input (Q4); the newest would hide a stale input
    "date_max_not_min": ("return min(ins.values())", "return max(ins.values())",
                         {"test_checked_at_is_min_of_inputs_and_inputs_are_only_used_fields", "test_tavily_named_case_dates"}, "prices.py"),
    # banker's rounding would turn 68.5% into 68%
    "banker_rounding": ("return f\"{(_D(x) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)}%\"",
                        "return f\"{(_D(x) * 100).quantize(Decimal(1), rounding=\"ROUND_HALF_EVEN\")}%\"", {"test_rounding_cases_half_up"}, "prices.py"),
    # chart accessible name dropped
    "chart_alt_dropped": ("alt = e(ctx.alt[name], quote=True)", "alt = ''", {"test_charts_alt_title_caption", "test_one_h1_skip_link_main_and_img_alts"}),
    # a real pack sample value leaking into a page must be caught
    "pack_sample_leak": ('<p><a href="/methodology/">Methodology and limits</a></p>', '<p>$0.80 per 1,000 pages · <a href="/methodology/">Methodology and limits</a></p>',
                         {"test_no_pack_sample_values"}),
    # a 'cheapest tier covering 100k/month' claim reaching any page must be caught (R7)
    "cheapest_tier_claim": ('<p><a href="/methodology/">Methodology and limits</a></p>', '<p>Cheapest tier covering 100k/month · <a href="/methodology/">Methodology and limits</a></p>',
                            {"test_no_cheapest_tier_100k_claim_anywhere"}),
    # published exclusions must use the allowlist; a denylist of just "note" leaks any other internal key
    "exclusion_denylist": ("{k:x[k] for k in EXCLUSION_PUBLIC if k in x}", '{k:v for k,v in x.items() if k!="note"}',
                           {"test_unknown_exclusion_key_never_published"}, "build.py"),
}
EXPECTED_CANARIES = 6  # emptying or trimming CANARIES fails the runner


def real_run():
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_dist")
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    errs = []
    if res.skipped:
        errs.append(f"{len(res.skipped)} skipped test(s): " + ", ".join(str(t) for t, _ in res.skipped[:5]))
    if res.testsRun != EXPECTED:
        errs.append(f"{res.testsRun} test(s) ran; expected exactly {EXPECTED}")
    if not res.wasSuccessful():
        errs.append("real run failed")
    print(f"meta: {res.testsRun} tests ran, {len(res.skipped)} skipped (expected exactly {EXPECTED})")
    return errs


def canary(name, old, new, must_fail, fn="render.py"):
    src = (R / fn).read_text()
    if src.count(old) != 1:
        return [f"canary {name}: anchor not found once in {fn} (update CANARIES with the code)"]
    with tempfile.TemporaryDirectory(prefix="awi-canary.") as t:
        w = Path(t) / "w"
        shutil.copytree(R, w, ignore=shutil.ignore_patterns(".git", "dist", "__pycache__"))
        (w / fn).write_text(src.replace(old, new))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        b = subprocess.run([sys.executable, "build.py"], cwd=w, env=env, capture_output=True, text=True)
        if b.returncode:
            return [f"canary {name}: build failed: {b.stderr[-300:]}"]
        p = subprocess.run([sys.executable, "-m", "unittest", "-v", "tests.test_dist"], cwd=w, env=env, capture_output=True, text=True)
    failed = set(re.findall(r"^(?:FAIL|ERROR): (test_\w+)", p.stderr, re.M))
    missing = sorted(must_fail - failed)
    print(f"canary {name}: failing: {', '.join(sorted(failed))}")
    print(f"canary {name}: suite exit {p.returncode}; {len(failed)} failing; required {len(must_fail)}, missed {len(missing)}")
    if p.returncode == 0 or missing:
        return [f"canary {name} survived: these tests did not fail on the injected defect: {', '.join(missing) or '(suite passed)'}"]
    return []


def main():
    errs = real_run()
    if len(CANARIES) != EXPECTED_CANARIES:
        errs.append(f"{len(CANARIES)} canaries defined; expected exactly {EXPECTED_CANARIES}")
    for name, (old, new, must, *fn) in CANARIES.items():
        errs += canary(name, old, new, must, *fn)
    for m in errs:
        print("META FAIL:", m, file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
