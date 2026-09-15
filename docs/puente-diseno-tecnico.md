# Puente — Diseño técnico

**Versión:** 0.2 — alcance de prototipo definido
**Última revisión:** 2026-09-13

---

## 1. Propósito

Transferir texto y archivos entre equipos propios en red local, sin reconfigurar nada al formatear un equipo.

Un **hub** corre en una máquina encendida. Los demás equipos entran por navegador a una URL local. La interacción es un chat: mensajes y archivos en un timeline por puente.

### Qué NO es

- No es respaldo. El contenido caduca por defecto (diferido a v2).
- No es sincronización de carpetas. No hay espejo ni resolución de conflictos.
- No es acceso remoto por internet. Alcance: LAN.
- No mueve archivos enormes. Para eso existe un disco externo. Ver ADR-10.

### Restricción rectora

Todo el estado cabe en **una carpeta portátil**. Nada de configuración en el sistema operativo, salvo la regla de firewall (ADR-11). Un formateo se recupera reinstalando y restaurando esa carpeta.

---

## 2. Alcance del prototipo (v1)

**Escenario objetivo:** el servicio corre en la torre. VMs y notebook de la misma red entran por navegador, se identifican con un nombre de equipo, y comparten texto y archivos en puentes con hasta 5 actores.

### Dentro

| Área | Alcance v1 |
|---|---|
| Hub | corre en la torre, escucha en todas las interfaces |
| Acceso | por IP directa; quien alcanza la URL, entra |
| Actor | equipo identificado por nombre + cookie persistente |
| Puentes | lista lateral, nombre editable, hasta 5 actores |
| Chat | texto y archivos en un timeline, con actor y hora |
| Archivos | subida directa, límite de tamaño, blob por hash |
| Firewall | módulo propio, Windows y Linux |
| Retención | campos guardados, nada se borra |

### Fuera (diferido a v2)

Identidad criptográfica, invitaciones, roles, cola de aprobación, expulsión, auditoría, barrido de expiración, recolector de blobs, mDNS, QR, subida reanudable (tus), instalador.

### Criterio de término

Desde la notebook y desde una VM, ambas simultáneamente, enviar texto y archivos a un puente alojado en la torre y verlos aparecer en el otro equipo sin recargar.

---

## 3. Decisiones de arquitectura (ADR)

Formato: decisión → razón → consecuencia aceptada. Las marcadas **[v2]** están decididas pero no se implementan en el prototipo.

### ADR-01 — Hub central, no malla P2P

Una máquina es fuente de verdad; el resto son clientes.

**Razón:** elimina reconciliación, conflictos y vector clocks. Habilita revocación inmediata, imposible de garantizar en una malla.

**Consecuencia:** si el hub está apagado, no hay puente. Aceptado: el hub es la torre.

### ADR-02 — Cliente = navegador

Sin instalación en los equipos cliente.

**Razón:** un PC recién formateado, una VM o un teléfono entran con una URL. Solo la torre necesita la app instalada, que es exactamente el problema original.

**Consecuencia:** sin acceso al sistema de archivos del cliente.

### ADR-03 — Log append-only, no estado mutable

El contenido son eventos que se agregan, nunca se editan.

**Razón:** no existen conflictos si nada se modifica. Elimina la clase de bugs más cara del proyecto.

**Consecuencia:** editar un mensaje no existe; se envía uno nuevo.

### ADR-04 — Blobs direccionados por contenido

Cada archivo se almacena bajo el hash de su contenido, desde el primer archivo del prototipo.

**Razón:** deduplicado entre puentes, verificación de integridad y descarga por rangos, todo gratis. Migrar después desde un almacén por nombre obliga a reescribir todo el disco.

**Consecuencia:** obliga a contar referencias antes de borrar (§5.3).

### ADR-05 [v2] — Protocolo tus con servidor propio

Cliente: Uppy / tus-js-client (31k y 2.5k estrellas). Servidor: implementación propia del núcleo tus.

**Razón:** la lógica difícil (reintentos, reanudación tras cerrar el navegador) vive en el cliente y es código maduro de terceros. El servidor tus son cuatro verbos y un offset. Las librerías tus para Python rondan 10–30 estrellas: no justifican una dependencia crítica, y un sidecar en Go rompería el binario único.

**Disparador:** se implementa cuando el límite de tamaño (ADR-10) empiece a estorbar de verdad, no antes.

### ADR-06 — Plano de control y plano de datos separados

WebSocket para eventos y presencia. HTTP aparte para bytes.

**Razón:** una transferencia no debe congelar la interfaz ni retrasar los mensajes de texto.

