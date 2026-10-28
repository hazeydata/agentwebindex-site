// AWI-SIGNUP-FORM-001 store-first signup. Adapted from hazeydata/hazeydata.ai functions/api/subscribe.js @ d8ef4bbf
// (HD-SIGNUP-001, PRs #30/#32): same-origin POST, D1 row first, then Beehiiv v2, CSV export as fallback.
// Everything external is injected (env bindings, opts.fetch, opts.now) so tests run on mocks with no network.
import {
  SOURCE, BEEHIIV_SOURCE_TAG, BEEHIIV_SOURCE_FIELD, UTM_SOURCE, DOUBLE_OPT_IN, SEND_WELCOME_EMAIL, ALLOW_UNICODE_LOCAL,
  RATE_LIMIT, BEEHIIV_TIMEOUT_MS, MAX_ATTEMPTS, RETRY_BATCH, RETENTION_DAYS, BOT_CHECK, STATUSES, SUCCESS_STATUS,
} from './config.js';

const HTTP = { pending_confirmation: 200, subscribed: 200, queued: 200, invalid: 400, rate_limited: 429, error: 502 };

// Every SQL statement in one place (checked against migrations/0001_signups.sql by tests/signup/sql_check.py).
export const Q = {
  insert: `INSERT INTO signups (email_norm, email_raw, source, page, created_at, beehiiv_status, attempts, ip_hash)
           VALUES (?, ?, ?, ?, ?, 'pending', 0, ?) ON CONFLICT(email_norm, source) DO NOTHING`,
  byEmail: 'SELECT id, beehiiv_status FROM signups WHERE email_norm = ? AND source = ? AND deleted_at IS NULL',
  markSent: `UPDATE signups SET beehiiv_status = 'sent', beehiiv_sub_id = ?, sent_at = ?, attempts = attempts + 1, last_error = NULL
             WHERE id = ? AND beehiiv_status != 'sent'`,
  markFailed: "UPDATE signups SET beehiiv_status = 'failed', attempts = attempts + 1, last_error = ? WHERE id = ? AND beehiiv_status != 'sent'",
  markQueued: "UPDATE signups SET beehiiv_status = 'queued', last_error = ? WHERE id = ? AND beehiiv_status != 'sent'",
  due: `SELECT id, email_norm, page FROM signups WHERE beehiiv_status IN ('failed', 'pending') AND attempts < ? AND deleted_at IS NULL
        ORDER BY id LIMIT ${RETRY_BATCH}`,
  // AC 18: only rows Beehiiv accepted (status 'sent' with a sent_at) and only once sent_at is at or before the cutoff.
  purge: "DELETE FROM signups WHERE beehiiv_status = 'sent' AND sent_at IS NOT NULL AND sent_at <= ?",
  exportRows: "SELECT email_norm AS email, source, created_at FROM signups WHERE beehiiv_status != 'sent' AND deleted_at IS NULL ORDER BY id",
};

// ---------------------------------------------------------------- validation (AC 2, OQ-5)
export function normalizeEmail(raw) {
  if (typeof raw !== 'string') return null;
  const s = raw.trim();
  if (s.length === 0 || s.length > 254) return null;
  if (/\s/.test(s)) return null;
  const parts = s.split('@');
  if (parts.length !== 2) return null;                       // exactly one @
  const [local, domain] = parts;
  if (!local || !domain || local.length > 64) return null;
  if (!ALLOW_UNICODE_LOCAL && /[^\x21-\x7e]/.test(s)) return null;
  if (/["<>()\[\],;:\\]/.test(local)) return null;
  if (!/^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/.test(domain)) return null; // has a dot
  return `${local}@${domain.toLowerCase()}`;
}

// ---------------------------------------------------------------- logging: fixed enums only, never email, IP or key (AC 12)
const REASONS = /^(timeout|network|no_key|d1_write|d1_missing|no_salt|forbidden_origin|honeypot|unicode|http_[0-9]{3})$/;
export function log(evt, status, reason) {
  if (reason != null && !REASONS.test(reason)) reason = null;
  console.log(JSON.stringify({ evt, status, reason: reason ?? null }));
}

// ---------------------------------------------------------------- ip hash + rate limit (AC 5, AC 6)
async function sha256hex(s) {
  const h = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, '0')).join('');
}
export async function ipHash(ip, salt) { return sha256hex(`${salt}\u0000${ip}`); }

const memory = new Map(); // fallback when no SIGNUP_RL KV binding (local dev, tests)
export function _resetMemoryLimiter() { memory.clear(); }

async function bump(kv, key, ttl) {
  if (kv) {
    try {
      const n = (parseInt(await kv.get(key), 10) || 0) + 1;
      await kv.put(key, String(n), { expirationTtl: ttl + 60 });
      return n;
    } catch { return 0; } // KV error fails open; the D1 unique index still dedupes
  }
  const n = (memory.get(key) || 0) + 1; memory.set(key, n); return n;
}

