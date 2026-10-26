// Mocks for the signup tests: an in-memory D1 that implements exactly the statements in Q (unknown SQL throws),
// a KV, a recording fetch, and a log capture. No network.
import { Q } from '../../signup/core.js';

export function mockD1({ failInsert = false, failMark = false, failMarkTimes = 0 } = {}) {
  const rows = []; let nextId = 1; const calls = [];
  const live = (r) => r.deleted_at == null;
  const exec = (sql, a) => {
    calls.push(sql);
    if (failMark && [Q.markSent, Q.markFailed, Q.markQueued].includes(sql)) throw new Error('D1_ERROR');
    if (failMarkTimes > 0 && [Q.markSent, Q.markFailed, Q.markQueued].includes(sql)) { failMarkTimes--; throw new Error('D1_ERROR'); }
    switch (sql) {
      case Q.insert: {
        if (failInsert) throw new Error('D1_ERROR');
        const [email_norm, email_raw, source, page, created_at, ip_hash] = a;
        if (rows.some((r) => r.email_norm === email_norm && r.source === source)) return { changes: 0 };
        rows.push({ id: nextId++, email_norm, email_raw, source, page, created_at, beehiiv_status: 'pending', beehiiv_sub_id: null,
          attempts: 0, last_error: null, ip_hash, sent_at: null, deleted_at: null });
        return { changes: 1 };
      }
      case Q.byEmail: return rows.find((r) => r.email_norm === a[0] && r.source === a[1] && live(r)) || null;
      case Q.markSent: { const r = rows.find((x) => x.id === a[2] && x.beehiiv_status !== 'sent'); if (r) Object.assign(r, { beehiiv_status: 'sent', beehiiv_sub_id: a[0], sent_at: a[1], attempts: r.attempts + 1, last_error: null }); return { changes: r ? 1 : 0 }; }
      case Q.markFailed: { const r = rows.find((x) => x.id === a[1] && x.beehiiv_status !== 'sent'); if (r) Object.assign(r, { beehiiv_status: 'failed', attempts: r.attempts + 1, last_error: a[0] }); return { changes: r ? 1 : 0 }; }
      case Q.markQueued: { const r = rows.find((x) => x.id === a[1] && x.beehiiv_status !== 'sent'); if (r) Object.assign(r, { beehiiv_status: 'queued', last_error: a[0] }); return { changes: r ? 1 : 0 }; }
      case Q.due: return rows.filter((r) => ['failed', 'pending'].includes(r.beehiiv_status) && r.attempts < a[0] && live(r)).slice(0, 100).map((r) => ({ ...r }));
      case Q.purge: {
        const before = rows.length;
        for (let i = rows.length - 1; i >= 0; i--) { const r = rows[i]; if (r.beehiiv_status === 'sent' && r.sent_at != null && r.sent_at <= a[0]) rows.splice(i, 1); }
        return { changes: before - rows.length };
      }
      case Q.exportRows: return rows.filter((r) => r.beehiiv_status !== 'sent' && live(r)).map((r) => ({ email: r.email_norm, source: r.source, created_at: r.created_at }));
      default: throw new Error(`unexpected SQL: ${sql}`);
    }
  };
  const db = {
    rows, calls,
    prepare(sql) {
      let args = [];
      const st = {
        bind(...x) { args = x; return st; },
        async run() { return { meta: exec(sql, args) }; },
        async first() { return exec(sql, args); },
        async all() { return { results: exec(sql, args) }; },
      };
      return st;
    },
  };
  return db;
}

export function mockKV() {
  const m = new Map();
  return { m, async get(k) { return m.get(k) ?? null; }, async put(k, v) { m.set(k, v); } };
}

// responder: (callIndex, init) => Response | 'timeout' | 'network'
export function mockFetch(responder = () => new Response(JSON.stringify({ data: { id: 'sub_123' } }), { status: 201 })) {
  const calls = [];
  const f = async (url, init) => {
    calls.push({ url, init, body: JSON.parse(init.body) });
    const r = responder(calls.length - 1, init);
    if (r === 'network') throw new TypeError('fetch failed');
    if (r === 'timeout') {
      return new Promise((_, rej) => init.signal.addEventListener('abort', () => rej(new DOMException('aborted', 'AbortError'))));
    }
    return r;
  };
  f.calls = calls;
  return f;
}

export const SECRET_KEY = 'fake-TEST-beehiiv-key';
export const SALT = 'fake-TEST-salt';
export const ORIGIN = 'https://agentwebindex.com';
export function env(over = {}) {
  return { SIGNUPS: mockD1(), SIGNUP_RL: mockKV(), BEEHIIV_API_KEY: SECRET_KEY, BEEHIIV_PUB_ID: 'pub_test', IP_SALT: SALT, EXPORT_TOKEN: 'fake-TEST-export', ...over };
}

export function post(fields, { json = true, ip = '203.0.113.7', origin = ORIGIN, body } = {}) {
  const headers = { 'CF-Connecting-IP': ip };
  if (origin) headers.Origin = origin;
  if (json) { headers.Accept = 'application/json'; headers['Content-Type'] = 'application/json'; }
  else headers['Content-Type'] = 'application/x-www-form-urlencoded';
  return new Request(`${ORIGIN}/api/subscribe`, {
    method: 'POST', headers, body: body ?? (json ? JSON.stringify(fields) : new URLSearchParams(fields).toString()),
  });
}

export async function capture(fn) {
  const lines = []; const orig = console.log;
  console.log = (...a) => lines.push(a.join(' '));
  try { const out = await fn(); return { out, lines }; } finally { console.log = orig; }
}
