# Iniciar servicio:
uvicorn app.main:app --host 0.0.0.0 --port 8080

# Puente

Transferencia de texto y archivos entre equipos propios en red local, sin reconfigurar nada al formatear.

Un **hub** corre en una máquina encendida. El resto de los equipos entran por navegador a una URL local. La interacción es un chat: mensajes y archivos en un timeline compartido, organizados en puentes independientes.

---

## El problema que resuelve

Una carpeta compartida de Windows no es lenta ni está mal diseñada. El problema es **dónde vive su configuración**: usuarios, permisos NTFS, perfiles de red y reglas de firewall viven dentro del sistema operativo. Formateas y todo eso desaparece. Hay que rehacerlo, equipo por equipo, cada vez.

Puente parte de una restricción distinta: **todo el estado cabe en una carpeta portátil**. Copias `data/` y el servicio completo se mudó de máquina. La única excepción es la regla de firewall, y para eso hay un módulo que la crea y la quita.

La segunda decisión que hace posible lo anterior: **el cliente es el navegador**. Solo el hub necesita instalación. Un PC recién formateado, una VM o un teléfono entran con una URL, sin instalar nada.

### Qué no es

- **No es respaldo.** El contenido está pensado para caducar.
- **No es sincronización de carpetas.** No hay espejo ni resolución de conflictos.
- **No es acceso remoto.** El alcance es la LAN.
- **No mueve archivos enormes.** Hay un límite configurable; para 50 GB, un disco externo siempre será mejor.

---

## Estado actual

Prototipo funcional, en uso real. Las pruebas end-to-end cubren 55 comprobaciones y corren en poco más de un segundo.

| Capacidad | Estado |
|---|---|
| Chat en vivo entre equipos (WebSocket) | funcional |
| Archivos con deduplicado por contenido | funcional |
| Puentes múltiples, hasta 5 equipos | funcional |
| Panel de administración | funcional |
| Papelera con restauración | funcional |
| Transferencia de propiedad | funcional |
| Recolección de basura | funcional |
| Módulo de firewall multiplataforma | funcional |
| Alta rápida por invitación + QR | funcional |
| Acceso por nombre en vez de IP (script + verificación) | funcional |
| Recuperación de identidad (enlace de un solo uso) | funcional |
| Amistades entre cuentas (solicitud/aceptar) | funcional |
| Tope de actores del servicio (40) | funcional |
| Identidad criptográfica por dispositivo | pendiente |
| Configuración externalizada (`data/config.json`) | funcional |
| Subidas reanudables (tus) | pendiente |
| Expiración automática a 7 días | campos listos, barrido pendiente |
| Hub instalado (bandeja del sistema, sin CMD) | en diseño |

---

## Instalación

Requiere Python 3.10 o superior.

```bash
git clone <url-del-repo> Bridge
cd Bridge

python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
```

### Levantar el hub

```bash
python run.py
```

Lee host y puerto desde `data/config.json` (se crea solo, con valores por defecto, la primera vez). Equivale a:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

`--host 0.0.0.0` **no es opcional** en ninguno de los dos casos. El valor por defecto de casi todos los frameworks es `127.0.0.1`, que funciona perfecto en la máquina local y es completamente invisible desde cualquier otra. Es la causa número uno de "no me conecta".

La base de datos y las carpetas se crean solas en el primer arranque.

### Entrar desde otro equipo

Averigua la IP del hub (`ipconfig` en Windows, `ip addr` en Linux) y abre `http://IP-DEL-HUB:8080` desde cualquier navegador de la red. La primera vez pide un nombre de equipo.

Si no conecta, mira **Resolución de problemas** más abajo.

---

## Uso

**Crear un puente** desde el botón de la barra lateral. Quien lo crea queda como dueño.

**Agregar un equipo nuevo, que todavía no tiene cuenta en el hub**, desde el engranaje del puente → **Invitar**. Genera un enlace de un solo uso (vence en 15 minutos) con su QR; se abre en el equipo o se escanea desde el celular, y queda dentro del puente.

**Agregar a alguien que ya es tu amigo** también desde el engranaje del puente → **Agregar equipo**: aparece en una lista, sin exponer el resto de los equipos del servicio.

