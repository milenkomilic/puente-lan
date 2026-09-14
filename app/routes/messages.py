import time

from fastapi import APIRouter, Cookie, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.db import connect
from app.routes.actors import actor_from_token
from app.routes.bridges import require_actor

router = APIRouter(prefix="/api/bridges")


def now_ms() -> int:
    return int(time.time() * 1000)


def is_member(conn, bridge_id: str, actor_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM bridge_actor WHERE bridge_id = ? AND actor_id = ?",
        (bridge_id, actor_id),
    ).fetchone() is not None


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class Hub:
    def __init__(self):
        self.rooms: dict[str, list[WebSocket]] = {}

    async def join(self, bridge_id: str, ws: WebSocket):
        await ws.accept()
        self.rooms.setdefault(bridge_id, []).append(ws)

    def leave(self, bridge_id: str, ws: WebSocket):
        if bridge_id in self.rooms:
            self.rooms[bridge_id] = [w for w in self.rooms[bridge_id] if w is not ws]

    async def broadcast(self, bridge_id: str, payload: dict):
        for ws in list(self.rooms.get(bridge_id, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                self.leave(bridge_id, ws)


hub = Hub()


@router.get("/{bridge_id}/messages")
def list_messages(bridge_id: str, before: int | None = None, limit: int = 50,
                  actor=Depends(require_actor)):
    limit = min(limit, 100)
    with connect() as conn:
        if not is_member(conn, bridge_id, actor["id"]):
            raise HTTPException(403, "no eres miembro")
        sql = (
            "SELECT m.id, m.actor_id, a.name AS actor_name, m.created_at,"
            " m.kind, m.body, m.blob_hash, m.filename, m.pinned, bl.size"
            " FROM message m JOIN actor a ON a.id = m.actor_id"
            " LEFT JOIN blob bl ON bl.hash = m.blob_hash"
            " WHERE m.bridge_id = ?"
        )
        params: list = [bridge_id]
        if before:
            sql += " AND m.id < ?"
            params.append(before)
        sql += " ORDER BY m.id DESC LIMIT ?"
        params.append(limit)
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    rows.reverse()
    return rows


@router.post("/{bridge_id}/messages")
async def send_message(bridge_id: str, data: MessageIn, actor=Depends(require_actor)):
    ts = now_ms()
    with connect() as conn:
        if not is_member(conn, bridge_id, actor["id"]):
            raise HTTPException(403, "no eres miembro")
        cur = conn.execute(
            "INSERT INTO message (bridge_id, actor_id, created_at, kind, body)"
            " VALUES (?, ?, ?, 'text', ?)",
            (bridge_id, actor["id"], ts, data.body),
        )
        msg_id = cur.lastrowid

    payload = {
        "id": msg_id, "actor_id": actor["id"], "actor_name": actor["name"],
        "created_at": ts, "kind": "text", "body": data.body,
        "blob_hash": None, "filename": None, "pinned": 0,
    }
    await hub.broadcast(bridge_id, payload)
    return payload


@router.websocket("/{bridge_id}/ws")
async def bridge_ws(websocket: WebSocket, bridge_id: str,
                    puente_token: str | None = Cookie(default=None)):
    actor = actor_from_token(puente_token)
    if not actor:
        await websocket.close(code=4401)
        return
    with connect() as conn:
        if not is_member(conn, bridge_id, actor["id"]):
            await websocket.close(code=4403)
            return

    await hub.join(bridge_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.leave(bridge_id, websocket)