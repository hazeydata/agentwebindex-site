"""refresh_dist.sh must refuse to run without AWI_DEPLOY_ROOT / AWI_TMP_ROOT, failing on its own guard (not set -u)."""
import os
import pathlib
import subprocess
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts/deploy/refresh_dist.sh"
MSG = {"AWI_DEPLOY_ROOT": "refresh_dist: STOP: set AWI_DEPLOY_ROOT", "AWI_TMP_ROOT": "refresh_dist: STOP: set AWI_TMP_ROOT"}


def run(unset):
    env = {k: v for k, v in os.environ.items() if not k.startswith("AWI_")}
    env.update(AWI_DEPLOY_ROOT="/nonexistent-awi-deploy", AWI_TMP_ROOT="/nonexistent-awi-tmp")
    del env[unset]
    return subprocess.run(["bash", str(SCRIPT), "--help"], env=env, capture_output=True, text=True, timeout=20)


class GuardTest(unittest.TestCase):
    def _check(self, var):
        r = run(var)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(MSG[var], r.stderr)
        self.assertNotIn("unbound variable", r.stderr)

    def test_deploy_root_unset(self):
        self._check("AWI_DEPLOY_ROOT")

    def test_tmp_root_unset(self):
        self._check("AWI_TMP_ROOT")

    def test_empty_counts_as_unset(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("AWI_")}
        env.update(AWI_DEPLOY_ROOT="", AWI_TMP_ROOT="/nonexistent-awi-tmp")
        r = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=20)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(MSG["AWI_DEPLOY_ROOT"], r.stderr)


if __name__ == "__main__":
    unittest.main()