### ADR-07 [v2] — Identidad, invitación y membresía son tres cosas distintas

- **Identidad:** par de claves por dispositivo, nunca sale de la máquina.
- **Invitación:** código de un solo uso, con vencimiento, limitado a un puente.
- **Membresía:** resultado durable de canjear una invitación.

**Razón:** si el link compartible fuera la identidad, compartirlo sería filtrarla, y no podría rotarse sin romper todos los puentes.

**En v1:** el actor es solo un nombre y una cookie. El campo de rol existe en los datos; la UI de gestión no.

**Adelantado desde v2 (2026-09-14):** la invitación y la recuperación de identidad ya están implementadas, sin esperar a la identidad criptográfica. Una tabla `invite` (`docs/migracion-003.sql`) guarda un token de un solo uso, con vencimiento de 15 minutos, de dos tipos: `join` (limitado a un puente) y `reclaim` (limitado a un actor). Canjear un `reclaim` rota el token del actor, así que un enlace interceptado invalida también al equipo legítimo en vez de compartir la sesión con el atacante. La identidad de dispositivo con par de claves sigue diferida.

### ADR-13 — Puente es un servicio público (2026-09-14): amistad explícita en vez de directorio

Cambio de alcance: Puente deja de asumir "todos los actores son mis propios equipos" y pasa a ser algo que cualquiera puede correr y publicar. Eso rompió un supuesto implícito del panel de puente: el selector "agregar equipo" listaba **todos los actores del hub**, porque hasta ahora todos eran del mismo dueño. Con actores de dueños distintos, esa lista es una fuga de información — cualquiera que abra el panel de un puente ve el padrón completo de equipos del servicio.

**Decisión:** una relación de amistad explícita y consentida por ambos lados, con el esquema clásico de solicitud/respuesta (`docs/migracion-004.sql`, tabla `friendship`): `pending` → `accepted`. Rechazar o cancelar borra la fila; no hay estado `rejected` que conservar. Una solicitud sin responder vence a los 7 días (se deriva por `expires_at`, se barre al leer — no es contenido del usuario, así que no aplica la cautela de modo simulación del punto 5).

**Cómo se conecta:** identificar a la otra persona sigue sin usar un directorio. Se reutiliza el mecanismo de invitación (tercer `kind`: `friend`) — quien quiere agregar a alguien genera un enlace/QR de un solo uso (vence en 7 días) y lo comparte por fuera de Puente. Al abrirlo, quien lo recibe ve quién lo invita y decide: aceptar o rechazar ahí mismo, o dejarlo pendiente hasta 7 días en su panel de "Amigos".

**Consecuencia en el panel de puente:** "Agregar equipo" ahora lista solo amigos aceptados que no son ya miembros. Para alguien que todavía no es amigo, sigue existiendo el enlace de invitación al puente (`kind=join`), sin pasar por la amistad.

**Se descartó** el bloqueo de actores en este snapshot — "agregar/quitar amigo" alcanza para el caso de uso actual; bloquear (impedir nuevas solicitudes, expulsar de puentes activos) queda para cuando haga falta.

### ADR-14 — Tope de actores del servicio completo (2026-09-14)

**Decisión:** máximo 40 actores registrados por instancia del hub, chequeado en `POST /api/actor` y en cualquier alta de actor nueva vía invitación (`join`, `friend`). No es el tope de 5 por puente (ADR-12): es un techo de magnitud para todo el servicio.

**Razón:** al publicarse como algo que cualquiera puede instalar, un hub sin techo puede acumular actores sin límite (SQLite crece, pero también crece la superficie: más identidades, más amistades posibles, más código nunca ejercitado a esa escala). 40 es deliberadamente chico para este snapshot — cinco puentes llenos de cinco actores distintos ya lo justifican como orden de magnitud razonable — y puede revisarse con uso real.

**Consecuencia:** con el hub lleno, tanto un equipo nuevo entrando por `POST /api/actor` como uno entrando por un enlace de invitación reciben un 409 explícito. Vive como constante en código por ahora; migra a `data/config.json` junto con el resto en el punto 3 del roadmap.

### ADR-08 [v2] — Sesión con estado en servidor, membresía verificada por petición

Sin tokens autocontenidos tipo JWT.

**Razón:** con JWT, expulsar a alguien no surte efecto hasta que el token vence. La revocación debe ser inmediata o no es revocación.

### ADR-09 — El puente es la unidad de acceso, retención y conversación

**Consecuencia:** los blobs se comparten entre puentes; las referencias nunca. El permiso se evalúa sobre la referencia, no sobre el blob.

