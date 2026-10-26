// Scheduled Worker for AC 9 (cron */15 * * * *). Pages Functions have no cron, so this small Worker binds the same D1
// (SIGNUPS) and secrets. Not deployed by this PR: chief creates it at deploy (see README "Signup" and workers/wrangler.signup-retry.toml.example).
import { retryPending } from '../signup/core.js';
export default { async scheduled(_event, env, ctx) { ctx.waitUntil(retryPending(env)); } };
