"""Every statement in signup/core.js Q runs against migrations/0001_signups.sql in real SQLite (D1 is SQLite), and the
mock D1 in helpers.mjs agrees with SQLite on the behaviours the endpoint relies on. Run: python3 tests/signup/sql_check.py"""
import json, sqlite3, subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parents[2]
Q = json.loads(subprocess.run(["node", "--input-type=module", "-e", "import {Q} from './signup/core.js'; console.log(JSON.stringify(Q))"],
                              cwd=R, capture_output=True, text=True, check=True).stdout)
db = sqlite3.connect(":memory:")
db.executescript((R / "migrations/0001_signups.sql").read_text())
db.executescript((R / "migrations/0001_signups.sql").read_text())   # idempotent
n = 0
def ok(cond, msg):
    global n
    if not cond: sys.exit(f"sql_check FAIL: {msg}")
    n += 1
ins = lambda e: db.execute(Q["insert"], (e, e, "awi", "/", "2026-10-26T13:00:00.000Z", "h" * 64)).rowcount
ok(ins("a@example.com") == 1, "insert writes a row")
ok(ins("a@example.com") == 0, "duplicate (email_norm, source) is ignored (changes 0)")
ok(db.execute("SELECT count(*) FROM signups").fetchone()[0] == 1, "one row")
rid, st = db.execute(Q["byEmail"], ("a@example.com", "awi")).fetchone(); ok(st == "pending", "new row pending")
ok(db.execute(Q["due"], (5,)).fetchall()[0][1] == "a@example.com", "pending row is due")
db.execute(Q["markFailed"], ("http_503", rid)); ok(db.execute("SELECT beehiiv_status, attempts FROM signups").fetchone() == ("failed", 1), "markFailed")
db.execute(Q["markSent"], ("sub_1", "2026-10-26T13:00:00Z", rid)); ok(db.execute("SELECT beehiiv_status, attempts, beehiiv_sub_id FROM signups").fetchone() == ("sent", 2, "sub_1"), "markSent")
ok(db.execute(Q["markFailed"], ("timeout", rid)).rowcount == 0, "a sent row is never downgraded")
ok(db.execute(Q["markQueued"], ("no_key", rid)).rowcount == 0, "a sent row is never queued")
ok(db.execute(Q["due"], (5,)).fetchall() == [], "sent row is not due")
ok(db.execute(Q["exportRows"]).fetchall() == [], "sent row not exported")
ins("b@example.com"); rb = db.execute(Q["byEmail"], ("b@example.com", "awi")).fetchone()[0]
db.execute(Q["markQueued"], ("http_401", rb)); ok(db.execute(Q["due"], (5,)).fetchall() == [], "queued rows are not retried")
ok([r[0] for r in db.execute(Q["exportRows"]).fetchall()] == ["b@example.com"], "queued row exported")
ok(db.execute(Q["exportRows"]).description and [d[0] for d in db.execute(Q["exportRows"]).description] == ["email", "source", "created_at"], "export columns")
try:
    db.execute("UPDATE signups SET beehiiv_status='bogus'"); ok(False, "CHECK constraint")
except sqlite3.IntegrityError:
    ok(True, "")
ok("ip" not in [c[1] for c in db.execute("PRAGMA table_info(signups)")], "no raw ip column")
print(f"sql_check: {n} checks passed against SQLite {sqlite3.sqlite_version}")
