#!/usr/bin/env python3
"""
reset_fabrica.py — vuelve Puente a cero.

Borra TODO el contenido de data/ (la base SQLite y los blobs) y deja el
hub como recién instalado, con el esquema al día. Es la operación más
destructiva del proyecto: no hay papelera para esto.

Uso:
    python reset_fabrica.py              # solo muestra qué se borraría
    python reset_fabrica.py --force      # borra de verdad (pide confirmación escrita)

Salvaguardas:
  - Sin --force, es de solo lectura: muestra un resumen y no toca nada.
  - Con --force, además de la bandera, pide escribir una frase exacta.
  - Antes de borrar, copia data/ completa a data_backup_<fecha>/ (al lado
    de data/, no dentro, para no perderla junto con ella) — salvo que se
    pase --no-backup.
  - Si detecta el hub corriendo en el puerto configurado, se niega a
    seguir: borrar con el proceso vivo puede dejar el WAL de SQLite a
    medio escribir.
"""
import argparse
import shutil
import socket
import sqlite3
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "bridge.db"
CONFIRM_PHRASE = "BORRAR TODO"
PORT = 8080  # ver docs/puente-diseno-tecnico.md §8; ajusta si tu hub usa otro puerto


def hub_esta_corriendo(port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def resumen() -> dict | None:
    if not DATA_DIR.exists():
        print("No existe data/ todavía: no hay nada que resetear.")
        return None

    info = {"bytes": sum(f.stat().st_size for f in DATA_DIR.rglob("*") if f.is_file())}

    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            for tabla in ("actor", "bridge", "message", "blob", "friendship", "invite"):
                try:
                    info[tabla] = conn.execute(f"SELECT COUNT(*) AS n FROM {tabla}").fetchone()["n"]
                except sqlite3.OperationalError:
                    pass  # tabla de una migración que este hub todavía no aplicó
            conn.close()
        except sqlite3.Error as e:
            print(f"(no se pudo leer bridge.db para el resumen: {e})")
    return info


def mostrar_resumen(info: dict) -> None:
    etiquetas = [
        ("actor", "Equipos (actores)"), ("bridge", "Puentes"),
        ("message", "Mensajes"), ("blob", "Archivos únicos"),
        ("friendship", "Amistades / solicitudes"), ("invite", "Invitaciones"),
    ]
    print("\nEsto es lo que hay hoy en data/:\n")
    print(f"  Tamaño total:            {info['bytes'] / 1024 / 1024:.1f} MB")
    for tabla, etiqueta in etiquetas:
        if tabla in info:
            print(f"  {etiqueta:<24} {info[tabla]}")
    print()


def hacer_backup() -> Path:
    marca = time.strftime("%Y%m%d_%H%M%S")
    destino = BASE_DIR / f"data_backup_{marca}"
    shutil.copytree(DATA_DIR, destino)
    return destino


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Reset de fábrica de Puente: borra toda data/ y la recrea vacía."
    )
    ap.add_argument("--force", action="store_true",
                     help="ejecuta el borrado real (sin esto, solo muestra el resumen)")
    ap.add_argument("--no-backup", action="store_true",
                     help="no copiar data/ antes de borrar (no recomendado)")
    ap.add_argument("--ignorar-servidor", action="store_true",
                     help="continuar aunque el puerto del hub responda (no recomendado)")
    args = ap.parse_args()

    info = resumen()
    if info is None:
        return
    mostrar_resumen(info)

    if not args.force:
        print("Modo de solo lectura. Nada se ha tocado.")
        print("Para borrar de verdad: python reset_fabrica.py --force")
        return

    if hub_esta_corriendo() and not args.ignorar_servidor:
        print(f"El hub parece estar corriendo en el puerto {PORT}.")
        print("Detenlo primero (Ctrl+C en la consola de uvicorn) y vuelve a intentarlo:")
        print("borrar con el proceso vivo puede dejar la base a medio escribir.")
        print("Si estás seguro de que no está corriendo de verdad, repite con --ignorar-servidor.")
        sys.exit(1)

    print("Esta acción es IRREVERSIBLE más allá del respaldo que se hace a continuación.")
    print(f"Para confirmar, escribe exactamente: {CONFIRM_PHRASE}")
    respuesta = input("> ").strip()
    if respuesta != CONFIRM_PHRASE:
        print("No coincide. Cancelado, no se tocó nada.")
        sys.exit(1)

    if not args.no_backup:
        destino = hacer_backup()
        print(f"Respaldo creado en: {destino}")
    else:
        print("Sin respaldo (--no-backup). Sigo de todas formas.")

    shutil.rmtree(DATA_DIR)
    print("data/ borrada.")

    sys.path.insert(0, str(BASE_DIR))
    from app.db import init_db  # noqa: E402  (import tardío: recién aquí hace falta)

    init_db()
    print("Hub reinicializado: data/bridge.db recreada, vacía, con el esquema al día.")
    print("Listo. Ya puedes arrancar el servidor normalmente.")


if __name__ == "__main__":
    main()
