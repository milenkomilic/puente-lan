# Puente — Roadmap de ejecución (prototipo v1)

**Base del proyecto:** `C:\Users\milmi\Desktop\Bridge`
**Última revisión:** 2026-09-13

Cada hito tiene **qué construyes** y **cómo sabes que funcionó**. No pases al siguiente sin cumplir el criterio: casi todos los hitos dependen del anterior.

---

## M0 — Entorno y estructura

### Estructura objetivo

```
Bridge/
├── docs/
│   ├── puente-diseno-tecnico.md
│   └── puente-schema.sql
├── app/
│   ├── main.py          arranque y montaje de rutas
│   ├── config.py        lectura de config.json
│   ├── db.py            conexión SQLite y PRAGMAs
│   ├── firewall.py      detección y aplicación
│   ├── routes/          endpoints por área
│   └── static/          interfaz web
├── data/                ← estado: bridge.db, blobs/, config.json
├── requirements.txt
└── .gitignore
```

`data/` es la carpeta portátil del diseño. Todo lo demás es código reemplazable.

### Comandos

```
cd C:\Users\milmi\Desktop\Bridge
py --version
```

Necesitas 3.10 o superior. Si `py` no existe, instala Python desde python.org marcando "Add to PATH".

```
mkdir docs app app\routes app\static data
move puente-*.md docs
move puente-*.sql docs

py -m venv .venv
.venv\Scripts\activate
pip install fastapi "uvicorn[standard]" python-multipart
pip freeze > requirements.txt
```

El prompt debe quedar con `(.venv)` al inicio. Si abres una consola nueva, hay que volver a activar.

### Git desde ahora

Son treinta segundos y te ahorra el momento en que rompas algo que funcionaba:

```
git init
```

Crea `.gitignore` con este contenido **antes** del primer commit:

```
.venv/
data/
__pycache__/
*.pyc
```

`data/` fuera de Git no es opcional: ahí van a vivir tus archivos reales. Un repositorio con tus blobs adentro es un problema serio y difícil de deshacer.

### Criterio

`.venv` activo, `import fastapi` no falla, `git status` no lista `data/` ni `.venv/`.

---

## M1 — El hub responde desde otro equipo

**Este hito va primero y es el más importante.** Valida red, binding y firewall antes de que exista una sola línea de lógica. Si algo aquí falla, lo descubres ahora y no después de tres días de trabajo encima.

### Qué construyes

`app/main.py` con una app FastAPI y un solo endpoint que devuelva `{"ok": true}`. Nada más.

### Ejecutar

```
cd C:\Users\milmi\Desktop\Bridge
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

`--host 0.0.0.0` es obligatorio. El default es `127.0.0.1` y desde otra máquina es invisible: es la causa número uno de "no conecta".

Windows va a mostrar el aviso de firewall en este momento. Acepta para redes privadas.

### Averiguar la IP de la torre

```
ipconfig
```

Busca **Dirección IPv4** del adaptador de tu red (algo como `192.168.1.x`).

### Probar

1. En la torre: `http://localhost:8080`
2. En la torre, por IP: `http://192.168.1.x:8080`
3. **Desde la notebook:** misma URL
4. **Desde una VM:** misma URL

### Si falla desde otro equipo

| Falla en | Causa probable |
|---|---|
| Paso 2 (la propia IP) | binding en localhost; revisa `--host` |
| Paso 3 (notebook) | firewall o perfil de red Público; ver §6.4 del diseño |
| Paso 4 (solo la VM) | adaptador en NAT; cámbialo a **modo bridge** |

### Criterio

Los cuatro pasos devuelven `{"ok": true}`. **No avances sin esto.**

---

## M2 — Base de datos

### Qué construyes

`app/db.py`: crea `data/bridge.db` desde el SQL de `docs/` si no existe, y entrega conexiones con los PRAGMAs aplicados.

Lo crítico: los PRAGMAs van en **cada conexión**, no solo al crear la base. `foreign_keys` viene apagado por defecto en SQLite, así que sin esa línea todas las claves foráneas del esquema son decoración.

### Criterio

