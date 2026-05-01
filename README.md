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
| `POST /mcp` | Endpoint MCP principal para Claude |
| `GET /debug/activities` | Debug: últimas 5 actividades |
| `GET /debug/audit` | Debug: métricas normalizadas del caché |

Todos los endpoints incluyen CORS completo (`allow_origins=["*"]`) — el visualizador web puede llamarlos directamente desde el navegador, incluyendo desde móvil.

Si los tokens locales han expirado, `/activities` y `/download` hacen fallback automático al servidor Railway de producción.

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

## Uso con el visualizador web

El visualizador [garmin-entreno](https://github.com/Alejandrlucena/garmin-entreno) tiene un botón **🔌 Conector** que:

- Por defecto apunta al servidor Railway (funciona desde cualquier dispositivo sin configuración)
- Muestra solo actividades con datos de splits (oculta fuerza, yoga, etc.)
- Carga el `.fit` con un clic y renderiza la tabla directamente

Si corres el servidor localmente, abre `http://localhost:8000` — sirve el `index.html` directamente desde el servidor, sin problemas de CORS.

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
