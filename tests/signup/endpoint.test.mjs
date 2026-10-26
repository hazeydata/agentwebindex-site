// AWI-SIGNUP-FORM-001 S1/S2 on mocks. Run: node --test tests/signup/
import test from 'node:test';
import assert from 'node:assert/strict';
import { handleSubscribe, retryPending, purgeSent, normalizeEmail, beehiivBody, _resetMemoryLimiter, BOT_CHECKS } from '../../signup/core.js';
import { runScheduled } from '../../workers/signup-retry.js';
import { handleExport } from '../../functions/api/signups/export.csv.js';
import * as CFG from '../../signup/config.js';
import { mockD1, mockFetch, env, post, capture, SECRET_KEY, SALT, ORIGIN } from './helpers.mjs';

const T0 = Date.UTC(2026, 9, 26, 13, 0, 0);
let clock = T0;
async function sub(e, fields, o = {}) {
  const f = o.fetch || mockFetch();
  const { out, lines } = await capture(() => handleSubscribe(post(fields, o), e, { fetch: f, now: o.now ?? clock, timeoutMs: o.timeoutMs }));
  const text = await out.text();
  return { res: out, status: out.headers.get('Content-Type')?.includes('json') ? JSON.parse(text).status : null, text, fetch: f, lines };
}
const OK = { email: 'Kitty@Example.COM', page: '/' };
test.beforeEach(() => { _resetMemoryLimiter(); clock += 3600_000; });

