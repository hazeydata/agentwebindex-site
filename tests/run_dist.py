"""Run tests.test_dist and fail if it was hollowed out (skip-all, emptied class, import-time SkipTest).

A skip decorator or `raise unittest.SkipTest` makes unittest report OK with every test skipped;
this runner treats any skip, or fewer real tests than FLOOR, as a failure.
"""
import sys, unittest

FLOOR = 30  # test_dist has 36 non-skipped tests at the time of writing; raise this as tests are added


def main():
    suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_dist")
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    ran = res.testsRun - len(res.skipped)
    errs = []
    if res.skipped:
        errs.append(f"{len(res.skipped)} skipped test(s): " + ", ".join(str(t) for t, _ in res.skipped[:5]))
    if ran < FLOOR:
        errs.append(f"only {ran} non-skipped test(s) ran; floor is {FLOOR}")
    for m in errs:
        print("META FAIL:", m, file=sys.stderr)
    print(f"meta: {ran} non-skipped tests ran (floor {FLOOR})")
    return 0 if res.wasSuccessful() and not errs else 1


if __name__ == "__main__":
    sys.exit(main())
