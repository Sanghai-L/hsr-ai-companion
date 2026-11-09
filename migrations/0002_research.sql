BEGIN IMMEDIATE;
CREATE TABLE evidence (
 id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
 claim TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(id, account_id)
);
CREATE INDEX evidence_claim ON evidence(account_id,claim);
CREATE TABLE uid_queries (
 id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
 request_ref TEXT NOT NULL, purpose TEXT NOT NULL, state TEXT NOT NULL,
 payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX uid_queries_account ON uid_queries(account_id,created_at);
CREATE TABLE memory_heads (
 account_id TEXT NOT NULL REFERENCES accounts(id), root_id TEXT NOT NULL,
 current_id TEXT NOT NULL, revision INTEGER NOT NULL,
 PRIMARY KEY(account_id,root_id),
 FOREIGN KEY(root_id,account_id) REFERENCES research(id,account_id),
 FOREIGN KEY(current_id,account_id) REFERENCES research(id,account_id)
);
CREATE TABLE revision_plans (
 id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
 conflict_id TEXT NOT NULL REFERENCES conflicts(id), root_id TEXT NOT NULL,
 expected_id TEXT NOT NULL, payload TEXT NOT NULL, binding_sha256 TEXT NOT NULL,
 state TEXT NOT NULL, confirmation TEXT, result_id TEXT,
 FOREIGN KEY(root_id,account_id) REFERENCES research(id,account_id)
);
PRAGMA user_version = 2;
COMMIT;
