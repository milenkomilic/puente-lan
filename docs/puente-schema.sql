-- Puente — esquema SQLite (prototipo v1)
-- Revisión: 2026-09-13
--
-- Convenciones:
--   · timestamps = INTEGER, epoch en milisegundos (SQLite no tiene tipo fecha)
--   · ids de actor y bridge = TEXT uuid  (se exponen al cliente, no enumerables)
--   · id de message = INTEGER  (orden natural + paginación por cursor)

-- ───────────────────────────────────────────────────────────────
-- PRAGMAs — se aplican en CADA conexión, no una sola vez
-- ───────────────────────────────────────────────────────────────

PRAGMA journal_mode = WAL;      -- lectores concurrentes sin bloquear al escritor.
                                -- Persistente en el archivo; el resto no lo es.
PRAGMA foreign_keys = ON;       -- APAGADO por defecto en SQLite. Si se olvida,
                                -- las FK de abajo son decorativas.
PRAGMA busy_timeout = 5000;     -- con varios equipos escribiendo, sin esto
                                -- aparece "database is locked" de inmediato.
PRAGMA synchronous = NORMAL;    -- seguro con WAL, bastante más rápido que FULL.

PRAGMA user_version = 1;        -- versión de esquema, para migraciones futuras.

-- ───────────────────────────────────────────────────────────────
-- actor — un equipo que usa el servicio
-- ───────────────────────────────────────────────────────────────

CREATE TABLE actor (
    id          TEXT PRIMARY KEY,
    name        TEXT    NOT NULL,
    token       TEXT    NOT NULL UNIQUE,   -- va en la cookie; en v1 ES la
                                           -- credencial. Generar con un CSPRNG,
                                           -- nunca con random() ni con el id.
    created_at  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL
);

CREATE UNIQUE INDEX idx_actor_token ON actor(token);

-- ───────────────────────────────────────────────────────────────
-- bridge — un puente
-- ───────────────────────────────────────────────────────────────

CREATE TABLE bridge (
    id           TEXT PRIMARY KEY,
    manual_name  TEXT,                     -- NULL = el nombre se deriva de los
                                           -- miembros al leer. Ver nota abajo.
    owner_id     TEXT    NOT NULL REFERENCES actor(id),
    created_at   INTEGER NOT NULL,
    max_actors   INTEGER NOT NULL DEFAULT 5
);

-- NOTA: no se guarda el nombre derivado. Si se guardara, agregar un miembro
-- dejaría el nombre obsoleto y habría que recalcularlo en cada alta y baja.
-- Derivarlo al leer no puede quedar desincronizado.

-- ───────────────────────────────────────────────────────────────
-- bridge_actor — membresía
-- ───────────────────────────────────────────────────────────────

CREATE TABLE bridge_actor (
    bridge_id  TEXT    NOT NULL REFERENCES bridge(id) ON DELETE CASCADE,
    actor_id   TEXT    NOT NULL REFERENCES actor(id)  ON DELETE CASCADE,
    role       TEXT    NOT NULL DEFAULT 'member'
               CHECK (role IN ('owner', 'member', 'guest')),
    joined_at  INTEGER NOT NULL,
    PRIMARY KEY (bridge_id, actor_id)
);

CREATE INDEX idx_bridge_actor_actor ON bridge_actor(actor_id);  -- "mis puentes"

-- El tope de 5 se valida en la aplicación, no aquí: es configuración (ADR-12),
-- y un CHECK lo dejaría cableado en el esquema.

-- ───────────────────────────────────────────────────────────────
-- blob — contenido físico, único por hash
-- ───────────────────────────────────────────────────────────────

CREATE TABLE blob (
    hash        TEXT PRIMARY KEY,          -- sha256 del contenido
    size        INTEGER NOT NULL,
    created_at  INTEGER NOT NULL
);