### ADR-10 — Límite de tamaño de archivo en vez de subida reanudable

Se rechazan archivos sobre un umbral configurable (sugerido: 100 MB).

**Razón:** recorta la parte más difícil del proyecto sin perder el caso de uso principal. Documentos, fotos, código e instaladores chicos caben; para mover 50 GB un disco externo siempre será mejor. El umbral elegido evita justamente ISOs y video, que es donde una subida sin reanudación duele.

**Consecuencias obligatorias:**
- El navegador rechaza **antes de subir**, usando el tamaño conocido al seleccionar. Subir 400 MB para fallar al final es la peor experiencia posible.
- El servidor valida también; el cliente puede fallar o alguien puede llamar el endpoint directo.
- El umbral es configuración, no constante en el código.

### ADR-11 — Módulo de firewall propio, multiplataforma

Sección de la app que detecta el backend de firewall, genera la regla y la aplica con elevación.

**Razón:** es la única configuración fuera de la carpeta portátil y la causa más común de "no me conecta". Dejarla al usuario contradice el objetivo del proyecto.

**Consecuencias y límites:** ver §6, donde están las trampas reales.

### ADR-12 — Máximo 5 actores por puente

Límite configurable, no estructural.

**Razón:** acota la superficie de pruebas del prototipo. No hay nada en el modelo de datos que impida más.

**Consecuencia:** el límite vive en configuración y se valida al agregar, nunca cableado en el esquema.

---

## 4. Componentes (v1)

```
┌──────────────── HUB (torre) ────────────────┐
│                                              │
│   HTTP API ──┬── /api    puentes, mensajes   │
│              ├── /upload subida directa      │
│              └── /blob   descarga con Range  │
│                                              │
│   WebSocket ──── mensajes nuevos, presencia  │
│                                              │
│   Módulo firewall ──── detectar / aplicar    │
│                                              │
│   Estado ────┬── índice (SQLite)             │
│              └── blobs/ (contenido por hash) │
└──────────────────────────────────────────────┘
      ▲                ▲                ▲
  Navegador VM    Notebook         Navegador torre
```

Todo el estado vive en la carpeta del hub. Copiarla mueve el puente completo.

---

## 5. Modelo de datos

### 5.1 Capas

```
Actor    →  equipo identificado (nombre + cookie en v1)
   ↓
Puente   →  hasta 5 actores, chat propio, dueño
   ↓
Mensaje  →  referencia; lleva actor, pin y vencimiento
   ↓
Blob     →  contenido único, global, deduplicado
```

### 5.2 Tablas del prototipo

| Tabla | Campos |
|---|---|
| `actor` | id, nombre, cookie, creado, último acceso |
| `bridge` | id, nombre, **dueño** (actor), creado, máx_actores |
| `bridge_actor` | bridge, actor, rol, alta |
| `message` | id, **bridge**, **actor**, timestamp, tipo, texto, blob, **pinned**, **expira_en** |
| `blob` | hash, tamaño, creado |

**Corrección respecto a v0.1:** el nombre del archivo vive en `message`, no en `blob` (el mismo contenido puede enviarse con distintos nombres), y no existe columna `refs`: el conteo de referencias se deriva por consulta, porque un contador almacenado se desincroniza y el síntoma es pérdida silenciosa de datos. Ver `puente-schema.sql`.

**Campos presentes pero sin uso en v1:** `rol`, `pinned`, `expira_en`. Cuestan nada ahora y son molestos de agregar sobre datos reales.

**Entidades diferidas:** `device` (identidad criptográfica), `invite`, `upload`, `event`.

### 5.3 Retención (diferida, campos presentes)

- Sin pin: el mensaje expira a los **7 días**.
- Con pin: permanente. El pin se puede aplicar **después** del envío.
- El barrido borra **referencias**, nunca blobs. Un recolector aparte borra blobs con `refs = 0`.
- **Invariante:** un blob no se borra mientras exista un mensaje vivo que lo apunte, aunque esté en otro puente.
- Al implementarse, primero en modo simulación: que registre qué borraría, sin borrar, hasta validar.

### 5.4 Nombres de puente

- 2 actores → nombres completos: `Torre ↔ Notebook`
- 3 o más → dos primeros más contador: `Torre, VM-Ubuntu +2`
- Renombre manual siempre disponible y prioritario.

---

## 6. Módulo de firewall

Sección apartada en la app: detecta el estado, muestra la regla propuesta y la aplica con elevación.

### 6.1 Flujo

