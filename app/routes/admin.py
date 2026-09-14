import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import gc
from app.db import connect
from app.routes.bridges import require_actor

router = APIRouter(prefix="/api")
TRASH_DAYS = 7


def now_ms() -> int:
    return int(time.time() * 1000)


def load_bridge(conn, bridge_id: str):
    b = conn.execute(
        "SELECT id, manual_name, owner_id, deleted_at FROM bridge WHERE id = ?",
        (bridge_id,)
    ).fetchone()
    if not b:
        raise HTTPException(404, "puente no existe")
    return b


def require_owner(conn, bridge_id: str, actor):
    b = load_bridge(conn, bridge_id)
    if b["owner_id"] != actor["id"]:
        raise HTTPException(403, "solo el dueño")
    return b


def bridge_label(conn, b) -> str:
    if b["manual_name"]:
        return b["manual_name"]
    names = [r["name"] for r in conn.execute(
        "SELECT a.name FROM actor a JOIN bridge_actor ba ON ba.actor_id = a.id"
        " WHERE ba.bridge_id = ? ORDER BY ba.joined_at", (b["id"],))]
    if len(names) <= 2:
        return " ↔ ".join(names) or "(vacío)"
    return f"{names[0]}, {names[1]} +{len(names)-2}"


def notify(conn, actor_ids, kind, bridge_name, by_name):
    ts = now_ms()
    for aid in actor_ids:
        conn.execute(
            "INSERT INTO notice (actor_id, created_at, kind, bridge_name, by_name)"
            " VALUES (?, ?, ?, ?, ?)", (aid, ts, kind, bridge_name, by_name))


# ── Panel ──────────────────────────────────────────────

@router.get("/bridges/{bridge_id}/panel")
def panel(bridge_id: str, actor=Depends(require_actor)):
    with connect() as conn:
        b = load_bridge(conn, bridge_id)
        miembros = [dict(r) for r in conn.execute(
            "SELECT a.id, a.name, ba.role, ba.joined_at FROM bridge_actor ba"
            " JOIN actor a ON a.id = ba.actor_id"
            " WHERE ba.bridge_id = ? ORDER BY ba.joined_at", (bridge_id,))]
        if not any(m["id"] == actor["id"] for m in miembros):
            raise HTTPException(403, "no eres miembro")

        dentro = {m["id"] for m in miembros}
        disponibles = [dict(r) for r in conn.execute(
            "SELECT id, name FROM actor ORDER BY name")
            if r["id"] not in dentro]

        uso = conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(bl.size),0) bytes FROM message m"
            " LEFT JOIN blob bl ON bl.hash = m.blob_hash"
            " WHERE m.bridge_id = ?", (bridge_id,)).fetchone()

        return {
            "id": b["id"], "name": bridge_label(conn, b),
            "manual_name": b["manual_name"],
            "is_owner": b["owner_id"] == actor["id"],
            "owner_id": b["owner_id"],
            "members": miembros, "available": disponibles,
            "messages": uso["n"], "bytes": uso["bytes"],
        }


# ── Miembros ───────────────────────────────────────────

@router.delete("/bridges/{bridge_id}/members/{actor_id}")
def remove_member(bridge_id: str, actor_id: str, actor=Depends(require_actor)):
    with connect() as conn:
        b = load_bridge(conn, bridge_id)
        propio = actor_id == actor["id"]

        if not propio and b["owner_id"] != actor["id"]:
            raise HTTPException(403, "solo el dueño puede expulsar")
        if actor_id == b["owner_id"]:
            raise HTTPException(409,
                "el dueño no puede salir: transfiere la propiedad o elimina el puente")

        label = bridge_label(conn, b)
        conn.execute("DELETE FROM bridge_actor WHERE bridge_id = ? AND actor_id = ?",
                     (bridge_id, actor_id))
        if not propio:
            notify(conn, [actor_id], "removed", label, actor["name"])
    return {"ok": True}


class TransferIn(BaseModel):
    actor_id: str


@router.post("/bridges/{bridge_id}/transfer")
def transfer(bridge_id: str, data: TransferIn, actor=Depends(require_actor)):
    with connect() as conn:
        b = require_owner(conn, bridge_id, actor)
        es_miembro = conn.execute(
            "SELECT 1 FROM bridge_actor WHERE bridge_id = ? AND actor_id = ?",
            (bridge_id, data.actor_id)).fetchone()
        if not es_miembro:
            raise HTTPException(409, "el destinatario debe ser miembro")

        label = bridge_label(conn, b)
        conn.execute("UPDATE bridge SET owner_id = ? WHERE id = ?",
                     (data.actor_id, bridge_id))
        conn.execute("UPDATE bridge_actor SET role='owner'"
                     " WHERE bridge_id=? AND actor_id=?", (bridge_id, data.actor_id))
        conn.execute("UPDATE bridge_actor SET role='member'"
                     " WHERE bridge_id=? AND actor_id=?", (bridge_id, actor["id"]))
        notify(conn, [data.actor_id], "ownership", label, actor["name"])
    return {"ok": True}