-- NOTA 1 — el nombre del archivo NO vive aquí.
-- El mismo contenido puede subirse como "informe.pdf" y como "informe_v2.pdf".
-- El nombre es del mensaje, no del contenido. Ponerlo en blob rompe el
-- deduplicado o pierde el nombre de uno de los dos envíos.
--
-- NOTA 2 — no hay columna refcount.
-- Un contador almacenado se desincroniza ante cualquier borrado mal manejado,
-- y el síntoma es pérdida de datos silenciosa. Se deriva con la consulta del
-- final del archivo, que con idx_message_blob es barata.

-- ───────────────────────────────────────────────────────────────
-- message — el timeline
-- ───────────────────────────────────────────────────────────────

CREATE TABLE message (
    id          INTEGER PRIMARY KEY,       -- alias de rowid: orden natural
    bridge_id   TEXT    NOT NULL REFERENCES bridge(id) ON DELETE CASCADE,
    actor_id    TEXT    NOT NULL REFERENCES actor(id),
    created_at  INTEGER NOT NULL,
    kind        TEXT    NOT NULL CHECK (kind IN ('text', 'file')),

    body        TEXT,                      -- texto del mensaje (kind='text')
    blob_hash   TEXT REFERENCES blob(hash),-- contenido      (kind='file')
    filename    TEXT,                      -- nombre con el que se envió
    mime        TEXT,

    pinned      INTEGER NOT NULL DEFAULT 0 CHECK (pinned IN (0, 1)),
    expires_at  INTEGER,                   -- NULL = no vence

    CHECK (
        (kind = 'text' AND body IS NOT NULL AND blob_hash IS NULL) OR
        (kind = 'file' AND blob_hash IS NOT NULL AND filename IS NOT NULL)
    )
);

-- Paginación del timeline: WHERE bridge_id = ? AND id < ? ORDER BY id DESC
-- Por id y no por created_at: dos mensajes pueden compartir milisegundo,
-- y un cursor por tiempo empieza a saltarse o repetir filas cuando eso pasa.
CREATE INDEX idx_message_timeline ON message(bridge_id, id DESC);

-- Para el recolector de blobs huérfanos (v2)
CREATE INDEX idx_message_blob ON message(blob_hash);

-- Para el barrido de expiración (v2). Índice parcial: solo indexa las filas
-- que el barrido puede tocar, así los mensajes con pin no ocupan lugar.
CREATE INDEX idx_message_expiry ON message(expires_at)
    WHERE pinned = 0 AND expires_at IS NOT NULL;

-- ───────────────────────────────────────────────────────────────
-- Consultas de referencia
-- ───────────────────────────────────────────────────────────────

-- Puentes de un actor, con conteo de miembros:
--
--   SELECT b.id, b.manual_name, b.owner_id, COUNT(ba2.actor_id) AS miembros
--   FROM bridge b
--   JOIN bridge_actor ba  ON ba.bridge_id = b.id AND ba.actor_id = :actor
--   JOIN bridge_actor ba2 ON ba2.bridge_id = b.id
--   GROUP BY b.id;

-- Blobs huérfanos, candidatos a borrar (v2):
--
--   SELECT bl.hash, bl.size
--   FROM blob bl
--   LEFT JOIN message m ON m.blob_hash = bl.hash
--   WHERE m.id IS NULL;

-- Mensajes vencidos (v2). Borra la referencia; el blob lo resuelve la de
-- arriba en una pasada aparte:
--
--   DELETE FROM message
--   WHERE pinned = 0 AND expires_at IS NOT NULL AND expires_at < :ahora;

-- ───────────────────────────────────────────────────────────────
-- Orden de borrado — importante
-- ───────────────────────────────────────────────────────────────
-- Siempre: 1) borrar filas de message  2) recién ahí buscar blobs huérfanos
--          3) borrar el archivo del disco  4) borrar la fila de blob
--
-- Borrar el archivo antes que la fila deja una referencia apuntando a un
-- archivo inexistente, que es peor que un blob huérfano: el huérfano solo
-- ocupa espacio, la referencia rota es un error visible para el usuario.
