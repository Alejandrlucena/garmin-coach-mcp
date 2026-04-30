# Garmin Coach MCP · by AlejandrLucena

Servidor MCP que conecta tus datos reales de Garmin Connect con Claude y ChatGPT.
Sin exportar nada, sin copiar JSONs — pregunta y obtendrás respuestas basadas en tus datos en tiempo real.

Desplegado en Railway con transporte HTTP streamable (FastMCP 3.2.4).

---

## Ficheros del proyecto

| Fichero | Para qué sirve |
|---|---|
| `server.py` | El servidor MCP con las 57 herramientas. Es el núcleo del proyecto |
| `requirements.txt` | Las 3 dependencias Python: `fastmcp`, `garminconnect`, `curl_cffi` |
| `Dockerfile` | Define el contenedor: Python 3.11, instala dependencias, arranca `server.py` |
| `railway.toml` | Configuración de Railway: usa Dockerfile, reinicia si falla, healthcheck en `/health` |
| `login_once.py` | Hace el primer login de Garmin en local y muestra el token JSON para copiarlo en Railway |
| `bootstrap.sh` | Script todo-en-uno: instala Python/Railway, hace login, crea el proyecto y despliega automáticamente |

---

## Despliegue en Railway

### Opción A — Automático con bootstrap.sh (recomendado)

```bash
chmod +x bootstrap.sh
./bootstrap.sh
```

El script hace todo solo: instala dependencias, te pide las credenciales de Garmin, crea el proyecto en Railway y despliega. Al final te da la URL del servidor.

### Opción B — Manual paso a paso