Arrancar dos veces no duplica ni destruye nada. Con `sqlite3 data/bridge.db ".tables"` aparecen las cinco tablas. Un `INSERT` con una FK inválida **falla** (si pasa, el PRAGMA no se está aplicando).

---

## M3 — Actor

### Qué construyes

`POST /api/actor` recibe un nombre, crea la fila, genera el token con `secrets.token_urlsafe` y lo deja en una cookie `HttpOnly`. Una dependencia que resuelve el actor desde la cookie en cada petición.

Nunca generes el token con `random`, ni lo derives del id o del nombre. En v1 ese token **es** la credencial.

### Criterio

Entras desde la notebook, pones "Notebook", recargas y te sigue reconociendo. Entras desde la VM y aparece como un actor distinto.

---

## M4 — Puentes

### Qué construyes

Crear, listar y renombrar. El creador queda como `owner`. Validación del tope de 5 al agregar, leída de la config y no cableada.

El nombre derivado se calcula al leer cuando `manual_name` es `NULL`: dos actores → nombres completos; tres o más → los dos primeros y un contador.

### Criterio

Creas dos puentes desde la torre, los ves listados desde la notebook, renombras uno y el nombre persiste tras recargar.

---

## M5 — Chat de texto en vivo

Aquí el esqueleto vertical queda completo y el proyecto empieza a ser real.

### Qué construyes

Enviar y listar mensajes con paginación por cursor (`WHERE bridge_id = ? AND id < ?`), WebSocket que difunde a los conectados al puente, y la interfaz: lista de puentes a la izquierda, chat a la derecha, cada mensaje con actor y hora.

### Criterio

Notebook y VM abiertas en el mismo puente. Escribes en una y **aparece en la otra sin recargar**. Cierras la VM, escribes desde la notebook, reabres la VM y el mensaje está ahí.

---

## M6 — Archivos

### Qué construyes

Subida con validación de tamaño en **ambos** lados, hash mientras se recibe, almacenamiento por hash, y descarga con `Range` usando `sendfile`.

El navegador rechaza antes de subir, usando el tamaño que conoce al seleccionar el archivo. Subir 400 MB para fallar al final es la peor experiencia posible.

### Criterio

Envías un PDF desde la notebook y lo descargas desde la VM íntegro. Intentas uno sobre el límite y el rechazo es **inmediato**, sin barra de progreso. Envías el mismo archivo dos veces: en `data/blobs/` hay una sola copia.

---

## M7 — Módulo de firewall

### Qué construyes

`app/firewall.py`: detecta sistema y backend, comprueba si la regla existe, y una sección en la interfaz que **muestra el comando antes de ejecutarlo** y pide elevación.

En Linux, detectar firewall inactivo y reportar "no hay nada que hacer" es un resultado correcto, no un error. Nunca actives un firewall que el usuario no tenía.

### Criterio

En la torre reporta el estado real. Si borras la regla a mano, la detecta como ausente y la vuelve a crear. Cancelar el UAC deja el comando en pantalla en vez de un error.

---

## M8 — Pulido

Pegar con `Ctrl+V` y que se envíe. Arrastrar a cualquier parte de la página. Barra de progreso. Indicador de quién está conectado. Ventana de información según §12 del diseño.

Esto es lo que hace que se sienta rápido. El throughput ya está resuelto en M6; lo que falta es el gesto.

### Criterio

Copias una captura y la pegas: se envía sin abrir ningún diálogo.

---

## Después del prototipo

En orden de valor, no de facilidad:

1. **tus** cuando el límite de tamaño estorbe de verdad (ADR-05).
2. **Identidad e invitaciones** cuando quieras controlar quién entra (ADR-07).
3. **Retención**, siempre en modo simulación primero: que registre qué borraría, sin borrar, hasta que confíes en lo que reporta.
4. **mDNS y QR** para dejar de escribir la IP.
5. **Instalador y arranque automático** para cerrar el ciclo del formateo.

---

## Regla de mantenimiento

Cuando un hito contradiga una decisión del documento de diseño, **edita el ADR** en vez de dejar que el código y el documento se separen en silencio. Un diseño desactualizado es peor que ninguno: te hace confiar en algo falso.
