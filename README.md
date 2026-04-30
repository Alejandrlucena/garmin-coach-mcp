# Garmin Coach MCP · by AlejandrLucena

Servidor MCP que conecta tus datos reales de Garmin Connect con Claude y ChatGPT.
Sin exportar nada, sin copiar JSONs — pregunta y obtendrás respuestas basadas en tus datos en tiempo real.

Desplegado en Railway con transporte HTTP streamable (FastMCP 3.2.4).

---

## Herramientas disponibles (37 total)

### Snapshot diario y caché
| Herramienta | Descripción |
|---|---|
| `get_cache_status` | Estado del caché y última sincronización |
| `get_cached_snapshot` | Snapshot completo en caché (sin nueva llamada a Garmin) |
| `get_day_snapshot` | Snapshot completo de un día específico |
| `get_raw_sources` | Datos brutos de Garmin sin procesar |
| `get_primary_device_info` | Información del dispositivo principal |

### Actividades
| Herramienta | Descripción |
|---|---|
| `get_recent_activities` | Lista de actividades recientes |
| `get_activity_fit_download` | Descarga el fichero .fit de una actividad |
| `get_activity_full` | Datos completos de una actividad (con series temporales opcional) |
| `get_activity_time_series` | Series temporales de FC, ritmo, etc. de una actividad |
| `get_recent_activities_full` | Datos completos de las últimas N actividades |
| `get_activity_all_data` | Todos los datos disponibles de una actividad |
| `get_recent_activities_catalog` | Catálogo compacto de actividades recientes |
| `get_recent_activities_all_data` | Datos completos de las últimas N actividades con series |
| `get_activity_sport_profile` | Perfil deportivo de una actividad |
| `get_recent_activity_sport_profiles` | Perfiles deportivos de las últimas N actividades |
| `get_activity_visible_profile` | Vista de actividad alineada con Garmin Connect ES |
| `get_activity_evaluation` | Evaluación del entrenador virtual de Garmin para una actividad |
| `get_activities_paged` | Historial paginado de actividades (hasta 100 por página) |
| `get_activities_in_range` | Actividades entre dos fechas con filtro por tipo |

### Vistas híbridas (resumen inteligente)
| Herramienta | Descripción |
|---|---|
| `get_window_rollup` | Resumen agregado de los últimos N días |
| `get_hybrid_recent_overview` | Vista híbrida reciente — actividades + métricas |
| `get_hybrid_coach_snapshot` | Snapshot de coach con estado de forma y carga |
| `get_hybrid_coach_decision` | Decisión de entrenamiento: descansar o entrenar |
| `get_hybrid_user_briefing` | Briefing completo del usuario para el día |
| `get_hybrid_nutrition_briefing` | Briefing de nutrición e hidratación |

### Historial y wellness por rango
| Herramienta | Descripción |
|---|---|
| `get_daily_wellness` | Métricas completas de un día (pasos, BB, sueño, HRV…) |
| `get_wellness_range` | Resumen wellness diario compacto para un rango (máx 30 días) |

### Rendimiento y predicciones
| Herramienta | Descripción |
|---|---|
| `get_race_predictions` | Predicciones de tiempo para 5K, 10K, media maratón y maratón |
| `get_personal_records` | Récords personales por distancia y tipo de actividad |
| `get_fitness_age` | Edad física (Fitness Age) calculada por Garmin |
| `get_endurance_score` | Puntuación de resistencia aeróbica (Endurance Score) |
| `get_hill_score` | Puntuación de rendimiento en montaña/desnivel (Hill Score) |

### Objetivos, material y peso
| Herramienta | Descripción |
|---|---|
| `get_goals` | Objetivos de entrenamiento activos, futuros o pasados |
| `get_gear` | Material deportivo registrado (zapatillas, bicis) con estadísticas |
| `get_weigh_ins` | Historial de pesajes en un rango de fechas |
| `add_weigh_in` | Registra un nuevo pesaje en Garmin Connect |

---

## Despliegue en Railway

### Requisitos previos
- Cuenta en [Railway](https://railway.app)
- Cuenta en [Garmin Connect](https://connect.garmin.com)
- Python 3.11+

### Paso 1 — Fork y conecta el repo

1. Haz fork de este repositorio
2. En Railway: **New Project → Deploy from GitHub repo**
3. Selecciona tu fork

### Paso 2 — Añade un volumen

El servidor guarda los tokens de autenticación de Garmin en disco para no tener que re-autenticarse en cada reinicio.

En Railway → tu servicio → **Volumes** → **Add Volume**:
- Mount path: `/data`

### Paso 3 — Variables de entorno

En Railway → tu servicio → **Variables**:

| Variable | Descripción | Obligatorio |
|---|---|---|
| `GARMIN_EMAIL` | Email de tu cuenta Garmin Connect | ✓ |
| `GARMIN_PASSWORD` | Contraseña de Garmin Connect | ✓ |
| `GARMIN_TIMEZONE` | Tu zona horaria, ej: `Europe/Madrid` | recomendado |
| `CACHE_MINUTES` | Minutos entre refrescos del caché (defecto: `30`) | opcional |
| `PORT` | Railway lo asigna automáticamente | automático |

> **Nota:** Las credenciales se usan para hacer login en Garmin Connect y obtener tokens OAuth. No se almacenan en texto plano después del primer login.

### Paso 4 — Primer login

Tras el primer despliegue, el servidor intentará autenticarse con Garmin automáticamente. Si Garmin pide verificación por email o MFA, revisa los logs de Railway para ver si hay algún paso manual.

### Paso 5 — Conectar con Claude o ChatGPT

Una vez desplegado, Railway te da una URL pública. La URL del endpoint MCP es:

```
https://tu-proyecto.up.railway.app/mcp
```

**En Claude (claude.ai o app móvil):**
Configuración → Conectores → Añadir conector MCP → pega la URL

**En ChatGPT:**
Ajustes → Conectores → URL personalizada → pega la URL

### Verificar que funciona

Abre en el navegador:
```
https://tu-proyecto.up.railway.app/health
```

Deberías ver algo como:
```json
{
  "status": "ok",
  "app": "Garmin Coach MCP",
  "cache_status": "ok"
}
```

---

## Desarrollo local

```bash
# Clona el repo
git clone https://github.com/tu-usuario/garmin-coach-mcp
cd garmin-coach-mcp

# Crea entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instala dependencias
pip install -r requirements.txt

# Variables de entorno
export GARMIN_EMAIL="tu@email.com"
export GARMIN_PASSWORD="tu_contraseña"
export GARMIN_TIMEZONE="Europe/Madrid"

# Arranca el servidor
python server.py
```

El servidor queda en `http://localhost:8000/mcp`.

---

## Actualizar en Railway

```bash
git push origin main
```

Railway detecta el push y redespliegue automáticamente.

---

## Proyectos relacionados

- [garmin-entreno](https://github.com/luce23/garmin-entreno) — Visualizador web de entrenamientos que consume los datos de este conector
