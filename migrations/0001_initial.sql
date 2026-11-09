BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY, label TEXT NOT NULL, uid TEXT, region TEXT,
  style TEXT CHECK(style IN ('A','B') OR style IS NULL), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
  payload TEXT NOT NULL, sha256 TEXT NOT NULL, observed_at TEXT NOT NULL,
  UNIQUE(id, account_id)
);
CREATE TABLE IF NOT EXISTS field_sources (
  account_id TEXT NOT NULL REFERENCES accounts(id), snapshot_id TEXT NOT NULL,
  entity_id TEXT NOT NULL, field_id TEXT NOT NULL, payload TEXT NOT NULL,
  PRIMARY KEY(account_id, snapshot_id, entity_id, field_id),
  FOREIGN KEY(snapshot_id, account_id) REFERENCES snapshots(id, account_id)
);
CREATE TABLE IF NOT EXISTS preferences (
  account_id TEXT NOT NULL REFERENCES accounts(id), key TEXT NOT NULL,
  value TEXT NOT NULL, PRIMARY KEY(account_id, key)
);
CREATE TABLE IF NOT EXISTS research (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), title TEXT NOT NULL,
  body_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(id, account_id)
);
CREATE TABLE IF NOT EXISTS conflicts (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), research_id TEXT NOT NULL,
  state TEXT NOT NULL, payload TEXT NOT NULL,
  FOREIGN KEY(research_id, account_id) REFERENCES research(id, account_id)
);
CREATE TABLE IF NOT EXISTS experiments (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id), payload TEXT NOT NULL,
  input_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operations (
  id TEXT PRIMARY KEY, account_id TEXT REFERENCES accounts(id), kind TEXT NOT NULL,
  payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS update_plans (
  id TEXT PRIMARY KEY, payload TEXT NOT NULL, binding_sha256 TEXT NOT NULL,
  state TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS confirmations (
  id TEXT PRIMARY KEY, plan_id TEXT NOT NULL UNIQUE REFERENCES update_plans(id), binding_sha256 TEXT NOT NULL,
  source_kind TEXT NOT NULL, source_ref TEXT NOT NULL, host_permission TEXT NOT NULL,
  decision TEXT NOT NULL, created_at TEXT NOT NULL, consumed_at TEXT
);
PRAGMA user_version = 1;
COMMIT;

