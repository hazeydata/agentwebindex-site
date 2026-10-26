// AC7 drift guard: site.config.json "signup" (used by build.py for the page copy) must equal signup/config.js.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as CFG from '../../signup/config.js';

const site = JSON.parse(readFileSync(new URL('../../site.config.json', import.meta.url))).signup;
test('AC7 page copy and double opt-in match the function config', () => {
  assert.equal(site.double_opt_in, CFG.DOUBLE_OPT_IN);
  assert.deepEqual(site.messages, CFG.MESSAGES);
  assert.equal(CFG.SUCCESS_STATUS, CFG.DOUBLE_OPT_IN ? 'pending_confirmation' : 'subscribed');
  assert.equal(CFG.MESSAGES[CFG.SUCCESS_STATUS], CFG.DOUBLE_OPT_IN ? 'Check your inbox to confirm your subscription.' : "You're subscribed.");
});
test('AC7 every status has copy and a thank-you page', () => {
  for (const s of CFG.STATUSES) {
    assert.ok(CFG.MESSAGES[s], s);
    readFileSync(new URL(`../../dist/newsletter/thanks/${s}/index.html`, import.meta.url));
  }
});