// ---------------- S1
test('AC1 one awi row is written before the Beehiiv call', async () => {
  const e = env(); let rowsAtCall = -1;
  const f = mockFetch(() => { rowsAtCall = e.SIGNUPS.rows.length; return new Response('{"data":{"id":"sub_1"}}', { status: 201 }); });
  const r = await sub(e, OK, { fetch: f });
  assert.equal(rowsAtCall, 1);
  assert.equal(e.SIGNUPS.rows.length, 1);
  assert.equal(e.SIGNUPS.rows[0].source, 'awi');
  assert.equal(f.calls.length, 1);
  assert.equal(r.status, CFG.SUCCESS_STATUS);
});
test('AC1 D1 write failure -> error and no Beehiiv call', async () => {
  const e = env({ SIGNUPS: mockD1({ failInsert: true }) });
  const r = await sub(e, OK);
  assert.equal(r.status, 'error'); assert.equal(r.res.status, 502); assert.equal(r.fetch.calls.length, 0);
});
test('edge: missing D1 binding fails closed with error, no Beehiiv call', async () => {
  const e = env({ SIGNUPS: undefined });
  const r = await sub(e, OK);
  assert.equal(r.status, 'error'); assert.equal(r.fetch.calls.length, 0);
});
test('AC2 normalization: trim, lowercase domain only', () => {
  assert.equal(normalizeEmail('  Kitty.Q@Example.COM \n'), 'Kitty.Q@example.com');
});
for (const [name, v] of [['empty', ''], ['spaces', '   '], ['inner space', 'a b@example.com'], ['a@b', 'a@b'], ['a@@b.com', 'a@@b.com'],
  ['300 chars', `${'a'.repeat(290)}@example.com`], ['unicode local part (OQ-5 default ASCII)', 'kätzchen@example.com'], ['IDN domain', 'a@bücher.de'],
  ['no @', 'example.com'], ['missing field', undefined]]) {
  test(`AC2 invalid: ${name} -> invalid, no row, no call`, async () => {
    const e = env();
    const r = await sub(e, { email: v, page: '/' });
    assert.equal(r.status, 'invalid'); assert.equal(r.res.status, 400);
    assert.equal(e.SIGNUPS.rows.length, 0); assert.equal(r.fetch.calls.length, 0);
  });
}
test('AC2 254 chars accepted, 255 rejected', () => {
  const at = (n) => `${'a'.repeat(64)}@${'b'.repeat(n - 64 - 1 - 4)}.com`;
  // build domain of labels <= 63 chars
  const mk = (n) => { let d = ''; while (d.length < n - 65 - 4) d += (d ? '.' : '') + 'b'.repeat(Math.min(60, n - 65 - 4 - d.length - (d ? 1 : 0))); return `${'a'.repeat(64)}@${d}.com`; };
  assert.equal(mk(254).length, 254); assert.ok(normalizeEmail(mk(254)));
  assert.equal(normalizeEmail(mk(254) + 'x'), null); void at;
});
test('OQ-5 unicode rejection is logged as unicode (no address in the log)', async () => {
  const r = await sub(env(), { email: 'kätzchen@example.com' });
  assert.ok(r.lines.some((l) => l.includes('"reason":"unicode"')));
  assert.ok(!r.lines.join('').includes('example.com'));
});
test('AC3 repeat after success: no second row, no second call, same text', async () => {
  const e = env(); const f = mockFetch();
  const a = await sub(e, OK, { fetch: f });
  const b = await sub(e, { email: ' Kitty@EXAMPLE.com ', page: '/newsletter/' }, { fetch: f });
  assert.equal(e.SIGNUPS.rows.length, 1); assert.equal(f.calls.length, 1);
  assert.equal(a.status, b.status); assert.equal(a.res.status, b.res.status);
});
test('AC3 repeat while queued answers queued, like a first signup in that state', async () => {
  const e = env({ BEEHIIV_API_KEY: undefined });
  const a = await sub(e, OK); const b = await sub(e, OK);
  assert.equal(a.status, 'queued'); assert.equal(b.status, 'queued'); assert.equal(e.SIGNUPS.rows.length, 1);
});
test('edge: two tabs at once -> one row (unique email_norm, source)', async () => {
  const e = env(); const f = mockFetch();
  await Promise.all([sub(e, OK, { fetch: f }), sub(e, OK, { fetch: f })]);
  assert.equal(e.SIGNUPS.rows.length, 1); assert.equal(f.calls.length, 1);
});
test('AC4 honeypot filled -> fake success, nothing stored, no call', async () => {
  const e = env();
  const r = await sub(e, { ...OK, website: 'http://spam.example' });
  assert.equal(r.status, CFG.SUCCESS_STATUS); assert.equal(e.SIGNUPS.rows.length, 0); assert.equal(r.fetch.calls.length, 0);
});
test('AC4/R2 bot check is pluggable and only the honeypot is registered', () => {
  assert.deepEqual(Object.keys(BOT_CHECKS), ['honeypot']); assert.equal(CFG.BOT_CHECK, 'honeypot');
});
test('AC5 per-IP: 5 posts per 10 min, 6th rate_limited, window resets (mocked clock)', async () => {
  const e = env(); const t = clock - (clock % 600_000);
  for (let i = 0; i < 5; i++) assert.notEqual((await sub(e, { email: `k${i}@example.com` }, { now: t + i * 1000 })).status, 'rate_limited');
  const r = await sub(e, { email: 'k9@example.com' }, { now: t + 9000 });
  assert.equal(r.status, 'rate_limited'); assert.equal(r.res.status, 429);
  assert.equal(e.SIGNUPS.rows.length, 5);
  assert.equal(CFG.MESSAGES.rate_limited, 'Too many tries, please wait a few minutes.');
  assert.notEqual((await sub(e, { email: 'k10@example.com' }, { now: t + 600_000 })).status, 'rate_limited');
});
test('AC5 site-wide: 50 per minute across IPs, 51st rate_limited, nothing stored', async () => {
  const e = env(); const t = clock - (clock % 60_000);
  for (let i = 0; i < 50; i++) assert.notEqual((await sub(e, { email: `s${i}@example.com` }, { now: t, ip: `198.51.100.${i}` })).status, 'rate_limited');
  const r = await sub(e, { email: 'late@example.com' }, { now: t + 59_000, ip: '192.0.2.1' });
  assert.equal(r.status, 'rate_limited'); assert.equal(e.SIGNUPS.rows.length, 50);
  assert.notEqual((await sub(e, { email: 'next@example.com' }, { now: t + 60_000, ip: '192.0.2.1' })).status, 'rate_limited');
});
test('AC5 rate limit also applies to honeypot and invalid posts (counted before them)', async () => {
  const e = env(); const t = clock - (clock % 600_000);
  for (let i = 0; i < 5; i++) await sub(e, { email: 'bad' }, { now: t });
  assert.equal((await sub(e, OK, { now: t })).status, 'rate_limited');
});
test('AC6 raw IP never stored; ip_hash is salted SHA-256', async () => {
  const e = env(); await sub(e, OK, { ip: '203.0.113.99' });
  const row = e.SIGNUPS.rows[0];
  assert.ok(!JSON.stringify(row).includes('203.0.113.99'));
  assert.ok(![...e.SIGNUP_RL.m.keys()].join().includes('203.0.113.99'));
  assert.match(row.ip_hash, /^[0-9a-f]{64}$/);
  const e2 = env({ IP_SALT: 'other_TESTSALT' }); await sub(e2, OK, { ip: '203.0.113.99' });
  assert.notEqual(e2.SIGNUPS.rows[0].ip_hash, row.ip_hash);
});
test('AC6 missing IP_SALT fails closed with error, nothing stored', async () => {
  const e = env({ IP_SALT: undefined }); const r = await sub(e, OK);
  assert.equal(r.status, 'error'); assert.equal(e.SIGNUPS.rows.length, 0); assert.equal(r.fetch.calls.length, 0);
});
test('edge: cross-origin or missing Origin -> 403, nothing stored', async () => {
  for (const origin of ['https://evil.example', null]) {
    const e = env(); const r = await sub(e, OK, { origin });
    assert.equal(r.res.status, 403); assert.equal(e.SIGNUPS.rows.length, 0); assert.equal(r.res.headers.get('Access-Control-Allow-Origin'), null);
  }
});
test('GET /api/subscribe -> 405', async () => {
  const r = await handleSubscribe(new Request(`${ORIGIN}/api/subscribe`), env());
  assert.equal(r.status, 405);
});
test('AC15 (mock part) no-JS form post -> 303 to the static thank-you page', async () => {
  const e = env();
  const r = await sub(e, OK, { json: false });
  assert.equal(r.res.status, 303);
  assert.equal(r.res.headers.get('Location'), `/newsletter/thanks/${CFG.SUCCESS_STATUS}/`);
  assert.equal(e.SIGNUPS.rows.length, 1);
  const bad = await sub(env(), { email: 'a@b' }, { json: false });
  assert.equal(bad.res.headers.get('Location'), '/newsletter/thanks/invalid/');
});

