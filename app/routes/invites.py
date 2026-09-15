import io
import secrets
import time
import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel, Field

from app.db import connect
from app.routes.actors import (
    COOKIE_NAME, COOKIE_MAX_AGE, actor_from_token, assert_actor_capacity,
)
from app.routes.bridges import display_name, require_actor

router = APIRouter(prefix="/api")

# Puntos 1 y 2 del roadmap, más amistades entre cuentas, comparten
# mecanismo: un token de un solo uso, con vencimiento, limitado a lo que
# dice `kind`. Ver docs/migracion-003.sql y 004, y ADR-07 en el diseño
# técnico.
JOIN_TTL_MS = 15 * 60 * 1000
RECLAIM_TTL_MS = 15 * 60 * 1000
FRIEND_TTL_MS = 7 * 24 * 60 * 60 * 1000   # el enlace tarda más en compartirse
FRIEND_REQUEST_TTL_MS = 7 * 24 * 60 * 60 * 1000  # ventana para responder, aparte


def now_ms() -> int:
    return int(time.time() * 1000)


def new_token() -> str:
    return secrets.token_urlsafe(24)


def load_valid_invite(conn, token: str):
    inv = conn.execute("SELECT * FROM invite WHERE token = ?", (token,)).fetchone()
    if not inv:
        raise HTTPException(404, "invitación no existe")
    if inv["used_at"] is not None:
        raise HTTPException(410, "invitación ya usada")
    if inv["expires_at"] < now_ms():
        raise HTTPException(410, "invitación vencida")
    return inv


# ── crear ──────────────────────────────────────────────

@router.post("/bridges/{bridge_id}/invites")
def create_join_invite(bridge_id: str, actor=Depends(require_actor)):
    with connect() as conn:
        b = conn.execute(
            "SELECT owner_id, max_actors FROM bridge"
            " WHERE id = ? AND deleted_at IS NULL", (bridge_id,)
        ).fetchone()
        if not b:
            raise HTTPException(404, "puente no existe")
        if b["owner_id"] != actor["id"]:
            raise HTTPException(403, "solo el dueño puede invitar")

        count = conn.execute(
            "SELECT COUNT(*) AS n FROM bridge_actor WHERE bridge_id = ?", (bridge_id,)
        ).fetchone()["n"]
        if count >= b["max_actors"]:
            raise HTTPException(409, f"tope de {b['max_actors']} alcanzado")

        token = new_token()
        ts = now_ms()
        conn.execute(
            "INSERT INTO invite (token, kind, bridge_id, created_by, created_at, expires_at)"
            " VALUES (?, 'join', ?, ?, ?, ?)",
            (token, bridge_id, actor["id"], ts, ts + JOIN_TTL_MS),
        )
    return {"token": token, "kind": "join", "expires_at": ts + JOIN_TTL_MS, "path": f"/i/{token}"}


@router.post("/actor/reclaim-invite")
def create_reclaim_invite(actor=Depends(require_actor)):
    token = new_token()
    ts = now_ms()
    with connect() as conn:
        conn.execute(
            "INSERT INTO invite (token, kind, actor_id, created_by, created_at, expires_at)"
            " VALUES (?, 'reclaim', ?, ?, ?, ?)",
            (token, actor["id"], actor["id"], ts, ts + RECLAIM_TTL_MS),
        )
    return {"token": token, "kind": "reclaim", "expires_at": ts + RECLAIM_TTL_MS, "path": f"/i/{token}"}


@router.post("/actor/friend-invite")
def create_friend_invite(actor=Depends(require_actor)):
    token = new_token()
    ts = now_ms()
    with connect() as conn:
        conn.execute(
            "INSERT INTO invite (token, kind, actor_id, created_by, created_at, expires_at)"
            " VALUES (?, 'friend', ?, ?, ?, ?)",
            (token, actor["id"], actor["id"], ts, ts + FRIEND_TTL_MS),
        )
    return {"token": token, "kind": "friend", "expires_at": ts + FRIEND_TTL_MS, "path": f"/i/{token}"}


# ── consultar y canjear ────────────────────────────────

@router.get("/invites/{token}")
def invite_info(token: str):
    with connect() as conn:
        inv = load_valid_invite(conn, token)
        out = {"kind": inv["kind"], "expires_at": inv["expires_at"]}
        if inv["kind"] == "join":
            b = conn.execute(
                "SELECT manual_name, deleted_at FROM bridge WHERE id = ?", (inv["bridge_id"],)
            ).fetchone()
            if not b or b["deleted_at"]:
                raise HTTPException(404, "el puente ya no existe")
            names = [r["name"] for r in conn.execute(
                "SELECT a.name FROM actor a JOIN bridge_actor ba ON ba.actor_id = a.id"
                " WHERE ba.bridge_id = ? ORDER BY ba.joined_at", (inv["bridge_id"],))]
            out["bridge_name"] = display_name(b["manual_name"], names)
        elif inv["kind"] == "friend":
            requester = conn.execute(
                "SELECT name FROM actor WHERE id = ?", (inv["actor_id"],)
            ).fetchone()
            if not requester:
                raise HTTPException(404, "el equipo que invitó ya no existe")
            out["from_name"] = requester["name"]
        return out


class RedeemIn(BaseModel):
    name: str | None = Field(default=None, max_length=40)


