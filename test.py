"""
Pruebas end-to-end de Puente.

Uso:
    pip install requests
    # con el servidor corriendo en otra consola:
    py test_api.py

Crea actores y puentes de prueba con prefijo "_test_" y los limpia al final.
No toca tus datos reales.
"""

import io
import sys
import time

import requests

BASE = "http://127.0.0.1:8080"
PREFIX = "_test_"

ok_count = 0
fail_count = 0
fails: list[str] = []


def check(cond, label):
    global ok_count, fail_count
    if cond:
        ok_count += 1
        print(f"  \033[92mOK\033[0m   {label}")
    else:
        fail_count += 1
        fails.append(label)
        print(f"  \033[91mFAIL\033[0m {label}")


def section(t):
    print(f"\n\033[1m{t}\033[0m")


def actor(name):
    """Sesión nueva registrada como actor."""
    s = requests.Session()
    r = s.post(f"{BASE}/api/actor", json={"name": PREFIX + name})
    r.raise_for_status()
    s.actor_id = r.json()["id"]
    s.actor_name = r.json()["name"]
    return s


def run():
    section("Conectividad")
    try:
        r = requests.get(f"{BASE}/api/limits", timeout=3)
        check(r.status_code == 200, "el servidor responde")
        limit = r.json()["max_bytes"]
    except Exception as e:
        print(f"\n\033[91mNo hay servidor en {BASE}\033[0m ({e})")
        print("Levántalo con: uvicorn app.main:app --host 0.0.0.0 --port 8080")
        sys.exit(1)

    section("Actores")
    ana = actor("ana")
    beto = actor("beto")
    check(ana.actor_id != beto.actor_id, "dos actores tienen ids distintos")
    check(ana.get(f"{BASE}/api/actor").json()["id"] == ana.actor_id,
          "la cookie identifica al actor")
    check(requests.get(f"{BASE}/api/actor").status_code == 401,
          "sin cookie devuelve 401")

    section("Puentes")
    b = ana.post(f"{BASE}/api/bridges", json={"name": PREFIX + "puente"}).json()
    bid = b["id"]
    check(b["name"] == PREFIX + "puente", "puente con nombre manual")

    auto = ana.post(f"{BASE}/api/bridges", json={"name": None}).json()
    check(auto["name"] == ana.actor_name, "nombre derivado de un miembro")

    mine = [x["id"] for x in ana.get(f"{BASE}/api/bridges").json()]
    check(bid in mine, "el dueño ve su puente")
    theirs = [x["id"] for x in beto.get(f"{BASE}/api/bridges").json()]
    check(bid not in theirs, "un ajeno NO ve el puente")

    section("Aislamiento")
    check(beto.get(f"{BASE}/api/bridges/{bid}/messages").status_code == 403,
          "leer mensajes de un puente ajeno da 403")
    check(beto.post(f"{BASE}/api/bridges/{bid}/messages",
                    json={"body": "intruso"}).status_code == 403,
          "escribir en un puente ajeno da 403")
    check(beto.patch(f"{BASE}/api/bridges/{bid}",
                     json={"name": "robado"}).status_code == 403,
          "renombrar sin ser dueño da 403")

    section("Membresía")
    r = ana.post(f"{BASE}/api/bridges/{bid}/actors/{beto.actor_id}")
    check(r.status_code == 200, "el dueño agrega un miembro")
    check(bid in [x["id"] for x in beto.get(f"{BASE}/api/bridges").json()],
          "el nuevo miembro ya ve el puente")
    check(beto.get(f"{BASE}/api/bridges/{bid}/messages").status_code == 200,
          "el miembro ya puede leer")

    panel = ana.get(f"{BASE}/api/bridges/{bid}/panel").json()
    check(len(panel["members"]) == 2, "el panel lista dos miembros")
    check(panel["is_owner"] is True, "el panel marca al dueño")
    roles = {m["id"]: m["role"] for m in panel["members"]}
    check(roles[ana.actor_id] == "owner", "rol owner correcto")

    section("Tope de actores")
    extras = [actor(f"x{i}") for i in range(4)]
    codes = [ana.post(f"{BASE}/api/bridges/{bid}/actors/{e.actor_id}").status_code
             for e in extras]
    check(codes[:3] == [200, 200, 200], "acepta hasta 5 actores")
    check(codes[3] == 409, "el sexto actor es rechazado con 409")

    section("Mensajes")
    m1 = ana.post(f"{BASE}/api/bridges/{bid}/messages",
                  json={"body": "hola"}).json()
    m2 = beto.post(f"{BASE}/api/bridges/{bid}/messages",
                   json={"body": "qué tal"}).json()
    check(m2["id"] > m1["id"], "los ids son crecientes")
    check(m2["actor_name"] == beto.actor_name, "el mensaje trae su autor")

    msgs = ana.get(f"{BASE}/api/bridges/{bid}/messages").json()
    check([x["id"] for x in msgs] == sorted(x["id"] for x in msgs),
          "el listado viene en orden cronológico")

    page = ana.get(f"{BASE}/api/bridges/{bid}/messages",
                   params={"before": m2["id"]}).json()
    check(all(x["id"] < m2["id"] for x in page), "la paginación respeta el cursor")

    check(ana.post(f"{BASE}/api/bridges/{bid}/messages",
                   json={"body": ""}).status_code == 422,
          "mensaje vacío rechazado")

    section("Archivos")
    data = b"contenido de prueba " * 100
    files = {"file": ("prueba.txt", io.BytesIO(data), "text/plain")}
    up = ana.post(f"{BASE}/api/bridges/{bid}/files", files=files).json()
    check(up["kind"] == "file", "la subida crea un mensaje de archivo")
    check(up["size"] == len(data), "el tamaño coincide")
    digest = up["blob_hash"]

    files = {"file": ("otro-nombre.txt", io.BytesIO(data), "text/plain")}
    dup = ana.post(f"{BASE}/api/bridges/{bid}/files", files=files).json()
    check(dup["blob_hash"] == digest, "el mismo contenido deduplica al mismo hash")
    check(dup["id"] != up["id"], "pero genera un mensaje distinto")
    check(dup["filename"] == "otro-nombre.txt", "cada mensaje guarda su nombre")

    d = beto.get(f"{BASE}/api/blob/{digest}")
    check(d.status_code == 200 and d.content == data,
          "un miembro descarga el contenido íntegro")

    otro = actor("fuera")
    check(otro.get(f"{BASE}/api/blob/{digest}").status_code == 404,
          "un no miembro NO descarga aunque conozca el hash")

    section("Papelera")
    check(beto.delete(f"{BASE}/api/bridges/{bid}").status_code == 403,
          "un miembro no puede borrar el puente")
    check(ana.delete(f"{BASE}/api/bridges/{bid}").status_code == 200,
          "el dueño lo manda a la papelera")
    check(bid not in [x["id"] for x in ana.get(f"{BASE}/api/bridges").json()],
          "desaparece de la lista activa")
    check(bid in [x["id"] for x in ana.get(f"{BASE}/api/trash").json()],
          "aparece en la papelera")

    notices = beto.get(f"{BASE}/api/notices").json()
    check(any(n["kind"] == "bridge_deleted" for n in notices),
          "el miembro recibe el aviso")
    check(beto.get(f"{BASE}/api/notices").json() == [],
          "los avisos se marcan como vistos")

    check(ana.post(f"{BASE}/api/trash/{bid}/restore").status_code == 200,
          "se restaura desde la papelera")
    check(len(ana.get(f"{BASE}/api/bridges/{bid}/messages").json()) >= 4,
          "los mensajes sobreviven al viaje")

    section("Transferencia")
    check(ana.post(f"{BASE}/api/bridges/{bid}/transfer",
                   json={"actor_id": otro.actor_id}).status_code == 409,
          "no se transfiere a un no miembro")
    check(ana.post(f"{BASE}/api/bridges/{bid}/transfer",
                   json={"actor_id": beto.actor_id}).status_code == 200,
          "se transfiere a un miembro")
    check(beto.get(f"{BASE}/api/bridges/{bid}/panel").json()["is_owner"] is True,
          "el nuevo dueño manda")
    check(ana.delete(f"{BASE}/api/bridges/{bid}").status_code == 403,
          "el dueño anterior perdió el control")
    beto.post(f"{BASE}/api/bridges/{bid}/transfer", json={"actor_id": ana.actor_id})

    section("Expulsión y salida")
    check(ana.delete(f"{BASE}/api/bridges/{bid}/members/{beto.actor_id}"
                     ).status_code == 200, "el dueño expulsa")
    check(beto.get(f"{BASE}/api/bridges/{bid}/messages").status_code == 403,
          "el expulsado pierde acceso")
    check(any(n["kind"] == "removed" for n in beto.get(f"{BASE}/api/notices").json()),
          "el expulsado recibe el aviso")
    check(len(ana.get(f"{BASE}/api/bridges/{bid}/messages").json()) >= 4,
          "sus mensajes permanecen en el historial")
    check(ana.delete(f"{BASE}/api/bridges/{bid}/members/{ana.actor_id}"
                     ).status_code == 409, "el dueño no puede salirse")

    section("Purgado y recolección")
    check(ana.delete(f"{BASE}/api/trash/{bid}").status_code == 409,
          "no se purga un puente activo")
    ana.delete(f"{BASE}/api/bridges/{bid}")
    res = ana.delete(f"{BASE}/api/trash/{bid}")
    check(res.status_code == 200, "el purgado funciona")
    check(res.json()["blobs_borrados"] >= 1, "el purgado liberó blobs")
    check(ana.get(f"{BASE}/api/blob/{digest}").status_code == 404,
          "el contenido ya no está disponible")
    check(ana.get(f"{BASE}/api/maintenance").json()["blobs_huerfanos"] == 0,
          "no quedan blobs huérfanos")

    section("Firewall")
    st = ana.get(f"{BASE}/api/firewall").json()
    check("backend" in st and "command" in st, "reporta backend y comando")
    check(isinstance(st["action_needed"], bool), "reporta si hace falta actuar")

    section("Limpieza")
    ana.delete(f"{BASE}/api/bridges/{auto['id']}")
    ana.delete(f"{BASE}/api/trash/{auto['id']}")
    huerfanos = ana.get(f"{BASE}/api/maintenance").json()["actores_huerfanos"]
    n = 0
    for h in huerfanos:
        if h["name"].startswith(PREFIX):
            if ana.delete(f"{BASE}/api/actors/{h['id']}").status_code == 200:
                n += 1
    print(f"  actores de prueba eliminados: {n}")
    print("  nota: los actores que dejaron mensajes no se borran (es correcto)")


if __name__ == "__main__":
    t0 = time.time()
    print("\033[1mPuente — pruebas end-to-end\033[0m")
    try:
        run()
    except Exception as e:
        print(f"\n\033[91mLa suite se interrumpió: {type(e).__name__}: {e}\033[0m")
        fail_count += 1

    total = ok_count + fail_count
    dur = time.time() - t0
    print(f"\n{'─' * 50}")
    if fail_count == 0:
        print(f"\033[92m{ok_count}/{total} pruebas OK\033[0m  ({dur:.1f}s)")
    else:
        print(f"\033[91m{fail_count} fallaron\033[0m de {total}  ({dur:.1f}s)")
        for f in fails:
            print(f"  · {f}")
    sys.exit(1 if fail_count else 0)