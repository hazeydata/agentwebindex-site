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

test("Lindsay's copy is used verbatim for invalid and error (copy/signup-form-copy.md, 10:00)", () => {
  assert.equal(CFG.MESSAGES.invalid, "That email doesn't look right. Check it and try again.");
  assert.equal(CFG.MESSAGES.error, 'Something broke on our end. Try again in a minute, or email fred@hazeydata.ai.');
});

test("AC19 privacy line is Lindsay's copy verbatim (+ 'when you signed up': created_at is stored) and is on the page", () => {
  const L = 'We keep your email, the page you signed up on, when you signed up, a scrambled version of your IP address and delivery records in our own database, pass your email to Beehiiv, which sends the newsletter, and delete our copy 30 days after it reaches Beehiiv.';
  assert.equal(CFG.PRIVACY_LINE, L);
  assert.equal(site.privacy, L);
  const page = readFileSync(new URL('../../dist/newsletter/index.html', import.meta.url), 'utf8');
  assert.ok(page.includes(L.replace(/'/g, '&#x27;')), 'privacy line rendered under the form');
});
