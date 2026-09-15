-- Migración 003: invitaciones (alta rápida + recuperación de identidad)
--
-- Una sola tabla cubre los dos mecanismos del punto 1 y 2 del roadmap,
-- porque comparten forma: un token de un solo uso, con vencimiento, que
-- el navegador canjea.
--
--   kind = 'join'    → bridge_id apunta al puente al que se entra.
--                       Canjear agrega (o crea y agrega) un actor.
--   kind = 'reclaim' → actor_id apunta al actor a revincular.
--                       Canjear rota el token de ese actor y lo pone
--                       en la cookie del navegador que canjeó.
--
-- El token de la invitación es un secreto aparte del token de sesión del
-- actor (actor.token): nunca se reutiliza uno como el otro.

CREATE TABLE invite (
    token       TEXT PRIMARY KEY,
    kind        TEXT    NOT NULL CHECK (kind IN ('join', 'reclaim')),
    bridge_id   TEXT    REFERENCES bridge(id) ON DELETE CASCADE,
    actor_id    TEXT    REFERENCES actor(id)  ON DELETE CASCADE,
    created_by  TEXT    NOT NULL REFERENCES actor(id),
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL,
    used_at     INTEGER,                      -- NULL = sin canjear todavía

    CHECK (
        (kind = 'join'    AND bridge_id IS NOT NULL AND actor_id IS NULL) OR
        (kind = 'reclaim' AND actor_id IS NOT NULL AND bridge_id IS NULL)
    )
);

-- Para el barrido futuro de invitaciones vencidas sin usar (v2).
CREATE INDEX idx_invite_pending ON invite(expires_at) WHERE used_at IS NULL;

PRAGMA user_version = 3;
