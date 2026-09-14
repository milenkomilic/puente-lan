import time
import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import connect
from app.routes.actors import actor_from_token

router = APIRouter(prefix="/api/bridges")

MAX_ACTORS = 5


def require_actor(puente_token: str | None = Cookie(default=None)):
    actor = actor_from_token(puente_token)
    if not actor:
        raise HTTPException(status_code=401, detail="sin actor")
    return actor


def now_ms() -> int:
    return int(time.time() * 1000)


def display_name(manual: str | None, members: list[str]) -> str:
    if manual:
        return manual
    if len(members) <= 2:
        return " ↔ ".join(members)
    return f"{members[0]}, {members[1]} +{len(members) - 2}"


class BridgeIn(BaseModel):
    name: str | None = Field(default=None, max_length=60)


@router.post("")
def create_bridge(data: BridgeIn, actor=Depends(require_actor)):
    bridge_id = str(uuid.uuid4())
    ts = now_ms()
    with connect() as conn:
        conn.execute(
            "INSERT INTO bridge (id, manual_name, owner_id, created_at, max_actors)"
            " VALUES (?, ?, ?, ?, ?)",
            (bridge_id, data.name, actor["id"], ts, MAX_ACTORS),
        )
        conn.execute(
            "INSERT INTO bridge_actor (bridge_id, actor_id, role, joined_at)"
            " VALUES (?, ?, 'owner', ?)",
            (bridge_id, actor["id"], ts),
        )
    return {"id": bridge_id, "name": display_name(data.name, [actor["name"]])}


@router.get("")
def list_bridges(actor=Depends(require_actor)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT b.id, b.manual_name, b.owner_id, b.created_at"
            " FROM bridge b"
            " JOIN bridge_actor ba ON ba.bridge_id = b.id"
            " WHERE ba.actor_id = ? AND b.deleted_at IS NULL"
            " ORDER BY b.created_at DESC",
            (actor["id"],),
        ).fetchall()

        out = []
        for r in rows:
            members = [
                m["name"]
                for m in conn.execute(
                    "SELECT a.name FROM actor a"
                    " JOIN bridge_actor ba ON ba.actor_id = a.id"
                    " WHERE ba.bridge_id = ? ORDER BY ba.joined_at",
                    (r["id"],),
                ).fetchall()
            ]
            out.append({
                "id": r["id"],
                "name": display_name(r["manual_name"], members),
                "members": members,
                "is_owner": r["owner_id"] == actor["id"],
            })
    return out


@router.patch("/{bridge_id}")
def rename_bridge(bridge_id: str, data: BridgeIn, actor=Depends(require_actor)):
    with connect() as conn:
        row = conn.execute(
            "SELECT owner_id FROM bridge WHERE id = ?", (bridge_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "puente no existe")
        if row["owner_id"] != actor["id"]:
            raise HTTPException(403, "solo el dueño puede renombrar")
        conn.execute(
            "UPDATE bridge SET manual_name = ? WHERE id = ?", (data.name, bridge_id)
        )
    return {"ok": True}


@router.post("/{bridge_id}/actors/{actor_id}")
def add_actor(bridge_id: str, actor_id: str, actor=Depends(require_actor)):
    with connect() as conn:
        bridge = conn.execute(
            "SELECT owner_id, max_actors FROM bridge WHERE id = ?", (bridge_id,)
        ).fetchone()
        if not bridge:
            raise HTTPException(404, "puente no existe")
        if bridge["owner_id"] != actor["id"]:
            raise HTTPException(403, "solo el dueño puede agregar")

        count = conn.execute(
            "SELECT COUNT(*) AS n FROM bridge_actor WHERE bridge_id = ?", (bridge_id,)
        ).fetchone()["n"]
        if count >= bridge["max_actors"]:
            raise HTTPException(409, f"tope de {bridge['max_actors']} alcanzado")

        conn.execute(
            "INSERT OR IGNORE INTO bridge_actor (bridge_id, actor_id, role, joined_at)"
            " VALUES (?, ?, 'member', ?)",
            (bridge_id, actor_id, now_ms()),
        )
    return {"ok": True}