@router.post("/invites/{token}/redeem")
def redeem(token: str, data: RedeemIn, response: Response,
          puente_token: str | None = Cookie(default=None)):
    with connect() as conn:
        inv = load_valid_invite(conn, token)
        ts = now_ms()

        if inv["kind"] == "reclaim":
            row = conn.execute(
                "SELECT id, name FROM actor WHERE id = ?", (inv["actor_id"],)
            ).fetchone()
            if not row:
                raise HTTPException(404, "el equipo ya no existe")
            # Rotar el token en vez de reenviar el mismo: si alguien más
            # intercepta este enlace, el equipo legítimo también queda
            # invalidado y lo nota de inmediato, en vez de compartir sesión.
            new_tok = secrets.token_urlsafe(32)
            conn.execute(
                "UPDATE actor SET token = ?, last_seen = ? WHERE id = ?",
                (new_tok, ts, row["id"]),
            )
            conn.execute("UPDATE invite SET used_at = ? WHERE token = ?", (ts, token))
            response.set_cookie(COOKIE_NAME, new_tok, max_age=COOKIE_MAX_AGE,
                                 httponly=True, samesite="lax")
            return {"kind": "reclaim", "actor": {"id": row["id"], "name": row["name"]}}

        def resolve_or_create_actor():
            """Actor detrás de la cookie de quien canjea, o uno nuevo si no
            tiene sesión todavía. Compartido entre 'join' y 'friend': ambos
            dejan entrar a un equipo que recién llega."""
            actor = actor_from_token(puente_token)
            if actor:
                return actor
            name = (data.name or "").strip()
            if not name:
                raise HTTPException(422, "falta el nombre del equipo")
            assert_actor_capacity(conn)
            actor_id = str(uuid.uuid4())
            new_tok = secrets.token_urlsafe(32)
            conn.execute(
                "INSERT INTO actor (id, name, token, created_at, last_seen)"
                " VALUES (?, ?, ?, ?, ?)",
                (actor_id, name, new_tok, ts, ts),
            )
            response.set_cookie(COOKIE_NAME, new_tok, max_age=COOKIE_MAX_AGE,
                                 httponly=True, samesite="lax")
            return {"id": actor_id, "name": name}

        if inv["kind"] == "friend":
            requester_id = inv["actor_id"]
            requester = conn.execute(
                "SELECT id, name FROM actor WHERE id = ?", (requester_id,)
            ).fetchone()
            if not requester:
                raise HTTPException(404, "el equipo que invitó ya no existe")

            actor = resolve_or_create_actor()
            if actor["id"] == requester_id:
                raise HTTPException(409, "no puedes agregarte a ti mismo")

            existente = conn.execute(
                "SELECT id, status FROM friendship WHERE"
                " (requester_id = ? AND addressee_id = ?) OR"
                " (requester_id = ? AND addressee_id = ?)",
                (requester_id, actor["id"], actor["id"], requester_id),
            ).fetchone()
            if existente and existente["status"] == "accepted":
                raise HTTPException(409, "ya son amigos")
            if existente and existente["status"] == "pending":
                raise HTTPException(409, "ya existe una solicitud pendiente entre ustedes")

            cur = conn.execute(
                "INSERT INTO friendship (requester_id, addressee_id, status, created_at, expires_at)"
                " VALUES (?, ?, 'pending', ?, ?)",
                (requester_id, actor["id"], ts, ts + FRIEND_REQUEST_TTL_MS),
            )
            conn.execute("UPDATE invite SET used_at = ? WHERE token = ?", (ts, token))
            return {
                "kind": "friend", "actor": actor,
                "request": {"id": cur.lastrowid, "from_name": requester["name"]},
            }

        # kind == "join"
        bridge_id = inv["bridge_id"]
        b = conn.execute(
            "SELECT max_actors, deleted_at FROM bridge WHERE id = ?", (bridge_id,)
        ).fetchone()
        if not b or b["deleted_at"]:
            raise HTTPException(404, "el puente ya no existe")

        actor = resolve_or_create_actor()

        ya_es_miembro = conn.execute(
            "SELECT 1 FROM bridge_actor WHERE bridge_id = ? AND actor_id = ?",
            (bridge_id, actor["id"]),
        ).fetchone()
        if not ya_es_miembro:
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM bridge_actor WHERE bridge_id = ?", (bridge_id,)
            ).fetchone()["n"]
            if count >= b["max_actors"]:
                raise HTTPException(409, f"tope de {b['max_actors']} alcanzado")
            conn.execute(
                "INSERT INTO bridge_actor (bridge_id, actor_id, role, joined_at)"
                " VALUES (?, ?, 'member', ?)",
                (bridge_id, actor["id"], ts),
            )

        conn.execute("UPDATE invite SET used_at = ? WHERE token = ?", (ts, token))
    return {"kind": "join", "bridge_id": bridge_id, "actor": actor}


@router.get("/invites/{token}/qr.svg")
def invite_qr(token: str, request: Request):
    with connect() as conn:
        load_valid_invite(conn, token)

    import qrcode
    from qrcode.image.svg import SvgImage

    base = f"{request.url.scheme}://{request.url.netloc}"
    url = f"{base}/i/{token}"
    img = qrcode.make(url, image_factory=SvgImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return RawResponse(content=buf.getvalue(), media_type="image/svg+xml")
