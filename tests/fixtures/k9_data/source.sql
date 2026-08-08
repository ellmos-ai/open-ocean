CREATE TABLE items (
    id TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE secrets (
    id TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO items VALUES ('shared', 'source-newer', '2026-08-08T08:00:00Z');
INSERT INTO items VALUES ('source-only', 'source-value', '2026-08-08T08:01:00Z');
INSERT INTO secrets VALUES ('placeholder', 'synthetic-secret-placeholder', '2026-08-08T08:00:00Z');
