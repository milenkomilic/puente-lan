from pathlib import Path

from app.db import connect

BLOBS_DIR = Path(__file__).resolve().parent.parent / "data" / "blobs"


def collect() -> dict:
    """Borra blobs sin referencias. Orden: DB primero, disco después."""
    with connect() as conn:
        huerfanos = [
            (r["hash"], r["size"]) for r in conn.execute(
                "SELECT bl.hash, bl.size FROM blob bl"
                " LEFT JOIN message m ON m.blob_hash = bl.hash"
                " WHERE m.id IS NULL"
            ).fetchall()
        ]

    borrados, bytes_libres = 0, 0
    for digest, size in huerfanos:
        path = BLOBS_DIR / digest
        try:
            if path.exists():
                path.unlink()
            with connect() as conn:
                conn.execute("DELETE FROM blob WHERE hash = ?", (digest,))
            borrados += 1
            bytes_libres += size
        except Exception:
            continue

    return {"blobs_borrados": borrados, "bytes_liberados": bytes_libres}


def limpiar_temporales() -> int:
    """Restos de subidas interrumpidas."""
    n = 0
    if BLOBS_DIR.exists():
        for f in BLOBS_DIR.glob(".tmp-*"):
            try:
                f.unlink(); n += 1
            except Exception:
                pass
    return n


def actores_huerfanos() -> list[dict]:
    """Actores sin puentes. No los borra: solo los lista."""
    with connect() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT a.id, a.name, a.last_seen FROM actor a"
            " LEFT JOIN bridge_actor ba ON ba.actor_id = a.id"
            " LEFT JOIN message m ON m.actor_id = a.id"
            " WHERE ba.actor_id IS NULL AND m.id IS NULL"
        ).fetchall()]