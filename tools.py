import sqlite3

conn = sqlite3.connect("data/bridge.db")
conn.row_factory = sqlite3.Row

print("\n--- ACTORES ---")
for r in conn.execute("SELECT id, name, token FROM actor"):
    print(f"{r['name']:<10} id={r['id']}")
    print(f"{'':<10} token={r['token']}\n")

print("--- PUENTES ---")
for r in conn.execute("SELECT id, manual_name, owner_id FROM bridge"):
    print(f"{r['manual_name'] or '(auto)':<12} id={r['id']}")

print("\n--- MIEMBROS ---")
for r in conn.execute(
    "SELECT b.id AS bid, b.manual_name, a.name FROM bridge_actor ba"
    " JOIN bridge b ON b.id = ba.bridge_id"
    " JOIN actor a ON a.id = ba.actor_id"
):
    print(f"{r['manual_name'] or '(auto)':<12} → {r['name']}")