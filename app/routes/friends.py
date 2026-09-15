import time

from fastapi import APIRouter, Depends, HTTPException

from app.db import connect
from app.routes.bridges import require_actor

router = APIRouter(prefix="/api/friends")


def now_ms() -> int:
    return int(time.time() * 1000)


def sweep_expired(conn, ts: int) -> None:
    """Solicitudes pendientes vencidas: se borran solas al leer, igual que
    se deriva cualquier otro estado en este proyecto. No son contenido del
    usuario (mensajes/archivos), así que no hace falta el modo simulación
    reservado para el barrido de la papelera (punto 5 del roadmap)."""
    conn.execute(
        "DELETE FROM friendship WHERE status = 'pending' AND expires_at < ?", (ts,)
    )


@router.get("")
def list_friends(actor=Depends(require_actor)):
    ts = now_ms()
    with connect() as conn:
        sweep_expired(conn, ts)

        amigos = [dict(r) for r in conn.execute(
            "SELECT a.id, a.name, f.responded_at FROM friendship f"
            " JOIN actor a ON a.id = CASE WHEN f.requester_id = ? THEN f.addressee_id"
            "                             ELSE f.requester_id END"
            " WHERE f.status = 'accepted' AND (f.requester_id = ? OR f.addressee_id = ?)"
            " ORDER BY a.name", (actor["id"], actor["id"], actor["id"]))]

        entrantes = [dict(r) for r in conn.execute(
            "SELECT f.id, a.id AS actor_id, a.name, f.created_at, f.expires_at"
            " FROM friendship f JOIN actor a ON a.id = f.requester_id"
            " WHERE f.status = 'pending' AND f.addressee_id = ?"
            " ORDER BY f.created_at DESC", (actor["id"],))]

        salientes = [dict(r) for r in conn.execute(
            "SELECT f.id, a.id AS actor_id, a.name, f.created_at, f.expires_at"
            " FROM friendship f JOIN actor a ON a.id = f.addressee_id"
            " WHERE f.status = 'pending' AND f.requester_id = ?"
            " ORDER BY f.created_at DESC", (actor["id"],))]

    return {"friends": amigos, "incoming": entrantes, "outgoing": salientes}


@router.post("/{friendship_id}/accept")
def accept(friendship_id: int, actor=Depends(require_actor)):
    ts = now_ms()
    with connect() as conn:
        sweep_expired(conn, ts)
        row = conn.execute(
            "SELECT addressee_id, status FROM friendship WHERE id = ?", (friendship_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "la solicitud ya no existe (puede haber vencido)")
        if row["addressee_id"] != actor["id"]:
            raise HTTPException(403, "no es tu solicitud")
        if row["status"] != "pending":
            raise HTTPException(409, "ya fue respondida")
        conn.execute(
            "UPDATE friendship SET status = 'accepted', responded_at = ?, expires_at = NULL"
            " WHERE id = ?", (ts, friendship_id),
        )
    return {"ok": True}


@router.post("/{friendship_id}/reject")
def reject(friendship_id: int, actor=Depends(require_actor)):
    with connect() as conn:
        row = conn.execute(
            "SELECT requester_id, addressee_id, status FROM friendship WHERE id = ?",
            (friendship_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "la solicitud ya no existe")
        if actor["id"] not in (row["requester_id"], row["addressee_id"]):
            raise HTTPException(403, "no es tu solicitud")
        if row["status"] != "pending":
            raise HTTPException(409, "ya fue respondida")
        # Sirve tanto para que el destinatario rechace como para que quien
        # la envió la cancele antes de que respondan.
        conn.execute("DELETE FROM friendship WHERE id = ?", (friendship_id,))
    return {"ok": True}


@router.delete("/{other_actor_id}")
def unfriend(other_actor_id: str, actor=Depends(require_actor)):
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM friendship WHERE status = 'accepted' AND"
            " ((requester_id = ? AND addressee_id = ?) OR"
            "  (requester_id = ? AND addressee_id = ?))",
            (actor["id"], other_actor_id, other_actor_id, actor["id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "no eran amigos")
    return {"ok": True}