**1. Obtener el token de Garmin**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python login_once.py
```

Introduce tu email y contraseña de Garmin. Si tienes MFA activado, introduce el código que te llegue por email. Al final te muestra el JSON del token — cópialo entero.

**2. Crear el proyecto en Railway**

1. Ve a [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
2. Selecciona tu fork de este repositorio
3. Railway detecta el `Dockerfile` automáticamente

**3. Añadir volumen persistente**

Railway → tu servicio → **Volumes** → **Add Volume** → Mount path: `/data`

El volumen guarda los tokens para que no haya que re-autenticarse en cada reinicio.

**4. Variables de entorno**

Railway → tu servicio → **Variables**:

| Variable | Descripción | Obligatorio |
|---|---|---|
| `GARMIN_EMAIL` | Email de tu cuenta Garmin Connect | ✓ |
| `GARMIN_PASSWORD` | Contraseña de Garmin Connect | ✓ |
| `GARMIN_TOKENS_JSON` | Token JSON obtenido con `login_once.py` | recomendado |
| `GARMIN_TIMEZONE` | Tu zona horaria, ej: `Europe/Madrid` | recomendado |
| `CACHE_MINUTES` | Minutos entre refrescos del caché (defecto: `30`) | opcional |

**5. Verificar que funciona**

```
https://tu-proyecto.up.railway.app/health
```

Respuesta esperada:
```json
{ "status": "ok", "app": "Garmin Coach MCP", "cache_status": "ok" }
```

**6. Conectar con Claude o ChatGPT**

URL del endpoint MCP:
```
https://tu-proyecto.up.railway.app/mcp
```

- **Claude:** Configuración → Conectores → Añadir conector MCP → pega la URL
- **ChatGPT:** Ajustes → Conectores → URL personalizada → pega la URL

---

## Actualizar

```bash
git push origin main
```

Railway redespliegue automáticamente al detectar el push.

---

## Herramientas disponibles (57 total)

### Snapshot diario y caché
| Herramienta | Descripción |
|---|---|
| `get_cache_status` | Estado del caché y última sincronización |
| `get_cached_snapshot` | Snapshot completo en caché (sin nueva llamada a Garmin) |
| `get_day_snapshot` | Snapshot completo de un día específico |
| `get_raw_sources` | Datos brutos de Garmin sin procesar |
| `get_primary_device_info` | Información del dispositivo principal |

### Actividades — listado e historial
| Herramienta | Descripción |
|---|---|
| `get_recent_activities` | Lista de actividades recientes |
| `get_last_activity` | Última actividad registrada (acceso rápido) |
| `get_activity_types` | Tipos de actividad disponibles en Garmin |
| `get_activities_paged` | Historial paginado (hasta 100 por página) |
| `get_activities_in_range` | Actividades entre dos fechas con filtro por tipo |

### Actividades — datos detallados
| Herramienta | Descripción |
|---|---|
| `get_activity_fit_download` | Descarga el fichero .fit de una actividad |
| `get_activity_full` | Datos completos con series temporales opcionales |
| `get_activity_time_series` | Series temporales de FC, ritmo, potencia, etc. |
| `get_activity_all_data` | Todos los datos disponibles de una actividad |
| `get_activity_sport_profile` | Perfil deportivo de una actividad |
| `get_activity_visible_profile` | Vista alineada con Garmin Connect ES |
| `get_activity_evaluation` | Evaluación del entrenador virtual de Garmin |
| `get_activity_splits` | Splits kilométricos detallados |
| `get_activity_split_summaries` | Resumen de splits por bloque/fase |
| `get_activity_hr_in_timezones` | Distribución del tiempo por zona de FC |
| `get_activity_exercise_sets` | Series de fuerza: ejercicio, reps, peso |
| `get_activity_weather` | Condiciones meteorológicas durante el entreno |
| `get_activity_gear` | Material usado en una actividad concreta |

### Actividades — vistas múltiples
| Herramienta | Descripción |
|---|---|
| `get_recent_activities_full` | Datos completos de las últimas N actividades |
| `get_recent_activities_catalog` | Catálogo compacto de actividades recientes |
| `get_recent_activities_all_data` | Datos completos con series de las últimas N |
| `get_recent_activity_sport_profiles` | Perfiles deportivos de las últimas N actividades |

### Vistas híbridas (resumen inteligente)
| Herramienta | Descripción |
|---|---|
| `get_window_rollup` | Resumen agregado de los últimos N días |
| `get_hybrid_recent_overview` | Vista híbrida reciente — actividades + métricas |
| `get_hybrid_coach_snapshot` | Snapshot de coach con estado de forma y carga |
| `get_hybrid_coach_decision` | Decisión de entrenamiento: descansar o entrenar |
| `get_hybrid_user_briefing` | Briefing completo del usuario para el día |
| `get_hybrid_nutrition_briefing` | Briefing de nutrición e hidratación |

### Wellness diario
| Herramienta | Descripción |
|---|---|
| `get_daily_wellness` | Métricas completas de un día (pasos, BB, sueño, HRV…) |
| `get_wellness_range` | Resumen wellness compacto para un rango (máx 30 días) |
| `get_all_day_stress` | Curva de estrés minuto a minuto durante el día |
| `get_steps_data` | Serie temporal de pasos (intervalos de 15 min) |
| `get_daily_steps` | Pasos diarios totales en un rango de fechas |
| `get_floors` | Pisos subidos y bajados durante el día |
| `get_stats_and_body` | Resumen combinado de actividad + composición corporal |
| `get_blood_pressure` | Registros de presión arterial en un rango de fechas |

### Rendimiento y predicciones
| Herramienta | Descripción |
|---|---|
| `get_race_predictions` | Predicciones para 5K, 10K, media maratón y maratón |
| `get_personal_records` | Récords personales por distancia y tipo |
| `get_fitness_age` | Edad física (Fitness Age) calculada por Garmin |
| `get_endurance_score` | Puntuación de resistencia aeróbica |
| `get_hill_score` | Puntuación de rendimiento en desnivel |
| `get_progress_summary` | Progresión de distancia/tiempo/calorías entre fechas |

### Objetivos, material y peso
| Herramienta | Descripción |
|---|---|
| `get_goals` | Objetivos de entrenamiento activos, futuros o pasados |
| `get_gear` | Material deportivo registrado con estadísticas |
| `get_weigh_ins` | Historial de pesajes en un rango de fechas |
| `add_weigh_in` | Registra un nuevo pesaje en Garmin Connect |

### Retos e insignias
| Herramienta | Descripción |
|---|---|
| `get_earned_badges` | Insignias y logros conseguidos |
| `get_badge_challenges` | Retos de insignias activos |
| `get_adhoc_challenges` | Retos espontáneos activos |
| `get_available_badge_challenges` | Retos disponibles para unirse |

### Dispositivo
| Herramienta | Descripción |
|---|---|
| `get_device_last_used` | Último dispositivo Garmin sincronizado |

---

## Proyectos relacionados

- [garmin-entreno](https://github.com/Alejandrlucena/garmin-entreno) — Visualizador web de entrenamientos que consume los datos de este conector
