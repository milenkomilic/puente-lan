import sqlite3
from pathlib import Path

conn = sqlite3.connect("data/bridge.db")
v = conn.execute("PRAGMA user_version").fetchone()[0]
print(f"versión actual: {v}")

if v < 2:
    conn.executescript(Path("docs/migracion-002.sql").read_text(encoding="utf-8"))
    conn.commit()
    print("migración 002 aplicada")
else:
    print("nada que hacer")
conn.close()