// ---------------- S2
test('AC7 2xx -> sent + sub id; DOI on -> pending_confirmation "Check your inbox to confirm your subscription."', async () => {
  const e = env(); const r = await sub(e, OK);
  const row = e.SIGNUPS.rows[0];
  assert.equal(row.beehiiv_status, 'sent'); assert.equal(row.beehiiv_sub_id, 'sub_123'); assert.equal(row.attempts, 1);
  assert.equal(CFG.DOUBLE_OPT_IN, true);
  assert.equal(r.status, 'pending_confirmation');
  assert.equal(CFG.MESSAGES[r.status], 'Check your inbox to confirm your subscription.');
  assert.equal(r.fetch.calls[0].body.double_opt_override, 'on');
});
test('AC7 edge: Beehiiv returns an existing/unsubscribed subscriber (2xx) -> sent, same text', async () => {
  const e = env();
  const r = await sub(e, OK, { fetch: mockFetch(() => new Response('{"data":{"id":"sub_old","status":"inactive"}}', { status: 200 })) });
  assert.equal(e.SIGNUPS.rows[0].beehiiv_status, 'sent'); assert.equal(r.status, CFG.SUCCESS_STATUS);
  assert.equal(r.fetch.calls[0].body.reactivate_existing, false);
});
for (const [name, resp, code] of [['5xx', 503, 'http_503'], ['429', 429, 'http_429'], ['timeout', 'timeout', 'timeout'], ['network', 'network', 'network'], ['400', 400, 'http_400']]) {
  test(`AC8 Beehiiv ${name} -> failed, code logged without key, queued text`, async () => {
    const e = env();
    const f = mockFetch(() => (typeof resp === 'number' ? new Response(`{"errors":"${SECRET_KEY}"}`, { status: resp }) : resp));
    const r = await sub(e, OK, { fetch: f, timeoutMs: 20 });
    const row = e.SIGNUPS.rows[0];
    assert.equal(row.beehiiv_status, 'failed'); assert.equal(row.last_error, code);
    assert.equal(r.status, 'queued'); assert.equal(r.res.status, 200);
    assert.equal(CFG.MESSAGES.queued, "Thanks, you're on the list. We'll send a confirmation email soon.");
    assert.ok(!/check your inbox/i.test(CFG.MESSAGES.queued));
    assert.ok(r.lines.some((l) => l.includes(code)));
    assert.ok(!(r.lines.join('\n') + r.text).includes(SECRET_KEY));
  });
}
test('AC8 the timeout is 5 s', () => assert.equal(CFG.BEEHIIV_TIMEOUT_MS, 5000));
for (const [name, over, resp] of [['key unset', { BEEHIIV_API_KEY: undefined }, null], ['401', {}, 401], ['403', {}, 403]]) {
  test(`AC8a ${name} -> row queued (CSV path), queued text`, async () => {
    const e = env(over);
    const f = mockFetch(() => new Response('{}', { status: resp || 500 }));
    const r = await sub(e, OK, { fetch: f });
    assert.equal(e.SIGNUPS.rows[0].beehiiv_status, 'queued');
    assert.equal(r.status, 'queued');
    assert.equal(f.calls.length, resp ? 1 : 0);
  });
}
test('AC8a retry job skips the Beehiiv call when the key is unset', async () => {
  const e = env({ BEEHIIV_API_KEY: undefined }); await sub(e, OK);
  e.SIGNUPS.rows[0].beehiiv_status = 'failed';
  const f = mockFetch(); const { out } = await capture(() => retryPending(e, { fetch: f }));
  assert.equal(f.calls.length, 0); assert.equal(out.skipped, 'no_key');
});
test('AC9 retry: failed/pending rows retried, max 5 attempts, sent never re-sent, idempotent', async () => {
  const e = env();
  await sub(e, { email: 'f@example.com' }, { fetch: mockFetch(() => new Response('', { status: 500 })) });
  await sub(e, { email: 's@example.com' });
  const db = e.SIGNUPS;
  db.rows.push({ ...db.rows[0], id: 99, email_norm: 'p@example.com', beehiiv_status: 'pending', attempts: 0 });
  const down = mockFetch(() => new Response('', { status: 502 }));
  for (let i = 0; i < 10; i++) await capture(() => retryPending(e, { fetch: down }));
  const byEmail = Object.fromEntries(db.rows.map((r) => [r.email_norm, r]));
  assert.equal(byEmail['f@example.com'].attempts, 5); assert.equal(byEmail['p@example.com'].attempts, 5);
  assert.ok(down.calls.every((c) => c.body.email !== 's@example.com'));
  assert.equal(down.calls.length, 4 + 5);
  byEmail['p@example.com'].attempts = 2;
  const up = mockFetch();
  await capture(() => retryPending(e, { fetch: up }));
  await capture(() => retryPending(e, { fetch: up }));
  assert.equal(up.calls.length, 1); assert.equal(byEmail['p@example.com'].beehiiv_status, 'sent');
});
test('AC9 retry stops calling Beehiiv in a run once it answers 401/403 (plan lapsed)', async () => {
  const e = env(); const f0 = mockFetch(() => new Response('', { status: 500 }));
  for (const x of ['a', 'b', 'c']) await sub(e, { email: `${x}@example.com` }, { fetch: f0 });
  const f = mockFetch(() => new Response('', { status: 403 }));
  await capture(() => retryPending(e, { fetch: f }));
  assert.equal(f.calls.length, 1);
  assert.equal(e.SIGNUPS.rows[0].beehiiv_status, 'queued');
});
test('AC10 export: 401 without or with a wrong X-Export-Token', async () => {
  const e = env();
  for (const h of [{}, { 'X-Export-Token': 'nope' }, { Authorization: 'Bearer fake-TEST-export' }]) {
    const { out } = await capture(() => handleExport(new Request(`${ORIGIN}/api/signups/export.csv`, { headers: h }), e));
    assert.equal(out.status, 401); assert.ok(!(await out.text()).includes('@'));
  }
  const { out } = await capture(() => handleExport(new Request(`${ORIGIN}/api/signups/export.csv`, { headers: { 'X-Export-Token': 'x' } }), env({ EXPORT_TOKEN: undefined })));
  assert.equal(out.status, 401);
});
test('AC10 export: email,source,created_at for unsent rows only; formula-guarded; exporting deletes nothing', async () => {
  const e = env();
  await sub(e, { email: 'sent@example.com' });
  await sub(e, { email: 'fail@example.com' }, { fetch: mockFetch(() => new Response('', { status: 500 })) });
  await sub(e, { email: '=cmd@example.com' }, { fetch: mockFetch(() => new Response('', { status: 401 })) });
  const n = e.SIGNUPS.rows.length;
  const { out } = await capture(() => handleExport(new Request(`${ORIGIN}/api/signups/export.csv`, { headers: { 'X-Export-Token': 'fake-TEST-export' } }), e));
  assert.equal(out.status, 200);
  const lines = (await out.text()).trim().split('\r\n');
  assert.equal(lines[0], 'email,source,created_at');
  assert.equal(lines.length, 3);
  assert.match(lines[1], /^fail@example\.com,awi,2026-/);
  assert.match(lines[2], /^'=cmd@example\.com,awi,/);
  assert.equal(e.SIGNUPS.rows.length, n);
});
test('AC11 payload carries source AWI + utm_source=agentwebindex', async () => {
  const r = await sub(env(), { email: 'k@example.com', page: '/newsletter/' });
  const b = r.fetch.calls[0].body;
  assert.deepEqual(b.custom_fields, [{ name: 'source', value: 'AWI' }]);
  assert.equal(b.utm_source, 'agentwebindex');
  assert.equal(b.referring_site, `${ORIGIN}/newsletter/`);
  assert.equal(b.email, 'k@example.com');
  assert.equal(b.send_welcome_email, false);
  assert.equal(r.fetch.calls[0].url, 'https://api.beehiiv.com/v2/publications/pub_test/subscriptions');
  assert.equal(r.fetch.calls[0].init.headers.Authorization, `Bearer ${SECRET_KEY}`);
  assert.deepEqual(beehiivBody('x@example.com', '/', ORIGIN).custom_fields, b.custom_fields);
});
test('AC12 key, salt and email never in logs or responses across every path', async () => {
  const all = [];
  const paths = [
    [env(), OK, {}], [env(), OK, { fetch: mockFetch(() => new Response('', { status: 401 })) }],
    [env({ SIGNUPS: mockD1({ failInsert: true }) }), OK, {}], [env(), { email: 'bad' }, {}], [env(), { ...OK, website: 'x' }, {}],
    [env(), OK, { fetch: mockFetch(() => 'network') }],
  ];
  for (const [e, fl, o] of paths) { const r = await sub(e, fl, o); all.push(r.text, ...r.lines, JSON.stringify([...r.res.headers])); }
  const blob = all.join('\n');
  for (const s of [SECRET_KEY, SALT, 'Kitty@', 'kitty@', '203.0.113.7']) assert.ok(!blob.includes(s), s);
});

// ---------------------------------------------------------------- AC 18 retention (R2: 30 days after the row reached Beehiiv)
const DAY = 86400000;
function seeded() {
  const e = env(); const db = e.SIGNUPS; const iso = (ms) => new Date(ms).toISOString();
  const mk = (email, st, sentMs) => db.rows.push({ id: db.rows.length + 1, email_norm: email, email_raw: email, source: 'awi', page: '/',
    created_at: iso(T0 - 40 * DAY), beehiiv_status: st, beehiiv_sub_id: st === 'sent' ? 'sub' : null, attempts: 1, last_error: null,
    ip_hash: 'h', sent_at: sentMs == null ? null : iso(sentMs), deleted_at: null });
  mk('old-sent@example.com', 'sent', T0 - 31 * DAY);
  mk('edge-sent@example.com', 'sent', T0 - 30 * DAY);           // exactly 30 days: due
  mk('young-sent@example.com', 'sent', T0 - 30 * DAY + 1000);   // 1 s short of 30 days: kept
  mk('new-sent@example.com', 'sent', T0 - 1 * DAY);
  mk('queued@example.com', 'queued', null);
  mk('pending@example.com', 'pending', null);
  mk('failed@example.com', 'failed', null);
  mk('odd-queued@example.com', 'queued', T0 - 90 * DAY);       // not sent, even with an old sent_at: kept
  return e;
}
const left = (e) => e.SIGNUPS.rows.map((r) => r.email_norm).sort();

test('AC18: purge deletes sent rows 30+ days after sent_at, keeps the rest', async () => {
  const e = seeded(); const { out } = await capture(() => purgeSent(e, { now: T0 }));
  assert.equal(out.deleted, 2);
  assert.deepEqual(left(e), ['failed@example.com', 'new-sent@example.com', 'odd-queued@example.com', 'pending@example.com', 'queued@example.com', 'young-sent@example.com']);
});
test('AC18: purge never deletes queued, pending or failed rows, however old', async () => {
  const e = seeded(); await capture(() => purgeSent(e, { now: T0 + 3650 * DAY }));
  assert.deepEqual(left(e), ['failed@example.com', 'odd-queued@example.com', 'pending@example.com', 'queued@example.com']);
});
test('AC18: purge is idempotent', async () => {
  const e = seeded(); await capture(() => purgeSent(e, { now: T0 }));
  const snap = JSON.stringify(e.SIGNUPS.rows);
  const { out } = await capture(() => purgeSent(e, { now: T0 })); assert.equal(out.deleted, 0);
  assert.equal(JSON.stringify(e.SIGNUPS.rows), snap);
});
test('AC18: cutoff is exactly now - 30 days and the log carries no email', async () => {
  const e = seeded(); const { out, lines: logs } = await capture(() => purgeSent(e, { now: T0 }));
  assert.equal(out.cutoff, new Date(T0 - 30 * DAY).toISOString());
  assert.ok(!logs.join('\n').includes('@'));
});
test('AC18: scheduled run purges even with no Beehiiv key (retry skipped)', async () => {
  const e = seeded(); delete e.BEEHIIV_API_KEY; const f = mockFetch();
  const { out } = await capture(() => runScheduled(e, { now: T0, fetch: f }));
  assert.equal(out.retry.skipped, 'no_key'); assert.equal(out.purge.deleted, 2); assert.equal(f.calls.length, 0);
});
test('AC18: a row sent by retry today is kept until day 30, then purged; the export never lists it', async () => {
  const e = env(); await sub(e, { email: 'later@example.com' }, { fetch: mockFetch(() => 'timeout') });
  await capture(() => runScheduled(e, { now: T0, fetch: mockFetch() }));
  assert.equal(e.SIGNUPS.rows[0].beehiiv_status, 'sent');
  await capture(() => purgeSent(e, { now: T0 + 29 * DAY })); assert.equal(e.SIGNUPS.rows.length, 1);
  await capture(() => purgeSent(e, { now: T0 + 30 * DAY })); assert.equal(e.SIGNUPS.rows.length, 0);
});

// ---------------------------------------------------------------- Kitty's mutant gaps (9:48 steering)
for (const [name, v, ok] of [
  ['dotless domain', 'a@localhost', false], ['1-letter TLD', 'a@example.c', false], ['2-letter TLD ok', 'a@example.co', true],
  ['1-letter label ok', 'a@x.example.com', true], ['two @', 'a@b@example.com', false], ['two @, valid first domain', 'a@example.com@example.org', false], ['no @', 'example.com', false],
  ['local 64 ok', `${'a'.repeat(64)}@example.com`, true], ['local 65', `${'a'.repeat(65)}@example.com`, false],
]) test(`AC2 validation: ${name}`, () => { assert.equal(normalizeEmail(v) !== null, ok, v); });

test('rate limit: per-IP window is 10 minutes (6th post in window blocked, next window open)', async () => {
  const e = env(); const base = Date.UTC(2026, 9, 26, 14, 0, 0);
  for (let i = 0; i < 5; i++) assert.notEqual((await sub(e, { email: `rl${i}@example.com` }, { now: base + i * 1000 })).status, 'rate_limited');
  assert.equal((await sub(e, { email: 'rl5@example.com' }, { now: base + 9 * 60_000 + 59_000 })).status, 'rate_limited');
  assert.notEqual((await sub(e, { email: 'rl6@example.com' }, { now: base + 10 * 60_000 })).status, 'rate_limited');
  assert.equal(CFG.RATE_LIMIT.perIp.windowSeconds, 600);
});

test('Beehiiv accepted but the status update fails -> 500, not success', async () => {
  const e = env({ SIGNUPS: mockD1({ failMark: true }) });
  const r = await sub(e, OK);
  assert.equal(r.res.status, 500); assert.equal(r.status, 'error'); assert.equal(r.fetch.calls.length, 1);
});

for (const [p, want] of [['/newsletter/', '/newsletter/'], ['javascript:alert(1)', '/'], ['https://evil.example.com/x', '/'], ['//evil.example.com', '/'],
  ['/a?email=a@example.com', '/'], ['/<script>', '/'], [`/${'a'.repeat(101)}`, '/'], [42, '/']]) {
  test(`page field sanitized: ${String(p).slice(0, 30)}`, async () => {
    const e = env(); const r = await sub(e, { email: 'page@example.com', page: p });
    assert.equal(e.SIGNUPS.rows[0].page, want);
    assert.equal(r.fetch.calls[0].body.referring_site, `${ORIGIN}${want}`);
  });
}

for (const hp of [' ', '\t', ' x ']) test(`honeypot with whitespace ${JSON.stringify(hp)} counts as a bot`, async () => {
  const e = env(); const r = await sub(e, { email: 'hp@example.com', website: hp });
  assert.equal(r.status, CFG.SUCCESS_STATUS); assert.equal(e.SIGNUPS.rows.length, 0); assert.equal(r.fetch.calls.length, 0);
});
