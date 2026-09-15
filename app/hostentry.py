"""Acceso por nombre en vez de IP (discusión 2026-09-15).

Un sitio web no puede editar el archivo hosts del equipo que lo visita —
esa restricción la impone el navegador, no algo que Puente pueda evitar
con más código. Es distinto del módulo de firewall (ADR-11): ahí el hub
modifica su propia máquina, porque el hub y "la máquina a cambiar" son el
mismo equipo. Acá "la máquina a cambiar" es cada equipo que se conecta, y
lo único que puede tocar su sistema de archivos es algo que corra
nativamente en ese equipo.

Se sigue el mismo espíritu: nunca aplicar nada elevado en silencio,
mostrar siempre exactamente qué se va a hacer. Como hay que repetirlo en
cada equipo nuevo (no solo una vez en el hub), en vez de un botón que lo
aplica se ofrece un script descargable y explícito para que cada equipo
lo corra una sola vez.
"""
import socket

from app.config import CONFIG

HOSTNAME = CONFIG["hostname"]


def lan_ip() -> str:
    """La IP con la que este equipo se ve desde el resto de la red.

    El truco del socket UDP no envía ningún paquete: solo le pregunta al
    sistema operativo qué interfaz usaría para llegar a esa IP, y de ahí
    se lee la propia dirección. Si no hay red disponible, cae a
    localhost en vez de fallar."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def hosts_line() -> str:
    return f"{lan_ip()}\t{HOSTNAME}"


def windows_script() -> str:
    ip = lan_ip()
    port = CONFIG["port"]
    return (
        "@echo off\n"
        "net session >nul 2>&1\n"
        "if %errorlevel% neq 0 (\n"
        "    echo Este cambio necesita permisos de administrador. Pidiendo permiso...\n"
        "    powershell -NoProfile -Command \"Start-Process -FilePath '%~f0' -Verb RunAs\"\n"
        "    exit /b\n"
        ")\n\n"
        "set HOSTS=%WINDIR%\\System32\\drivers\\etc\\hosts\n\n"
        f'findstr /C:"{HOSTNAME}" "%HOSTS%" >nul 2>&1\n'
        "if %errorlevel%==0 (\n"
        f'    echo Ya existe una entrada para "{HOSTNAME}" en hosts. No se hizo ningun cambio.\n'
        ") else (\n"
        f'    echo Agregando "{ip}    {HOSTNAME}" a %HOSTS%\n'
        f'    echo {ip}\t{HOSTNAME}>>"%HOSTS%"\n'
        f"    echo Listo. Ahora puedes abrir http://{HOSTNAME}:{port}\n"
        ")\n"
        "pause\n"
    )


def unix_script() -> str:
    ip = lan_ip()
    port = CONFIG["port"]
    return (
        "#!/bin/sh\n"
        "HOSTS=/etc/hosts\n\n"
        f'if grep -q "{HOSTNAME}" "$HOSTS" 2>/dev/null; then\n'
        f'    echo "Ya existe una entrada para {HOSTNAME} en hosts. No se hizo ningun cambio."\n'
        "else\n"
        f'    echo "Agregando \'{ip}    {HOSTNAME}\' a $HOSTS (puede pedir tu contrasena)"\n'
        f'    echo "{ip}\\t{HOSTNAME}" | sudo tee -a "$HOSTS" > /dev/null\n'
        f'    echo "Listo. Ahora puedes abrir http://{HOSTNAME}:{port}"\n'
        "fi\n"
    )
