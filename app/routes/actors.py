import secrets
import time
import uuid

from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel, Field

from app.db import connect

router = APIRouter(prefix="/api")

COOKIE_NAME = "puente_token"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365

# Tope de magnitud del servicio completo, no por puente (eso ya lo cubre
# bridge.max_actors). Puente pasa a ser algo que cualquiera puede correr
# publicado en GitHub; sin un techo, un hub queda expuesto a acumular
# actores sin límite. 40 es deliberadamente chico para este snapshot —
# ajustable en el futuro `data/config.json` (punto 3 del roadmap).
MAX_ACTORS_TOTAL = 40


class ActorIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


def now_ms() -> int:
    return int(time.time() * 1000)


def assert_actor_capacity(conn) -> None:
    n = conn.execute("SELECT COUNT(*) AS n FROM actor").fetchone()["n"]
    if n >= MAX_ACTORS_TOTAL:
        raise HTTPException(
            409, f"este servicio ya tiene {MAX_ACTORS_TOTAL} equipos registrados, el máximo del snapshot"
        )


def actor_from_token(token: str | None):
    if not token:
        return None
    with connect() as conn:
        row = conn.execute(
            "SELECT id, name FROM actor WHERE token = ?", (token,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE actor SET last_seen = ? WHERE id = ?", (now_ms(), row["id"])
            )
    return dict(row) if row else None


@router.post("/actor")
def register_actor(data: ActorIn, response: Response):
    actor_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    ts = now_ms()

    with connect() as conn:
        assert_actor_capacity(conn)
        conn.execute(
            "INSERT INTO actor (id, name, token, created_at, last_seen)"
            " VALUES (?, ?, ?, ?, ?)",
            (actor_id, data.name.strip(), token, ts, ts),
        )

    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return {"id": actor_id, "name": data.name.strip()}


@router.get("/actor")
def current_actor(puente_token: str | None = Cookie(default=None)):
    actor = actor_from_token(puente_token)
    if not actor:
        raise HTTPException(status_code=401, detail="sin actor")
    return actor