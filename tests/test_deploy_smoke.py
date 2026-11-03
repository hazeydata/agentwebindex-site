"""Unit tests for scripts/deploy/smoke.py (no network)."""
import importlib.util
import pathlib
import unittest

_spec = importlib.util.spec_from_file_location("smoke", pathlib.Path(__file__).resolve().parent.parent / "scripts/deploy/smoke.py")
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

HTML = "text/html; charset=utf-8"
INDEX = b'<html><title>AgentWebIndex</title><a href="/cdn-cgi/l/email-protection#0c6a7e"><span data-cfemail="5630"></span></html>'
INDEX_OTHER_TOKEN = INDEX.replace(b"0c6a7e", b"f39581").replace(b"5630", b"afc9")
WORKER_JS = b"export default { async fetch(r, env) { return handleSubscribe(r, env) } }"


class ScriptedTypeAnyStatusTest(unittest.TestCase):
    """r1 mutant b: JS/JSON content type on worker/routes paths must fail at ANY status, incl. 404."""
    def test_worker_404_javascript_fails(self):
        for p in ("/_worker.js", "/_worker.js/", "/_worker.js/index.js"):
            for ct in ("application/javascript", "text/javascript; charset=utf-8"):
                self.assertFalse(smoke.check(p, 404, ct, b"x", INDEX)[0], (p, ct))

    def test_routes_404_json_fails(self):
        self.assertFalse(smoke.check("/_routes.json", 404, "application/json", b"{}", INDEX)[0])
        self.assertFalse(smoke.check("/_routes.json", 404, "application/json", b"x", INDEX)[0])

    def test_js_json_fail_at_every_status(self):
        for st in (200, 301, 403, 404, 500):
            self.assertFalse(smoke.check("/_worker.js", st, "application/javascript", b"x", INDEX)[0], st)
            self.assertFalse(smoke.check("/_routes.json", st, "application/json", b"x", INDEX)[0], st)


class SmokeTest(unittest.TestCase):
    def test_spa_fallback_200_is_not_a_served_worker(self):
        # The W45 false positive: 200 for /_worker.js/index.js was only the index.html fallback.
        ok, why = smoke.check("/_worker.js/index.js", 200, HTML, INDEX_OTHER_TOKEN, INDEX)
        self.assertTrue(ok, why)
        self.assertIn("SPA fallback", why)

    def test_worker_served_as_javascript_fails(self):
        for p in ("/_worker.js", "/_worker.js/index.js"):
            ok, _ = smoke.check(p, 200, "application/javascript", WORKER_JS, INDEX)
            self.assertFalse(ok, p)

    def test_worker_code_in_html_body_fails(self):
        ok, why = smoke.check("/_worker.js/index.js", 200, HTML, WORKER_JS, INDEX)
        self.assertFalse(ok)
        self.assertIn("WORKER CODE", why)

    def test_routes_json_as_json_fails(self):
        self.assertFalse(smoke.check("/_routes.json", 200, "application/json", b'{"version":1}', INDEX)[0])

    def test_worker_404_passes(self):
        self.assertTrue(smoke.check("/_worker.js", 404, "text/plain", b"Not found", INDEX)[0])

    def test_api_routes_spa_fallback_is_a_failure(self):
        # A 200 SPA page on an API route means the Functions did not deploy.
        self.assertFalse(smoke.check("/api/subscribe", 200, HTML, INDEX, INDEX)[0])
        self.assertFalse(smoke.check("/api/signups/export.csv", 200, HTML, INDEX, INDEX)[0])

    def test_api_routes_expected_responses_pass(self):
        self.assertTrue(smoke.check("/api/subscribe", 405, "", b"", INDEX)[0])
        self.assertTrue(smoke.check("/api/signups/export.csv", 401, "text/plain;charset=UTF-8", b"Unauthorized", INDEX)[0])

    def test_export_wrong_status_fails(self):
        self.assertFalse(smoke.check("/api/signups/export.csv", 200, "text/csv", b"email\n", INDEX)[0])

    def test_home(self):
        self.assertTrue(smoke.check("/", 200, HTML, INDEX, INDEX)[0])
        self.assertFalse(smoke.check("/", 200, "application/json", b"{}", INDEX)[0])

    def test_normalize_strips_cf_email_tokens(self):
        self.assertEqual(smoke.normalize(INDEX), smoke.normalize(INDEX_OTHER_TOKEN))


class DistTest(unittest.TestCase):
    def test_site_build_emits_no_worker_or_routes(self):
        # refresh_dist.sh compiles functions/ into dist/_worker.js/ itself and refuses a build that already has one.
        dist = pathlib.Path(__file__).resolve().parent.parent / "dist"
        if not dist.is_dir():
            self.skipTest("dist/ not built")
        self.assertFalse((dist / "_worker.js").exists())
        self.assertFalse((dist / "_routes.json").exists())


if __name__ == "__main__":
    unittest.main()