1. Detectar sistema y backend de firewall.
2. Comprobar si la regla ya existe. Si sí, no hacer nada.
3. **Mostrar el comando exacto al usuario** antes de ejecutarlo.
4. Pedir elevación y aplicar.
5. Verificar releyendo el estado, no confiando en el código de salida.

### 6.2 Backends

| Sistema | Backend | Elevación |
|---|---|---|
| Windows | `netsh advfirewall` | UAC |
| Linux (Ubuntu, Debian) | `ufw` | `pkexec` o `sudo` |
| Linux (Fedora, RHEL) | `firewalld` | ídem |
| Linux (otros) | `nftables` / `iptables` | ídem |

### 6.3 Trampas conocidas

**En Linux muchas veces no hay nada que hacer.** En Ubuntu de escritorio `ufw` viene inactivo por defecto: el puerto ya está abierto. El módulo debe detectar "sin firewall activo" y decirlo, en vez de habilitar un firewall que nadie pidió solo para abrirle un hueco. Activar protección que el usuario no tenía es un efecto secundario inaceptable.

**En Windows el firewall no es el único problema.** Si la red está clasificada como Pública, el perfil bloquea el descubrimiento aunque la regla exista. El módulo debe detectar el perfil y advertir; cambiarlo es decisión del usuario, no del programa.

**Nunca ejecutar elevado en silencio.** Un programa que corre comandos como administrador sin mostrarlos es exactamente el patrón que no debe normalizarse. El comando se muestra siempre, aunque el usuario no lo lea.

**La elevación puede fallar y es un caso normal**, no un error. Si el usuario cancela el UAC o no tiene `sudo`, la salida esperada es el comando en pantalla para que lo corra a mano.

**Desinstalar debe quitar la regla.** Dejar reglas huérfanas tras formatear contradice la restricción rectora.

### 6.4 Instrucciones para el usuario

Texto que muestra el módulo. El puerto se sustituye por el configurado.

#### Windows

**Paso 1 — Abrir la consola como administrador**

Presiona la tecla Windows, escribe `cmd`, haz clic derecho sobre **Símbolo del sistema** y elige **Ejecutar como administrador**. Windows te va a preguntar si permites cambios: responde **Sí**.

Sin el clic derecho no funciona. Una consola normal ejecuta el comando y falla con un error de permisos.

**Paso 2 — Pegar el comando**

```
netsh advfirewall firewall add rule name="Puente" dir=in action=allow protocol=TCP localport=8080 profile=private
```

Respuesta esperada: `Aceptado.`

`profile=private` limita la regla a redes marcadas como privadas. Si alguna vez conectas el equipo a una red pública, el puerto no queda expuesto ahí.

**Paso 3 — Verificar**

```
netsh advfirewall firewall show rule name="Puente"
```

**Si aun así no conectas desde otro equipo**, el problema no es el firewall sino el perfil de red. Windows clasifica las redes nuevas como Públicas y eso bloquea la conexión aunque la regla exista. Revísalo en Configuración → Red e Internet → tu conexión → **Perfil de red**, y cámbialo a **Privada**.

**Para deshacer** (al desinstalar):

```
netsh advfirewall firewall delete rule name="Puente"
```

#### Linux

**Paso 1 — Averiguar si hay algo que hacer**

Muchas distribuciones de escritorio, incluida Ubuntu, traen el firewall **apagado**. En ese caso el puerto ya está abierto y no hay que tocar nada.

```
sudo ufw status
```

Si responde `Status: inactive`, **terminaste**. No actives el firewall solo para abrirle un hueco: quedarías con una protección que antes no tenías y que nadie pidió.

Si el comando no existe, prueba con `sudo firewall-cmd --state` (Fedora, RHEL).

**Paso 2 — Solo si el firewall está activo**

Con `ufw` (Ubuntu, Debian, Mint):

```
sudo ufw allow 8080/tcp
```

Con `firewalld` (Fedora, RHEL, openSUSE):