# ── Papelera ───────────────────────────────────────────

@router.delete("/bridges/{bridge_id}")
def to_trash(bridge_id: str, actor=Depends(require_actor)):
    with connect() as conn:
        b = require_owner(conn, bridge_id, actor)
        if b["deleted_at"]:
            raise HTTPException(409, "ya está en la papelera")
        label = bridge_label(conn, b)
        otros = [r["actor_id"] for r in conn.execute(
            "SELECT actor_id FROM bridge_actor WHERE bridge_id = ? AND actor_id != ?",
            (bridge_id, actor["id"]))]
        conn.execute("UPDATE bridge SET deleted_at = ? WHERE id = ?",
                     (now_ms(), bridge_id))
        notify(conn, otros, "bridge_deleted", label, actor["name"])
    return {"ok": True, "trash_days": TRASH_DAYS}


@router.get("/trash")
def list_trash(actor=Depends(require_actor)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT b.id, b.manual_name, b.deleted_at FROM bridge b"
            " WHERE b.owner_id = ? AND b.deleted_at IS NOT NULL"
            " ORDER BY b.deleted_at DESC", (actor["id"],)).fetchall()
        return [{
            "id": r["id"],
            "name": r["manual_name"] or "(sin nombre)",
            "deleted_at": r["deleted_at"],
            "purge_at": r["deleted_at"] + TRASH_DAYS * 86400000,
        } for r in rows]


@router.post("/trash/{bridge_id}/restore")
def restore(bridge_id: str, actor=Depends(require_actor)):
    with connect() as conn:
        require_owner(conn, bridge_id, actor)
        conn.execute("UPDATE bridge SET deleted_at = NULL WHERE id = ?", (bridge_id,))
    return {"ok": True}


@router.delete("/trash/{bridge_id}")
def purge(bridge_id: str, actor=Depends(require_actor)):
    with connect() as conn:
        b = require_owner(conn, bridge_id, actor)
        if not b["deleted_at"]:
            raise HTTPException(409, "primero muévelo a la papelera")
        conn.execute("DELETE FROM message WHERE bridge_id = ?", (bridge_id,))
        conn.execute("DELETE FROM bridge_actor WHERE bridge_id = ?", (bridge_id,))
        conn.execute("DELETE FROM bridge WHERE id = ?", (bridge_id,))

    limpieza = gc.collect()
    return {"ok": True, **limpieza}


# ── Avisos ─────────────────────────────────────────────

@router.get("/notices")
def notices(actor=Depends(require_actor)):
    with connect() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, kind, bridge_name, by_name, created_at FROM notice"
            " WHERE actor_id = ? AND seen = 0 ORDER BY id", (actor["id"],))]
        if rows:
            conn.execute("UPDATE notice SET seen = 1 WHERE actor_id = ? AND seen = 0",
                         (actor["id"],))
    textos = {
        "bridge_deleted": "eliminó el puente",
        "removed": "te quitó del puente",
        "ownership": "te transfirió el puente",
    }
    for r in rows:
        r["text"] = f'{r["by_name"]} {textos[r["kind"]]} «{r["bridge_name"]}»'
    return rows


# ── Mantenimiento ──────────────────────────────────────

@router.get("/maintenance")
def maintenance(actor=Depends(require_actor)):
    with connect() as conn:
        t = conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(size),0) b FROM blob").fetchone()
        h = conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(bl.size),0) b FROM blob bl"
            " LEFT JOIN message m ON m.blob_hash = bl.hash"
            " WHERE m.id IS NULL").fetchone()
    return {
        "blobs_total": t["n"], "bytes_total": t["b"],
        "blobs_huerfanos": h["n"], "bytes_recuperables": h["b"],
        "actores_huerfanos": gc.actores_huerfanos(),
    }


@router.post("/maintenance/clean")
def clean(actor=Depends(require_actor)):
    r = gc.collect()
    r["temporales"] = gc.limpiar_temporales()
    return r


@router.delete("/actors/{actor_id}")
def drop_actor(actor_id: str, actor=Depends(require_actor)):
    if actor_id == actor["id"]:
        raise HTTPException(409, "no puedes borrarte a ti mismo")
    if actor_id not in {a["id"] for a in gc.actores_huerfanos()}:
        raise HTTPException(409, "el actor tiene puentes o mensajes")
    with connect() as conn:
        conn.execute("DELETE FROM actor WHERE id = ?", (actor_id,))
    return {"ok": True}