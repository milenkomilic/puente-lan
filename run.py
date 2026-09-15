"""Levanta el hub leyendo host y puerto desde data/config.json.

Uso:
    python run.py

Equivalente a:
    uvicorn app.main:app --host <host de config.json> --port <puerto de config.json>

Este es el punto de entrada que va a usar el futuro lanzador de bandeja
del sistema (ver la discusión del instalador): un .exe generado con
PyInstaller necesita una función Python que arranque todo, no una línea
de comandos. Para desarrollo, seguir usando el comando de uvicorn de
arriba también funciona — hace exactamente lo mismo, solo que con host y
puerto fijos en vez de leídos de la configuración.
"""
import uvicorn

from app.config import CONFIG


def main() -> None:
    uvicorn.run("app.main:app", host=CONFIG["host"], port=CONFIG["port"])


if __name__ == "__main__":
    main()
