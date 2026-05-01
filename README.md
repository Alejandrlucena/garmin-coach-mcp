# Garmin Coach MCP

Servidor MCP que conecta Garmin Connect con Claude y ChatGPT — 57 herramientas, datos en tiempo real · by AlejandrLucena

---

## Qué es

Servidor FastMCP que autentica contra Garmin Connect, descarga métricas y actividades reales, y las expone como tools MCP para que Claude las use como entrenador, analista y apoyo nutricional.

Se despliega en Railway (el servidor vive ahí aunque el Mac esté apagado) y también puede correr localmente para alimentar el [visualizador web](https://github.com/Alejandrlucena/garmin-entreno).

---

## Flujo

```
Garmin Connect → garminconnect (Python) → server.py → Railway → Claude / Web / Móvil
```

---

## Endpoints HTTP

| Ruta | Descripción |
|------|-------------|
| `GET /` | Sirve el visualizador web (`index.html`) si está en `../` |
| `GET /health` | Estado del servidor y del caché |
| `GET /activities?limit=30` | Lista de actividades recientes (JSON) con CORS |
| `GET /download/{activity_id}` | Descarga el .zip/.fit de una actividad con CORS |
| `GET /config` | Lee la configuración web guardada en el volumen Railway |
| `POST /config` | Guarda configuración web (solo clave `driveUrl`) en el volumen Railway |
| `POST /mcp` | Endpoint MCP principal para Claude |
| `GET /debug/activities` | Debug: últimas 5 actividades |
| `GET /debug/audit` | Debug: métricas normalizadas del caché |

Todos los endpoints incluyen CORS completo (`allow_origins=["*"]`) — el visualizador web puede llamarlos directamente desde el navegador, incluyendo desde móvil.

Si los tokens locales han expirado, `/activities` y `/download` hacen fallback automático a la URL definida en `RAILWAY_FALLBACK_URL`.

---

## Instalación local

```bash
# 1. Clonar
git clone https://github.com/Alejandrlucena/garmin-coach-mcp.git
cd garmin-coach-mcp

# 2. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Autenticar con Garmin (genera tokens en ~/.garminconnect/)
python login_once.py

# 5. Arrancar
python server.py
# → http://localhost:8000
```

Abre `http://localhost:8000` en el navegador para usar el visualizador web sin problemas de CORS.

---

## Despliegue en Railway

1. Fork este repo en GitHub
2. Conecta el repo en [railway.app](https://railway.app)
3. Añade un volumen montado en `/data`
4. Variables de entorno necesarias:
   - `GARMIN_TOKENS_JSON` — JSON de tokens obtenido con `login_once.py`
   - `PORT` — Railway lo pone automáticamente
5. Para redesplegar: `railway up` desde la carpeta del proyecto (requiere Railway CLI)

---

## Variables de entorno

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `PORT` | `8000` | Puerto del servidor |
| `GARMIN_TOKEN_DIR` | `~/.garminconnect` | Carpeta de tokens |
| `GARMIN_TOKENS_JSON` | — | Tokens en JSON/base64 (para Railway) |
| `GARMIN_TIMEZONE` | `Europe/Madrid` | Zona horaria local |
| `CACHE_MINUTES` | `30` | Minutos entre refresco de caché |
| `ACTIVITY_LIMIT` | `8` | Límite de actividades en caché |
| `RAILWAY_FALLBACK_URL` | URL Railway prod | Fallback si tokens locales fallan |

---

## Configuración web persistente (`/config`)

El endpoint `/config` almacena la URL del Google Apps Script de Drive en el volumen de Railway (`/data/web_config.json`). Esto permite que el visualizador web sincronice su configuración automáticamente en todos los dispositivos: basta con introducir la URL del servidor una sola vez y la URL de Drive se carga sola.

- `GET /config` — devuelve `{"driveUrl": "..."}` o `{}`
- `POST /config` — acepta `{"driveUrl": "..."}` y lo persiste en disco

Solo se permite la clave `driveUrl`. No se almacena ningún dato de usuario ni credencial.

---

## Uso con el visualizador web

El visualizador [garmin-entreno](https://github.com/Alejandrlucena/garmin-entreno) tiene un botón **🔌 Conector** que carga el `.fit` con un clic y renderiza la tabla directamente. Cada usuario configura la URL de su propio servidor en **⚙ Configurar**.

- Despliega este repo en Railway, copia la URL que te dé y pégala en **⚙**
- O arranca el servidor en local (`http://localhost:8000`) — sirve el `index.html` directamente, sin problemas de CORS
- Solo muestra actividades con datos de splits (oculta fuerza, yoga, etc.)

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