**Hacer amigos** desde el botón **Amigos** de la barra lateral: genera un enlace de un solo uso (vence en 7 días), lo compartes por fuera de Puente, y quien lo abre ve quién invita y decide aceptar o rechazar. Una solicitud sin responder se vence sola a los 7 días.

**Recuperar la sesión de un equipo** (por ejemplo tras limpiar la caché del navegador) con el botón **⟲** junto a tu nombre: genera un enlace de recuperación de un solo uso para abrir en el navegador donde perdiste el acceso.

**Enviar** texto con Enter, archivos arrastrando a la ventana, pegando con `Ctrl+V`, o con el botón `+`.

**Administrar** desde el mismo engranaje: expulsar, transferir propiedad, renombrar, mover a la papelera.

**Mantenimiento** desde la barra lateral: uso de disco, liberar espacio, limpiar equipos sin uso y aplicar la regla de firewall.

**Reset de fábrica**, si quieres volver a probar todo desde cero: `python reset_fabrica.py` (ver más abajo, en Operación).

**Entrar por nombre en vez de IP**, desde el enlace "Configura un nombre fácil de recordar" en la pantalla inicial (o **Acceso por nombre** dentro de Mantenimiento): descarga un script para el sistema operativo de ese equipo (`.bat` en Windows, `.sh` en Linux/macOS), lo corres una vez ahí (pide permiso de administrador para editar el archivo `hosts` de esa máquina), y desde entonces `http://puente:8080` funciona en ese equipo igual que la IP. Hay que hacerlo una vez por cada equipo nuevo — el hub no puede editar el archivo de otra máquina por sí solo, ver ADR-15.

---

## Arquitectura

```
┌──────────────── HUB ────────────────────┐
│                                          │
│  HTTP  ──┬── /api    puentes, mensajes   │
│          ├── /upload subida directa      │
│          └── /blob   descarga con Range  │
│                                          │
│  WS    ──── mensajes en vivo             │
│                                          │
│  Estado ─┬── data/bridge.db   (SQLite)   │
│          └── data/blobs/      (por hash) │
└──────────────────────────────────────────┘
     ▲              ▲              ▲
  Navegador      Notebook         VM
```

### Modelo de datos

```
Actor    →  equipo identificado (nombre + cookie)
   ↓
Puente   →  hasta 5 actores, chat propio, dueño
   ↓
Mensaje  →  referencia; lleva actor, pin y vencimiento
   ↓
Blob     →  contenido único, global, deduplicado
```

Esa separación entre **mensaje** y **blob** es la pieza central del diseño. El mensaje es una referencia que vive dentro de un puente y tiene sus propios permisos y vencimiento. El blob es el contenido físico, es global y se comparte entre puentes.

De ahí salen tres propiedades sin código extra: enviar el mismo archivo dos veces ocupa espacio una sola vez; el hash verifica integridad; y un blob nunca se borra mientras exista un mensaje vivo que lo apunte, aunque esté en otro puente.

### Estructura

```
Bridge/
├── app/
│   ├── main.py           arranque, routers, estáticos
│   ├── db.py             conexión SQLite, PRAGMAs, migraciones
│   ├── gc.py             recolección de blobs huérfanos
│   ├── firewall.py       detección y aplicación multiplataforma
│   ├── routes/
│   │   ├── actors.py     identidad y sesión
│   │   ├── bridges.py    creación, listado, membresía
│   │   ├── messages.py   timeline y WebSocket
│   │   ├── files.py      subida, blobs, descarga
│   │   ├── admin.py      panel, papelera, avisos
│   │   ├── invites.py    alta rápida, recuperación, amistad (token único)
│   │   ├── friends.py    amigos: listar, aceptar, rechazar, quitar
│   │   └── firewall.py   endpoints del módulo
│   └── static/index.html interfaz completa
├── docs/                 diseño técnico, esquema, migraciones, roadmap
├── data/                 ← estado portátil (fuera de Git)
├── test.py               suite end-to-end
├── tools.py              inspección rápida de la base
├── migrar.py             migraciones a mano
└── reset_fabrica.py      borra data/ y reinicia el hub desde cero
```

---

## Decisiones de diseño

Las decisiones están registradas como ADR en `docs/puente-diseno-tecnico.md`, con su razón y la consecuencia aceptada. Las más importantes:

**Hub central, no malla P2P.** Elimina reconciliación, conflictos y vector clocks. Y habilita revocación inmediata, que es prácticamente imposible de garantizar en una malla porque no hay nadie que pueda decir "no" de forma autoritativa. El costo aceptado: si el hub está apagado, no hay puente.

**Log append-only.** El contenido son eventos que se agregan, nunca se editan. No existen conflictos si nada se modifica, lo que elimina la clase de bugs más cara del proyecto.

**Blobs direccionados por contenido, desde el primer archivo.** Migrar después desde un almacén por nombre obliga a reescribir todo el disco.

**Sin contador de referencias almacenado.** Un contador se desincroniza ante cualquier borrado mal manejado, y el síntoma es pérdida silenciosa de datos. Se deriva por consulta, que con índice es igual de rápido y no puede mentir.

**El nombre del archivo vive en el mensaje, no en el blob.** El mismo contenido puede enviarse como `informe.pdf` y como `informe_v2.pdf`. Ponerlo junto al contenido rompe el deduplicado o pierde un nombre.

**Límite de tamaño en vez de subida reanudable.** Recorta la parte más difícil del proyecto sin perder el caso de uso principal. Se implementará el protocolo tus cuando el límite estorbe de verdad.

**El dueño no puede salirse de su propio puente.** Debe transferir o eliminar. Sin esa regla se generan puentes sin administrador que nadie puede arreglar.

---

## Modelo de seguridad

**Sé honesto sobre dónde está parado el proyecto.** En esta versión, quien alcanza la URL entra. No hay control de acceso entre equipos de la red. Es aceptable en una LAN doméstica; no lo es en una red compartida.

Lo que sí está resuelto:

- Un actor solo ve los puentes de los que es miembro.
- Conocer el hash de un archivo **no** basta para descargarlo: hay que ser miembro de algún puente donde ese blob aparezca.
- El WebSocket verifica membresía al conectar, no solo el token.
- El token de sesión se genera con un CSPRNG y la cookie es `HttpOnly`.
- El contenido de los mensajes se renderiza con `textContent`, nunca concatenado en HTML.
- **Agregar a alguien a un puente ya no expone la lista completa de actores del hub.** El panel solo ofrece amigos aceptados; para cualquier otro caso existe el enlace de invitación, que identifica exactamente a un equipo.
- **Los enlaces de invitación, recuperación y amistad son de un solo uso, con vencimiento** (15 minutos para alta y recuperación, 7 días para amistad), y canjearlos los invalida de inmediato.
- **Recuperar un equipo rota su token de sesión.** Si alguien más interceptó el enlace de recuperación, el equipo legítimo también pierde el acceso al canjearlo él, y lo nota en el momento, en vez de compartir la sesión en silencio.
- **El servicio completo tiene un tope de 40 actores registrados**, para que instalarlo públicamente no signifique una base sin límite de magnitud.

Límites que conviene tener presentes:

- **El token viaja en claro.** No hay HTTPS. En una red propia es aceptable; en una ajena no.
- **Quien controla el hub tiene poder absoluto**, porque tiene el disco y puede leer los blobs sin pasar por la aplicación. El rol de dueño es una herramienta de gestión, no una barrera frente al dueño del hardware.
- **Revocar detiene el acceso futuro, no el pasado.** Lo ya descargado no se recupera, y ninguna arquitectura cambia eso.
- **El WebSocket comprueba el permiso solo al abrir.** Un expulsado con la pestaña abierta sigue recibiendo hasta que recargue.

---

## Pruebas

```bash
pip install requests
# con el servidor corriendo en otra consola:
python test.py
```

55 comprobaciones en poco más de un segundo, contra el servidor real. Crea sus datos con prefijo `_test_` y limpia al terminar, así que no toca lo tuyo.

Cubre aislamiento entre actores, el tope de 5 equipos, paginación por cursor, deduplicado, que un no miembro no descargue aunque conozca el hash, papelera con restauración, transferencia, expulsión con aviso, y que el purgado libere los blobs en disco.

**Correrlo antes de cada commit.** Es la única forma barata de saber que un cambio no rompió algo que ya funcionaba.

### Inspeccionar la base

```bash
python tools.py
```