// Fixed windows: 5 per ip_hash per 10 min, 50 site-wide per minute. Both counters are bumped on every post.
export async function overLimit(env, hash, nowMs) {
  const { perIp, site } = RATE_LIMIT;
  const wi = Math.floor(nowMs / 1000 / perIp.windowSeconds);
  const ws = Math.floor(nowMs / 1000 / site.windowSeconds);
  const a = await bump(env.SIGNUP_RL, `rl:ip:${wi}:${hash.slice(0, 24)}`, perIp.windowSeconds);
  const b = await bump(env.SIGNUP_RL, `rl:site:${ws}`, site.windowSeconds);
  return a > perIp.max || b > site.max;
}

// ---------------------------------------------------------------- bot checks (pluggable; R2: honeypot only)
export const BOT_CHECKS = {
  honeypot: (fields) => String(fields.website || '') === '',   // true = looks human
};
export function botCheck(fields, name = BOT_CHECK) {
  const fn = BOT_CHECKS[name];
  if (!fn) throw new Error('unknown bot check');
  return fn(fields);
}

// ---------------------------------------------------------------- Beehiiv (AC 7, 8, 8a, 11)
export function beehiivBody(email, page, origin) {
  return {
    email,
    reactivate_existing: false,
    send_welcome_email: SEND_WELCOME_EMAIL,
    double_opt_override: DOUBLE_OPT_IN ? 'on' : 'off',
    utm_source: UTM_SOURCE,
    utm_medium: 'signup_form',
    referring_site: `${origin}${page || '/'}`,
    custom_fields: [{ name: BEEHIIV_SOURCE_FIELD, value: BEEHIIV_SOURCE_TAG }],
  };
}

// -> {kind:'sent', subId} | {kind:'queued', code} (no key, 401, 403: CSV path, AC 8a) | {kind:'failed', code}
export async function sendToBeehiiv(env, body, fetchImpl, timeoutMs = BEEHIIV_TIMEOUT_MS) {
  if (!env.BEEHIIV_API_KEY || !env.BEEHIIV_PUB_ID) return { kind: 'queued', code: 'no_key' };
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetchImpl(`https://api.beehiiv.com/v2/publications/${encodeURIComponent(env.BEEHIIV_PUB_ID)}/subscriptions`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.BEEHIIV_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (res.status >= 200 && res.status < 300) {
      let subId = null;
      try { subId = (await res.json())?.data?.id ?? null; } catch { /* body optional */ }
      return { kind: 'sent', subId };
    }
    try { await res.body?.cancel?.(); } catch { /* ignore */ }
    const code = `http_${res.status}`;
    return (res.status === 401 || res.status === 403) ? { kind: 'queued', code } : { kind: 'failed', code };
  } catch {
    return { kind: 'failed', code: ctrl.signal.aborted ? 'timeout' : 'network' };
  } finally {
    clearTimeout(timer);
  }
}

async function record(db, id, out, nowIso) {
  if (out.kind === 'sent') await db.prepare(Q.markSent).bind(out.subId, nowIso, id).run();
  else if (out.kind === 'queued') await db.prepare(Q.markQueued).bind(out.code, id).run();
  else await db.prepare(Q.markFailed).bind(out.code, id).run();
}

// ---------------------------------------------------------------- request handling
function respond(request, status, httpStatus) {
  if (!STATUSES.includes(status)) status = 'error';
  const accept = request.headers.get('Accept') || '';
  const ctype = request.headers.get('Content-Type') || '';
  if (accept.includes('application/json') || ctype.includes('application/json')) {
    return new Response(JSON.stringify({ status }), {
      status: httpStatus ?? HTTP[status], headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
    });
  }
  // No-JS path: 303 to a static per-status thank-you page (works with JS off; see README).
  return new Response(null, { status: 303, headers: { Location: `/newsletter/thanks/${status}/`, 'Cache-Control': 'no-store' } });
}

async function readFields(request) {
  const ctype = request.headers.get('Content-Type') || '';
  try {
    if (ctype.includes('application/json')) { const j = await request.json(); return j && typeof j === 'object' ? j : {}; }
    const f = await request.formData();
    return Object.fromEntries([...f.entries()].map(([k, v]) => [k, String(v)]));
  } catch { return {}; }
}

function cleanPage(p) { return typeof p === 'string' && /^\/(?!\/)[A-Za-z0-9/_-]{0,100}$/.test(p) ? p : '/'; }

