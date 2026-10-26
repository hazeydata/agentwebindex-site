// AWI-SIGNUP-FORM-001: single place for signup limits, statuses and visitor copy (no secrets here).
// Copied and adapted from hazeydata/hazeydata.ai assets/signup/signup-config.js @ d8ef4bbf (HD-SIGNUP-001, PRs #30/#32).
// site.config.json "signup" must carry the same double_opt_in and messages; tests/signup/config.test.mjs fails on drift (AC7).
// Secrets/bindings (names only): BEEHIIV_API_KEY, BEEHIIV_PUB_ID, IP_SALT, EXPORT_TOKEN (Pages secrets); SIGNUPS (D1); SIGNUP_RL (KV, optional).

export const SOURCE = 'awi';                 // stored row source (AC1)
export const BEEHIIV_SOURCE_TAG = 'AWI';     // custom field value sent to Beehiiv (AC11)
export const BEEHIIV_SOURCE_FIELD = 'source';
export const UTM_SOURCE = 'agentwebindex';

// Double opt-in (R2 OQ-6, Fred 8:52: "reply to verify"). The publication setting is off (audit awi-signup-check-001), so every
// API call sends double_opt_override derived from this flag: the confirmation email and the thank-you copy follow the same value.
export const DOUBLE_OPT_IN = true;
// R2: the welcome automation is not switched on by code; Fred approves its copy first (AC 17a).
export const SEND_WELCOME_EMAIL = false;

export const ALLOW_UNICODE_LOCAL = false;    // OQ-5 open, R2 default: ASCII only; an IDN/unicode address is `invalid` and logged
export const RATE_LIMIT = { perIp: { max: 5, windowSeconds: 600 }, site: { max: 50, windowSeconds: 60 } };
export const BEEHIIV_TIMEOUT_MS = 5000;
export const MAX_ATTEMPTS = 5;
// AC 18 (R2): a row is deleted RETENTION_DAYS after it reached Beehiiv (sent_at). queued/pending/failed rows are never deleted.
export const RETENTION_DAYS = 30;

// Bot check (R2 OQ-1: "Honeypot plus rate limit only"). Pluggable: checks live in BOT_CHECKS (signup/core.js); only
// 'honeypot' is registered. Adding another means a new entry there plus a spec ruling (AC 13 allows 0 third-party scripts).
export const BOT_CHECK = 'honeypot';

// 'already_subscribed' is in the spec enum but never sent: a repeat gets the same answer a first signup would (AC 3).
// 'subscribed' is used only if DOUBLE_OPT_IN is false.
export const STATUSES = ['pending_confirmation', 'subscribed', 'queued', 'invalid', 'rate_limited', 'error'];
// The success status after a Beehiiv 2xx depends on the publication's double opt-in setting.
export const SUCCESS_STATUS = DOUBLE_OPT_IN ? 'pending_confirmation' : 'subscribed';

// AC 19 privacy line: Lindsay's copy, verbatim, plus ', when you signed up' because created_at is stored.
export const PRIVACY_LINE = "We keep your email, the page you signed up on, when you signed up, a scrambled version of your IP address and delivery records in our own database, pass your email to Beehiiv, which sends the newsletter, and delete our copy 30 days after it reaches Beehiiv.";

export const MESSAGES = {
  pending_confirmation: 'Check your inbox to confirm your subscription.',
  subscribed: "You're subscribed.",
  queued: "Thanks, you're on the list. We'll send a confirmation email soon.",
  invalid: "That email doesn't look right. Check it and try again.",  // Lindsay, copy/signup-form-copy.md (verbatim)
  rate_limited: 'Too many tries, please wait a few minutes.',
  error: 'Something broke on our end. Try again in a minute, or email fred@hazeydata.ai.',  // Lindsay, copy/signup-form-copy.md (verbatim)
};