Lista actores con sus ids, puentes y membresías. Útil cuando necesitas un id a mano.

---

## Resolución de problemas

**Conecto desde el hub pero no desde otro equipo.** Casi siempre es el binding. Verifica que levantaste con `--host 0.0.0.0`.

**En Windows conecta desde el hub pero no desde la red.** Dos problemas distintos que se confunden:

1. *Falta la regla de firewall.* El módulo de mantenimiento la aplica, o a mano:
   ```
   netsh advfirewall firewall add rule name="Puente" dir=in action=allow protocol=TCP localport=8080 profile=private
   ```
2. *La red está clasificada como Pública.* Windows bloquea la conexión aunque la regla exista. Revísalo con:
   ```powershell
   Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, NetworkCategory
   ```
   Y cámbialo a `Private` desde Configuración o con `Set-NetConnectionProfile`.

**En Linux.** Lo más probable es que no haya nada que hacer: en Ubuntu de escritorio `ufw` viene inactivo y el puerto ya está abierto. Compruébalo con `sudo ufw status`. Si dice `inactive`, terminaste. **No actives el firewall solo para abrirle un hueco**: quedarías con una protección que no tenías y que nadie pidió.

**Una VM no conecta.** Con adaptador en NAT el tráfico sale con la IP del anfitrión. Funciona para acceder por IP directa, pero el descubrimiento por red no va a funcionar. Cambia el adaptador a modo bridge.

**Perdí la sesión de un equipo.** Ya no hace falta el truco manual: desde cualquier navegador donde sigas con sesión, hacé clic en **⟲** (junto a tu nombre) para generar un enlace de recuperación de un solo uso, y abrilo en el navegador donde la perdiste. Vence en 15 minutos.

**Quiero volver a probar todo desde cero.** `python reset_fabrica.py` muestra un resumen de lo que hay antes de tocar nada; con `--force` borra `data/` (con respaldo automático) y deja el hub como recién instalado. Ver la sección **Operación**.

**Quiero entrar con `http://puente:8080` en vez de la IP.** Usa "Configura un nombre fácil de recordar" desde la pantalla inicial (o **Acceso por nombre** en Mantenimiento) y descarga el script para ese equipo. Es un archivo `hosts`, así que hay que repetirlo una vez por cada equipo que quiera usar el nombre — el navegador no puede tocar el sistema de archivos de otra máquina, así que no hay forma de aplicarlo de forma remota y automática. Ver ADR-15 en el diseño técnico.

---

## Configuración

| Clave | Valor actual | Nota |
|---|---|---|
| Puerto | 8080 | |
| Tamaño máximo de archivo | 100 MB | validado en cliente y servidor |
| Equipos por puente | 5 | límite de prueba, no estructural |
| Días en papelera | 7 | barrido automático pendiente |
| Retención sin pin | 7 días | campos listos, barrido pendiente |
| Actores totales (tope del servicio) | 40 | no es el tope de 5 por puente; ver ADR-14 |
| Vencimiento de invitación (alta/recuperación) | 15 min | de un solo uso |
| Vencimiento de invitación de amistad | 7 días | la solicitud creada al canjearla vence en otros 7 días |
| Nombre de host | `puente` | ver ADR-15, acceso por nombre en vez de IP |

Viven en `data/config.json` (se crea solo con estos valores en el primer arranque). Editarlo a mano y reiniciar el hub alcanza por ahora; la app de Configuración del futuro instalador es la versión sin editar JSON a mano.

---

## Operación

### Reset de fábrica

```bash
python reset_fabrica.py              # solo muestra qué hay, no toca nada
python reset_fabrica.py --force      # borra data/ de verdad (pide confirmación escrita)
```

Antes de borrar copia `data/` completa a `data_backup_<fecha>/` (salvo `--no-backup`), y se niega a correr si detecta el hub respondiendo en el puerto configurado. Al terminar, `data/bridge.db` queda recreada vacía con el esquema al día — no hay que volver a levantar el servidor para que se aplique.

---

## Hacia dónde va

Lo que sigue, en orden de valor y no de facilidad.

### Inmediato

