# Garmin Coach MCP

Servidor MCP que conecta Garmin Connect con Claude y ChatGPT — 95 herramientas, datos en tiempo real · by AlejandrLucena

---

## Tutorial paso a paso (desde cero, sin saber nada)

Este tutorial asume que **no tienes ni idea** de GitHub ni Railway. Todo se hace en el navegador, en móvil o PC. Tiempo: ~10 minutos.

### Lo que necesitas antes de empezar
- Tu cuenta de **Garmin Connect** (la del reloj).
- Una cuenta de **GitHub** (gratis). Si no tienes: ve a [github.com](https://github.com) → **Sign up**.
- Una **IA con soporte de conectores MCP**: Claude, ChatGPT u otra compatible con MCP.

---

### Paso 1 · Haz una copia del proyecto (fork)

Un "fork" es tu copia personal del proyecto en tu propia cuenta de GitHub.

1. Abre el proyecto: <https://github.com/Alejandrlucena/garmin-coach-mcp>
2. Arriba a la derecha, pulsa el botón **Fork**.
3. En la pantalla que sale, pulsa **Create fork**.
4. Ahora tienes tu copia en `https://github.com/TU-USUARIO/garmin-coach-mcp`.

### Paso 2 · Crea tu cuenta de Railway (con GitHub)

Railway es donde vivirá tu servidor (gratis para empezar).

1. Ve a [railway.com](https://railway.com).
2. Pulsa **Login** → **Login with GitHub**.
3. Autoriza a Railway a acceder a tu GitHub (botón verde **Authorize**).

### Paso 3 · Despliega tu copia

1. En Railway, pulsa **New Project** (o **+ New**).
2. Elige **Deploy from GitHub repo**.
3. La primera vez te pedirá dar permiso: pulsa **Configure GitHub App** → marca tu fork `garmin-coach-mcp` (o "All repositories") → **Save**, y vuelve atrás.
4. Selecciona tu repo `garmin-coach-mcp` en la lista.
5. Railway detecta el `Dockerfile` y empieza a construir solo. Espera a que el deploy se ponga **Active** (verde). Tarda 2-5 min.

### Paso 4 · Consigue la dirección web de tu servidor

1. Cuando esté **Active**, entra en tu servicio.
2. Ve a **Settings** → sección **Networking** → pulsa **Generate Domain**.
3. Si te pregunta un puerto, pon **8000**.
4. Te dará una dirección tipo `https://tu-proyecto.up.railway.app`. **Esa es tu web.**

### Paso 5 · Configura todo desde el panel (sin tocar nada raro)

Abre tu dirección web. Verás un **panel** con una lista de pasos. Pulsa cada botón y rellena lo que te pida:

1. **Conectar** → tu email de Garmin + contraseña + el código que te llega al Gmail (MFA).
2. **Guardado permanente** → pega un "Railway API token". El propio panel te explica con un enlace de dónde sacarlo (Railway → Account → Tokens). Esto hace que no tengas que re-loguearte cada vez que el servidor reinicie.
3. **Protección con contraseña** → eliges una contraseña para que solo tú puedas abrir el panel.

Cada paso se pone en **verde ✅** cuando está hecho. **Nunca tienes que tocar "variables de entorno" ni nada técnico.**

### Paso 6 · Conéctalo a tu IA (Claude, ChatGPT, etc.)

Funciona con cualquier IA que acepte conectores MCP.

1. En el panel, pulsa **Copiar URL del conector** (es `https://tu-proyecto.up.railway.app/mcp`).
2. En tu IA, ve a la sección de conectores/MCP y añade un conector personalizado:
   - **Claude**: Settings → **Connectors** → **Add custom connector**.
   - **ChatGPT**: Settings → **Connectors** (MCP) → añadir servidor.
   - **Otras**: busca "MCP" o "conector personalizado" y pega la URL.
3. Pega la URL → guarda.
4. Listo. Ya puedes pedirle tus métricas de Garmin.

---

### ¿Necesitas re-loguearte en el futuro?

Cuando Garmin caduque tu sesión (raro, ~1 año) o cambies de contraseña en Garmin:
- Abre tu panel (te pedirá tu contraseña), pulsa **Re-loguear Garmin** y repite el Paso 5.1. Desde el móvil, en 1 minuto.

---

## Cómo se ve

### El recorrido completo

```
①  Fork en GitHub  +  Deploy en Railway
        │
②  Abrir la URL  ───────────►   aparece el Panel de estado
        │
③  [Conectar]                   email · contraseña · código MFA
        │
④  [Guardado permanente]        pegar Railway API token
        │
⑤  [Protección]                 elegir contraseña (con ojito 👁)
        │
⑥  Copiar URL /mcp  ────────►   pegar en Claude → Connectors
        │
      ✅  Listo
```

### El panel (`/`)

```
Garmin Coach MCP · Panel de estado
══════════════════════════════════

Estado del setup
  ✅  Servidor desplegado          Activo y respondiendo
  ✅  Garmin conectado             Tokens válidos, caché al día
  ✅  Guardado permanente          Aguanta reinicios
  ⚠️  Protección con contraseña    [ Activar ]
  ⚠️  Claude sin conectar          [ Cómo conectar ]

Acciones
  [ Re-loguear Garmin ]
  [ Copiar URL para Claude ]
  [ Abrir Railway Variables ]
  [ Bloquear sesión ]
```

### Pantalla de acceso (cuando hay contraseña)

```
Panel protegido
───────────────
Introduce tu contraseña para acceder.

  Contraseña:  [ ••••••••••          👁 ]

  [ Entrar ]

  ▸ ¿No recuerdas la contraseña?
```

### Asistente de Garmin (3 pasos)

```
 Paso 1 ─ Email + contraseña      ●○○
 Paso 2 ─ Código MFA del Gmail    ○●○
 Paso 3 ─ Confirmación            ○○●
```

---

## El panel y los asistentes web

Todo se hace desde el navegador, sin terminal. El servidor sirve un panel en `/` con asistentes guiados:

- **`/` (panel de estado)**: muestra cada paso del setup (servidor, Garmin, guardado permanente, protección, Claude) en verde ✅ o pendiente ⚠️, con su botón de acción.
- **Conectar Garmin**: reemplaza a `login_once.py`. Email + contraseña + MFA, todo web, en 3 pasos.
- **Guardado permanente**: pega un Railway API token; el servidor guarda `GARMIN_TOKENS_JSON` y `RAILWAY_API_TOKEN` en Railway vía su API (usando `curl_cffi` para pasar Cloudflare). Cero copy-paste manual de variables.
- **Protección con contraseña**: eliges tu propia contraseña (o generas una al azar). El servidor la guarda en Railway (`ADMIN_TOKEN`) **y** en un archivo local que lee en vivo → los cambios de contraseña son **instantáneos, sin reiniciar el servidor**.
- **Auto-sync opcional**: con `AUTO_SYNC_TOKENS=1`, un hilo de fondo sincroniza el token maestro a Railway si rota.

### Detalles del acceso por contraseña

- **Campo con ojito 👁**: la contraseña va oculta por defecto; pulsa el ojo para mostrarla u ocultarla.
- **Sesión deslizante**: tras entrar, el navegador te recuerda 365 días y renueva el plazo en cada visita (como Instagram/X/TikTok). No te pide la contraseña una y otra vez.
- **Bloquear sesión**: botón en el panel que borra la cookie; la próxima visita vuelve a pedir contraseña (útil en equipos compartidos).
- **Cambiar contraseña**: botón **Cambiar** en la fila de Protección. Aplica al instante.
- **¿Olvidaste la contraseña?**: la pantalla de bloqueo incluye un desplegable con enlace directo a las Variables de Railway, donde está/cambias `ADMIN_TOKEN`.

---

## Flujo técnico

```
Garmin Connect → garminconnect (Python) → server.py → Railway → Claude / Web / Móvil
```

---

## Endpoints HTTP

| Ruta | Descripción |
|------|-------------|
| `GET /` | Panel de estado y configuración (pide contraseña si está protegido) |
| `GET /lock` | Cierra la sesión del panel (borra la cookie) |
| `GET /login` | Wizard web para conectar / re-loguear en Garmin |
| `GET/POST /setup/persistencia` | Asistente para activar el guardado permanente (Railway API token) |
| `GET/POST /setup/proteccion` | Asistente para poner / cambiar la contraseña del panel |
| `GET /health` | Estado del servidor y del caché |
| `GET /activities?limit=30` | Lista de actividades recientes (JSON) con CORS |
| `GET /download/{activity_id}` | Descarga el .zip/.fit de una actividad con CORS |
| `GET /config` · `POST /config` | Configuración web persistida (solo clave `driveUrl`) |
| `POST /mcp` | Endpoint MCP principal para Claude |
| `GET /debug/activities` · `GET /debug/audit` | Debug: actividades / métricas del caché |

Todos los endpoints incluyen CORS completo (`allow_origins=["*"]`).

Si defines `RAILWAY_FALLBACK_URL` (vacío por defecto), `/activities` y `/download` pueden reenviar a otra instancia cuando fallan los tokens locales. En despliegues normales no hace falta.

---

## Instalación local (solo para desarrollo)

Solo necesitas esto si vas a modificar el código. Para uso normal, sigue el Quick Start de arriba.

```bash
git clone https://github.com/Alejandrlucena/garmin-coach-mcp.git
cd garmin-coach-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python login_once.py          # autentica y genera tokens locales
python server.py              # → http://localhost:8000
```

---

## Variables de entorno

> No necesitas poner ninguna a mano: los asistentes web del panel las configuran por ti. Esta tabla es solo de referencia.

### Gestionadas por los asistentes web
| Variable | Descripción |
|----------|-------------|
| `GARMIN_TOKENS_JSON` | Tokens de Garmin (JSON o base64). La crea y actualiza el wizard de "Conectar Garmin". |
| `RAILWAY_API_TOKEN` | Token de Railway para que los asistentes guarden variables solos. Lo configura "Guardado permanente". |
| `ADMIN_TOKEN` | Contraseña del panel. La pone/cambia el asistente "Protección con contraseña". Mientras no exista, el panel está abierto (sin contraseña); una vez existe, el panel la pide. |

### Opcionales
| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `PORT` | `8000` | Puerto del servidor (Railway lo asigna) |
| `GARMIN_TOKEN_DIR` | `~/.garminconnect` | Carpeta de tokens en local |
| `GARMIN_TIMEZONE` | `Europe/Madrid` | Zona horaria local |
| `GARMIN_LANGUAGE` | `es` | Idioma de traducciones |
| `CACHE_MINUTES` | `30` | Minutos entre refresco de caché |
| `ACTIVITY_LIMIT` | `8` | Límite de actividades en caché |
| `AUTO_SYNC_TOKENS` | `0` | Si `1`, sincroniza el OAuth1 rotado a Railway cada 12h |
| `AUTO_SYNC_INTERVAL_SECONDS` | `43200` | Intervalo del auto-sync (mínimo 3600) |
| `RAILWAY_FALLBACK_URL` | _(vacío)_ | Opcional: reenvía a otra instancia si fallan los tokens locales |

### Inyectadas automáticamente por Railway (no las pongas tú)
- `RAILWAY_PROJECT_ID`, `RAILWAY_ENVIRONMENT_ID`, `RAILWAY_SERVICE_ID`

---

## Configuración web persistente (`/config`)

El endpoint `/config` almacena la URL del Google Apps Script de Drive en el volumen de Railway (`/data/web_config.json`). Esto permite que el visualizador web sincronice su configuración automáticamente en todos los dispositivos: basta con introducir la URL del servidor una sola vez y la URL de Drive se carga sola.

- `GET /config` — devuelve `{"driveUrl": "..."}` o `{}`
- `POST /config` — acepta `{"driveUrl": "..."}` y lo persiste en disco

Solo se permite la clave `driveUrl`. No se almacena ningún dato de usuario ni credencial.

---

## Uso con el visualizador web

El visualizador [garmin-laps](https://github.com/Alejandrlucena/garmin-laps) tiene un botón **🔌 Conector** que carga la actividad con un clic y renderiza la tabla directamente. Cada usuario configura la URL de su propio servidor en **⚙ Configurar**.

- Despliega este repo en Railway, copia la URL que te dé y pégala en **⚙**
- O arranca el servidor en local (`http://localhost:8000`) — sirve el `index.html` directamente, sin problemas de CORS
- Soporta running, ciclismo y motorsport (moto, coche, kart) — el visualizador adapta las columnas según el tipo de actividad
- Filtros de tipo en el panel: 🗂️ Todo · 🏃 Running · 🚴 Ciclismo · 🏍️ Motorsport 🏎️ (busca entre las últimas 500 actividades)
- Solo muestra actividades con datos de splits (oculta fuerza, yoga, etc.)

---

## Herramientas MCP (95)

### Snapshot y caché
`get_day_snapshot` · `get_cached_snapshot` · `get_raw_sources` · `get_cache_status` · `refresh_snapshot` · `get_window_rollup`

### Actividades
`get_recent_activities` · `get_recent_activities_full` · `get_recent_activities_catalog` · `get_recent_activities_all_data` · `get_activities_paged` · `get_activities_in_range` · `get_last_activity` · `get_activity_full` · `get_activity_all_data` · `get_activity_sport_profile` · `get_activity_visible_profile` · `get_activity_splits` · `get_activity_split_summaries` · `get_activity_time_series` · `get_activity_hr_in_timezones` · `get_activity_evaluation` · `get_activity_exercise_sets` · `get_activity_gear` · `get_activity_weather` · `get_activity_types` · `get_recent_activity_sport_profiles` · `get_activity_fit_download` · `download_activity` · `upload_activity`

### Métricas diarias
`get_stats` · `get_stats_and_body` · `get_daily_wellness` · `get_user_summary` · `get_steps_data` · `get_daily_steps` · `get_floors` · `get_all_day_stress` · `get_stress_data` · `get_heart_rates` · `get_rhr_day` · `get_body_battery` · `get_respiration_data` · `get_spo2_data` · `get_hydration_data` · `get_blood_pressure` · `get_body_composition`

### Sueño y recuperación
`get_sleep_data` · `get_hrv_data` · `get_training_readiness` · `get_wellness_range`

### Entrenamiento y rendimiento
`get_training_status` · `get_max_metrics` · `get_endurance_score` · `get_hill_score` · `get_race_predictions` · `get_personal_records` · `get_progress_summary` · `get_primary_device_info` · `get_fitness_age`

### Dispositivos y equipamiento
`get_devices` · `get_device_settings` · `get_device_last_used` · `get_device_alarms` · `get_gear` · `get_gear_defaults` · `get_gear_stats` · `set_gear_default`

### Peso y salud
`get_weigh_ins` · `get_daily_weigh_ins` · `add_weigh_in` · `delete_weigh_in` · `delete_weigh_ins`

### Retos y badges
`get_goals` · `get_earned_badges` · `get_available_badge_challenges` · `get_badge_challenges` · `get_adhoc_challenges` · `get_inprogress_virtual_challenges` · `get_non_completed_badge_challenges`

### Workouts y planes
`get_workout_library` · `get_workout_detail` · `get_todays_workout` · `get_scheduled_workouts` · `schedule_workout` · `unschedule_workout` · `get_training_plans` · `get_training_plan_detail`

### Nutrición
`get_nutrition_log`

### Perfil de usuario
`get_user_profile_info`

### Hybrid Coach (Claude-native)
`get_hybrid_user_briefing` · `get_hybrid_coach_snapshot` · `get_hybrid_coach_decision` · `get_hybrid_recent_overview` · `get_hybrid_nutrition_briefing`

---

## Archivos

| Archivo | Descripción |
|---------|-------------|
| `server.py` | Servidor principal — tools MCP + endpoints HTTP |
| `login_once.py` | Script para autenticar y generar tokens locales |
| `requirements.txt` | Dependencias Python |
| `Dockerfile` | Para despliegue en Railway |
| `railway.toml` | Configuración Railway |
| `bootstrap.sh` | Script de inicio en Railway |
| `docker-compose.yml` | Para uso local con Docker |
| `nginx.conf` | Config Nginx para proxy local |
| `.env.example` | Variables de entorno de ejemplo |

