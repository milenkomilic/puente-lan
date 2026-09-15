-- Migración 004: amistades entre actores
--
-- Puente pasa de "mis propios equipos" a un servicio que cualquiera puede
-- correr. Dos actores de dueños distintos ya no comparten identidad ni
-- puente por defecto: para que el dueño de un puente pueda agregar a
-- alguien más sin exponer la lista completa de actores del hub (ver
-- discusión 2026-09-14), hace falta una relación explícita y consentida
-- por ambos lados.
--
-- Esquema clásico de solicitud/respuesta, como cualquier red social:
--   pending  → alguien pidió, falta que el otro responda
--   accepted → ambos confirmaron
-- Rechazar o cancelar borra la fila (no hay "rejected" que conservar: no
-- aporta nada guardarlo, y evita acumular filas muertas para siempre).
-- Una solicitud pendiente vence a los 7 días si nadie responde.

CREATE TABLE friendship (
    id            INTEGER PRIMARY KEY,
    requester_id  TEXT    NOT NULL REFERENCES actor(id) ON DELETE CASCADE,
    addressee_id  TEXT    NOT NULL REFERENCES actor(id) ON DELETE CASCADE,
    status        TEXT    NOT NULL CHECK (status IN ('pending', 'accepted')) DEFAULT 'pending',
    created_at    INTEGER NOT NULL,
    responded_at  INTEGER,
    expires_at    INTEGER,                 -- solo mientras status='pending'; NULL una vez aceptada

    CHECK (requester_id != addressee_id)
);

-- Para listar "mis amigos" y "mis solicitudes" sin escanear la tabla entera.
CREATE INDEX idx_friendship_requester ON friendship(requester_id, status);
CREATE INDEX idx_friendship_addressee ON friendship(addressee_id, status);

-- La unicidad del par (evitar dos solicitudes cruzadas entre los mismos dos
-- actores) se valida en la aplicación antes de insertar: SQLite no puede
-- expresar "único sin importar el orden de las dos columnas" en un índice.

-- ───────────────────────────────────────────────────────────────
-- invite — se le suma el tipo 'friend'
-- ───────────────────────────────────────────────────────────────
-- Mismo mecanismo que 'join' y 'reclaim': un token de un solo uso.
-- 'friend' usa actor_id igual que 'reclaim' (identifica a quien invita;
-- quien canjea queda como el otro lado de la solicitud). Cambiar el CHECK
-- de una tabla existente en SQLite exige recrearla.

ALTER TABLE invite RENAME TO invite_old;

CREATE TABLE invite (
    token       TEXT PRIMARY KEY,
    kind        TEXT    NOT NULL CHECK (kind IN ('join', 'reclaim', 'friend')),
    bridge_id   TEXT    REFERENCES bridge(id) ON DELETE CASCADE,
    actor_id    TEXT    REFERENCES actor(id)  ON DELETE CASCADE,
    created_by  TEXT    NOT NULL REFERENCES actor(id),
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL,
    used_at     INTEGER,

    CHECK (
        (kind = 'join' AND bridge_id IS NOT NULL AND actor_id IS NULL) OR
        (kind IN ('reclaim', 'friend') AND actor_id IS NOT NULL AND bridge_id IS NULL)
    )
);

INSERT INTO invite SELECT * FROM invite_old;
DROP TABLE invite_old;

CREATE INDEX idx_invite_pending ON invite(expires_at) WHERE used_at IS NULL;

PRAGMA user_version = 4;