**Hub instalado, sin depender de CMD.** Hoy levantar el servicio significa abrir una consola y activar el entorno virtual a mano (`python run.py` ya ayuda, pero sigue siendo una consola). La idea en diseño: un instalador (PyInstaller + Inno Setup) que deje dos accesos directos — un lanzador de bandeja del sistema para prender/apagar el hub con un clic, con opción de "iniciar con Windows", y una app de Configuración que edite `data/config.json` sin tocar JSON a mano. En diseño activo.

**Corte de conexión al expulsar.** Hoy el WebSocket verifica el permiso solo al abrir. Un expulsado con la pestaña abierta sigue recibiendo mensajes hasta que recargue. Arreglarlo bien significa cerrar activamente sus conexiones y verificar membresía por cada petición de rango durante una descarga en curso.

**Barrido de la papelera y expiración.** Los campos existen y el diseño está definido. La precaución importante: implementarlo primero en **modo simulación**, registrando qué borraría sin borrar, hasta confiar en lo que reporta. Es el único código del sistema que destruye datos, y un bug ahí no da un error, pierde archivos.

**Ventana de información** en la interfaz, consultable en cualquier momento (no un modal de bienvenida que se cierra y no vuelve).

### Mediano plazo

**Identidad criptográfica por dispositivo (resto de ADR-07).** La parte de invitación y recuperación de ADR-07 ya está implementada (alta rápida, recuperación de identidad, amistades — ver la tabla de arriba). Lo que falta es la identidad misma: hoy el actor sigue siendo un nombre y una cookie que el servidor emite; el diseño original preveía un par de claves por dispositivo que nunca sale de la máquina. Es el salto que falta para no depender por completo de la base del hub como única fuente de identidad.

**Subidas reanudables con tus.** El cliente maduro existe (Uppy, 31k estrellas; tus-js-client, 2.5k) y resuelve la parte difícil: reintentos, reanudación tras cerrar el navegador, recuperación de crash. El servidor son cuatro verbos y un contador de offset. Con eso, el límite de tamaño deja de ser necesario.

**Descubrimiento por mDNS** para dejar de escribir la IP del hub a mano (el QR para compartir un enlace ya existe, esto es sobre encontrar el hub en la red). Ojo: las VMs en NAT van a necesitar igual el método manual, así que escribir la IP no desaparece del todo, se vuelve el respaldo.

**Registro de actividad por puente.** Sin un log de quién entró y qué descargó, la revocación es ciega: no hay forma de enterarse de un acceso indebido. Probablemente vale más que el botón de expulsar, porque es lo que dispara la reacción.

### Largo plazo

**Arranque automático con el sistema operativo**, una vez que exista el instalador (ver Inmediato): que el hub esté disponible sin ni siquiera abrirlo a mano tras reiniciar la máquina. Cierra el ciclo completo del formateo: instalas, restauras `data/`, y el servicio está de vuelta sin tocar nada más.

**Cifrado extremo a extremo.** Hoy el hub ve todo el contenido. Cambiarlo implica repensar el deduplicado, porque contenido cifrado con claves distintas no deduplica.

**Federación entre hubs**, para que dos redes distintas puedan tender un puente entre sí. Es el cambio más profundo: rompe el supuesto de fuente única de verdad sobre el que descansa todo el modelo actual.

### Lo que deliberadamente no se hará

**Sincronización bidireccional de carpetas.** Fue evaluado y descartado al inicio. El modelo append-only es lo que hace simple todo lo demás; volver a estado mutable compartido reintroduce conflictos, borrados ambiguos y reconciliación, que es la clase de complejidad que el diseño existe para evitar.

**Montaje como unidad de red.** Técnicamente posible vía WebDAV, pero el cliente de Windows es históricamente lento y frágil. El navegador cubre el caso de uso real con mejor comportamiento.

---

## Nota de mantenimiento

Cuando un cambio contradiga una decisión registrada, **edita el ADR** en `docs/puente-diseno-tecnico.md` en vez de dejar que el código y el documento se separen en silencio.

Un diseño desactualizado es peor que no tener ninguno: te hace confiar en algo falso.

---

## Documentación

| Documento | Contenido |
|---|---|
| `docs/puente-diseno-tecnico.md` | ADR completos, modelo de datos, seguridad, API |
| `docs/puente-schema.sql` | esquema SQLite comentado, consultas de referencia |
| `docs/puente-roadmap.md` | hitos con criterios de aceptación |