```
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

En `firewalld`, sin `--permanent` la regla desaparece al reiniciar, y sin `--reload` no toma efecto ahora. Se necesitan las dos.

**Paso 3 — Verificar**

`sudo ufw status` o `sudo firewall-cmd --list-ports`. El puerto debe aparecer en la lista.

**Para deshacer:**

```
sudo ufw delete allow 8080/tcp
```

```
sudo firewall-cmd --permanent --remove-port=8080/tcp && sudo firewall-cmd --reload
```

---

## 7. Superficie de API (v1)

| Método | Ruta | Función |
|---|---|---|
| POST | `/api/actor` | registrar nombre de equipo, set cookie |
| GET | `/api/bridges` | puentes del actor |
| POST | `/api/bridges` | crear puente (el actor queda como dueño) |
| PATCH | `/api/bridges/{id}` | renombrar |
| POST | `/api/bridges/{id}/actors` | agregar actor (valida máx. 5) |
| GET | `/api/bridges/{id}/messages` | timeline paginado |
| POST | `/api/bridges/{id}/messages` | enviar texto |
| POST | `/api/upload` | subir archivo (valida tamaño) |
| GET | `/blob/{hash}` | descargar con `Range` |
| GET | `/api/firewall` | estado detectado y comando propuesto |
| POST | `/api/firewall/apply` | aplicar con elevación |
| WS | `/ws` | mensajes nuevos y presencia |
| POST | `/api/bridges/{id}/invites` | el dueño genera un enlace de alta (`kind=join`) |
| POST | `/api/actor/reclaim-invite` | el actor genera su propio enlace de recuperación |
| GET | `/api/invites/{token}` | vista previa (puente, vencimiento) antes de canjear |
| POST | `/api/invites/{token}/redeem` | canjear: entra al puente o revincula el actor |
| GET | `/api/invites/{token}/qr.svg` | QR del enlace, para el celular |
| GET | `/i/{token}` | página que resuelve el enlace de invitación |
| POST | `/api/actor/friend-invite` | genera un enlace de amistad (`kind=friend`) |
| GET | `/api/friends` | mis amigos, solicitudes entrantes y salientes |
| POST | `/api/friends/{id}/accept` | aceptar una solicitud entrante |
| POST | `/api/friends/{id}/reject` | rechazar una entrante, o cancelar una saliente |
| DELETE | `/api/friends/{actor_id}` | quitar a alguien de mis amigos |

---

## 8. Configuración del hub

Archivo único en la carpeta de estado.

| Clave | Default | Nota |
|---|---|---|
| `host` | `0.0.0.0` | **no** `127.0.0.1`; el default de casi todo framework es solo localhost, y es la causa número uno de "no conecta desde la VM" |
| `port` | 8080 | |
| `max_file_mb` | 100 | ADR-10 |
| `max_actors_per_bridge` | 5 | ADR-12 |
| `retention_days` | 7 | sin efecto en v1 |

---

## 9. Rendimiento

El plano de datos no debe pasar byte por byte por el intérprete: usar `sendfile` y dejar que el kernel mueva los bytes. Python queda para el plano de control.

Hashear **mientras** se recibe, no releyendo el archivo al final: releer duplica el tiempo de cada subida.

Sobre la velocidad percibida: el factor dominante no es el throughput sino el gesto. Pegar con `Ctrl+V` y que se envíe, arrastrar a cualquier parte de la página, y que el texto aparezca en el otro equipo antes de soltar el mouse.

---

## 10. Límites conocidos

- **Sin control de acceso en v1.** Quien alcanza la URL, entra. Aceptable en LAN doméstica; no lo es en una red compartida.
- **Ser dueño en v1 significa** que los archivos viven en tu disco y que apagar el proceso apaga el puente. **No** significa poder negarle acceso a nadie: sin identidad no hay a quién negarle. El rol se guarda; la capacidad llega con ADR-07.
- **Quien controla el hub tiene poder absoluto**, porque tiene el disco y puede leer los blobs sin pasar por la app. El rol de dueño es gestión, no barrera frente al dueño del hardware.
- **[v2] La revocación detiene el acceso futuro, no el pasado.** Lo ya descargado no se recupera.

---

## 11. Riesgos abiertos

| Riesgo | Mitigación |
|---|---|
| VM con adaptador NAT no ve la torre | adaptador en modo bridge; probar antes de codificar |
| Windows marca la red como Pública | detectar y advertir desde el módulo de firewall |
| Hub escuchando solo en localhost | `host = 0.0.0.0` por configuración |
| Disco lleno | sin retención en v1; vigilar manualmente |
| El hub se apaga | puente no disponible; asumido por ADR-01 |

---

## 12. Ventana de información en la app

Sección consultable en cualquier momento, no un modal de bienvenida que se cierra y no vuelve. Con cifras concretas.

**En v1 debe cubrir:** que cualquiera en la red puede entrar; el límite de tamaño y por qué existe; que nada se borra todavía; qué hace el módulo de firewall y qué comando ejecuta; qué se pierde y qué sobrevive al formatear.

**Se agrega en v2:** regla de 7 días y comportamiento del pin; roles y qué implica invitar; por qué un archivo a veces sube en un segundo (deduplicado); el límite de la revocación.
