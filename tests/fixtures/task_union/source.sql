-- Synthetic task-union fixture schema and seed rows.
-- Shapes mimic the pinned BACH backlog (9 recorded fields) plus a minimal
-- union event log. All data is synthetic; no live database paths or user
-- identifiers appear here.
CREATE TABLE backlog (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT,
    depends_on TEXT,
    due TEXT,
    history TEXT,
    assigned_to TEXT,
    completion_comment TEXT
);
CREATE TABLE union_events (
    seq INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL,
    kind TEXT NOT NULL
);
INSERT INTO backlog (id, title, status, priority, depends_on, due, history, assigned_to, completion_comment) VALUES
    (1, 'Task Alpha', 'pending', 'normal', '[]', NULL, NULL, NULL, NULL);
INSERT INTO backlog (id, title, status, priority, depends_on, due, history, assigned_to, completion_comment) VALUES
    (2, 'Task Beta', 'in_progress', 'normal', '[]', NULL, '[{"event": "claimed"}]', 'actor-a', NULL);
INSERT INTO backlog (id, title, status, priority, depends_on, due, history, assigned_to, completion_comment) VALUES
    (3, 'Task Gamma', 'done', 'normal', '[]', NULL, '[{"event": "created"}, {"event": "completed"}]', NULL, 'synthetic completion');
INSERT INTO backlog (id, title, status, priority, depends_on, due, history, assigned_to, completion_comment) VALUES
    (4, 'Task Delta', 'blocked', 'normal', '[]', NULL, NULL, NULL, NULL);
INSERT INTO backlog (id, title, status, priority, depends_on, due, history, assigned_to, completion_comment) VALUES
    (5, 'Task Epsilon', 'deferred', 'normal', '[]', NULL, NULL, NULL, NULL);
