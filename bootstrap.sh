#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_NAME="${PROJECT_NAME:-garmin-coach-mcp}"
SERVICE_NAME="${SERVICE_NAME:-garmin-coach-mcp}"
CACHE_MINUTES="${CACHE_MINUTES:-30}"
ACTIVITY_LIMIT="${ACTIVITY_LIMIT:-8}"
MOUNT_PATH="${MOUNT_PATH:-/data}"
TOKEN_FILE="${HOME}/.garminconnect/garmin_tokens.json"

need_file() {
  [[ -f "$1" ]] || { echo "❌ Falta el archivo: $1"; exit 1; }
}

echo "== Garmin Coach MCP · bootstrap =="

for f in requirements.txt server.py Dockerfile railway.toml login_once.py; do
  need_file "$f"
done

if ! command -v brew >/dev/null 2>&1; then
  echo "❌ Necesitas Homebrew instalado."
  exit 1
fi

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "→ Instalando python@3.11..."
  brew install python@3.11
fi

if ! command -v railway >/dev/null 2>&1; then
  echo "→ Instalando Railway CLI..."
  brew install railway
fi

if [[ ! -d .venv ]]; then
  echo "→ Creando entorno virtual..."
  python3.11 -m venv .venv
fi

source .venv/bin/activate

echo "→ Python activo:"
python --version

echo "→ Instalando dependencias..."
python -m pip install --upgrade pip
pip install -r requirements.txt

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo
  echo "→ No existe token Garmin todavía. Voy a lanzarte el login una vez."
  python login_once.py
fi

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "❌ No se ha creado $TOKEN_FILE"
  exit 1
fi

echo "→ Empaquetando token Garmin..."
TOKEN_B64="$(python - <<'PY'
import base64
from pathlib import Path
p = Path.home()/'.garminconnect'/'garmin_tokens.json'
print(base64.b64encode(p.read_bytes()).decode())
PY
)"

echo
echo "→ Comprobando login de Railway..."
if ! railway whoami >/dev/null 2>&1; then
  railway login
fi

echo
echo "→ Creando o enlazando proyecto Railway..."
if ! railway status >/dev/null 2>&1; then
  railway init -n "$PROJECT_NAME"
fi

echo
echo "→ Creando servicio si no existe..."
railway add -s "$SERVICE_NAME" || true

echo
echo "→ Adjuntando volume persistente en $MOUNT_PATH ..."
railway volume add -m "$MOUNT_PATH" || true

echo
echo "→ Guardando variables..."
printf "%s" "$TOKEN_B64" | railway variable set GARMIN_TOKENS_JSON --stdin
railway variable set CACHE_MINUTES="$CACHE_MINUTES" ACTIVITY_LIMIT="$ACTIVITY_LIMIT"

echo
echo "→ Desplegando..."
railway up

echo
echo "→ Generando dominio público..."
DOMAIN_JSON="$(railway domain --json 2>/dev/null || true)"

DOMAIN_URL="$(python - <<'PY'
import json, re, sys

raw = sys.stdin.read().strip()
if not raw:
    print("")
    raise SystemExit

try:
    obj = json.loads(raw)
except Exception:
    print("")
    raise SystemExit

def walk(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)
    elif isinstance(x, str):
        yield x

for s in walk(obj):
    m = re.search(r'https://[A-Za-z0-9.-]+\.up\.railway\.app', s)
    if m:
        print(m.group(0))
        raise SystemExit
    m = re.search(r'[A-Za-z0-9.-]+\.up\.railway\.app', s)
    if m:
        print("https://" + m.group(0))
        raise SystemExit

print("")
PY
<<<"$DOMAIN_JSON")"

echo
if [[ -n "$DOMAIN_URL" ]]; then
  echo "✅ Dominio: $DOMAIN_URL"
  echo "✅ Health:  $DOMAIN_URL/health"
  echo "✅ MCP:     $DOMAIN_URL/mcp"
  echo
  echo "→ Probando /health ..."
  curl -fsSL "$DOMAIN_URL/health" || true
  echo
  echo "----------------------------------------"
  echo "En Claude pon esta URL como custom connector:"
  echo "$DOMAIN_URL/mcp"
  echo "----------------------------------------"
else
  echo "⚠️ No pude extraer el dominio automáticamente."
  echo "Abro Railway para que copies el dominio público del servicio."
  railway open || true
fi

echo
echo "✅ Bootstrap terminado."
