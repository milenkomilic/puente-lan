from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.db import init_db
from app.routes import actors, bridges, messages, files, firewall, admin

app = FastAPI(title="Puente")
app.include_router(files.router)
app.include_router(actors.router)
app.include_router(bridges.router)
app.include_router(messages.router)
app.include_router(firewall.router)
app.include_router(admin.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

@app.on_event("startup")
def startup():
    init_db()