export async function handleSubscribe(request, env, opts = {}) {
  const fetchImpl = opts.fetch || fetch;
  const now = opts.now ?? Date.now();
  const timeoutMs = opts.timeoutMs ?? BEEHIIV_TIMEOUT_MS;

  if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405, headers: { Allow: 'POST' } });
  const self = new URL(request.url).origin;
  if (request.headers.get('Origin') !== self) { log('signup', 'forbidden', 'forbidden_origin'); return new Response('Forbidden', { status: 403 }); }
  if (!env.IP_SALT) { log('signup', 'error', 'no_salt'); return respond(request, 'error'); }

  const fields = await readFields(request);
  const hash = await ipHash(request.headers.get('CF-Connecting-IP') || 'none', env.IP_SALT);
  if (await overLimit(env, hash, now)) { log('signup', 'rate_limited'); return respond(request, 'rate_limited'); }
  if (!botCheck(fields)) { log('signup', 'bot', 'honeypot'); return respond(request, SUCCESS_STATUS); } // fake success (AC 4)

  const raw = typeof fields.email === 'string' ? fields.email : '';
  const email = normalizeEmail(raw);
  if (!email) { log('signup', 'invalid', /[^\x00-\x7f]/.test(raw) ? 'unicode' : null); return respond(request, 'invalid'); }

  const db = env.SIGNUPS;
  if (!db) { log('signup', 'error', 'd1_missing'); return respond(request, 'error'); }
  const nowIso = new Date(now).toISOString();
  let row;
  try {
    const r = await db.prepare(Q.insert).bind(email, raw.trim(), SOURCE, cleanPage(fields.page), nowIso, hash).run();
    row = await db.prepare(Q.byEmail).bind(email, SOURCE).first();
    if (!row) throw new Error('row missing');
    if (!((r?.meta?.changes ?? 0) > 0)) {
      // Repeat (AC 3): no second row, no second call; answer as a first signup would have been answered.
      log('signup', 'repeat');
      return respond(request, row.beehiiv_status === 'sent' ? SUCCESS_STATUS : 'queued');
    }
  } catch {
    log('signup', 'error', 'd1_write');
    return respond(request, 'error'); // AC 1: no Beehiiv call without a stored row
  }

  const out = await sendToBeehiiv(env, beehiivBody(email, cleanPage(fields.page), self), fetchImpl, timeoutMs);
  let saved = true;
  try { await record(db, row.id, out, nowIso); } catch {
    saved = false;
    // Beehiiv accepted: try once more to persist the acceptance (sub id + sent), so the retry job won't call Beehiiv again.
    if (out.kind === 'sent') { try { await record(db, row.id, out, nowIso); saved = true; } catch { /* still pending */ } }
  }
  if (!saved) {
    // Both writes failed: the row still says pending and the retry job WILL call Beehiiv again for it (Beehiiv dedupes the
    // subscriber, but a confirmation email may be re-sent). Surface it as a server error (500) so it shows in logs/monitoring.
    log('signup', 'error', 'd1_write');
    if (out.kind === 'sent') return respond(request, 'error', 500);
  }
  log('signup', out.kind, out.code ?? null);
  return respond(request, out.kind === 'sent' ? SUCCESS_STATUS : 'queued');
}

// ---------------------------------------------------------------- retry job (AC 9, AC 8a); scheduled every 15 min
export async function retryPending(env, opts = {}) {
  const fetchImpl = opts.fetch || fetch;
  const nowIso = new Date(opts.now ?? Date.now()).toISOString();
  const origin = opts.origin || 'https://agentwebindex.com';
  const db = env.SIGNUPS;
  if (!db) { log('retry', 'error', 'd1_missing'); return { tried: 0 }; }
  if (!env.BEEHIIV_API_KEY || !env.BEEHIIV_PUB_ID) { log('retry', 'skipped', 'no_key'); return { tried: 0, skipped: 'no_key' }; }
  const rows = (await db.prepare(Q.due).bind(MAX_ATTEMPTS).all()).results || [];
  const tally = { tried: 0, sent: 0, failed: 0, queued: 0 };
  for (const r of rows) {
    const out = await sendToBeehiiv(env, beehiivBody(r.email_norm, r.page, origin), fetchImpl, opts.timeoutMs);
    tally.tried++; tally[out.kind]++;
    await record(db, r.id, out, nowIso);
    if (out.kind === 'queued') break; // key revoked / plan lapsed: stop calling Beehiiv this run
  }
  log('retry', 'done');
  return tally;
}

// AC 18 retention (R2): hard-delete rows 30 days after they reached Beehiiv. Idempotent: a second run deletes nothing
// more; never touches queued, pending or failed rows (they are the CSV fallback). Called by the scheduled Worker.
export async function purgeSent(env, opts = {}) {
  const db = env.SIGNUPS;
  if (!db) { log('purge', 'error', 'd1_missing'); return { deleted: 0 }; }
  const cutoff = new Date((opts.now ?? Date.now()) - RETENTION_DAYS * 86400000).toISOString();
  const r = await db.prepare(Q.purge).bind(cutoff).run();
  const deleted = r?.meta?.changes ?? 0;
  log('purge', 'done');
  return { deleted, cutoff };
}
