-- Migración 002: papelera y notificaciones

ALTER TABLE bridge ADD COLUMN deleted_at INTEGER;

CREATE INDEX idx_bridge_trash ON bridge(deleted_at)
    WHERE deleted_at IS NOT NULL;

CREATE TABLE notice (
    id          INTEGER PRIMARY KEY,
    actor_id    TEXT    NOT NULL REFERENCES actor(id) ON DELETE CASCADE,
    created_at  INTEGER NOT NULL,
    kind        TEXT    NOT NULL
                CHECK (kind IN ('bridge_deleted', 'removed', 'ownership')),
    bridge_name TEXT    NOT NULL,
    by_name     TEXT    NOT NULL,
    seen        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_notice_pending ON notice(actor_id) WHERE seen = 0;

PRAGMA user_version = 2;