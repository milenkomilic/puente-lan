from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.db import init_db
from app.routes import actors, bridges, messages, files, firewall, admin, invites, friends, hostentry

app = FastAPI(title="Puente")

# Necesario para "Acceso por nombre" (ADR-15): la pantalla de verificación
# hace un fetch() desde el origen con IP (ej. http://192.168.0.7:8080)
# hacia el nombre (http://puente:8080). Aunque sea la misma máquina y el
# mismo puerto, el nombre de host distinto ya es "otro origen" para el
# navegador, y sin estas cabeceras la respuesta llega igual al servidor
# (se ve en el log) pero el navegador bloquea que el JS la lea. Solo GET
# y sin credenciales: no cambia el modelo de seguridad, porque la cookie
# de sesión (HttpOnly) nunca viaja en una petición cross-origin sin
# `credentials: "include"`, que este servicio no usa.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(files.router)
app.include_router(actors.router)
app.include_router(bridges.router)
app.include_router(messages.router)
app.include_router(firewall.router)
app.include_router(admin.router)
app.include_router(invites.router)
app.include_router(friends.router)
app.include_router(hostentry.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"


# Los enlaces de invitación (/i/{token}) los resuelve el front-end en JS
# leyendo la URL; solo hace falta servirles el mismo index.html. Va antes
# del mount de estáticos para que no lo tape el 404 de StaticFiles.
@app.get("/i/{token}")
def invite_page(token: str):
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.on_event("startup")
def startup():
    init_db()
