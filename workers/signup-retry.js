// Scheduled Worker for AC 9 retry and AC 18 retention (cron */15 * * * *). Pages Functions have no cron, so this small Worker
// binds the same D1 (SIGNUPS) and secrets. Not deployed by this PR: chief creates it at deploy (see README "Signup" and
// workers/wrangler.signup-retry.toml). Retention runs even when retry is skipped (no key).
import { retryPending, purgeSent } from '../signup/core.js';
export async function runScheduled(env, opts = {}) {
  const retry = await retryPending(env, opts);
  const purge = await purgeSent(env, opts);
  return { retry, purge };
}
export default { async scheduled(_event, env, ctx) { ctx.waitUntil(runScheduled(env)); } };
