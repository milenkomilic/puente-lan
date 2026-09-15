import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "bridge.db"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "docs" / "puente-schema.sql"


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "blobs").mkdir(exist_ok=True)
    fresh = not DB_PATH.exists()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    if fresh:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    v = conn.execute("PRAGMA user_version").fetchone()[0]
    if v < 2:
        mig = SCHEMA_PATH.parent / "migracion-002.sql"
        conn.executescript(mig.read_text(encoding="utf-8"))
        v = conn.execute("PRAGMA user_version").fetchone()[0]
    if v < 3:
        mig = SCHEMA_PATH.parent / "migracion-003.sql"
        conn.executescript(mig.read_text(encoding="utf-8"))
        v = conn.execute("PRAGMA user_version").fetchone()[0]
    if v < 4:
        mig = SCHEMA_PATH.parent / "migracion-004.sql"
        conn.executescript(mig.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()