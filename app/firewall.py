import platform
import shutil
import subprocess

RULE_NAME = "Puente"


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return -1, str(e)


def _windows(port: int) -> dict:
    code, out = _run([
        "netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE_NAME}"
    ])
    exists = code == 0 and RULE_NAME in out

    profile_note = None
    code_p, out_p = _run([
        "powershell", "-NoProfile", "-Command",
        "(Get-NetConnectionProfile).NetworkCategory"
    ])
    if code_p == 0 and "Public" in out_p:
        profile_note = ("La red está clasificada como Pública. Aunque exista la "
                        "regla, Windows bloquea la conexión. Cámbiala a Privada "
                        "en Configuración → Red e Internet → tu conexión.")

    return {
        "system": "windows",
        "backend": "netsh advfirewall",
        "active": True,
        "rule_exists": exists,
        "action_needed": not exists,
        "command": (
            f'netsh advfirewall firewall add rule name="{RULE_NAME}" dir=in '
            f'action=allow protocol=TCP localport={port} profile=private'
        ),
        "remove_command": (
            f'netsh advfirewall firewall delete rule name="{RULE_NAME}"'
        ),
        "note": profile_note,
    }


def _linux(port: int) -> dict:
    if shutil.which("ufw"):
        code, out = _run(["ufw", "status"])
        if code != 0:
            code, out = _run(["sudo", "-n", "ufw", "status"])
        active = "inactive" not in out.lower() and "active" in out.lower()
        exists = f"{port}/tcp" in out
        return {
            "system": "linux", "backend": "ufw", "active": active,
            "rule_exists": exists,
            "action_needed": active and not exists,
            "command": f"sudo ufw allow {port}/tcp",
            "remove_command": f"sudo ufw delete allow {port}/tcp",
            "note": None if active else (
                "El firewall está inactivo: el puerto ya está abierto y no hay "
                "nada que hacer. No se activará un firewall que no estaba en uso."
            ),
        }

    if shutil.which("firewall-cmd"):
        code, out = _run(["firewall-cmd", "--state"])
        active = "running" in out
        _, ports = _run(["firewall-cmd", "--list-ports"])
        exists = f"{port}/tcp" in ports
        return {
            "system": "linux", "backend": "firewalld", "active": active,
            "rule_exists": exists,
            "action_needed": active and not exists,
            "command": (f"sudo firewall-cmd --permanent --add-port={port}/tcp && "
                        f"sudo firewall-cmd --reload"),
            "remove_command": (f"sudo firewall-cmd --permanent --remove-port={port}/tcp"
                               f" && sudo firewall-cmd --reload"),
            "note": None if active else "El firewall está inactivo: no hay nada que hacer.",
        }

    return {
        "system": "linux", "backend": None, "active": False,
        "rule_exists": False, "action_needed": False,
        "command": None, "remove_command": None,
        "note": "No se detectó ufw ni firewalld. Probablemente no hay firewall activo.",
    }


def status(port: int) -> dict:
    return _windows(port) if platform.system() == "Windows" else _linux(port)


def apply(port: int) -> dict:
    st = status(port)
    if not st["action_needed"]:
        return {"applied": False, "reason": "no hacía falta", "status": st}

    if st["system"] == "windows":
        code, out = _run([
            "powershell", "-NoProfile", "-Command",
            f"Start-Process netsh -Verb RunAs -Wait -ArgumentList "
            f"'advfirewall firewall add rule name=\"{RULE_NAME}\" dir=in "
            f"action=allow protocol=TCP localport={port} profile=private'"
        ], timeout=60)
    else:
        runner = "pkexec" if shutil.which("pkexec") else "sudo"
        cmd = ([runner, "ufw", "allow", f"{port}/tcp"] if st["backend"] == "ufw"
               else [runner, "firewall-cmd", "--permanent", f"--add-port={port}/tcp"])
        code, out = _run(cmd, timeout=60)
        if code == 0 and st["backend"] == "firewalld":
            _run([runner, "firewall-cmd", "--reload"], timeout=30)

    after = status(port)
    return {
        "applied": after["rule_exists"],
        "output": out.strip()[:400],
        "status": after,
    }