from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.config import CONFIG
from app.hostentry import HOSTNAME, hosts_line, lan_ip, unix_script, windows_script

router = APIRouter(prefix="/api")

# Sin autenticación a propósito: un equipo nuevo todavía no tiene sesión
# cuando necesita esto (aparece en la pantalla "¿Qué equipo es este?"),
# igual que /api/limits.


@router.get("/hostentry")
def hostentry_info():
    return {
        "hostname": HOSTNAME,
        "ip": lan_ip(),
        "port": CONFIG["port"],
        "line": hosts_line(),
    }


@router.get("/hostentry/script")
def hostentry_script(os: str = "windows"):
    if os == "unix":
        content, filename = unix_script(), "agregar-puente.sh"
    else:
        content, filename = windows_script(), "agregar-puente.bat"
    return PlainTextResponse(
        content, media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
