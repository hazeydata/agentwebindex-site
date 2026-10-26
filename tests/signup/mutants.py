"""Mutation check for the signup save-order and fallback logic (AWI-SIGNUP-FORM-001 AC 1, 3, 4, 7, 8, 8a, 9, 10).
Each mutant copies signup/, functions/, migrations/, tests/signup/, site.config.json and dist/newsletter/thanks/ to a temp
dir, injects one defect, and runs the node signup tests plus sql_check.py there with a timeout. Every mutant must be killed.
Run after `python3 build.py`: python3 tests/signup/mutants.py"""
import os, shutil, signal, subprocess, sys, tempfile
from pathlib import Path
R = Path(__file__).resolve().parents[2]
C, CFG = "signup/core.js", "signup/config.js"
SEND_FIRST = "  const db = env.SIGNUPS;\n  if (!db) { log('signup', 'error', 'd1_missing')"
MUTANTS = {
    "send_before_store": (C, SEND_FIRST, "  await sendToBeehiiv(env, beehiivBody(email, '/', self), fetchImpl, timeoutMs);\n" + SEND_FIRST),
    "d1_fail_still_sends": (C, "    log('signup', 'error', 'd1_write');\n    return respond(request, 'error');", "    log('signup', 'error', 'd1_write'); row = { id: 0 };"),
    "missing_d1_says_queued": (C, "if (!db) { log('signup', 'error', 'd1_missing'); return respond(request, 'error'); }", "if (!db) { return respond(request, 'queued'); }"),
    "repeat_resends": (C, "if (!((r?.meta?.changes ?? 0) > 0)) {", "if (false) {"),
    "honeypot_ignored": (C, "if (!botCheck(fields))", "if (false && !botCheck(fields))"),
    "rate_limit_after_store": (C, "if (await overLimit(env, hash, now)) { log('signup', 'rate_limited'); return respond(request, 'rate_limited'); }", ""),
    "failure_says_success": (C, "return respond(request, out.kind === 'sent' ? SUCCESS_STATUS : 'queued');", "return respond(request, SUCCESS_STATUS);"),
    "failure_marked_sent": (C, "if (out.kind === 'sent') await db.prepare(Q.markSent)", "if (out.kind !== 'queued') await db.prepare(Q.markSent)"),
    "401_not_queued": (C, "(res.status === 401 || res.status === 403)", "(res.status === 403)"),
    "403_not_queued": (C, "(res.status === 401 || res.status === 403)", "(res.status === 401)"),
    "no_key_still_calls": (C, "  if (!env.BEEHIIV_API_KEY || !env.BEEHIIV_PUB_ID) return { kind: 'queued', code: 'no_key' };\n", ""),
    "retry_no_key_not_skipped": (C, "  if (!env.BEEHIIV_API_KEY || !env.BEEHIIV_PUB_ID) { log('retry', 'skipped', 'no_key'); return { tried: 0, skipped: 'no_key' }; }\n", ""),
    "retry_includes_sent": (C, "WHERE beehiiv_status IN ('failed', 'pending') AND attempts", "WHERE beehiiv_status IN ('failed', 'pending', 'sent') AND attempts"),
    "retry_includes_queued": (C, "WHERE beehiiv_status IN ('failed', 'pending') AND attempts", "WHERE beehiiv_status IN ('failed', 'pending', 'queued') AND attempts"),
    "sent_downgradable": (C, "last_error = ? WHERE id = ? AND beehiiv_status != 'sent'\",\n  markQueued", "last_error = ? WHERE id = ?\",\n  markQueued"),
    "retry_keeps_calling_after_403": (C, "    if (out.kind === 'queued') break;", ""),
    "max_attempts_6": (CFG, "export const MAX_ATTEMPTS = 5;", "export const MAX_ATTEMPTS = 6;"),
    "export_includes_sent": (C, "FROM signups WHERE beehiiv_status != 'sent' AND deleted_at IS NULL ORDER BY id", "FROM signups WHERE deleted_at IS NULL ORDER BY id"),
    "export_no_auth": ("functions/api/signups/export.csv.js", "if (!(await tokenMatches(", "if (false && !(await tokenMatches("),
    "timeout_never_aborts": (C, "setTimeout(() => ctrl.abort(), timeoutMs)", "setTimeout(() => {}, timeoutMs)"),
    "doi_drift": (CFG, "export const DOUBLE_OPT_IN = true;", "export const DOUBLE_OPT_IN = false;"),
    "no_source_tag": (C, "custom_fields: [{ name: BEEHIIV_SOURCE_FIELD, value: BEEHIIV_SOURCE_TAG }],", ""),
    "raw_ip_stored": (C, "nowIso, hash).run();", "nowIso, request.headers.get('CF-Connecting-IP')).run();"),
}
COPY = ["signup", "functions", "migrations", "tests/signup", "site.config.json", "dist/newsletter/thanks"]
CMDS = [["node", "--test", "tests/signup/"], [sys.executable, "tests/signup/sql_check.py"]]

def run(cmd, cwd, timeout=60):
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        return p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL); p.wait(); return "timeout"

def main():
    if not (R / "dist/newsletter/thanks").exists():
        sys.exit("run python3 build.py first")
    base = [run(c, R) for c in CMDS]
    if base != [0, 0]:
        sys.exit(f"mutants: baseline not green: {base}")
    killed, survived = 0, []
    t = tempfile.mkdtemp(prefix="awi-mutants.")
    try:
        for name, (fn, old, new) in MUTANTS.items():
            w = Path(t) / name
            for c in COPY:
                (w / c).parent.mkdir(parents=True, exist_ok=True)
                (shutil.copytree if (R / c).is_dir() else shutil.copy)(R / c, w / c)
            src = (w / fn).read_text()
            if src.count(old) != 1:
                sys.exit(f"mutant {name}: anchor found {src.count(old)} times in {fn}")
            (w / fn).write_text(src.replace(old, new))
            res = [run(c, w) for c in CMDS]
            dead = any(r != 0 for r in res)
            print(f"mutant {name}: {'killed' if dead else 'SURVIVED'} (node={res[0]}, sql={res[1]})")
            killed += dead
            if not dead: survived.append(name)
    finally:
        shutil.rmtree(t, ignore_errors=True)
    print(f"mutants: {killed}/{len(MUTANTS)} killed")
    return 1 if survived else 0

if __name__ == "__main__":
    sys.exit(main())
