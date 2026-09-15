"""Configuración del hub — vive en data/config.json, la carpeta portátil.

Se lee una sola vez al arrancar el proceso (igual que las migraciones de
la base: para que un cambio surta efecto, se reinicia el hub). Si el
archivo no existe, se crea con los valores por defecto en el primer
arranque, así queda a la vista y editable en vez de escondido en el
código — es justamente lo que dice el diseño técnico (§8) y lo que hace
falta para que la futura app de "Configuración" tenga algo real que
mostrar y modificar.
"""
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULTS = {
    "host": "0.0.0.0",              # NO 127.0.0.1: ver ADR y §8 del diseño técnico
    "port": 8080,
    "max_file_mb": 100,              # ADR-10
    "max_actors_per_bridge": 5,      # ADR-12, tope por puente
    "max_actors_total": 40,          # ADR-14, tope de todo el servicio
    "trash_days": 7,                 # días en la papelera antes de purgar
    "retention_days": 7,             # expiración de mensajes sin pin (barrido: punto 5, aún pendiente)
    "hostname": "puente",            # nombre amigable; ver app/hostentry.py
}


def load_config() -> dict:
    DATA_DIR.mkdir(exist_ok=True)

    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(DEFAULTS, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return dict(DEFAULTS)

    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"(config.json inválido, uso los valores por defecto: {e})")
        return dict(DEFAULTS)

    # Completa con el default cualquier clave ausente (por ejemplo, un
    # config.json de una versión anterior sin max_actors_total) en vez de
    # fallar. Claves desconocidas del archivo se ignoran silenciosamente.
    cfg = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in data:
            cfg[key] = data[key]
    return cfg


CONFIG = load_config()
