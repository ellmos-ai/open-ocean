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

INSERT INTO items VALUES ('shared', 'target-older', '2026-08-07T08:00:00Z');
INSERT INTO items VALUES ('target-only', 'target-value', '2026-08-08T07:59:00Z');
INSERT INTO secrets VALUES ('local-placeholder', 'target-local-placeholder', '2026-08-08T07:00:00Z');
