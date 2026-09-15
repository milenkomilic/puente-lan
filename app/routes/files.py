import hashlib
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import CONFIG
from app.db import connect
from app.routes.bridges import require_actor
from app.routes.messages import hub, is_member

router = APIRouter(prefix="/api")

BLOBS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "blobs"
MAX_FILE_MB = CONFIG["max_file_mb"]
MAX_BYTES = MAX_FILE_MB * 1024 * 1024
CHUNK = 1024 * 1024


@router.get("/limits")
def limits():
    return {"max_file_mb": MAX_FILE_MB, "max_bytes": MAX_BYTES}


@router.post("/bridges/{bridge_id}/files")
async def upload(bridge_id: str, file: UploadFile = File(...),
                 actor=Depends(require_actor)):
    with connect() as conn:
        if not is_member(conn, bridge_id, actor["id"]):
            raise HTTPException(403, "no eres miembro")

    BLOBS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = BLOBS_DIR / f".tmp-{actor['id']}-{int(time.time()*1000)}"
    sha = hashlib.sha256()
    size = 0

    try:
        with open(tmp, "wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, f"máximo {MAX_FILE_MB} MB")
                sha.update(chunk)
                out.write(chunk)

        digest = sha.hexdigest()
        final = BLOBS_DIR / digest

        if final.exists():
            tmp.unlink()
        else:
            tmp.rename(final)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    ts = int(time.time() * 1000)
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO blob (hash, size, created_at) VALUES (?, ?, ?)",
            (digest, size, ts),
        )
        cur = conn.execute(
            "INSERT INTO message (bridge_id, actor_id, created_at, kind,"
            " blob_hash, filename, mime) VALUES (?, ?, ?, 'file', ?, ?, ?)",
            (bridge_id, actor["id"], ts, digest, file.filename,
             file.content_type or "application/octet-stream"),
        )
        msg_id = cur.lastrowid

    payload = {
        "id": msg_id, "actor_id": actor["id"], "actor_name": actor["name"],
        "created_at": ts, "kind": "file", "body": None,
        "blob_hash": digest, "filename": file.filename, "size": size, "pinned": 0,
    }
    await hub.broadcast(bridge_id, payload)
    return payload


@router.get("/blob/{digest}")
def download(digest: str, actor=Depends(require_actor)):
    with connect() as conn:
        row = conn.execute(
            "SELECT m.filename, m.mime FROM message m"
            " JOIN bridge_actor ba ON ba.bridge_id = m.bridge_id"
            " WHERE m.blob_hash = ? AND ba.actor_id = ? LIMIT 1",
            (digest, actor["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(404, "no disponible")

    path = BLOBS_DIR / digest
    if not path.exists():
        raise HTTPException(404, "archivo perdido")

    return FileResponse(path, media_type=row["mime"], filename=row["filename"])