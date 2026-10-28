-- AWI-SIGNUP-FORM-001 store-first schema. D1 bound to the AWI Pages project as SIGNUPS (database created by chief at deploy).
-- Idempotent: wrangler d1 execute <awi-db> --remote --file=migrations/0001_signups.sql
CREATE TABLE IF NOT EXISTS signups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email_norm TEXT NOT NULL,              -- trimmed, domain lowercased
  email_raw TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'awi',
  page TEXT,
  created_at TEXT NOT NULL,              -- ISO 8601 UTC
  beehiiv_status TEXT NOT NULL DEFAULT 'pending' CHECK (beehiiv_status IN ('pending', 'sent', 'failed', 'queued')),
  beehiiv_sub_id TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,                       -- fixed codes only: timeout, network, no_key, http_<nnn>  (queued = CSV path, AC 8a)
  ip_hash TEXT,                          -- salted SHA-256 (IP_SALT); the raw IP is never stored
  sent_at TEXT,
  deleted_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS signups_email_source ON signups (email_norm, source);
CREATE INDEX IF NOT EXISTS signups_beehiiv_status ON signups (beehiiv_status);
