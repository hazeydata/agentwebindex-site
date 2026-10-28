// The two wrangler config templates agree with the code: every binding and secret the code reads is declared (bindings) or named
// (secrets comment), the Worker is cron-only, ids are placeholders and no secret value is in either file. No toml parser: line regexes.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
const R = new URL('../../', import.meta.url).pathname;
const read = (p) => readFileSync(join(R, p), 'utf8');
const PAGES = read('wrangler.pages.toml'), WORKER = read('workers/wrangler.signup-retry.toml');
const kv = (src, key) => [...src.matchAll(new RegExp(`^${key}\\s*=\\s*(.+?)\\s*(#.*)?$`, 'gm'))].map((m) => m[1]);
const secrets = (src) => (/^# secrets = (.+)$/m.exec(src)?.[1] || '').split(',').map((s) => s.trim()).filter(Boolean);
function envReads(dir) {
  const out = new Set();
  const walk = (d) => { for (const f of readdirSync(join(R, d))) { const p = join(d, f);
    if (statSync(join(R, p)).isDirectory()) walk(p); else if (p.endsWith('.js')) for (const m of read(p).matchAll(/env\.([A-Z][A-Z0-9_]+)/g)) out.add(m[1]); } };
  for (const x of [].concat(dir)) walk(x);
  return out;
}

test('deploy config: Pages template binds SIGNUPS (awi-signups) and SIGNUP_RL, output dir dist, placeholder ids only', () => {
  assert.deepEqual(kv(PAGES, 'name'), ['"agentwebindex"']);
  assert.deepEqual(kv(PAGES, 'pages_build_output_dir'), ['"dist"']);
  assert.deepEqual(kv(PAGES, 'binding'), ['"SIGNUPS"', '"SIGNUP_RL"']);
  assert.deepEqual(kv(PAGES, 'database_name'), ['"awi-signups"']);
  for (const id of [...kv(PAGES, 'database_id'), ...kv(PAGES, 'id')]) assert.match(id, /^"<PLACEHOLDER: [^>]+>"$/);
});
test('deploy config: retry Worker is awi-signup-retry, cron */15 only, no workers.dev URL, SIGNUPS on awi-signups', () => {
  assert.deepEqual(kv(WORKER, 'name'), ['"awi-signup-retry"']);
  assert.deepEqual(kv(WORKER, 'main'), ['"signup-retry.js"']);
  assert.deepEqual(kv(WORKER, 'crons'), ['["*/15 * * * *"]']);
  assert.deepEqual(kv(WORKER, 'workers_dev'), ['false']);
  assert.deepEqual(kv(WORKER, 'preview_urls'), ['false']);
  assert.deepEqual(kv(WORKER, 'binding'), ['"SIGNUPS"']);
  assert.deepEqual(kv(WORKER, 'database_name'), kv(PAGES, 'database_name'));
  for (const id of kv(WORKER, 'database_id')) assert.match(id, /^"<PLACEHOLDER: [^>]+>"$/);
  assert.ok(!/^\s*\[\[?routes|^\s*route\s*=/m.test(WORKER), 'no HTTP route');
});
test('deploy config: every env name the code reads is a declared binding or a named secret, and nothing extra', () => {
  const pagesNeeds = envReads(['functions', 'signup']);
  const pagesHas = new Set([...kv(PAGES, 'binding').map((b) => b.slice(1, -1)), ...secrets(PAGES)]);
  assert.deepEqual([...pagesNeeds].sort(), [...pagesHas].sort());
  const workerSrc = read('workers/signup-retry.js');
  assert.match(workerSrc, /retryPending, purgeSent/);
  const fn = (name) => { const s = read('signup/core.js'); const i = s.indexOf(`export async function ${name}(`); return s.slice(i, s.indexOf('\n}\n', i)); };
  const workerNeeds = new Set([...(fn('retryPending') + fn('purgeSent') + fn('sendToBeehiiv')).matchAll(/env\.([A-Z][A-Z0-9_]+)/g)].map((m) => m[1]));
  const workerHas = new Set([...kv(WORKER, 'binding').map((b) => b.slice(1, -1)), ...secrets(WORKER)]);
  assert.deepEqual([...workerNeeds].sort(), [...workerHas].sort());
});
test('deploy config: no secret value in either template', () => {
  for (const src of [PAGES, WORKER]) {
    assert.ok(!/^\s*\[vars\]/m.test(src), 'no [vars] block');
    for (const name of ['BEEHIIV_API_KEY', 'BEEHIIV_PUB_ID', 'IP_SALT', 'EXPORT_TOKEN']) assert.ok(!new RegExp(`^\\s*${name}\\s*=`, 'm').test(src), name);
    assert.ok(!/pub_[0-9a-f]{8}-/.test(src));
  }
});
