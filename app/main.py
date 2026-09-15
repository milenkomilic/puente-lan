from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.db import init_db
from app.routes import actors, bridges, messages, files, firewall, admin, invites, friends

app = FastAPI(title="Puente")
app.include_router(files.router)
app.include_router(actors.router)
app.include_router(bridges.router)
app.include_router(messages.router)
app.include_router(firewall.router)
app.include_router(admin.router)
app.include_router(invites.router)
app.include_router(friends.router)

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
