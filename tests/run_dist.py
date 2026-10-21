"""Run tests.test_dist and fail if it was hollowed out.

1. The real run must pass with exactly EXPECTED tests and no skips (skip-all, deleted tests, emptied class all fail).
2. Canaries: a scratch copy of the repo gets a known real defect injected into render.py, is rebuilt and re-tested,
   and the named tests MUST fail. Tests that return early, swallow assertions, or stop checking the behavior they
   name let a canary survive, which fails this runner.
"""
import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

EXPECTED = 39  # exact number of tests in tests.test_dist; update deliberately when adding or removing tests

R = Path(__file__).resolve().parent.parent
LPP_KEEP = 'if r["provider"] not in best or k > best[r["provider"]][0]:'
LPP_RET = "return [r for _, r in best.values()]"
# name -> (exact text in render.py, defect replacement, tests that must fail)
LPP = {"test_one_row_per_provider_single_week_title", "test_same_week_later_run_date_wins", "test_week_compared_numerically"}
CANARIES = {
    "dedupe_removed": (LPP_RET, "return list(rows)", LPP | {
        "test_latest_providers_exactly_once", "test_values_match_json", "test_browserless_own_set_label",
        "test_figures_no_legend_wilson_caption_title", "test_sets_published_only_shown_sets",
        "test_freshness_latest_week_per_provider", "test_freshness_latest_week_file_order_reversed"}),
    "first_in_file_wins": (LPP_KEEP, 'if r["provider"] not in best:', LPP | {
        "test_browserless_own_set_label", "test_freshness_latest_week_file_order_reversed"}),
    "last_in_file_wins": (LPP_KEEP, "if True:", LPP | {"test_freshness_latest_week_per_provider"}),
    # a real pack sample value rendered into every category panel must be caught as a leak
    "pack_sample_leak": ('<p class="lb-foot">', '<p class="lb-foot">$0.80 per 1,000 pages · ', {"test_no_pack_sample_values"}),
}
EXPECTED_CANARIES = 4  # emptying or trimming CANARIES fails the runner


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


def canary(name, old, new, must_fail):
    src = (R / "render.py").read_text()
    if src.count(old) != 1:
        return [f"canary {name}: anchor not found once in render.py (update CANARIES with the code)"]
    with tempfile.TemporaryDirectory(prefix="awi-canary.") as t:
        w = Path(t) / "w"
        shutil.copytree(R, w, ignore=shutil.ignore_patterns(".git", "dist", "__pycache__"))
        (w / "render.py").write_text(src.replace(old, new))
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
    for name, (old, new, must) in CANARIES.items():
        errs += canary(name, old, new, must)
    for m in errs:
        print("META FAIL:", m, file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
