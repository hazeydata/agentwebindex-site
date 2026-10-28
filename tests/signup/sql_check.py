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
ok(db.execute(Q["markSent"], ("sub_2", "2026-10-27T13:00:00Z", rid)).rowcount == 0 and db.execute("SELECT beehiiv_sub_id, sent_at, attempts FROM signups WHERE id = ?", (rid,)).fetchone() == ("sub_1", "2026-10-26T13:00:00Z", 2), "a sent row is never re-marked sent (sub id, sent_at and attempts kept)")
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
# 5-attempt cap and deleted_at filters (retry + export) in real SQLite
db.execute("DELETE FROM signups")
for e, st, att, dl in [("cap4@x.io", "failed", 4, None), ("cap5@x.io", "failed", 5, None), ("delf@x.io", "failed", 0, "2026-10-01T00:00:00Z"),
                       ("delq@x.io", "queued", 0, "2026-10-01T00:00:00Z"), ("liveq@x.io", "queued", 0, None)]:
    db.execute("INSERT INTO signups (email_norm, email_raw, source, page, created_at, beehiiv_status, attempts, ip_hash, deleted_at) VALUES (?,?,?,?,?,?,?,?,?)",
               (e, e, "awi", "/", "2026-10-01T00:00:00Z", st, att, "h", dl))
MAX = int(subprocess.run(["node", "--input-type=module", "-e", "import {MAX_ATTEMPTS} from './signup/config.js'; console.log(MAX_ATTEMPTS)"],
                         cwd=R, capture_output=True, text=True, check=True).stdout)
ok(MAX == 5, "MAX_ATTEMPTS is 5")
ok([r[1] for r in db.execute(Q["due"], (MAX,))] == ["cap4@x.io"], "retry: attempts 4 due, attempts 5 capped, deleted row skipped")
ok(sorted(r[0] for r in db.execute(Q["exportRows"])) == ["cap4@x.io", "cap5@x.io", "liveq@x.io"], "export skips deleted rows")
# retry batch cap (Workers Free: 50 external subrequests per invocation; one Beehiiv fetch per due row)
BATCH = int(subprocess.run(["node", "--input-type=module", "-e", "import {RETRY_BATCH} from './signup/config.js'; console.log(RETRY_BATCH)"],
                           cwd=R, capture_output=True, text=True, check=True).stdout)
ok(BATCH == 40, "RETRY_BATCH is 40 (< 50 subrequests)")
db.execute("DELETE FROM signups")
for i in range(1, 46):
    db.execute("INSERT INTO signups (email_norm, email_raw, source, page, created_at, beehiiv_status, attempts, ip_hash) VALUES (?,?,?,?,?,?,?,?)",
               (f"b{i}@x.io", f"b{i}@x.io", "awi", "/", "2026-10-01T00:00:00Z", "failed", 0, "h"))
due = [r[1] for r in db.execute(Q["due"], (MAX,))]
ok(len(due) == 40 and due == [f"b{i}@x.io" for i in range(1, 41)], "retry: 45 due rows -> first 40 by id (LIMIT RETRY_BATCH)")
# AC 18 retention against real SQLite: same seed as endpoint.test.mjs; cutoff = 2026-10-26T13:00Z - 30 days
db.execute("DELETE FROM signups")
seed = [("old@x.io", "sent", "2026-09-25T13:00:00.000Z"), ("edge@x.io", "sent", "2026-09-26T13:00:00.000Z"),
        ("young@x.io", "sent", "2026-09-26T13:00:01.000Z"), ("q@x.io", "queued", None), ("p@x.io", "pending", None),
        ("f@x.io", "failed", None), ("oddq@x.io", "queued", "2026-01-01T00:00:00.000Z")]
for e, st, sa in seed:
    db.execute("INSERT INTO signups (email_norm, email_raw, source, page, created_at, beehiiv_status, ip_hash, sent_at) VALUES (?,?,?,?,?,?,?,?)",
               (e, e, "awi", "/", "2026-09-01T00:00:00.000Z", st, "h", sa))
cut = "2026-09-26T13:00:00.000Z"
ok(db.execute(Q["purge"], (cut,)).rowcount == 2, "purge deletes the two sent rows at/after 30 days")
ok(sorted(r[0] for r in db.execute("SELECT email_norm FROM signups")) == ["f@x.io", "oddq@x.io", "p@x.io", "q@x.io", "young@x.io"], "purge keeps queued/pending/failed and young sent rows")
ok(db.execute(Q["purge"], (cut,)).rowcount == 0, "purge is idempotent")
ok(db.execute(Q["purge"], ("9999-12-31T00:00:00.000Z",)).rowcount == 1 and db.execute("SELECT count(*) FROM signups").fetchone()[0] == 4, "far-future cutoff still never deletes unsent rows")
mock = subprocess.run(["node", "--input-type=module", "-e", """
import { mockD1 } from './tests/signup/helpers.mjs'; import { Q } from './signup/core.js';
const d = mockD1(); const s = JSON.parse(process.argv[1]);
s.forEach(([e, st, sa], i) => d.rows.push({ id: i + 1, email_norm: e, beehiiv_status: st, sent_at: sa, deleted_at: null }));
const r = await d.prepare(Q.purge).bind(process.argv[2]).run();
console.log(JSON.stringify([r.meta.changes, d.rows.map((x) => x.email_norm).sort()]));""", json.dumps(seed), cut], cwd=R, capture_output=True, text=True, check=True).stdout
ok(json.loads(mock) == [2, ["f@x.io", "oddq@x.io", "p@x.io", "q@x.io", "young@x.io"]], "mock D1 purge agrees with SQLite")
ok("ip" not in [c[1] for c in db.execute("PRAGMA table_info(signups)")], "no raw ip column")
print(f"sql_check: {n} checks passed against SQLite {sqlite3.sqlite_version}")
