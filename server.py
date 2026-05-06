from __future__ import annotations

import base64
import functools
import json
import os
import threading
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response


APP_NAME = "Garmin Coach MCP"
CACHE_MINUTES = max(5, int(os.getenv("CACHE_MINUTES", "30")))
ACTIVITY_LIMIT = max(1, min(20, int(os.getenv("ACTIVITY_LIMIT", "8"))))
PORT = int(os.getenv("PORT", "8000"))
APP_TIMEZONE = ZoneInfo(os.getenv("GARMIN_TIMEZONE", "Europe/Madrid"))
RECOVERY_MAX_FRESH_MINUTES = max(15, int(os.getenv("RECOVERY_MAX_FRESH_MINUTES", "360")))
RECOVERY_CROSS_DAY_STALE_MINUTES = max(15, int(os.getenv("RECOVERY_CROSS_DAY_STALE_MINUTES", "180")))
GARMIN_LANGUAGE = os.getenv("GARMIN_LANGUAGE", "es").lower()

# Traducción de enums de la API de Garmin al español de Garmin Connect
_GARMIN_ES: dict[str, str] = {
    # HRV / VFC
    "BALANCED": "Equilibrado",
    "UNBALANCED": "Desequilibrado",
    "LOW": "Bajo",
    "POOR": "Deficiente",
    "NO_STATUS": "Sin estado",

    # Estado de entrenamiento (Training Status)
    "PRODUCTIVE": "Productivo",
    "MAINTAINING": "Manteniendo",
    "RECOVERY": "Recuperación",
    "OVERREACHING": "Sobreentrenamiento",
    "UNPRODUCTIVE": "No productivo",
    "DETRAINING": "Pérdida de forma",
    "PEAKING": "Pico de forma",
    "OVERLOAD": "Sobrecarga",

    # Predisposición para entrenar (Training Readiness)
    "EXCELLENT": "Óptima",
    "GOOD": "Alta",
    "FAIR": "Moderada",
    "BAD": "Baja",
    "VERY_BAD": "Muy baja",

    # Fases de sueño (la API puede devolver mayúsculas o minúsculas)
    "AWAKE": "Despierto",
    "LIGHT": "Ligero",
    "DEEP": "Profundo",
    "REM": "REM",
    "awake": "Despierto",
    "light": "Ligero",
    "deep": "Profundo",
    "rem": "REM",

    # Puntuación de sueño (Sleep Score)
    # GOOD → "Buena" (se comparte con Training Readiness, forma masculina es "Bueno")
    # FAIR → "Regular" (ya definido arriba)
    # POOR → "Deficiente" (ya definido arriba)
    # EXCELLENT → "Excelente" (ya definido arriba)

    # Efecto del entrenamiento (Training Effect)
    "IMPROVING": "Mejorando",
    "HIGHLY_AEROBIC": "Aeróbico intenso",
    "AEROBIC": "Aeróbico",
    "ANAEROBIC": "Anaeróbico",
    "VO2MAX": "Mejora VO2max",
    "ANAEROBIC_CAPACITY": "Capacidad anaeróbica",
    "AEROBIC_BASE": "Base aeróbica",

    # Zonas de intensidad
    "ZONE_1": "Calentamiento",
    "ZONE_2": "Suave",
    "ZONE_3": "Aeróbica",
    "ZONE_4": "Umbral",
    "ZONE_5": "Máximo",

    # Tipos de actividad
    "treadmill_running": "Carrera en cinta",
    "strength_training": "Fuerza",

    # Mensajes Body Battery / feedback UI
    "DAY_STRESSFUL_AND_INACTIVE": "Día estresante e inactivo",
    "SLEEP_TIME_PASSED_STRESSFUL_AND_INACTIVE": "Noche estresante + inactividad",

    # Insights de sueño
    "NEGATIVE_STRENUOUS_EXERCISE": "Ejercicio intenso previo",
    "HARD_EXERCISE_NEG_FAIR_OR_POOR_SLEEP": "Entrenamiento duro + mal sueño",

    # Estados genéricos de nivel / calidad
    "OPTIMAL": "Óptimo",
    "MODERATE": "Moderado",
    "HIGH": "Alto",
    "NORMAL": "Normal",
    "ABOVE_NORMAL": "Por encima de lo normal",
    "BELOW_NORMAL": "Por debajo de lo normal",

    # Tendencias (composición corporal, peso, VO2max…)
    "STABLE": "Estable",
    "INCREASING": "En aumento",
    "DECREASING": "En descenso",
    "IMPROVED": "Mejorado",
    "DECLINED": "Empeorado",
    "UNCHANGED": "Sin cambios",
    "INCREASED": "Aumentado",
    "DECREASED": "Disminuido",

    # Estado de retos / objetivos
    "ACTIVE": "Activo",
    "INACTIVE": "Inactivo",
    "COMPLETED": "Completado",
    "IN_PROGRESS": "En progreso",
    "PENDING": "Pendiente",
    "FAILED": "No completado",
    "AVAILABLE": "Disponible",

    # Sistema de unidades
    "METRIC": "Métrico",
    "STATUTE": "Imperial",
    "MARINE": "Náutico",

    # Perfil / género
    "MALE": "Masculino",
    "FEMALE": "Femenino",

    # SPO2
    "STANDARD": "Estándar",
    "CONTINUOUS": "Continuo",
    "SPOT_CHECK": "Medición puntual",
    "INTERRUPTED": "Interrumpido",
    "HIGH_ALTITUDE": "Altitud elevada",
    "ENABLED": "Activo",
    "DISABLED": "Desactivado",

    # Respiración
    "TACHYPNEA": "Taquipnea",
    "BRADYPNEA": "Bradipnea",

    # Tipos de actividad adicionales
    "running": "Correr",
    "cycling": "Ciclismo",
    "walking": "Caminar",
    "hiking": "Senderismo",
    "swimming": "Natación",
    "trail_running": "Trail running",
    "road_biking": "Ciclismo en carretera",
    "indoor_cycling": "Ciclismo indoor",
    "mountain_biking": "Ciclismo de montaña",
    "virtual_ride": "Ciclismo virtual",
    "open_water_swimming": "Natación en aguas abiertas",
    "pool_swimming": "Natación en piscina",
    "cardio": "Cardio",
    "elliptical": "Elíptica",
    "track_running": "Carrera en pista",
    "multi_sport": "Multideporte",
    "triathlon": "Triatlón",
    "yoga": "Yoga",
    "pilates": "Pilates",
    "tennis": "Tenis",
    "golf": "Golf",
    "rowing": "Remo",
    "cross_country_skiing": "Esquí de fondo",
    "skiing": "Esquí alpino",
    "snowboarding": "Snowboard",
    "basketball": "Baloncesto",
    "football": "Fútbol americano",
    "soccer": "Fútbol",
    "other": "Otro",

    # Genéricos
    "UNKNOWN": "Desconocido",
    "NONE": "Sin datos",
    "NO_DATA": "Sin datos",
    "POSITIVE": "Positivo",
    "NEGATIVE": "Negativo",
    "NEUTRAL": "Neutral",
    "ASCENDING": "Ascendente",
    "DESCENDING": "Descendente",
    "WEEKLY": "Semanal",
    "DAILY": "Diario",
    "DISTANCE": "Distancia",
    "DURATION": "Duración",
    "CALORIES": "Calorías",
    "STEPS": "Pasos",
}


def _translate_garmin(obj: Any) -> Any:
    """Traduce recursivamente los enums de Garmin al español de Garmin Connect."""
    if not GARMIN_LANGUAGE.startswith("es"):
        return obj
    if isinstance(obj, dict):
        return {k: _translate_garmin(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_translate_garmin(i) for i in obj]
    if isinstance(obj, str) and obj in _GARMIN_ES:
        return _GARMIN_ES[obj]
    return obj

RAILWAY_VOLUME_ROOT = Path(os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "/data"))
VOLUME_ROOT = RAILWAY_VOLUME_ROOT  # backward compatibility for legacy references
LOCAL_GARMINCONNECT_DIR = Path.home() / ".garminconnect"
LOCAL_DEBUG_TOKEN_DIR = Path.cwd() / ".debug-data" / "garmin"

def _resolve_token_dir() -> Path:
    explicit = os.getenv("GARMIN_TOKEN_DIR", "").strip()
    if explicit:
        return Path(explicit).expanduser()

    if LOCAL_GARMINCONNECT_DIR.exists():
        return LOCAL_GARMINCONNECT_DIR

    if RAILWAY_VOLUME_ROOT.exists() and os.access(RAILWAY_VOLUME_ROOT, os.W_OK):
        return RAILWAY_VOLUME_ROOT / "garmin"

    return LOCAL_DEBUG_TOKEN_DIR

TOKEN_DIR = _resolve_token_dir()
TOKEN_FILE = TOKEN_DIR / "garmin_tokens.json"

GARMIN_TOKENS_JSON = os.getenv("GARMIN_TOKENS_JSON", "").strip()
RESET_GARMIN_TOKENS = os.getenv("RESET_GARMIN_TOKENS", "0").lower() in {"1", "true", "yes"}

CACHE_LOCK = threading.Lock()
FETCH_LOCK = threading.Lock()

CACHE: dict[str, Any] = {
    "status": "starting",
    "last_refresh": None,
    "last_error": None,
    "snapshot": None,
}

mcp = FastMCP(
    APP_NAME,
    instructions=(
        
(
        "Herramientas para leer métricas reales de Garmin Connect. "
        "Responde siempre en español y prioriza términos canónicos alineados con Garmin Connect en español. "
        "Usa 'Predisposición para entrenar', 'VFC', 'Puntuación de sueño', 'Carga aguda' y 'Estrés'. "
        "NUNCA uses los acrónimos en inglés 'HRV', 'RHR' ni los términos 'Training Readiness', 'Training Effect' o 'Stamina': usa siempre 'VFC', 'FC en reposo', 'Predisposición para entrenar', 'Efecto de entrenamiento' y 'Energía disponible' respectivamente. "
        "Mantén 'Body Battery' como nombre propio de Garmin; si ayuda, puedes aclarar entre paréntesis 'energía corporal'. "
        "Traduce estados como FAIR->Aceptable, MODERATE->Moderada, BALANCED->Equilibrado, OPTIMAL->Óptimo y LOW->Bajo/Baja según contexto. "
        "Para tiempo de recuperación, usa siempre primero training_readiness_recovery_answer_for_llm o, si no existe, training_readiness_recovery_safe_text. "
        "No extrapoles manualmente. No conviertas descripciones cualitativas como 'Poca necesidad' en '0 minutos' salvo que exista un contador explícito de recuperación. "
        "Cuando el usuario pregunte por la hora de sincronización o de cuándo son los datos, prioriza ultima_sincronizacion_conector_local, snapshot_obtenido_local y datos_hasta_local.  Para Body Battery, usa el nombre 'Body Battery', no 'Batería corporal'. Para Predisposición para entrenar, usa estados en femenino: Muy baja, Baja, Moderada, Alta u Óptima según corresponda. Para sueño, prioriza sueno_texto_seguro, puntuacion_de_sueno y duracion_de_sueno_texto. No menciones REM, fases del sueño ni despertares salvo que existan campos canónicos explícitos para ello. "
        "Si el usuario pide máxima exactitud, usa get_raw_sources o get_cached_snapshot y responde basándote en raw_sources sin inventar campos. "
        "Si una métrica no existe, di que Garmin no la devolvió."
    )
),
)

# Aplica _translate_garmin a la salida de todos los tools automáticamente
if GARMIN_LANGUAGE.startswith("es"):
    _orig_mcp_tool = mcp.tool

    def _translating_tool(fn):
        @functools.wraps(fn)
        def _wrapped(*args, **kwargs):
            return _translate_garmin(fn(*args, **kwargs))
        return _orig_mcp_tool(_wrapped)

    mcp.tool = _translating_tool


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _now_local() -> datetime:
    return datetime.now(APP_TIMEZONE)


def _today_local() -> date:
    return _now_local().date()


def _isoish_to_local(value: Any) -> Any:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=APP_TIMEZONE)
        else:
            dt = dt.astimezone(APP_TIMEZONE)
        return dt.isoformat()
    except Exception:
        return value


def _format_duration_hm(seconds: Any) -> str | None:
    try:
        total = int(round(float(seconds)))
    except Exception:
        return None
    if total < 0:
        return None
    hours = total // 3600
    minutes = (total % 3600) // 60
    return f"{hours}h {minutes:02d}m"

def _short_local_dt_text(value: Any) -> str | None:
    dt = _parse_garmin_datetime(value) if value is not None else None
    if dt is None:
        return None
    return dt.strftime("%d/%m/%Y %H:%M")



def _normalize_readiness_status_es(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    mapping = {
        "very low": "Muy baja",
        "low": "Baja",
        "moderate": "Moderada",
        "high": "Alta",
        "optimal": "Óptima",
        "muy bajo": "Muy baja",
        "muy baja": "Muy baja",
        "bajo": "Baja",
        "baja": "Baja",
        "moderado": "Moderada",
        "moderada": "Moderada",
        "alto": "Alta",
        "alta": "Alta",
        "óptimo": "Óptima",
        "optimo": "Óptima",
        "óptima": "Óptima",
        "optima": "Óptima",
    }
    return mapping.get(raw.casefold(), raw)


def _build_sleep_safe_text(score: Any, duration_text: Any) -> str | None:
    if score is None and not duration_text:
        return None
    if score is not None and duration_text:
        return f"{score} puntos y {duration_text}"
    if score is not None:
        return f"{score} puntos"
    return str(duration_text)


def _json_loads_maybe_base64(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if not raw:
        raise RuntimeError("GARMIN_TOKENS_JSON está vacío")

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("GARMIN_TOKENS_JSON no contiene un objeto JSON válido")
        return parsed
    except json.JSONDecodeError:
        pass

    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        parsed = json.loads(decoded)
        if not isinstance(parsed, dict):
            raise RuntimeError("El base64 no contiene un objeto JSON válido")
        return parsed
    except Exception as exc:
        raise RuntimeError(
            "GARMIN_TOKENS_JSON no es JSON válido ni base64 de JSON válido"
        ) from exc


def _seed_token_file_if_needed() -> None:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    if RESET_GARMIN_TOKENS and GARMIN_TOKENS_JSON:
        parsed = _json_loads_maybe_base64(GARMIN_TOKENS_JSON)
        TOKEN_FILE.write_text(json.dumps(parsed), encoding="utf-8")
        return

    if TOKEN_FILE.exists():
        return

    if not GARMIN_TOKENS_JSON:
        raise RuntimeError(
            "No existe token persistido y falta GARMIN_TOKENS_JSON en variables de entorno"
        )

    parsed = _json_loads_maybe_base64(GARMIN_TOKENS_JSON)
    TOKEN_FILE.write_text(json.dumps(parsed), encoding="utf-8")


class _GarminActivityDownloadFormat:
    ORIGINAL = 1
    TCX = 2
    GPX = 3
    KML = 4
    CSV = 5


def _get_api() -> Garmin:
    _seed_token_file_if_needed()
    api = Garmin()
    api.login(str(TOKEN_DIR))
    return api


def _optional_call_first(api: Garmin, methods: tuple[str, ...], *args: Any) -> tuple[Any, str | None]:
    last_error = None
    attempted = False

    for name in methods:
        fn = getattr(api, name, None)
        if callable(fn):
            attempted = True
            try:
                return fn(*args), None
            except Exception as exc:
                last_error = f"{name}: {exc}"

    if not attempted:
        return None, None

    return None, last_error


def _optional_call_variants(
    api: Garmin,
    variants: list[tuple[tuple[str, ...], tuple[Any, ...]]],
) -> tuple[Any, str | None]:
    last_error = None
    attempted = False

    for methods, args in variants:
        for name in methods:
            fn = getattr(api, name, None)
            if callable(fn):
                attempted = True
                try:
                    return fn(*args), None
                except Exception as exc:
                    last_error = f"{name}{args}: {exc}"

    if not attempted:
        return None, None

    return None, last_error


def _parse_date(target_date: str | None) -> str:
    if not target_date:
        return _today_local().isoformat()
    return date.fromisoformat(target_date).isoformat()


def _resting_hr(heart_data: Any) -> Any:
    if not isinstance(heart_data, dict):
        return None

    if heart_data.get("restingHeartRate") is not None:
        return heart_data.get("restingHeartRate")

    try:
        return heart_data["allMetrics"]["metricsMap"]["WELLNESS_RESTING_HEART_RATE"][0]["value"]
    except Exception:
        return None


def _sleep_metrics(sleep_data: Any) -> dict[str, Any]:
    if not isinstance(sleep_data, dict):
        return {}

    daily = sleep_data.get("dailySleepDTO") or {}

    def sec_to_h(sec: Any) -> Any:
        try:
            return round(float(sec) / 3600, 2)
        except Exception:
            return None

    def sec_to_min(sec: Any) -> Any:
        try:
            return int(float(sec) / 60)
        except Exception:
            return None

    score = None
    try:
        score = daily["sleepScores"]["overall"]["value"]
    except Exception:
        score = None

    return {
        "sleep_hours": sec_to_h(daily.get("sleepTimeSeconds")),
        "sleep_score": score,
        "sleep_rem_min": sec_to_min(daily.get("remSleepSeconds")),
        "sleep_deep_min": sec_to_min(daily.get("deepSleepSeconds")),
        "sleep_light_min": sec_to_min(daily.get("lightSleepSeconds")),
        "sleep_awake_min": sec_to_min(daily.get("awakeSleepSeconds")),
    }


def _body_battery_metrics(bb_data: Any) -> dict[str, Any]:
    blocks = []
    if isinstance(bb_data, dict):
        blocks = [bb_data]
    elif isinstance(bb_data, list):
        blocks = [x for x in bb_data if isinstance(x, dict)]

    levels: list[float] = []
    charged = None
    drained = None
    last_timestamp_local = None
    feedback_level = None
    feedback_short = None
    feedback_long = None
    series = []

    for block in blocks:
        if charged is None and isinstance(block.get("charged"), (int, float)):
            charged = block.get("charged")

        if drained is None and isinstance(block.get("drained"), (int, float)):
            drained = block.get("drained")

        if last_timestamp_local is None and block.get("endTimestampLocal") is not None:
            last_timestamp_local = block.get("endTimestampLocal")

        feedback = block.get("bodyBatteryDynamicFeedbackEvent") or {}
        if feedback_level is None and feedback.get("bodyBatteryLevel") is not None:
            feedback_level = feedback.get("bodyBatteryLevel")
        if feedback_short is None and feedback.get("feedbackShortType") is not None:
            feedback_short = feedback.get("feedbackShortType")
        if feedback_long is None and feedback.get("feedbackLongType") is not None:
            feedback_long = feedback.get("feedbackLongType")

        values_array = block.get("bodyBatteryValuesArray")
        if isinstance(values_array, list):
            for item in values_array:
                if (
                    isinstance(item, list)
                    and len(item) >= 2
                    and isinstance(item[1], (int, float))
                    and 0 <= item[1] <= 100
                ):
                    levels.append(float(item[1]))
                    series.append({"timestamp_ms": item[0], "level": item[1]})
        elif isinstance(block.get("value"), (int, float)) and 0 <= block["value"] <= 100:
            levels.append(float(block["value"]))

    if not levels:
        return {
            "body_battery_current": None,
            "body_battery_max": None,
            "body_battery_min": None,
            "body_battery_charged": charged,
            "body_battery_drained": drained,
            "body_battery_last_timestamp_local": last_timestamp_local,
            "body_battery_feedback_level": feedback_level,
            "body_battery_feedback_short": feedback_short,
            "body_battery_feedback_long": feedback_long,
            "body_battery_series": series,
            "body_battery_raw": bb_data,
        }

    return {
        "body_battery_current": round(levels[-1]),
        "body_battery_max": round(max(levels)),
        "body_battery_min": round(min(levels)),
        "body_battery_charged": charged,
        "body_battery_drained": drained,
        "body_battery_last_timestamp_local": last_timestamp_local,
        "body_battery_feedback_level": feedback_level,
        "body_battery_feedback_short": feedback_short,
        "body_battery_feedback_long": feedback_long,
        "body_battery_series": series,
        "body_battery_raw": bb_data,
    }


def _stress_metrics(stress_data: Any) -> dict[str, Any]:
    if not isinstance(stress_data, dict):
        return {}

    def to_min(v: Any) -> Any:
        try:
            return int(float(v) / 60)
        except Exception:
            return None

    return {
        "stress_avg": stress_data.get("avgStressLevel"),
        "stress_max": stress_data.get("maxStressLevel"),
        "stress_duration_min": to_min(stress_data.get("stressDuration")),
        "rest_duration_min": to_min(stress_data.get("restStressDuration")),
    }


def _pick_first_present(container: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if not isinstance(container, dict):
            return None
        value = container.get(key)
        if value is not None:
            return value
    return None


def _hrv_metrics(hrv_data: Any) -> dict[str, Any]:
    if not isinstance(hrv_data, dict):
        return {}

    summary = hrv_data.get("hrvSummary") or {}
    if not isinstance(summary, dict):
        summary = {}

    return {
        "hrv_last_night": _pick_first_present(summary, ("lastNight", "lastNightAvg", "lastNightAverage")),
        "hrv_weekly_avg": _pick_first_present(summary, ("weeklyAvg", "sevenDayAvg", "baselineAvg")),
        "hrv_status": _pick_first_present(summary, ("hrvStatus", "status")),
        "hrv_baseline_low": _pick_first_present(summary, ("baselineBalancedLow", "balancedLow")),
        "hrv_baseline_high": _pick_first_present(summary, ("baselineBalancedHigh", "balancedHigh")),
    }


def _select_training_readiness_entry(training_readiness: Any) -> dict[str, Any] | None:
    if isinstance(training_readiness, dict):
        return training_readiness

    if isinstance(training_readiness, list):
        candidates = [e for e in training_readiness if isinstance(e, dict)]
        if not candidates:
            return None

        valid_sleep = [e for e in candidates if e.get("validSleep") is True]
        pool = valid_sleep or candidates

        def sort_key(entry: dict[str, Any]) -> tuple[int, str]:
            ts = entry.get("timestampLocal") or entry.get("timestamp") or ""
            return (1 if entry.get("inputContext") == "UPDATE_REALTIME_VARIABLES" else 0, str(ts))

        return sorted(pool, key=sort_key, reverse=True)[0]

    return None


TRAINING_READINESS_STATUS_ES = {
    "PRIMED": "Óptimo",
    "READY": "Listo",
    "GOOD": "Bueno",
    "MODERATE": "Moderada",
    "LOW": "Bajo",
    "POOR": "Muy bajo",
    "RECOVERY": "Recuperación",
    "REST": "Descanso",
    "WORKING_HARD": "Cargando fuerte",
    "BALANCE_YOUR_TRAINING_LOAD": "Equilibra tu carga de entrenamiento",
    "OVERREACHING": "Sobrecarga",
    "STRAINED": "Tensionado",
    "UNKNOWN": "Sin mensaje",
    "GOOD_RECOVERY": "Buena recuperación",
    "MOD_RT_LOW_SS_MOD_SLEEP_HISTORY_NEG": "Moderada — sueño reciente bajo",
    "HIGH_RT": "Alta disposición",
    "LOW_RT": "Baja disposición",
    "POOR_SLEEP": "Sueño insuficiente",
    "HIGH_STRESS_HISTORY": "Estrés acumulado alto",
}


def _translate_training_readiness_status(value: Any) -> Any:
    if value is None:
        return None
    key = str(value).strip().upper().replace(" ", "_")
    return TRAINING_READINESS_STATUS_ES.get(key, str(value).replace("_", " ").title())


def _training_readiness_metrics(training_readiness: Any) -> dict[str, Any]:
    entry = _select_training_readiness_entry(training_readiness)
    if not isinstance(entry, dict):
        return {}

    score = _pick_first_present(entry, (
        "score",
        "readinessScore",
        "trainingReadinessScore",
        "value",
    ))
    status = _pick_first_present(entry, (
        "level",
        "status",
        "readinessStatus",
        "shortFeedback",
        "feedbackShortType",
    ))
    message = _pick_first_present(entry, (
        "feedbackShort",
        "description",
        "message",
        "shortMessage",
        "fullMessage",
        "feedbackLong",
        "feedbackLongType",
    ))
    recovery_time = _pick_first_present(entry, (
        "recoveryTime",
        "recoveryHours",
    ))

    return {
        "training_readiness_score": score,
        "training_readiness_status": status,
        "training_readiness_status_es": _translate_training_readiness_status(status),
        "training_readiness_message": message,
        "training_readiness_message_es": _translate_training_readiness_status(message),
        "training_readiness_recovery_time": recovery_time,
        "training_readiness_input_context": entry.get("inputContext"),
        "training_readiness_selected_entry": entry,
    }


def _extract_vo2(max_metrics: Any, training_status: Any) -> Any:
    if isinstance(max_metrics, list) and max_metrics:
        try:
            value = max_metrics[0]["generic"]["vo2MaxPreciseValue"]
            if value is not None:
                return value
        except Exception:
            pass

    if isinstance(training_status, dict):
        try:
            generic = training_status["mostRecentVO2Max"]["generic"]
            value = generic.get("vo2MaxPreciseValue")
            if value is None:
                value = generic.get("vo2MaxValue")
            return value
        except Exception:
            return None

    return None


def _normalize_activity(activity: dict[str, Any]) -> dict[str, Any]:
    activity_type = activity.get("activityType") or activity.get("activityTypeDTO") or {}
    summary = activity.get("summaryDTO") or {}
    type_key = activity_type.get("typeKey")

    duration_seconds = activity.get("duration")
    if duration_seconds is None:
        duration_seconds = summary.get("duration")

    distance_m = activity.get("distance")
    if distance_m is None:
        distance_m = summary.get("distance")

    return {
        "activity_id": activity.get("activityId"),
        "name": activity.get("activityName"),
        "type": type_key,
        "activity_family": _activity_family(type_key),
        "start_time_local": activity.get("startTimeLocal") or summary.get("startTimeLocal"),
        "duration_min": round((duration_seconds or 0) / 60, 1),
        "distance_km": round((distance_m or 0) / 1000, 2),
        "avg_hr": activity.get("averageHR") or summary.get("averageHR"),
        "max_hr": activity.get("maxHR") or summary.get("maxHR"),
        "calories": activity.get("calories") or summary.get("calories"),
        "training_load": activity.get("trainingLoad") or activity.get("activityTrainingLoad") or summary.get("activityTrainingLoad"),
        "elevation_gain_m": activity.get("elevationGain") or summary.get("elevationGain"),
        "training_effect": summary.get("trainingEffect"),
        "anaerobic_training_effect": summary.get("anaerobicTrainingEffect"),
        "average_power": activity.get("averagePower") or summary.get("averagePower"),
        "normalized_power": summary.get("normalizedPower"),
        "average_run_cadence": activity.get("averageRunCadence") or summary.get("averageRunCadence"),
        "steps": activity.get("steps") or summary.get("steps"),
    }


def _extract_primary_device_info(training_status: Any, devices_raw: Any) -> dict[str, Any]:
    device_id = None
    device_name = None
    image_url = None

    if isinstance(training_status, dict):
        try:
            latest = training_status["mostRecentTrainingStatus"]["latestTrainingStatusData"]
            if isinstance(latest, dict) and latest:
                key = next(iter(latest.keys()))
                device_id = int(key)
        except Exception:
            pass

        if device_id is None:
            try:
                balance = training_status["mostRecentTrainingLoadBalance"]["metricsTrainingLoadBalanceDTOMap"]
                if isinstance(balance, dict) and balance:
                    key = next(iter(balance.keys()))
                    device_id = int(key)
            except Exception:
                pass

        for path in [
            ("mostRecentTrainingStatus", "recordedDevices"),
            ("mostRecentTrainingLoadBalance", "recordedDevices"),
        ]:
            try:
                devices = training_status[path[0]][path[1]]
                if isinstance(devices, list):
                    for dev in devices:
                        if not isinstance(dev, dict):
                            continue
                        dev_id = dev.get("deviceId")
                        if device_id is None and dev_id is not None:
                            device_id = dev_id
                        if device_id is not None and dev_id == device_id:
                            device_name = dev.get("deviceName")
                            image_url = dev.get("imageURL")
                            break
                    if device_name:
                        break
            except Exception:
                pass

    if device_id is None and isinstance(devices_raw, list):
        for dev in devices_raw:
            if not isinstance(dev, dict):
                continue
            for key in ("deviceId", "id", "unitId"):
                if dev.get(key) is not None:
                    device_id = dev.get(key)
                    break
            if device_id is not None:
                device_name = dev.get("deviceName") or dev.get("displayName") or dev.get("modelName")
                image_url = dev.get("imageURL")
                break

    return {
        "primary_device_id": device_id,
        "primary_device_name": device_name,
        "primary_device_image_url": image_url,
    }


def _collect_extra_raw(
    api: Garmin,
    target_date: str,
    training_status: Any,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    raw: dict[str, Any] = {}
    errors: dict[str, str] = {}

    extra_specs: dict[str, list[tuple[tuple[str, ...], tuple[Any, ...]]]] = {
        "spo2_raw": [
            (("get_spo2_data", "get_pulse_ox_data"), (target_date,)),
        ],
        "respiration_raw": [
            (("get_respiration_data",), (target_date,)),
        ],
        "floors_raw": [
            (("get_floors_data",), (target_date,)),
        ],
        "intensity_minutes_raw": [
            (("get_intensity_minutes_data", "get_intensity_minutes"), (target_date,)),
        ],
        "hydration_raw": [
            (("get_hydration_data",), (target_date,)),
            (("get_hydration_log",), tuple()),
        ],
        "body_composition_raw": [
            (("get_body_composition",), (target_date,)),
            (("get_weight_data",), (target_date,)),
        ],
        "user_profile_raw": [
            (("get_user_profile",), tuple()),
        ],
        "user_settings_raw": [
            (("get_user_settings",), tuple()),
        ],
        "devices_raw": [
            (("get_devices",), tuple()),
        ],
        "activities_for_date_raw": [
            (("get_activities_fordate", "get_activities_by_date"), (target_date,)),
        ],
        "solar_raw": [
            (("get_solar_data",), (target_date,)),
        ],
        "blood_pressure_raw": [
            (("get_blood_pressure_data",), (target_date,)),
        ],
        "resting_metabolic_rate_raw": [
            (("get_resting_metabolic_rate",), (target_date,)),
        ],
        "race_predictions_raw": [
            (("get_race_predictions",), tuple()),
        ],
        "fitness_age_raw": [
            (("get_fitnessage_data", "get_fitness_age"), (target_date,)),
        ],
        "personal_records_raw": [
            (("get_personal_records",), tuple()),
        ],
    }

    for key, variants in extra_specs.items():
        data, err = _optional_call_variants(api, variants)
        if data is not None:
            raw[key] = data
        elif err:
            errors[key] = err

    device_info = _extract_primary_device_info(training_status, raw.get("devices_raw"))
    primary_device_id = device_info.get("primary_device_id")

    if primary_device_id is not None:
        device_settings, device_settings_err = _optional_call_variants(
            api,
            [
                (("get_device_settings",), (primary_device_id,)),
            ],
        )
        if device_settings is not None:
            raw["device_settings_raw"] = device_settings
        elif device_settings_err:
            errors["device_settings_raw"] = device_settings_err

    return raw, errors, device_info


def _collect_day_snapshot(target_date: str, include_recent_activities: bool = False) -> dict[str, Any]:
    target_date = _parse_date(target_date)
    sleep_reference_day = target_date

    with FETCH_LOCK:
        api = _get_api()

        summary, summary_err = _optional_call_first(api, ("get_user_summary", "get_stats"), target_date)
        heart, heart_err = _optional_call_first(api, ("get_heart_rates", "get_rhr_day"), target_date)
        sleep, sleep_err = _optional_call_first(api, ("get_sleep_data",), sleep_reference_day)
        stress, stress_err = _optional_call_first(api, ("get_stress_data",), target_date)
        body_battery, bb_err = _optional_call_first(api, ("get_body_battery",), target_date)
        hrv, hrv_err = _optional_call_first(api, ("get_hrv_data",), target_date)
        max_metrics, vo2_err = _optional_call_first(api, ("get_max_metrics",), target_date)
        training_readiness, tr_err = _optional_call_first(api, ("get_training_readiness",), target_date)
        training_status, ts_err = _optional_call_first(api, ("get_training_status",), target_date)

        activities = []
        activities_raw = []
        activities_err = None
        if include_recent_activities:
            recent, activities_err = _optional_call_first(api, ("get_activities",), 0, ACTIVITY_LIMIT)
            if isinstance(recent, list):
                activities_raw = recent[:ACTIVITY_LIMIT]
                activities = [_normalize_activity(a) for a in recent[:ACTIVITY_LIMIT] if isinstance(a, dict)]

        extra_raw, extra_errors, device_info = _collect_extra_raw(api, target_date, training_status)

    metrics: dict[str, Any] = {
        "steps": (summary or {}).get("totalSteps"),
        "distance_km": round(((summary or {}).get("totalDistanceMeters") or 0) / 1000, 2),
        "active_kcal": (summary or {}).get("activeKilocalories"),
        "total_kcal": (summary or {}).get("totalKilocalories"),
        "resting_hr": _resting_hr(heart),
        "vo2max": _extract_vo2(max_metrics, training_status),
        "primary_device_id": device_info.get("primary_device_id"),
        "primary_device_name": device_info.get("primary_device_name"),
        "primary_device_image_url": device_info.get("primary_device_image_url"),
    }

    metrics.update(_sleep_metrics(sleep))
    metrics.update(_stress_metrics(stress))
    metrics.update(_body_battery_metrics(body_battery))
    metrics.update(_hrv_metrics(hrv))
    metrics.update(_training_readiness_metrics(training_readiness))

    if training_readiness is not None:
        metrics["training_readiness_raw"] = training_readiness
    if training_status is not None:
        metrics["training_status_raw"] = training_status

    raw_sources = {
        "summary_raw": summary,
        "heart_raw": heart,
        "sleep_raw": sleep,
        "stress_raw": stress,
        "body_battery_raw": body_battery,
        "hrv_raw": hrv,
        "max_metrics_raw": max_metrics,
        "training_readiness_raw": training_readiness,
        "training_status_raw": training_status,
        "recent_activities_raw": activities_raw,
        "primary_device_info_raw": device_info,
    }
    raw_sources.update(extra_raw)

    errors = {
        "summary": summary_err,
        "heart": heart_err,
        "sleep": sleep_err,
        "stress": stress_err,
        "body_battery": bb_err,
        "hrv": hrv_err,
        "vo2max": vo2_err,
        "training_readiness": tr_err,
        "training_status": ts_err,
        "activities": activities_err,
    }
    errors.update(extra_errors)
    errors = {k: v for k, v in errors.items() if v}

    # Si device_settings_raw ya vino bien, no mostramos error.
    if raw_sources.get("device_settings_raw") is not None:
        errors.pop("device_settings_raw", None)

    # Si el único problema era el método antiguo sin device_id, lo ocultamos
    # porque ahora la vía correcta es get_primary_device_info.
    if "device_settings_raw" in errors:
        msg = str(errors.get("device_settings_raw") or "")
        if "device_id" in msg or "missing 1 required positional argument" in msg:
            errors.pop("device_settings_raw", None)

    return {
        "date": target_date,
        "fetched_at": _now_iso(),
        "metrics": metrics,
        "recent_activities": activities,
        "raw_sources": raw_sources,
        "source_errors": errors,
    }


def _refresh_cache_sync() -> dict[str, Any]:
    try:
        snapshot = _collect_day_snapshot(_today_local().isoformat(), include_recent_activities=True)
        with CACHE_LOCK:
            CACHE["status"] = "ok"
            CACHE["last_refresh"] = _now_iso()
            CACHE["last_error"] = None
            CACHE["snapshot"] = snapshot
        return deepcopy(CACHE)
    except GarminConnectTooManyRequestsError as exc:
        with CACHE_LOCK:
            CACHE["status"] = "error"
            CACHE["last_error"] = f"429 Garmin rate limit: {exc}"
        return deepcopy(CACHE)
    except GarminConnectAuthenticationError as exc:
        with CACHE_LOCK:
            CACHE["status"] = "error"
            CACHE["last_error"] = f"Auth Garmin: {exc}"
        return deepcopy(CACHE)
    except GarminConnectConnectionError as exc:
        with CACHE_LOCK:
            CACHE["status"] = "error"
            CACHE["last_error"] = f"Conexión Garmin: {exc}"
        return deepcopy(CACHE)
    except Exception as exc:
        with CACHE_LOCK:
            CACHE["status"] = "error"
            CACHE["last_error"] = f"Error inesperado: {exc}"
        return deepcopy(CACHE)


def _background_refresh_loop() -> None:
    while True:
        _refresh_cache_sync()
        time.sleep(CACHE_MINUTES * 60)


@mcp.custom_route("/", methods=["GET"])
async def root(_: Request) -> Response:
    from starlette.responses import HTMLResponse
    index_path = Path(__file__).parent.parent / "index.html"
    if index_path.exists():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
    return PlainTextResponse("Garmin Coach MCP is running. MCP endpoint: /mcp | Health: /health")


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    with CACHE_LOCK:
        payload = {
            "status": "ok",
            "app": APP_NAME,
            "mcp_endpoint": "/mcp",
            "cache_status": CACHE["status"],
            "last_refresh": CACHE["last_refresh"],
            "last_refresh_local": _isoish_to_local(CACHE["last_refresh"]),
            "last_error": CACHE["last_error"],
            "token_file_exists": TOKEN_FILE.exists(),
            "volume_path": str(VOLUME_ROOT),
        }
    return JSONResponse(payload)


@mcp.custom_route("/download/{activity_id}", methods=["GET"])
async def download_activity_fit(request: Request) -> Response:
    import urllib.request as _urllib
    activity_id = request.path_params.get("activity_id")

    # Intenta primero con tokens locales
    try:
        with FETCH_LOCK:
            api = _get_api()
            data = None
            fmt_name = "zip"
            for fmt in [api.ActivityDownloadFormat.ORIGINAL, api.ActivityDownloadFormat.TCX, api.ActivityDownloadFormat.GPX]:
                try:
                    data = api.download_activity(activity_id, fmt)
                    if data:
                        fmt_name = "zip" if fmt == api.ActivityDownloadFormat.ORIGINAL else fmt.name.lower()
                        break
                except Exception:
                    continue
        if data:
            return Response(
                content=data,
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="activity_{activity_id}.{fmt_name}"'},
            )
    except Exception:
        pass

    # Fallback: proxy descarga al Railway
    try:
        proxy_url = f"{RAILWAY_FALLBACK_URL}/download/{activity_id}"
        with _urllib.urlopen(proxy_url, timeout=30) as resp:
            data = resp.read()
        content_disp = resp.headers.get("Content-Disposition", f'attachment; filename="activity_{activity_id}.zip"')
        return Response(
            content=data,
            media_type="application/octet-stream",
            headers={"Content-Disposition": content_disp},
        )
    except Exception as exc:
        return JSONResponse({"error": f"No se pudo descargar: {exc}"}, status_code=503)


RAILWAY_FALLBACK_URL = os.getenv("RAILWAY_FALLBACK_URL", "https://garmin-coach-mcp-production.up.railway.app").rstrip("/")

_WEB_CONFIG_FILE = RAILWAY_VOLUME_ROOT / "web_config.json"
_WEB_CONFIG_ALLOWED_KEYS = {"driveUrl"}


@mcp.custom_route("/config", methods=["GET"])
async def get_web_config(_: Request) -> JSONResponse:
    try:
        if _WEB_CONFIG_FILE.exists():
            return JSONResponse(json.loads(_WEB_CONFIG_FILE.read_text()))
    except Exception:
        pass
    return JSONResponse({})


@mcp.custom_route("/config", methods=["POST"])
async def save_web_config(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        patch = {k: str(v) for k, v in body.items() if k in _WEB_CONFIG_ALLOWED_KEYS}
        existing: dict = {}
        if _WEB_CONFIG_FILE.exists():
            try:
                existing = json.loads(_WEB_CONFIG_FILE.read_text())
            except Exception:
                pass
        existing.update(patch)
        _WEB_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _WEB_CONFIG_FILE.write_text(json.dumps(existing))
        return JSONResponse({"ok": True})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@mcp.custom_route("/activities", methods=["GET"])
async def list_activities_web(request: Request) -> JSONResponse:
    import urllib.request as _urllib
    limit = int(request.query_params.get("limit", "30"))
    limit = max(1, min(500, limit))
    start_date = request.query_params.get("start_date", "").strip()  # YYYY-MM-DD
    end_date = request.query_params.get("end_date", "").strip()      # YYYY-MM-DD

    def _normalize(a: dict) -> dict:
        activity_type = a.get("activityType") or {}
        type_key = activity_type.get("typeKey") if isinstance(activity_type, dict) else None
        return {
            "activityId": a.get("activityId"),
            "activityName": a.get("activityName"),
            "startTimeLocal": a.get("startTimeLocal"),
            "activityType": type_key,
            "distanceKm": round((a.get("distance") or 0) / 1000, 2),
            "durationMin": round((a.get("duration") or 0) / 60, 1),
            "avgHr": a.get("averageHR"),
        }

    # Intenta primero con tokens locales
    try:
        with FETCH_LOCK:
            api = _get_api()
            if start_date:
                end = end_date if end_date else date.today().isoformat()
                activities = api.get_activities_by_date(start_date, end, None)
            else:
                activities, _ = _optional_call_first(api, ("get_activities",), 0, limit)
        if activities is not None:
            result = [_normalize(a) for a in activities if isinstance(a, dict)]
            if not start_date:
                result = result[:limit]
            return JSONResponse({"activities": result, "source": "local"})
    except Exception:
        pass

    # Fallback: proxy al servidor Railway que tiene tokens válidos
    try:
        proxy_url = f"{RAILWAY_FALLBACK_URL}/debug/activities"
        with _urllib.urlopen(proxy_url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        acts = data.get("activities") or []
        # debug/activities devuelve menos campos; rellenamos con 0 los que faltan
        for a in acts:
            a.setdefault("distanceKm", 0)
            a.setdefault("durationMin", 0)
            a.setdefault("avgHr", None)
        return JSONResponse({"activities": acts, "source": "railway"})
    except Exception as exc:
        return JSONResponse({"error": f"Sin tokens locales y Railway no responde: {exc}"}, status_code=503)


@mcp.custom_route("/debug/audit", methods=["GET"])
async def debug_audit(_: Request) -> JSONResponse:
    with CACHE_LOCK:
        snapshot = deepcopy(CACHE.get("snapshot"))
        status = CACHE.get("status")
        last_refresh = CACHE.get("last_refresh")
        last_error = CACHE.get("last_error")

    metrics = {}
    if isinstance(snapshot, dict):
        metrics = snapshot.get("metrics") or {}

    keys = [
        "snapshot_obtenido_local",
        "snapshot_obtenido_texto",
        "datos_hasta_local",
        "datos_hasta_texto",
        "predisposicion_para_entrenar",
        "predisposicion_para_entrenar_estado",
        "predisposicion_para_entrenar_texto",
        "body_battery_actual",
        "body_battery_texto",
        "body_battery_resumen_humano",
        "body_battery_nivel_es",
        "estado_vfc",
        "vfc_media_noche_ms",
        "vfc_media_7_dias_ms",
        "estado_vfc_resumen_humano",
        "puntuacion_de_sueno",
        "duracion_de_sueno_texto",
        "sueno_texto_seguro",
        "sueno_resumen_humano",
        "sueno_rem_texto",
        "sueno_profundo_texto",
        "sueno_ligero_texto",
        "sueno_despierto_texto",
        "sueno_inicio_texto",
        "sueno_fin_texto",
        "sueno_fases_resumen_humano",
        "training_readiness_recovery_state",
        "training_readiness_recovery_safe_text",
        "training_readiness_recovery_answer_for_llm",
        "recuperacion_texto_seguro",
    ]

    payload = {
        "status": status,
        "last_refresh": last_refresh,
        "last_refresh_local": _isoish_to_local(last_refresh),
        "last_error": last_error,
        "snapshot_exists": isinstance(snapshot, dict),
        "metrics": {k: metrics.get(k) for k in keys},
    }
    return JSONResponse(payload)



@mcp.custom_route("/debug/activities", methods=["GET"])
async def debug_activities(_: Request) -> JSONResponse:
    with FETCH_LOCK:
        api = _get_api()
        activities, err = _optional_call_first(api, ("get_activities",), 0, 5)
        if err:
            return JSONResponse({"error": str(err)}, status_code=500)
        if not activities:
            return JSONResponse({"error": "No activities found"}, status_code=404)
        
        result = [
            {
                "activityId": a.get("activityId"),
                "activityName": a.get("activityName"),
                "startTimeLocal": a.get("startTimeLocal"),
                "activityType": a.get("activityType", {}).get("typeKey") if isinstance(a.get("activityType"), dict) else None,
            }
            for a in activities[:5]
        ]
        return JSONResponse({"activities": result})
    # === End debug_activities ===

    raw_sleep_top_level = {
        k: v for k, v in raw_sources.items()
        if should_keep(k)
    }

    raw_sleep_candidates = walk(raw_sources)

    normalized_sleep = {
        "snapshot_obtenido_local": metrics.get("snapshot_obtenido_local"),
        "snapshot_obtenido_texto": metrics.get("snapshot_obtenido_texto"),
        "datos_hasta_local": metrics.get("datos_hasta_local"),
        "datos_hasta_texto": metrics.get("datos_hasta_texto"),
        "puntuacion_de_sueno": metrics.get("puntuacion_de_sueno"),
        "duracion_de_sueno_texto": metrics.get("duracion_de_sueno_texto"),
        "sueno_texto_seguro": metrics.get("sueno_texto_seguro"),
        "sueno_resumen_humano": metrics.get("sueno_resumen_humano"),
        "sueno_rem_texto": metrics.get("sueno_rem_texto"),
        "sueno_profundo_texto": metrics.get("sueno_profundo_texto"),
        "sueno_ligero_texto": metrics.get("sueno_ligero_texto"),
        "sueno_despierto_texto": metrics.get("sueno_despierto_texto"),
        "sueno_inicio_texto": metrics.get("sueno_inicio_texto"),
        "sueno_fin_texto": metrics.get("sueno_fin_texto"),
        "sueno_fases_resumen_humano": metrics.get("sueno_fases_resumen_humano"),
        "sleep_score": metrics.get("sleep_score"),
        "sleep_duration_seconds": metrics.get("sleep_duration_seconds"),
    }

    payload = {
        "status": status,
        "last_refresh": last_refresh,
        "last_refresh_local": _isoish_to_local(last_refresh),
        "last_error": last_error,
        "snapshot_exists": isinstance(snapshot, dict),
        "normalized_sleep_metrics": normalized_sleep,
        "raw_sources_info": raw_sources_info,
        "raw_sleep_top_level": raw_sleep_top_level,
        "raw_sleep_candidates": raw_sleep_candidates,
    }
    return JSONResponse(payload)


@mcp.tool
def get_cache_status() -> dict[str, Any]:
    """Estado del caché y último error."""
    with CACHE_LOCK:
        return deepcopy(CACHE)


@mcp.tool
def get_cached_snapshot() -> dict[str, Any]:
    """Última foto cacheada del día actual, con métricas normalizadas y raw_sources."""
    with CACHE_LOCK:
        snapshot = deepcopy(CACHE["snapshot"])
        metrics = {}
        if isinstance(snapshot, dict):
            metrics = snapshot.get("metrics") or {}

        return {
            "status": CACHE["status"],
            "last_refresh": CACHE["last_refresh"],
            "last_refresh_local": _isoish_to_local(CACHE["last_refresh"]),
            "last_error": CACHE["last_error"],
            "snapshot_obtenido_local": _isoish_to_local(snapshot.get("fetched_at")) if isinstance(snapshot, dict) else None,
            "datos_hasta_local": metrics.get("datos_hasta_local") if isinstance(metrics, dict) else None,
            "ultima_sincronizacion_conector_local": _isoish_to_local(CACHE["last_refresh"]),
            "snapshot": snapshot,
        }


@mcp.tool
def refresh_snapshot() -> dict[str, Any]:
    """Fuerza una actualización inmediata desde Garmin."""
    return _refresh_cache_sync()


@mcp.tool
def get_day_snapshot(target_date: str | None = None) -> dict[str, Any]:
    """Foto completa de un día concreto (YYYY-MM-DD)."""
    return _collect_day_snapshot(_parse_date(target_date), include_recent_activities=False)


@mcp.tool
def get_raw_sources(target_date: str | None = None, include_recent_activities: bool = True) -> dict[str, Any]:
    """Devuelve los payloads crudos que ha devuelto Garmin para un día."""
    snapshot = _collect_day_snapshot(_parse_date(target_date), include_recent_activities=include_recent_activities)
    return {
        "date": snapshot["date"],
        "fetched_at": snapshot["fetched_at"],
        "raw_sources": snapshot["raw_sources"],
        "source_errors": snapshot["source_errors"],
    }


@mcp.tool
def get_primary_device_info(target_date: str | None = None) -> dict[str, Any]:
    """Devuelve el dispositivo principal detectado y, si existe, su configuración."""
    snapshot = _collect_day_snapshot(_parse_date(target_date), include_recent_activities=False)
    raw = snapshot["raw_sources"]
    return {
        "date": snapshot["date"],
        "primary_device_info_raw": raw.get("primary_device_info_raw"),
        "devices_raw": raw.get("devices_raw"),
        "device_settings_raw": raw.get("device_settings_raw"),
        "source_errors": snapshot["source_errors"],
    }


@mcp.tool
def get_recent_activities(limit: int = 100) -> list[dict[str, Any]]:
    """Actividades recientes normalizadas. Por defecto hasta 100.
    Usa limit=-1 para obtener TODAS las actividades (historico completo desde 2016).
    Advertencia: obtener todo puede tardar varios minutos."""
    if limit < 0:
        limit = 9999
    limit = max(1, min(200, int(limit)))
    with FETCH_LOCK:
        api = _get_api()
        activities, err = _optional_call_first(api, ("get_activities",), 0, limit)
        if activities is None:
            raise RuntimeError(err or "No pude leer las actividades recientes")
        return [_normalize_activity(a) for a in activities[:limit] if isinstance(a, dict)]


@mcp.tool
def get_activity_fit_download(activity_id: str) -> str:
    """Link de descarga del .fit/.zip de una actividad.
    Solo decí "dame el fit de [nombre o ID]" y te da el link para descargar.
    Ejemplo: get_activity_fit_download("22621731390")
    Returns clickable URL."""
    url = f"https://garmin-coach-mcp-production.up.railway.app/download/{activity_id}"
    return f"👉 Descarga el .fit aquí: {url}"


@mcp.tool
def get_window_rollup(days: int = 7) -> list[dict[str, Any]]:
    """Rollup de varios días hacia atrás."""
    days = max(1, min(7, int(days)))
    end = _today_local()
    results = []
    for offset in range(days - 1, -1, -1):
        target = (end - timedelta(days=offset)).isoformat()
        results.append(_collect_day_snapshot(target, include_recent_activities=False))
        time.sleep(0.4)
    return results


def _run_server() -> None:
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    thread = threading.Thread(target=_background_refresh_loop, daemon=True)
    thread.start()
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=PORT,
        middleware=[Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])],
    )


# === BEGIN GARMIN METRICS PATCH ===

_GARMIN_PATCH_STRESS_LABEL_ES = {
    "REST": "Descanso",
    "LOW": "Bajo",
    "MEDIUM": "Medio",
    "HIGH": "Alto",
    "BALANCED": "Equilibrado",
}

_GARMIN_PATCH_HRV_STATUS_ES = {
    "BALANCED": "Equilibrado",
    "UNBALANCED": "Desequilibrado",
    "LOW": "Bajo",
    "POOR": "Bajo",
}

_GARMIN_PATCH_TRAINING_READINESS_STATUS_ES = {
    "LOW": "Bajo",
    "MODERATE": "Moderada",
    "HIGH": "Alto",
}

_GARMIN_PATCH_TRAINING_READINESS_MESSAGE_ES = {
    "WORKING_HARD": "Entrenando duro",
    "BALANCE_YOUR_TRAINING_LOAD": "Equilibra tu carga de entrenamiento",
}

_GARMIN_PATCH_ACUTE_LOAD_STATUS_ES = {
    "OPTIMAL": "Óptimo",
    "LOW": "Baja",
    "HIGH": "Alta",
}


def _garmin_patch_first_non_none(*values):
    for v in values:
        if v is not None:
            return v
    return None


def _garmin_patch_put(metrics, key, value):
    if value is not None:
        metrics[key] = value


def _garmin_patch_minutes(seconds):
    if seconds is None:
        return None
    try:
        return int(round(float(seconds) / 60.0))
    except Exception:
        return None


def _garmin_patch_pick_training_readiness(raw_value):
    if isinstance(raw_value, dict):
        entries = [raw_value]
    elif isinstance(raw_value, list):
        entries = [x for x in raw_value if isinstance(x, dict)]
    else:
        entries = []

    if not entries:
        return None

    def rank(entry):
        ts = str(entry.get("timestampLocal") or entry.get("timestamp") or "")
        return (
            1 if entry.get("validSleep") else 0,
            1 if entry.get("inputContext") == "UPDATE_REALTIME_VARIABLES" else 0,
            ts,
        )

    return sorted(entries, key=rank, reverse=True)[0]


_GARMIN_PATCH_ORIGINAL_COLLECT_DAY_SNAPSHOT = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _GARMIN_PATCH_ORIGINAL_COLLECT_DAY_SNAPSHOT(*args, **kwargs)

    raw = snap.get("raw_sources") or {}
    metrics = snap.get("metrics") or {}
    snap["metrics"] = metrics

    summary = raw.get("summary_raw") or {}
    heart = raw.get("heart_raw") or {}
    sleep = raw.get("sleep_raw") or {}
    stress = raw.get("stress_raw") or {}
    hrv = raw.get("hrv_raw") or {}
    training_readiness = _garmin_patch_pick_training_readiness(raw.get("training_readiness_raw"))
    training_status = raw.get("training_status_raw") or {}
    user_profile = raw.get("user_profile_raw") or {}

    _garmin_patch_put(metrics, "body_battery_current", summary.get("bodyBatteryMostRecentValue"))
    _garmin_patch_put(metrics, "body_battery_max", summary.get("bodyBatteryHighestValue"))
    _garmin_patch_put(metrics, "body_battery_min", summary.get("bodyBatteryLowestValue"))

    sleep_dto = sleep.get("dailySleepDTO") or {}
    sleep_seconds = _garmin_patch_first_non_none(
        sleep_dto.get("sleepTimeSeconds"),
        summary.get("sleepingSeconds"),
    )
    _garmin_patch_put(metrics, "sleep_duration_seconds", sleep_seconds)
    _garmin_patch_put(metrics, "sleep_hours", round(sleep_seconds / 3600, 1) if sleep_seconds is not None else None)
    _garmin_patch_put(metrics, "sleep_score", ((sleep_dto.get("sleepScores") or {}).get("overall") or {}).get("value"))
    _garmin_patch_put(metrics, "sleep_deep_min", _garmin_patch_minutes(sleep_dto.get("deepSleepSeconds")))
    _garmin_patch_put(metrics, "sleep_rem_min", _garmin_patch_minutes(sleep_dto.get("remSleepSeconds")))
    _garmin_patch_put(metrics, "sleep_light_min", _garmin_patch_minutes(sleep_dto.get("lightSleepSeconds")))
    _garmin_patch_put(metrics, "sleep_awake_min", _garmin_patch_minutes(sleep_dto.get("awakeSleepSeconds")))

    _garmin_patch_put(
        metrics,
        "resting_heart_rate",
        _garmin_patch_first_non_none(
            heart.get("restingHeartRate"),
            summary.get("restingHeartRate"),
            sleep.get("restingHeartRate"),
        ),
    )
    _garmin_patch_put(
        metrics,
        "resting_heart_rate_7d_avg",
        _garmin_patch_first_non_none(
            heart.get("lastSevenDaysAvgRestingHeartRate"),
            summary.get("lastSevenDaysAvgRestingHeartRate"),
        ),
    )

    stress_label = _garmin_patch_first_non_none(
        summary.get("stressQualifier"),
        stress.get("stressQualifier"),
    )
    _garmin_patch_put(metrics, "stress_avg", _garmin_patch_first_non_none(summary.get("averageStressLevel"), stress.get("avgStressLevel")))
    _garmin_patch_put(metrics, "stress_max", _garmin_patch_first_non_none(summary.get("maxStressLevel"), stress.get("maxStressLevel")))
    _garmin_patch_put(metrics, "stress_label", stress_label)
    if stress_label is not None:
        metrics["stress_label_es"] = _GARMIN_PATCH_STRESS_LABEL_ES.get(stress_label, metrics.get("stress_label_es"))

    hrv_summary = hrv.get("hrvSummary") or {}
    hrv_baseline = hrv_summary.get("baseline") or {}
    hrv_status = hrv_summary.get("status")
    _garmin_patch_put(metrics, "hrv_last_night", hrv_summary.get("lastNightAvg"))
    _garmin_patch_put(metrics, "hrv_weekly_avg", hrv_summary.get("weeklyAvg"))
    _garmin_patch_put(metrics, "hrv_status", hrv_status)
    _garmin_patch_put(metrics, "hrv_baseline_low", hrv_baseline.get("balancedLow"))
    _garmin_patch_put(metrics, "hrv_baseline_high", hrv_baseline.get("balancedUpper"))
    _garmin_patch_put(metrics, "hrv_last_night_5min_high", hrv_summary.get("lastNight5MinHigh"))
    if hrv_status is not None:
        metrics["hrv_status_es"] = _GARMIN_PATCH_HRV_STATUS_ES.get(hrv_status, metrics.get("hrv_status_es"))

    if training_readiness:
        tr_status = training_readiness.get("level")
        tr_message = training_readiness.get("feedbackShort")
        _garmin_patch_put(metrics, "training_readiness_score", training_readiness.get("score"))
        _garmin_patch_put(metrics, "training_readiness_status", tr_status)
        _garmin_patch_put(metrics, "training_readiness_message", tr_message)
        _garmin_patch_put(metrics, "training_readiness_recovery_time", training_readiness.get("recoveryTime"))
        _garmin_patch_put(metrics, "training_readiness_input_context", training_readiness.get("inputContext"))
        if tr_status is not None:
            metrics["training_readiness_status_es"] = _GARMIN_PATCH_TRAINING_READINESS_STATUS_ES.get(
                tr_status,
                metrics.get("training_readiness_status_es"),
            )
        if tr_message is not None:
            metrics["training_readiness_message_es"] = _GARMIN_PATCH_TRAINING_READINESS_MESSAGE_ES.get(
                tr_message,
                metrics.get("training_readiness_message_es"),
            )

    latest_status_data = (((training_status.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData")) or {})
    acute = None
    if isinstance(latest_status_data, dict):
        for device_data in latest_status_data.values():
            if isinstance(device_data, dict):
                acute = device_data.get("acuteTrainingLoadDTO")
                if acute:
                    break

    acute_status = None
    if acute:
        acute_status = acute.get("acwrStatus")
        _garmin_patch_put(metrics, "acute_load", acute.get("dailyTrainingLoadAcute"))
        _garmin_patch_put(metrics, "acute_load_ratio", acute.get("dailyAcuteChronicWorkloadRatio"))
        _garmin_patch_put(metrics, "acute_load_status", acute_status)
        if acute_status is not None:
            metrics["acute_load_status_es"] = _GARMIN_PATCH_ACUTE_LOAD_STATUS_ES.get(
                acute_status,
                metrics.get("acute_load_status_es"),
            )

    _garmin_patch_put(metrics, "steps", summary.get("totalSteps"))
    _garmin_patch_put(metrics, "steps_goal", summary.get("dailyStepGoal"))

    vo2_block = ((training_status.get("mostRecentVO2Max") or {}).get("generic")) or {}
    profile_data = (user_profile.get("userData") or {})

    # Fitness age (Edad Física) – puede venir de fitness_age_raw o de vo2_block
    fitness_age_raw = raw.get("fitness_age_raw") or {}
    fitness_age_val = (
        vo2_block.get("fitnessAge")
        or (fitness_age_raw.get("fitnessAge") if isinstance(fitness_age_raw, dict) else None)
        or (fitness_age_raw.get("value") if isinstance(fitness_age_raw, dict) else None)
    )
    if fitness_age_val is not None:
        _garmin_patch_put(metrics, "fitness_age", fitness_age_val)

    _garmin_patch_put(
        metrics,
        "vo2max",
        _garmin_patch_first_non_none(
            vo2_block.get("vo2MaxPreciseValue"),
            vo2_block.get("vo2MaxValue"),
            profile_data.get("vo2MaxRunning"),
        ),
    )

    # VO2 max label (maxMetCategory: 0=Deficiente,1=Bajo,2=Aceptable,3=Bueno,4=Excelente,5=Superior)
    _VO2MAX_CAT_ES = {0: "Deficiente", 1: "Bajo", 2: "Aceptable", 3: "Bueno", 4: "Excelente", 5: "Superior"}
    vo2_cat = vo2_block.get("maxMetCategory")
    if vo2_cat is not None:
        _garmin_patch_put(metrics, "vo2max_label", _VO2MAX_CAT_ES.get(vo2_cat))

    # Respiración
    respiration = raw.get("respiration_raw") or {}
    _garmin_patch_put(metrics, "respiration_waking_avg", respiration.get("avgWakingRespirationValue"))
    _garmin_patch_put(metrics, "respiration_sleep_avg", respiration.get("avgSleepRespirationValue"))
    _garmin_patch_put(metrics, "respiration_min", respiration.get("lowestRespirationValue"))
    _garmin_patch_put(metrics, "respiration_max", respiration.get("highestRespirationValue"))

    # SpO2
    spo2 = raw.get("spo2_raw") or {}
    if isinstance(spo2, dict):
        _garmin_patch_put(metrics, "spo2_latest", spo2.get("latestSpO2"))
        _garmin_patch_put(metrics, "spo2_avg_day", spo2.get("averageSpO2"))
        _garmin_patch_put(metrics, "spo2_avg_sleep", spo2.get("avgSleepSpO2"))
        _garmin_patch_put(metrics, "spo2_min", spo2.get("lowestSpO2"))
        _garmin_patch_put(metrics, "spo2_7d_avg", spo2.get("lastSevenDaysAvgSpO2"))

    return snap

# === END GARMIN METRICS PATCH ===

# === GARMIN_ES_TRANSLATIONS_PATCH_START ===
_GARMIN_STATUS_ES_GENERIC = {
    "BALANCED": "Equilibrado",
    "LOW": "Bajo",
    "MODERATE": "Moderada",
    "HIGH": "Alto",
    "OPTIMAL": "Óptimo",
    "POOR": "Deficiente",
    "UNBALANCED": "Desequilibrado",
    "NORMAL": "Normal",
}

_GARMIN_STATUS_ES_BY_FIELD = {
    "stress_label": {
        "BALANCED": "Equilibrado",
        "LOW": "Bajo",
        "MODERATE": "Moderada",
        "HIGH": "Alto",
    },
    "hrv_status": {
        "BALANCED": "Equilibrada",
        "LOW": "Baja",
        "MODERATE": "Moderada",
        "HIGH": "Alta",
    },
    "training_readiness_status": {
        "BALANCED": "Equilibrada",
        "LOW": "Baja",
        "MODERATE": "Moderada",
        "HIGH": "Alta",
    },
    "acute_load_status": {
        "OPTIMAL": "Óptima",
        "LOW": "Baja",
        "MODERATE": "Moderada",
        "HIGH": "Alta",
        "BALANCED": "Equilibrada",
        "POOR": "Deficiente",
        "UNBALANCED": "Desequilibrada",
    },
}

_GARMIN_TRAINING_READINESS_MESSAGE_ES = {
    "WORKING_HARD": "Entrenando duro",
    "BALANCE_YOUR_TRAINING_LOAD": "Equilibra tu carga de entrenamiento",
    "READY_TO_TRAIN": "Listo para entrenar",
    "RECOVERING": "Recuperando",
    "WELL_RECOVERED": "Bien recuperado",
    "FATIGUED": "Fatigado",
}

_GARMIN_TRAINING_STATUS_ES = {
    "PRODUCTIVE": "Productivo",
    "MAINTAINING": "Mantenimiento",
    "RECOVERY": "Recuperación",
    "PEAKING": "Pico de forma",
    "UNPRODUCTIVE": "No productivo",
    "OVERREACHING": "Sobrecarga",
    "DETRAINING": "Desentrenamiento",
    "NO_STATUS": "Sin estado",
}

def _translate_metric_status_es(field_name, value):
    if not value or not isinstance(value, str):
        return None
    field_map = _GARMIN_STATUS_ES_BY_FIELD.get(field_name) or {}
    return field_map.get(value) or _GARMIN_STATUS_ES_GENERIC.get(value)

def _translate_training_readiness_message_es(value):
    if not value or not isinstance(value, str):
        return None
    return _GARMIN_TRAINING_READINESS_MESSAGE_ES.get(value)

def _translate_training_status_es(value):
    if not value or not isinstance(value, str):
        return None
    base = value.split("_", 1)[0]
    return _GARMIN_TRAINING_STATUS_ES.get(base)

def _extract_training_status_code(raw):
    if not isinstance(raw, dict):
        return None

    latest = ((raw.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData") or {})
    if not isinstance(latest, dict) or not latest:
        return None

    entry = None
    for v in latest.values():
        if isinstance(v, dict) and v.get("primaryTrainingDevice"):
            entry = v
            break

    if entry is None:
        entry = next((v for v in latest.values() if isinstance(v, dict)), None)

    if not isinstance(entry, dict):
        return None

    phrase = entry.get("trainingStatusFeedbackPhrase")
    if isinstance(phrase, str) and phrase:
        return phrase.split("_", 1)[0]

    return None

if "_collect_day_snapshot" in globals():
    _GARMIN_COACH_ORIGINAL_COLLECT_DAY_SNAPSHOT = _collect_day_snapshot

    def _collect_day_snapshot(*args, **kwargs):
        snap = _GARMIN_COACH_ORIGINAL_COLLECT_DAY_SNAPSHOT(*args, **kwargs)
        if not isinstance(snap, dict):
            return snap

        metrics = snap.setdefault("metrics", {})
        raw = snap.get("raw_sources") or {}

        for key_en, key_es in (
            ("stress_label", "stress_label_es"),
            ("hrv_status", "hrv_status_es"),
            ("acute_load_status", "acute_load_status_es"),
            ("training_readiness_status", "training_readiness_status_es"),
        ):
            translated = _translate_metric_status_es(key_en, metrics.get(key_en))
            if translated:
                metrics[key_es] = translated

        translated_msg = _translate_training_readiness_message_es(
            metrics.get("training_readiness_message")
        )
        if translated_msg:
            metrics["training_readiness_message_es"] = translated_msg

        training_status = metrics.get("training_status") or _extract_training_status_code(
            raw.get("training_status_raw")
        )
        if training_status:
            metrics["training_status"] = training_status
            translated_training_status = _translate_training_status_es(training_status)
            if translated_training_status:
                metrics["training_status_es"] = translated_training_status

        return snap
# === GARMIN_ES_TRANSLATIONS_PATCH_END ===

# ==== ES_FINAL_TRANSLATIONS_PATCH_START ====

_ES_STATUS_MAP = {
    "BALANCED": "Equilibrado",
    "LOW": "Bajo",
    "MODERATE": "Moderada",
    "HIGH": "Alto",
    "OPTIMAL": "Óptimo",
    "PRODUCTIVE": "Productivo",
    "RECOVERY": "Recuperación",
    "STRAINED": "Sobrecarga",
    "OVERREACHING": "Exceso de carga",
    "DETRAINING": "Desentrenamiento",
    "MAINTAINING": "Mantenimiento",
    "PEAKING": "Pico de forma",
}

_ES_MESSAGE_MAP = {
    "WORKING_HARD": "Entrenando duro",
    "BALANCE_YOUR_TRAINING_LOAD": "Equilibra tu carga de entrenamiento",
}

ES_FIELD_LABELS = {
    "body_battery_current": "Batería corporal actual",
    "body_battery_max": "Batería corporal máxima",
    "body_battery_min": "Batería corporal mínima",
    "body_battery_charged": "Batería corporal cargada",
    "body_battery_drained": "Batería corporal drenada",
    "body_battery_status": "Estado de la batería corporal",
    "sleep_duration_seconds": "Duración del sueño",
    "sleep_hours": "Horas de sueño",
    "sleep_score": "Puntuación de sueño",
    "sleep_deep_min": "Sueño profundo",
    "sleep_rem_min": "Sueño REM",
    "sleep_light_min": "Sueño ligero",
    "sleep_awake_min": "Tiempo despierto",
    "resting_heart_rate": "FC en reposo",
    "resting_heart_rate_7d_avg": "FC en reposo media de 7 días",
    "stress_avg": "Estrés medio",
    "stress_max": "Estrés máximo",
    "stress_label": "Estado del estrés",
    "hrv_last_night": "VFC nocturna",
    "hrv_weekly_avg": "VFC media semanal",
    "hrv_status": "Estado de la VFC",
    "hrv_baseline_low": "Límite inferior equilibrado de la VFC",
    "hrv_baseline_high": "Límite superior equilibrado de la VFC",
    "hrv_last_night_5min_high": "Máximo nocturno de VFC en 5 min",
    "training_readiness_score": "Preparación para entrenar",
    "training_readiness_status": "Estado de preparación para entrenar",
    "training_readiness_message": "Mensaje de preparación para entrenar",
    "training_readiness_recovery_time": "Recuperación restante",
    "training_readiness_input_context": "Contexto de preparación para entrenar",
    "acute_load": "Carga aguda",
    "acute_load_ratio": "Ratio carga aguda/crónica",
    "acute_load_status": "Estado de la carga aguda",
    "steps": "Pasos",
    "steps_goal": "Objetivo de pasos",
    "vo2max": "VO2max",
}

ES_TERM_LABELS = {
    "hr": "FC",
    "rhr": "FC en reposo",
    "hrv": "VFC",
    "vo2max": "VO2max",
    "spo2": "SpO2",
    "rem": "REM",
    "body_battery": "Batería corporal",
}

def _translate_status_es(value):
    if value is None:
        return None
    return _ES_STATUS_MAP.get(str(value).strip().upper(), value)

def _translate_message_es(value):
    if value is None:
        return None
    return _ES_MESSAGE_MAP.get(str(value).strip().upper(), value)

try:
    _collect_day_snapshot_original_es_patch
except NameError:
    _collect_day_snapshot_original_es_patch = _collect_day_snapshot

def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_es_patch(*args, **kwargs)
    metrics = snap.get("metrics") or {}

    metrics["stress_label_es"] = _translate_status_es(metrics.get("stress_label"))
    metrics["hrv_status_es"] = _translate_status_es(metrics.get("hrv_status"))
    metrics["training_readiness_status_es"] = _translate_status_es(metrics.get("training_readiness_status"))
    metrics["training_readiness_message_es"] = _translate_message_es(metrics.get("training_readiness_message"))
    metrics["acute_load_status_es"] = _translate_status_es(metrics.get("acute_load_status"))

    snap["metrics"] = metrics
    return snap

# ==== ES_FINAL_TRANSLATIONS_PATCH_END ====

# === CANONICAL_ES_TRANSLATIONS_START ===
_FINAL_STATUS_ES = {
    "BALANCED": "Equilibrado",
    "UNBALANCED": "Desequilibrado",
    "LOW": "Bajo",
    "MODERATE": "Moderada",
    "HIGH": "Alto",
    "VERY_HIGH": "Muy alto",
    "OPTIMAL": "Óptimo",
    "PRODUCTIVE": "Productivo",
    "RECOVERY": "Recuperación",
    "UNPRODUCTIVE": "No productivo",
    "PEAK": "Pico",
    "MAINTAINING": "Mantenimiento",
    "OVERREACHING": "Exceso de carga",
}

_FINAL_MESSAGE_ES = {
    "WORKING_HARD": "Entrenando duro",
    "BALANCE_YOUR_TRAINING_LOAD": "Equilibra tu carga de entrenamiento",
    "UNKNOWN": "Desconocido",
    "PRODUCTIVE": "Productivo",
    "RECOVERY": "Recuperación",
    "UNPRODUCTIVE": "No productivo",
    "OVERREACHING": "Exceso de carga",
}

def _translate_status_es(value):
    if value is None:
        return None
    value = str(value).strip().upper()
    return _FINAL_STATUS_ES.get(value, value)

def _translate_message_es(value):
    if value is None:
        return None
    value = str(value).strip().upper()
    return _FINAL_MESSAGE_ES.get(value, value)

try:
    _collect_day_snapshot_original_es_final
except NameError:
    _collect_day_snapshot_original_es_final = _collect_day_snapshot

def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_es_final(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})

    metrics["stress_label_es"] = _translate_status_es(metrics.get("stress_label"))
    metrics["hrv_status_es"] = _translate_status_es(metrics.get("hrv_status"))
    metrics["training_readiness_status_es"] = _translate_status_es(metrics.get("training_readiness_status"))
    metrics["training_readiness_message_es"] = _translate_message_es(metrics.get("training_readiness_message"))
    metrics["acute_load_status_es"] = _translate_status_es(metrics.get("acute_load_status"))

    return snap
# === CANONICAL_ES_TRANSLATIONS_END ===


# === TRAINING READINESS RECOVERY GUARDRAILS START ===
_RECOVERY_STATE_ES = {
    "fresh": "Fresco",
    "estimated_from_last_activity": "Estimado desde la última actividad",
    "stale": "Desactualizado",
    "missing_timestamp": "Sin marca temporal",
    "missing": "Sin datos",
}


def _safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _parse_garmin_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            ts = float(value)
            if ts > 1_000_000_000_000:
                ts /= 1000.0
            dt = datetime.fromtimestamp(ts, tz=APP_TIMEZONE)
        except Exception:
            return None
    else:
        raw = str(value).strip()
        if not raw:
            return None

        candidates = [raw]
        if " " in raw and "T" not in raw:
            candidates.append(raw.replace(" ", "T", 1))

        dt = None
        for candidate in candidates:
            normalized = candidate
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            try:
                dt = datetime.fromisoformat(normalized)
                break
            except ValueError:
                continue

        if dt is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue

        if dt is None:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=APP_TIMEZONE)
    return dt.astimezone(APP_TIMEZONE)


def _extract_latest_activity_end_local(raw_sources: Any) -> datetime | None:
    if not isinstance(raw_sources, dict):
        return None

    latest = None
    for key in ("recent_activities_raw", "activities_for_date_raw"):
        activities = raw_sources.get(key)
        if not isinstance(activities, list):
            continue

        for activity in activities:
            if not isinstance(activity, dict):
                continue

            start_dt = _parse_garmin_datetime(
                activity.get("endTimeLocal")
                or activity.get("stopTimeLocal")
                or activity.get("startTimeLocal")
                or activity.get("startTimeGMT")
                or activity.get("beginTimestamp")
            )
            if start_dt is None:
                continue

            end_dt = _parse_garmin_datetime(activity.get("endTimeLocal") or activity.get("stopTimeLocal"))
            if end_dt is None:
                duration_seconds = _safe_float(activity.get("duration"))
                if duration_seconds is not None:
                    end_dt = start_dt + timedelta(seconds=duration_seconds)
                else:
                    end_dt = start_dt

            if latest is None or end_dt > latest:
                latest = end_dt

    return latest


def _extract_recovery_value(entry: dict[str, Any]) -> tuple[float | None, str | None, str | None]:
    for key, unit in (
        ("recoveryMinutes", "minutes"),
        ("recoveryTimeMinutes", "minutes"),
        ("recoveryMin", "minutes"),
        ("recoveryHours", "hours"),
        ("recoveryTime", "hours_assumed"),
    ):
        value = _safe_float(entry.get(key))
        if value is not None:
            return value, unit, key
    return None, None, None


def _build_recovery_metrics(entry: Any, raw_sources: Any) -> dict[str, Any]:
    base_result: dict[str, Any] = {
        "training_readiness_recovery_time_raw": None,
        "training_readiness_recovery_time_raw_key": None,
        "training_readiness_recovery_time_unit": None,
        "training_readiness_recovery_time_unit_is_assumed": False,
        "training_readiness_recovery_reference_source": None,
        "training_readiness_recovery_reference_local": None,
        "training_readiness_recovery_age_minutes": None,
        "training_readiness_recovery_state": "missing",
        "training_readiness_recovery_state_es": _RECOVERY_STATE_ES.get("missing"),
        "training_readiness_recovery_is_stale": True,
        "training_readiness_recovery_minutes_remaining": None,
        "training_readiness_recovery_hours_remaining": None,
        "training_readiness_recovery_time": None,
        "training_readiness_recovery_safe_text": "Sin datos de recuperación",
        "training_readiness_recovery_answer_for_llm": "Sin datos de recuperación en este snapshot",
    }

    if not isinstance(entry, dict):
        return base_result

    raw_value, unit, raw_key = _extract_recovery_value(entry)
    reference_dt = _parse_garmin_datetime(entry.get("timestampLocal") or entry.get("timestamp"))
    reference_source = "training_readiness_timestamp"
    if reference_dt is None:
        reference_dt = _extract_latest_activity_end_local(raw_sources)
        if reference_dt is not None:
            reference_source = "last_activity_end"

    result: dict[str, Any] = {
        "training_readiness_recovery_time_raw": raw_value,
        "training_readiness_recovery_time_raw_key": raw_key,
        "training_readiness_recovery_time_unit": unit,
        "training_readiness_recovery_time_unit_is_assumed": unit == "hours_assumed",
        "training_readiness_recovery_reference_source": reference_source if reference_dt is not None else None,
        "training_readiness_recovery_reference_local": reference_dt.isoformat() if reference_dt is not None else None,
        "training_readiness_recovery_age_minutes": None,
        "training_readiness_recovery_state": "missing",
        "training_readiness_recovery_state_es": _RECOVERY_STATE_ES.get("missing"),
        "training_readiness_recovery_is_stale": True,
        "training_readiness_recovery_minutes_remaining": None,
        "training_readiness_recovery_hours_remaining": None,
        "training_readiness_recovery_time": None,
        "training_readiness_recovery_safe_text": "Sin datos de recuperación",
        "training_readiness_recovery_answer_for_llm": "Sin datos de recuperación en este snapshot",
    }

    if raw_value is None:
        state = "missing"
        age_minutes = None
    elif reference_dt is None:
        state = "missing_timestamp"
        age_minutes = None
    else:
        age_minutes = max(0, int((_now_local() - reference_dt).total_seconds() // 60))
        crossed_local_day = reference_dt.date() < _today_local()
        is_stale = age_minutes > RECOVERY_MAX_FRESH_MINUTES or (crossed_local_day and age_minutes > RECOVERY_CROSS_DAY_STALE_MINUTES)
        if is_stale:
            state = "stale"
        elif reference_source == "last_activity_end":
            state = "estimated_from_last_activity"
        else:
            state = "fresh"

    result["training_readiness_recovery_age_minutes"] = age_minutes
    result["training_readiness_recovery_state"] = state
    result["training_readiness_recovery_state_es"] = _RECOVERY_STATE_ES.get(state, state)
    result["training_readiness_recovery_is_stale"] = state in {"stale", "missing", "missing_timestamp"}

    if raw_value is None or state in {"stale", "missing", "missing_timestamp"} or unit is None:
        result.setdefault("training_readiness_recovery_minutes_remaining", None)
        result.setdefault("training_readiness_recovery_hours_remaining", None)
        result["training_readiness_recovery_time"] = 0 if raw_value == 0 else None

        if state == "stale":
            result["training_readiness_recovery_safe_text"] = "Dato de recuperación desactualizado; no extrapolar"
        elif state == "missing_timestamp":
            result["training_readiness_recovery_safe_text"] = "Sin marca temporal; no extrapolar"
        else:
            result["training_readiness_recovery_safe_text"] = "Sin datos de recuperación"

        result["training_readiness_recovery_answer_for_llm"] = result["training_readiness_recovery_safe_text"]
        return result

    if unit == "minutes":
        base_minutes = raw_value
    else:
        base_minutes = raw_value * 60.0

    remaining_minutes = max(0, int(round(base_minutes - float(age_minutes or 0))))
    remaining_hours = round(remaining_minutes / 60.0, 1)
    result["training_readiness_recovery_minutes_remaining"] = remaining_minutes
    result["training_readiness_recovery_hours_remaining"] = remaining_hours
    result["training_readiness_recovery_time"] = int((remaining_minutes + 59) // 60) if unit in {"hours", "hours_assumed"} else remaining_minutes

    if state == "fresh":
        if remaining_minutes == 0:
            result["training_readiness_recovery_safe_text"] = "0 min restantes"
        elif remaining_minutes < 60:
            result["training_readiness_recovery_safe_text"] = f"{remaining_minutes} min restantes"
        else:
            result["training_readiness_recovery_safe_text"] = f"{remaining_hours} h restantes"
    elif state == "estimated_from_last_activity":
        if remaining_minutes == 0:
            result["training_readiness_recovery_safe_text"] = "Estimación: 0 min restantes"
        elif remaining_minutes < 60:
            result["training_readiness_recovery_safe_text"] = f"Estimación: {remaining_minutes} min restantes"
        else:
            result["training_readiness_recovery_safe_text"] = f"Estimación: {remaining_hours} h restantes"
    elif state == "stale":
        result["training_readiness_recovery_safe_text"] = "Dato de recuperación desactualizado; no extrapolar"
    elif state == "missing_timestamp":
        result["training_readiness_recovery_safe_text"] = "Sin marca temporal; no extrapolar"
    else:
        result["training_readiness_recovery_safe_text"] = "Sin datos de recuperación"

    result["training_readiness_recovery_answer_for_llm"] = result["training_readiness_recovery_safe_text"]
    return result


try:
    _collect_day_snapshot_original_recovery_guardrails
except NameError:
    _collect_day_snapshot_original_recovery_guardrails = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_recovery_guardrails(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})
    raw_sources = snap.get("raw_sources") or {}

    entry = None
    selected_entry = metrics.get("training_readiness_selected_entry")
    if isinstance(selected_entry, dict):
        entry = selected_entry
    else:
        entry = _select_training_readiness_entry(raw_sources.get("training_readiness_raw"))

    recovery_metrics = _build_recovery_metrics(entry, raw_sources)
    metrics.update(recovery_metrics)

    selected_ts = None
    if isinstance(entry, dict):
        selected_ts = entry.get("timestampLocal") or entry.get("timestamp")
    metrics["training_readiness_selected_timestamp_local"] = selected_ts

    return snap


ES_FIELD_LABELS.update({
    "training_readiness_recovery_time_raw": "Recuperación Garmin bruta",
    "training_readiness_recovery_time_unit": "Unidad de recuperación Garmin",
    "training_readiness_recovery_reference_source": "Origen de la referencia de recuperación",
    "training_readiness_recovery_reference_local": "Referencia temporal de recuperación",
    "training_readiness_recovery_age_minutes": "Antigüedad de la recuperación (min)",
    "training_readiness_recovery_state": "Estado de frescura de la recuperación",
    "training_readiness_recovery_state_es": "Estado de frescura de la recuperación (ES)",
    "training_readiness_recovery_is_stale": "Recuperación desactualizada",
    "training_readiness_recovery_minutes_remaining": "Recuperación restante (min)",
    "training_readiness_recovery_hours_remaining": "Recuperación restante (h)",
    "training_readiness_recovery_safe_text": "Texto seguro de recuperación",
    "training_readiness_recovery_answer_for_llm": "Respuesta canónica de recuperación para LLM",
    "training_readiness_selected_timestamp_local": "Timestamp de la preparación para entrenar",
})
# === TRAINING READINESS RECOVERY GUARDRAILS END ===


# === CANONICAL UI/SPANISH FIELDS START ===
def _latest_known_data_timestamp_local(metrics: dict[str, Any]) -> str | None:
    candidates = []
    for key in (
        "body_battery_last_timestamp_local",
        "training_readiness_selected_timestamp_local",
        "training_readiness_recovery_reference_local",
    ):
        value = metrics.get(key)
        dt = _parse_garmin_datetime(value) if value is not None else None
        if dt is not None:
            candidates.append(dt)

    if not candidates:
        return None
    return max(candidates).isoformat()


try:
    _collect_day_snapshot_original_ui_canonical_fields
except NameError:
    _collect_day_snapshot_original_ui_canonical_fields = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_ui_canonical_fields(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})

    metrics["predisposicion_para_entrenar"] = metrics.get("training_readiness_score")
    readiness_status_es = _normalize_readiness_status_es(
        metrics.get("training_readiness_status_es")
        or metrics.get("training_readiness_status")
    )
    metrics["predisposicion_para_entrenar_estado"] = readiness_status_es
    metrics["predisposicion_para_entrenar_texto"] = (
        f'{metrics.get("training_readiness_score")} — {readiness_status_es}'
        if metrics.get("training_readiness_score") is not None and readiness_status_es
        else None
    )

    metrics["estado_vfc"] = metrics.get("hrv_status_es") or metrics.get("hrv_status")
    metrics["vfc_media_noche_ms"] = metrics.get("hrv_last_night")
    metrics["vfc_media_7_dias_ms"] = metrics.get("hrv_weekly_avg")

    readiness_entry = metrics.get("training_readiness_selected_entry") or {}
    if isinstance(readiness_entry, dict) and readiness_entry:
        metrics["predisposicion_factor_vfc_ms"] = readiness_entry.get("hrvWeeklyAverage")
        metrics["predisposicion_factor_sueno_score"] = readiness_entry.get("sleepScore")
        metrics["predisposicion_factor_recuperacion_raw"] = readiness_entry.get("recoveryTime")
        metrics["predisposicion_factor_carga_aguda"] = readiness_entry.get("acuteLoad")
        metrics["predisposicion_factor_feedback_vfc_raw"] = readiness_entry.get("hrvFactorFeedback")
        metrics["predisposicion_factor_feedback_recuperacion_raw"] = readiness_entry.get("recoveryTimeFactorFeedback")
        metrics["predisposicion_factor_feedback_sueno_reciente_raw"] = readiness_entry.get("sleepHistoryFactorFeedback")
        metrics["predisposicion_factor_feedback_estres_reciente_raw"] = readiness_entry.get("stressHistoryFactorFeedback")

    metrics["body_battery_actual"] = metrics.get("body_battery_current")
    metrics["body_battery_ultimo_timestamp_local"] = metrics.get("body_battery_last_timestamp_local")
    metrics["body_battery_texto"] = (
        f'{metrics.get("body_battery_current")} actual'
        if metrics.get("body_battery_current") is not None
        else None
    )

    metrics["puntuacion_de_sueno"] = metrics.get("sleep_score")
    metrics["duracion_de_sueno_texto"] = _format_duration_hm(metrics.get("sleep_duration_seconds"))
    metrics["sueno_texto_seguro"] = _build_sleep_safe_text(
        metrics.get("sleep_score"),
        metrics.get("duracion_de_sueno_texto"),
    )

    metrics["recuperacion_texto_seguro"] = (
        metrics.get("training_readiness_recovery_answer_for_llm")
        or metrics.get("training_readiness_recovery_safe_text")
    )

    metrics["snapshot_obtenido_local"] = _isoish_to_local(snap.get("fetched_at"))
    metrics["datos_hasta_local"] = _latest_known_data_timestamp_local(metrics)

    return snap


ES_FIELD_LABELS.update({
    "predisposicion_para_entrenar": "Predisposición para entrenar",
    "predisposicion_para_entrenar_estado": "Estado de predisposición para entrenar",
    "predisposicion_para_entrenar_texto": "Resumen de predisposición para entrenar",
    "estado_vfc": "Estado de VFC",
    "vfc_media_noche_ms": "VFC media nocturna (ms)",
    "vfc_media_7_dias_ms": "VFC media de 7 días (ms)",
    "body_battery_actual": "Body Battery actual",
    "body_battery_ultimo_timestamp_local": "Último timestamp de Body Battery",
    "body_battery_texto": "Resumen de Body Battery",
    "puntuacion_de_sueno": "Puntuación de sueño",
    "duracion_de_sueno_texto": "Duración de sueño",
    "sueno_texto_seguro": "Resumen de sueño",
    "recuperacion_texto_seguro": "Texto seguro de recuperación",
    "snapshot_obtenido_local": "Momento local de obtención del snapshot",
    "datos_hasta_local": "Datos disponibles hasta",
})
# === CANONICAL UI/SPANISH FIELDS END ===


# === HUMAN SLEEP PHASE FIELDS START ===
def _first_present_value_sleep(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def _duration_text_from_metric_keys_sleep(metrics: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    value = _first_present_value_sleep(metrics, keys)
    if value is None:
        return None
    return _format_duration_hm(value)


try:
    _collect_day_snapshot_original_human_sleep_phase_fields
except NameError:
    _collect_day_snapshot_original_human_sleep_phase_fields = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_human_sleep_phase_fields(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})

    metrics["sueno_rem_texto"] = _duration_text_from_metric_keys_sleep(metrics, (
        "sleep_rem_seconds",
        "sleep_rem_duration_seconds",
        "sleep_rem_time_seconds",
        "rem_sleep_seconds",
        "remSleepSeconds",
        "remSleepDuration",
        "rem_seconds",
    ))

    metrics["sueno_profundo_texto"] = _duration_text_from_metric_keys_sleep(metrics, (
        "sleep_deep_seconds",
        "sleep_deep_duration_seconds",
        "deep_sleep_seconds",
        "deepSleepSeconds",
        "deepSleepDuration",
        "deep_seconds",
    ))

    metrics["sueno_ligero_texto"] = _duration_text_from_metric_keys_sleep(metrics, (
        "sleep_light_seconds",
        "sleep_light_duration_seconds",
        "light_sleep_seconds",
        "lightSleepSeconds",
        "lightSleepDuration",
        "light_seconds",
    ))

    metrics["sueno_despierto_texto"] = _duration_text_from_metric_keys_sleep(metrics, (
        "sleep_awake_seconds",
        "sleep_awake_duration_seconds",
        "awake_sleep_seconds",
        "awakeSleepSeconds",
        "awakeDuration",
        "sleep_wake_seconds",
        "awake_seconds",
    ))

    sueno_inicio_raw = _first_present_value_sleep(metrics, (
        "sleep_start_local",
        "sleep_start_time_local",
        "sleep_bedtime_local",
        "sleep_start_timestamp_local",
        "sleepStartTimestampLocal",
        "sleepTimeLocal",
        "sleep_start",
    ))
    sueno_fin_raw = _first_present_value_sleep(metrics, (
        "sleep_end_local",
        "sleep_end_time_local",
        "sleep_wake_time_local",
        "wake_time_local",
        "sleep_end_timestamp_local",
        "sleepEndTimestampLocal",
        "wakeTimeLocal",
        "sleep_end",
    ))

    metrics["sueno_inicio_texto"] = _short_local_dt_text(_isoish_to_local(sueno_inicio_raw))
    metrics["sueno_fin_texto"] = _short_local_dt_text(_isoish_to_local(sueno_fin_raw))

    fases = []
    if metrics.get("sueno_rem_texto"):
        fases.append(f'REM {metrics.get("sueno_rem_texto")}')
    if metrics.get("sueno_profundo_texto"):
        fases.append(f'Profundo {metrics.get("sueno_profundo_texto")}')
    if metrics.get("sueno_ligero_texto"):
        fases.append(f'Ligero {metrics.get("sueno_ligero_texto")}')
    if metrics.get("sueno_despierto_texto"):
        fases.append(f'Despierto {metrics.get("sueno_despierto_texto")}')

    metrics["sueno_fases_resumen_humano"] = ", ".join(fases) if fases else None

    return snap


ES_FIELD_LABELS.update({
    "sueno_rem_texto": "Sueño REM",
    "sueno_profundo_texto": "Sueño profundo",
    "sueno_ligero_texto": "Sueño ligero",
    "sueno_despierto_texto": "Tiempo despierto",
    "sueno_inicio_texto": "Inicio del sueño",
    "sueno_fin_texto": "Fin del sueño",
    "sueno_fases_resumen_humano": "Resumen de fases del sueño",
})
# === HUMAN SLEEP PHASE FIELDS START ===


# === RAW SLEEP DTO CANONICALIZATION START ===
def _parse_epoch_millis_to_local_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        dt = datetime.fromtimestamp(ts, tz=APP_TIMEZONE)
        return dt.isoformat()
    except Exception:
        return None


try:
    _collect_day_snapshot_original_raw_sleep_canonicalization
except NameError:
    _collect_day_snapshot_original_raw_sleep_canonicalization = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_raw_sleep_canonicalization(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})
    raw_sources = snap.get("raw_sources") or {}

    # Completar textos humanos que estaban quedando nulos
    if metrics.get("snapshot_obtenido_texto") is None:
        metrics["snapshot_obtenido_texto"] = _short_local_dt_text(metrics.get("snapshot_obtenido_local"))
    if metrics.get("datos_hasta_texto") is None:
        metrics["datos_hasta_texto"] = _short_local_dt_text(metrics.get("datos_hasta_local"))

    if metrics.get("body_battery_resumen_humano") is None:
        bb_actual = metrics.get("body_battery_actual")
        bb_nivel = metrics.get("body_battery_nivel_es")
        if bb_actual is not None and bb_nivel:
            metrics["body_battery_resumen_humano"] = f"{bb_actual} actual, nivel {bb_nivel}"
        elif bb_actual is not None:
            metrics["body_battery_resumen_humano"] = f"{bb_actual} actual"

    if metrics.get("estado_vfc_resumen_humano") is None:
        estado = metrics.get("estado_vfc")
        noche = metrics.get("vfc_media_noche_ms")
        media7 = metrics.get("vfc_media_7_dias_ms")
        if estado and noche is not None and media7 is not None:
            metrics["estado_vfc_resumen_humano"] = f"{estado}, {noche} ms nocturnos, {media7} ms de media 7 días"
        elif estado:
            metrics["estado_vfc_resumen_humano"] = str(estado)

    if metrics.get("sueno_resumen_humano") is None:
        safe = metrics.get("sueno_texto_seguro")
        if safe:
            metrics["sueno_resumen_humano"] = safe

    sleep_raw = raw_sources.get("sleep_raw") or {}
    daily = sleep_raw.get("dailySleepDTO") if isinstance(sleep_raw, dict) else None

    if isinstance(daily, dict):
        score = None
        sleep_scores = daily.get("sleepScores")
        if isinstance(sleep_scores, dict):
            overall = sleep_scores.get("overall")
            if isinstance(overall, dict):
                score = overall.get("value")
        if score is None:
            score = metrics.get("puntuacion_de_sueno")

        duration_seconds = daily.get("sleepTimeSeconds")
        if duration_seconds is None:
            duration_seconds = metrics.get("sleep_duration_seconds")

        rem_seconds = daily.get("remSleepSeconds")
        deep_seconds = daily.get("deepSleepSeconds")
        light_seconds = daily.get("lightSleepSeconds")
        awake_seconds = daily.get("awakeSleepSeconds")

        start_local_iso = (
            _parse_epoch_millis_to_local_iso(daily.get("sleepStartTimestampLocal"))
            or _parse_epoch_millis_to_local_iso(daily.get("sleepStartTimestampGMT"))
        )
        end_local_iso = (
            _parse_epoch_millis_to_local_iso(daily.get("sleepEndTimestampLocal"))
            or _parse_epoch_millis_to_local_iso(daily.get("sleepEndTimestampGMT"))
        )

        metrics["sueno_fecha_calendario"] = daily.get("calendarDate")
        metrics["sueno_origen_canonico"] = "raw_sources.sleep_raw.dailySleepDTO"
        metrics["sleep_score"] = score
        metrics["sleep_duration_seconds"] = duration_seconds

        metrics["puntuacion_de_sueno"] = score
        metrics["duracion_de_sueno_texto"] = _format_duration_hm(duration_seconds)
        metrics["sueno_texto_seguro"] = _build_sleep_safe_text(
            metrics.get("puntuacion_de_sueno"),
            metrics.get("duracion_de_sueno_texto"),
        )
        metrics["sueno_resumen_humano"] = metrics.get("sueno_texto_seguro")

        metrics["sueno_rem_texto"] = _format_duration_hm(rem_seconds)
        metrics["sueno_profundo_texto"] = _format_duration_hm(deep_seconds)
        metrics["sueno_ligero_texto"] = _format_duration_hm(light_seconds)
        metrics["sueno_despierto_texto"] = _format_duration_hm(awake_seconds)

        metrics["sueno_inicio_local"] = start_local_iso
        metrics["sueno_fin_local"] = end_local_iso
        metrics["sueno_inicio_texto"] = _short_local_dt_text(start_local_iso)
        metrics["sueno_fin_texto"] = _short_local_dt_text(end_local_iso)

        metrics["sueno_numero_despertares"] = daily.get("awakeCount")
        metrics["sueno_feedback_raw"] = daily.get("sleepScoreFeedback")
        metrics["sueno_insight_raw"] = daily.get("sleepScoreInsight")
        metrics["sueno_personalized_insight_raw"] = daily.get("sleepScorePersonalizedInsight")

        fases = []
        if metrics.get("sueno_rem_texto"):
            fases.append(f'REM {metrics.get("sueno_rem_texto")}')
        if metrics.get("sueno_profundo_texto"):
            fases.append(f'Profundo {metrics.get("sueno_profundo_texto")}')
        if metrics.get("sueno_ligero_texto"):
            fases.append(f'Ligero {metrics.get("sueno_ligero_texto")}')
        if metrics.get("sueno_despierto_texto"):
            fases.append(f'Despierto {metrics.get("sueno_despierto_texto")}')
        metrics["sueno_fases_resumen_humano"] = ", ".join(fases) if fases else None

        # Si el fin del sueño es más reciente que el "datos_hasta_local" previo, lo actualizamos
        current_datos_hasta = _parse_garmin_datetime(metrics.get("datos_hasta_local")) if metrics.get("datos_hasta_local") else None
        sleep_end_dt = _parse_garmin_datetime(end_local_iso) if end_local_iso else None
        if sleep_end_dt is not None and (current_datos_hasta is None or sleep_end_dt > current_datos_hasta):
            metrics["datos_hasta_local"] = sleep_end_dt.isoformat()
            metrics["datos_hasta_texto"] = _short_local_dt_text(metrics.get("datos_hasta_local"))

    return snap


ES_FIELD_LABELS.update({
    "sueno_fecha_calendario": "Fecha del sueño",
    "sueno_origen_canonico": "Origen canónico del sueño",
    "sueno_inicio_local": "Inicio local del sueño",
    "sueno_fin_local": "Fin local del sueño",
    "sueno_numero_despertares": "Número de despertares",
    "sueno_feedback_raw": "Feedback raw de sueño",
    "sueno_insight_raw": "Insight raw de sueño",
    "sueno_personalized_insight_raw": "Insight personalizado raw de sueño",
})
# === RAW SLEEP DTO CANONICALIZATION END ===


# === SLEEP GMT TIMESTAMP FIX START ===
def _epoch_millis_gmt_to_local_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        return datetime.fromtimestamp(ts, tz=APP_TIMEZONE).isoformat()
    except Exception:
        return None


try:
    _collect_day_snapshot_original_sleep_gmt_timestamp_fix
except NameError:
    _collect_day_snapshot_original_sleep_gmt_timestamp_fix = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_sleep_gmt_timestamp_fix(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})
    raw_sources = snap.get("raw_sources") or {}

    sleep_raw = raw_sources.get("sleep_raw") or {}
    daily = sleep_raw.get("dailySleepDTO") if isinstance(sleep_raw, dict) else None

    if isinstance(daily, dict):
        start_from_gmt = _epoch_millis_gmt_to_local_iso(daily.get("sleepStartTimestampGMT"))
        end_from_gmt = _epoch_millis_gmt_to_local_iso(daily.get("sleepEndTimestampGMT"))

        if start_from_gmt:
            metrics["sueno_inicio_local"] = start_from_gmt
            metrics["sueno_inicio_texto"] = _short_local_dt_text(start_from_gmt)

        if end_from_gmt:
            metrics["sueno_fin_local"] = end_from_gmt
            metrics["sueno_fin_texto"] = _short_local_dt_text(end_from_gmt)

    return snap
# === SLEEP GMT TIMESTAMP FIX END ===


# === SLEEP FRESHNESS GUARDRAILS START ===
def _hours_between_local_datetimes(newer: Any, older: Any) -> float | None:
    newer_dt = _parse_garmin_datetime(newer) if newer is not None else None
    older_dt = _parse_garmin_datetime(older) if older is not None else None
    if newer_dt is None or older_dt is None:
        return None
    try:
        return round((newer_dt - older_dt).total_seconds() / 3600.0, 1)
    except Exception:
        return None


try:
    _collect_day_snapshot_original_sleep_freshness_guardrails
except NameError:
    _collect_day_snapshot_original_sleep_freshness_guardrails = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_sleep_freshness_guardrails(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})

    snapshot_local = metrics.get("snapshot_obtenido_local") or _now_local().isoformat()
    sleep_ref_local = metrics.get("sueno_fin_local") or metrics.get("sueno_referencia_local")
    sleep_ref_dt = _parse_garmin_datetime(sleep_ref_local) if sleep_ref_local is not None else None
    snapshot_dt = _parse_garmin_datetime(snapshot_local) if snapshot_local is not None else None

    state = "missing"
    if sleep_ref_dt is not None and snapshot_dt is not None:
        state = "fresh" if sleep_ref_dt.date() == snapshot_dt.date() else "stale"
    elif sleep_ref_dt is not None:
        state = "unknown"

    age_hours = _hours_between_local_datetimes(snapshot_local, sleep_ref_local)

    metrics["sueno_referencia_local"] = sleep_ref_dt.isoformat() if sleep_ref_dt is not None else None
    metrics["sueno_antiguedad_horas"] = age_hours
    metrics["sueno_estado_frescura"] = state
    metrics["sueno_es_actual"] = state == "fresh"

    summary = metrics.get("sueno_resumen_humano") or metrics.get("sueno_texto_seguro")
    phases = metrics.get("sueno_fases_resumen_humano")

    if state == "fresh":
        metrics["sueno_resumen_para_llm"] = summary
        metrics["sueno_fases_para_llm"] = phases
    elif state == "stale":
        ref_text = _short_local_dt_text(metrics.get("sueno_referencia_local")) or metrics.get("sueno_fecha_calendario")
        metrics["sueno_resumen_para_llm"] = f"Último sueño disponible del conector: {ref_text}; no asumir que corresponde a anoche"
        metrics["sueno_fases_para_llm"] = None
    elif state == "unknown":
        ref_text = _short_local_dt_text(metrics.get("sueno_referencia_local")) or "sin fecha clara"
        metrics["sueno_resumen_para_llm"] = f"Hay un sueño disponible ({ref_text}), pero no se pudo validar si corresponde a hoy"
        metrics["sueno_fases_para_llm"] = None
    else:
        metrics["sueno_resumen_para_llm"] = "No hay sueño usable en el snapshot actual"
        metrics["sueno_fases_para_llm"] = None

    return snap


@mcp.custom_route("/debug/sleep-freshness", methods=["GET"])
async def debug_sleep_freshness(_: Request) -> JSONResponse:
    with CACHE_LOCK:
        snapshot = deepcopy(CACHE.get("snapshot"))
        status = CACHE.get("status")
        last_refresh = CACHE.get("last_refresh")
        last_error = CACHE.get("last_error")

    metrics = {}
    if isinstance(snapshot, dict):
        metrics = snapshot.get("metrics") or {}

    keys = [
        "snapshot_obtenido_local",
        "snapshot_obtenido_texto",
        "sueno_fecha_calendario",
        "sueno_inicio_local",
        "sueno_fin_local",
        "sueno_inicio_texto",
        "sueno_fin_texto",
        "sueno_referencia_local",
        "sueno_antiguedad_horas",
        "sueno_estado_frescura",
        "sueno_es_actual",
        "puntuacion_de_sueno",
        "duracion_de_sueno_texto",
        "sueno_resumen_humano",
        "sueno_resumen_para_llm",
        "sueno_fases_resumen_humano",
        "sueno_fases_para_llm",
    ]

    payload = {
        "status": status,
        "last_refresh": last_refresh,
        "last_refresh_local": _isoish_to_local(last_refresh),
        "last_error": last_error,
        "snapshot_exists": isinstance(snapshot, dict),
        "metrics": {k: metrics.get(k) for k in keys},
    }
    return JSONResponse(payload)


ES_FIELD_LABELS.update({
    "sueno_referencia_local": "Referencia temporal del sueño",
    "sueno_antiguedad_horas": "Antigüedad del sueño (h)",
    "sueno_estado_frescura": "Estado de frescura del sueño",
    "sueno_es_actual": "Sueño actual",
    "sueno_resumen_para_llm": "Resumen seguro de sueño para LLM",
    "sueno_fases_para_llm": "Fases de sueño seguras para LLM",
})
# === SLEEP FRESHNESS GUARDRAILS END ===


# === MULTI_DAY_SLEEP_SELECTION START ===
def _find_sleep_client_in_args(*args, **kwargs):
    candidates = list(args) + list(kwargs.values())
    for obj in candidates:
        if hasattr(obj, "get_sleep_data") and callable(getattr(obj, "get_sleep_data")):
            return obj
    return None


def _sleep_candidate_from_raw(sleep_raw: Any) -> dict[str, Any] | None:
    if not isinstance(sleep_raw, dict):
        return None
    daily = sleep_raw.get("dailySleepDTO")
    if not isinstance(daily, dict):
        return None

    sleep_seconds = daily.get("sleepTimeSeconds")
    if sleep_seconds in (None, 0):
        return None

    end_local = (
        _epoch_millis_gmt_to_local_iso(daily.get("sleepEndTimestampGMT"))
        or _parse_epoch_millis_to_local_iso(daily.get("sleepEndTimestampLocal"))
    )
    start_local = (
        _epoch_millis_gmt_to_local_iso(daily.get("sleepStartTimestampGMT"))
        or _parse_epoch_millis_to_local_iso(daily.get("sleepStartTimestampLocal"))
    )

    end_dt = _parse_garmin_datetime(end_local) if end_local else None
    start_dt = _parse_garmin_datetime(start_local) if start_local else None

    if end_dt is None:
        return None

    return {
        "raw": sleep_raw,
        "daily": daily,
        "calendar_date": daily.get("calendarDate"),
        "sleep_seconds": sleep_seconds,
        "start_local": start_local,
        "end_local": end_local,
        "start_dt": start_dt,
        "end_dt": end_dt,
    }


def _pick_latest_sleep_from_client(client: Any, snapshot_local_iso: str | None) -> dict[str, Any] | None:
    snapshot_dt = _parse_garmin_datetime(snapshot_local_iso) if snapshot_local_iso else _now_local()
    if snapshot_dt is None:
        snapshot_dt = _now_local()

    checked = []
    candidates = []

    for delta_days in (0, 1, 2):
        day = (snapshot_dt.date() - timedelta(days=delta_days)).isoformat()
        try:
            raw = client.get_sleep_data(day)
        except Exception as exc:
            checked.append({
                "requested_date": day,
                "ok": False,
                "error": str(exc),
            })
            continue

        candidate = _sleep_candidate_from_raw(raw)
        checked.append({
            "requested_date": day,
            "ok": candidate is not None,
            "calendar_date": candidate.get("calendar_date") if candidate else None,
            "end_local": candidate.get("end_local") if candidate else None,
            "sleep_seconds": candidate.get("sleep_seconds") if candidate else None,
        })

        if candidate is None:
            continue

        if candidate["end_dt"] <= snapshot_dt:
            candidates.append(candidate)

    if not candidates:
        return {
            "selected": None,
            "checked": checked,
        }

    selected = max(candidates, key=lambda c: c["end_dt"])
    return {
        "selected": selected,
        "checked": checked,
    }


def _apply_sleep_candidate_to_metrics(metrics: dict[str, Any], candidate: dict[str, Any], source_label: str) -> None:
    daily = candidate["daily"]

    score = None
    sleep_scores = daily.get("sleepScores")
    if isinstance(sleep_scores, dict):
        overall = sleep_scores.get("overall")
        if isinstance(overall, dict):
            score = overall.get("value")

    duration_seconds = daily.get("sleepTimeSeconds")
    rem_seconds = daily.get("remSleepSeconds")
    deep_seconds = daily.get("deepSleepSeconds")
    light_seconds = daily.get("lightSleepSeconds")
    awake_seconds = daily.get("awakeSleepSeconds")

    start_local_iso = candidate.get("start_local")
    end_local_iso = candidate.get("end_local")

    metrics["sueno_fecha_calendario"] = daily.get("calendarDate")
    metrics["sueno_origen_canonico"] = source_label
    metrics["sleep_score"] = score
    metrics["sleep_duration_seconds"] = duration_seconds

    metrics["puntuacion_de_sueno"] = score
    metrics["duracion_de_sueno_texto"] = _format_duration_hm(duration_seconds)
    metrics["sueno_texto_seguro"] = _build_sleep_safe_text(
        metrics.get("puntuacion_de_sueno"),
        metrics.get("duracion_de_sueno_texto"),
    )
    metrics["sueno_resumen_humano"] = metrics.get("sueno_texto_seguro")

    metrics["sueno_rem_texto"] = _format_duration_hm(rem_seconds)
    metrics["sueno_profundo_texto"] = _format_duration_hm(deep_seconds)
    metrics["sueno_ligero_texto"] = _format_duration_hm(light_seconds)
    metrics["sueno_despierto_texto"] = _format_duration_hm(awake_seconds)

    metrics["sueno_inicio_local"] = start_local_iso
    metrics["sueno_fin_local"] = end_local_iso
    metrics["sueno_inicio_texto"] = _short_local_dt_text(start_local_iso)
    metrics["sueno_fin_texto"] = _short_local_dt_text(end_local_iso)

    metrics["sueno_numero_despertares"] = daily.get("awakeCount")
    metrics["sueno_feedback_raw"] = daily.get("sleepScoreFeedback")
    metrics["sueno_insight_raw"] = daily.get("sleepScoreInsight")
    metrics["sueno_personalized_insight_raw"] = daily.get("sleepScorePersonalizedInsight")

    fases = []
    if metrics.get("sueno_rem_texto"):
        fases.append(f'REM {metrics.get("sueno_rem_texto")}')
    if metrics.get("sueno_profundo_texto"):
        fases.append(f'Profundo {metrics.get("sueno_profundo_texto")}')
    if metrics.get("sueno_ligero_texto"):
        fases.append(f'Ligero {metrics.get("sueno_ligero_texto")}')
    if metrics.get("sueno_despierto_texto"):
        fases.append(f'Despierto {metrics.get("sueno_despierto_texto")}')
    metrics["sueno_fases_resumen_humano"] = ", ".join(fases) if fases else None

    current_datos_hasta = _parse_garmin_datetime(metrics.get("datos_hasta_local")) if metrics.get("datos_hasta_local") else None
    sleep_end_dt = _parse_garmin_datetime(end_local_iso) if end_local_iso else None
    if sleep_end_dt is not None and (current_datos_hasta is None or sleep_end_dt > current_datos_hasta):
        metrics["datos_hasta_local"] = sleep_end_dt.isoformat()
        metrics["datos_hasta_texto"] = _short_local_dt_text(metrics.get("datos_hasta_local"))


def _recompute_sleep_freshness_fields(metrics: dict[str, Any]) -> None:
    snapshot_local = metrics.get("snapshot_obtenido_local") or _now_local().isoformat()
    sleep_ref_local = metrics.get("sueno_fin_local") or metrics.get("sueno_referencia_local")
    sleep_ref_dt = _parse_garmin_datetime(sleep_ref_local) if sleep_ref_local is not None else None
    snapshot_dt = _parse_garmin_datetime(snapshot_local) if snapshot_local is not None else None

    state = "missing"
    if sleep_ref_dt is not None and snapshot_dt is not None:
        state = "fresh" if sleep_ref_dt.date() == snapshot_dt.date() else "stale"
    elif sleep_ref_dt is not None:
        state = "unknown"

    age_hours = _hours_between_local_datetimes(snapshot_local, sleep_ref_local)

    metrics["sueno_referencia_local"] = sleep_ref_dt.isoformat() if sleep_ref_dt is not None else None
    metrics["sueno_antiguedad_horas"] = age_hours
    metrics["sueno_estado_frescura"] = state
    metrics["sueno_es_actual"] = state == "fresh"

    summary = metrics.get("sueno_resumen_humano") or metrics.get("sueno_texto_seguro")
    phases = metrics.get("sueno_fases_resumen_humano")

    if state == "fresh":
        metrics["sueno_resumen_para_llm"] = summary
        metrics["sueno_fases_para_llm"] = phases
    elif state == "stale":
        ref_text = _short_local_dt_text(metrics.get("sueno_referencia_local")) or metrics.get("sueno_fecha_calendario")
        metrics["sueno_resumen_para_llm"] = f"Último sueño disponible del conector: {ref_text}; no asumir que corresponde a anoche"
        metrics["sueno_fases_para_llm"] = None
    elif state == "unknown":
        ref_text = _short_local_dt_text(metrics.get("sueno_referencia_local")) or "sin fecha clara"
        metrics["sueno_resumen_para_llm"] = f"Hay un sueño disponible ({ref_text}), pero no se pudo validar si corresponde a hoy"
        metrics["sueno_fases_para_llm"] = None
    else:
        metrics["sueno_resumen_para_llm"] = "No hay sueño usable en el snapshot actual"
        metrics["sueno_fases_para_llm"] = None


try:
    _collect_day_snapshot_original_multi_day_sleep_selection
except NameError:
    _collect_day_snapshot_original_multi_day_sleep_selection = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_multi_day_sleep_selection(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})
    raw_sources = snap.setdefault("raw_sources", {})

    client = _find_sleep_client_in_args(*args, **kwargs)
    snapshot_local_iso = metrics.get("snapshot_obtenido_local") or _isoish_to_local(snap.get("fetched_at")) or _now_local().isoformat()

    selection = None
    if client is not None:
        selection = _pick_latest_sleep_from_client(client, snapshot_local_iso)

    if isinstance(selection, dict):
        raw_sources["sleep_selection_debug"] = selection.get("checked")

    selected = selection.get("selected") if isinstance(selection, dict) else None
    if selected is not None:
        raw_sources["sleep_raw"] = selected["raw"]
        source_label = f'garmin.get_sleep_data({selected["calendar_date"]})'
        _apply_sleep_candidate_to_metrics(metrics, selected, source_label)
        _recompute_sleep_freshness_fields(metrics)

    return snap


@mcp.custom_route("/debug/sleep-selection", methods=["GET"])
async def debug_sleep_selection(_: Request) -> JSONResponse:
    with CACHE_LOCK:
        snapshot = deepcopy(CACHE.get("snapshot"))
        status = CACHE.get("status")
        last_refresh = CACHE.get("last_refresh")
        last_error = CACHE.get("last_error")

    metrics = {}
    raw_sources = {}
    if isinstance(snapshot, dict):
        metrics = snapshot.get("metrics") or {}
        raw_sources = snapshot.get("raw_sources") or {}

    payload = {
        "status": status,
        "last_refresh": last_refresh,
        "last_refresh_local": _isoish_to_local(last_refresh),
        "last_error": last_error,
        "snapshot_exists": isinstance(snapshot, dict),
        "selected_sleep": {
            "sueno_fecha_calendario": metrics.get("sueno_fecha_calendario"),
            "sueno_origen_canonico": metrics.get("sueno_origen_canonico"),
            "sueno_inicio_texto": metrics.get("sueno_inicio_texto"),
            "sueno_fin_texto": metrics.get("sueno_fin_texto"),
            "sueno_estado_frescura": metrics.get("sueno_estado_frescura"),
            "sueno_es_actual": metrics.get("sueno_es_actual"),
            "sueno_antiguedad_horas": metrics.get("sueno_antiguedad_horas"),
            "sueno_resumen_para_llm": metrics.get("sueno_resumen_para_llm"),
            "sueno_fases_para_llm": metrics.get("sueno_fases_para_llm"),
        },
        "selection_debug": raw_sources.get("sleep_selection_debug"),
    }
    return JSONResponse(payload)
# === MULTI_DAY_SLEEP_SELECTION END ===


# === GARMIN GET_SLEEP_DATA MULTI-DAY WRAPPER START ===
_SLEEP_SELECTION_DEBUG_LAST = None


def _parse_iso_date_or_today(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if value is None:
        return _today_local()
    raw = str(value).strip()
    if not raw:
        return _today_local()
    try:
        return date.fromisoformat(raw[:10])
    except Exception:
        return _today_local()


def _sleep_candidate_from_raw_for_wrapper(requested_date_iso: str, sleep_raw: Any) -> dict[str, Any] | None:
    if not isinstance(sleep_raw, dict):
        return None
    daily = sleep_raw.get("dailySleepDTO")
    if not isinstance(daily, dict):
        return None

    sleep_seconds = daily.get("sleepTimeSeconds")
    if sleep_seconds in (None, 0):
        return None

    end_local = (
        _epoch_millis_gmt_to_local_iso(daily.get("sleepEndTimestampGMT"))
        or _parse_epoch_millis_to_local_iso(daily.get("sleepEndTimestampLocal"))
    )
    start_local = (
        _epoch_millis_gmt_to_local_iso(daily.get("sleepStartTimestampGMT"))
        or _parse_epoch_millis_to_local_iso(daily.get("sleepStartTimestampLocal"))
    )

    end_dt = _parse_garmin_datetime(end_local) if end_local else None
    start_dt = _parse_garmin_datetime(start_local) if start_local else None
    if end_dt is None:
        return None

    return {
        "requested_date": requested_date_iso,
        "calendar_date": daily.get("calendarDate"),
        "sleep_seconds": sleep_seconds,
        "start_local": start_local,
        "end_local": end_local,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "raw": sleep_raw,
    }


try:
    _Garmin_get_sleep_data_original_multi_day
except NameError:
    try:
        _Garmin_get_sleep_data_original_multi_day = Garmin.get_sleep_data
    except Exception:
        _Garmin_get_sleep_data_original_multi_day = None


def _Garmin_get_sleep_data_multi_day(self, cdate):
    global _SLEEP_SELECTION_DEBUG_LAST

    if _Garmin_get_sleep_data_original_multi_day is None:
        raise RuntimeError("No se pudo capturar Garmin.get_sleep_data original")

    requested_date = _parse_iso_date_or_today(cdate)
    now_local = _now_local()

    checked = []
    candidates = []

    # Probamos el día pedido, ayer y anteayer
    offsets = (-1, 0, -2) if requested_date == _today_local() else (0, -1, -2)
    for offset in offsets:
        day = (requested_date + timedelta(days=offset)).isoformat()
        try:
            raw = _Garmin_get_sleep_data_original_multi_day(self, day)
        except Exception as exc:
            checked.append({
                "requested_date": day,
                "ok": False,
                "error": str(exc),
            })
            continue

        candidate = _sleep_candidate_from_raw_for_wrapper(day, raw)
        checked.append({
            "requested_date": day,
            "ok": candidate is not None,
            "calendar_date": candidate.get("calendar_date") if candidate else None,
            "end_local": candidate.get("end_local") if candidate else None,
            "sleep_seconds": candidate.get("sleep_seconds") if candidate else None,
        })

        if candidate is None:
            continue

        if candidate["end_dt"] <= now_local:
            candidates.append(candidate)

    selected = None
    if candidates:
        selected = max(candidates, key=lambda c: c["end_dt"])

    _SLEEP_SELECTION_DEBUG_LAST = {
        "requested_input": str(cdate),
        "requested_date_base": requested_date.isoformat(),
        "checked": checked,
        "selected": {
            "requested_date": selected.get("requested_date"),
            "calendar_date": selected.get("calendar_date"),
            "start_local": selected.get("start_local"),
            "end_local": selected.get("end_local"),
            "sleep_seconds": selected.get("sleep_seconds"),
        } if selected else None,
    }

    if selected is not None:
        return selected["raw"]

    return _Garmin_get_sleep_data_original_multi_day(self, requested_date.isoformat())


if _Garmin_get_sleep_data_original_multi_day is not None:
    try:
        Garmin.get_sleep_data = _Garmin_get_sleep_data_multi_day
    except Exception:
        pass


try:
    _collect_day_snapshot_original_sleep_selection_debug_bridge
except NameError:
    _collect_day_snapshot_original_sleep_selection_debug_bridge = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_sleep_selection_debug_bridge(*args, **kwargs)
    raw_sources = snap.setdefault("raw_sources", {})
    metrics = snap.setdefault("metrics", {})

    if _SLEEP_SELECTION_DEBUG_LAST is not None:
        raw_sources["sleep_selection_debug"] = deepcopy(_SLEEP_SELECTION_DEBUG_LAST)
        selected = _SLEEP_SELECTION_DEBUG_LAST.get("selected") or {}
        if selected:
            requested_date = selected.get("requested_date")
            calendar_date = selected.get("calendar_date")
            metrics["sueno_origen_canonico"] = f"garmin.get_sleep_data multi-day ({requested_date} -> {calendar_date})"

    return snap
# === GARMIN GET_SLEEP_DATA MULTI-DAY WRAPPER END ===



# === GARMIN GET_HRV_DATA MULTI-DAY WRAPPER START ===
_HRV_SELECTION_DEBUG_LAST = None


def _hrv_candidate_from_raw_for_wrapper(requested_date_iso: str, hrv_raw: Any) -> dict[str, Any] | None:
    if not isinstance(hrv_raw, dict):
        return None

    summary = hrv_raw.get("hrvSummary")
    if not isinstance(summary, dict):
        return None

    last_night = _pick_first_present(summary, ("lastNight", "lastNightAvg", "lastNightAverage"))
    weekly_avg = _pick_first_present(summary, ("weeklyAvg", "sevenDayAvg", "baselineAvg"))
    status = _pick_first_present(summary, ("hrvStatus", "status"))

    if last_night is None and weekly_avg is None and status is None:
        return None

    return {
        "requested_date": requested_date_iso,
        "last_night": last_night,
        "weekly_avg": weekly_avg,
        "status": status,
        "raw": hrv_raw,
    }


try:
    _Garmin_get_hrv_data_original_multi_day
except NameError:
    try:
        _Garmin_get_hrv_data_original_multi_day = Garmin.get_hrv_data
    except Exception:
        _Garmin_get_hrv_data_original_multi_day = None


def _Garmin_get_hrv_data_multi_day(self, cdate):
    global _HRV_SELECTION_DEBUG_LAST

    if _Garmin_get_hrv_data_original_multi_day is None:
        raise RuntimeError("No se pudo capturar Garmin.get_hrv_data original")

    requested_date = _parse_iso_date_or_today(cdate)
    checked = []
    selected = None

    for offset in (-1, 0, -2):
        day = (requested_date + timedelta(days=offset)).isoformat()
        try:
            raw = _Garmin_get_hrv_data_original_multi_day(self, day)
        except Exception as exc:
            checked.append({
                "requested_date": day,
                "ok": False,
                "error": str(exc),
            })
            continue

        candidate = _hrv_candidate_from_raw_for_wrapper(day, raw)
        checked.append({
            "requested_date": day,
            "ok": candidate is not None,
            "last_night": candidate.get("last_night") if candidate else None,
            "weekly_avg": candidate.get("weekly_avg") if candidate else None,
            "status": candidate.get("status") if candidate else None,
        })

        if candidate is not None:
            selected = candidate
            break

    _HRV_SELECTION_DEBUG_LAST = {
        "requested_input": str(cdate),
        "requested_date_base": requested_date.isoformat(),
        "checked": checked,
        "selected": {
            "requested_date": selected.get("requested_date"),
            "last_night": selected.get("last_night"),
            "weekly_avg": selected.get("weekly_avg"),
            "status": selected.get("status"),
        } if selected else None,
    }

    if selected is not None:
        return selected["raw"]

    return _Garmin_get_hrv_data_original_multi_day(self, requested_date.isoformat())


if _Garmin_get_hrv_data_original_multi_day is not None:
    try:
        Garmin.get_hrv_data = _Garmin_get_hrv_data_multi_day
    except Exception:
        pass


try:
    _collect_day_snapshot_original_hrv_selection_debug_bridge
except NameError:
    _collect_day_snapshot_original_hrv_selection_debug_bridge = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _collect_day_snapshot_original_hrv_selection_debug_bridge(*args, **kwargs)
    raw_sources = snap.setdefault("raw_sources", {})
    metrics = snap.setdefault("metrics", {})

    if _HRV_SELECTION_DEBUG_LAST is not None:
        raw_sources["hrv_selection_debug"] = deepcopy(_HRV_SELECTION_DEBUG_LAST)
        selected = _HRV_SELECTION_DEBUG_LAST.get("selected") or {}
        if selected:
            requested_date_base = _HRV_SELECTION_DEBUG_LAST.get("requested_date_base")
            source_date = selected.get("requested_date")
            metrics["vfc_fecha_api_garmin"] = source_date
            metrics["vfc_origen_canonico"] = f"garmin.get_hrv_data multi-day ({requested_date_base} -> {source_date})"
            try:
                intuitive_date = (date.fromisoformat(source_date) + timedelta(days=1)).isoformat()
            except Exception:
                intuitive_date = None
            metrics["vfc_noche_termina_en_fecha"] = intuitive_date

    if metrics.get("vfc_referencia_texto") is None:
        ref = metrics.get("vfc_noche_termina_en_fecha")
        if ref:
            try:
                ref_text = date.fromisoformat(ref).strftime("%d/%m/%Y")
            except Exception:
                ref_text = str(ref)
            fecha_api = metrics.get("vfc_fecha_api_garmin")
            if fecha_api and fecha_api != ref:
                metrics["vfc_referencia_texto"] = f"VFC nocturna de la noche que termina el {ref_text} (fecha API Garmin: {fecha_api})"
            else:
                metrics["vfc_referencia_texto"] = f"VFC nocturna de la noche que termina el {ref_text}"

    return snap


ES_FIELD_LABELS.update({
    "vfc_fecha_api_garmin": "Fecha API Garmin de VFC",
    "vfc_noche_termina_en_fecha": "Noche de VFC que termina en fecha",
    "vfc_origen_canonico": "Origen canónico de VFC",
    "vfc_referencia_texto": "Referencia humana de VFC",
})
# === GARMIN GET_HRV_DATA MULTI-DAY WRAPPER END ===


# === GARMIN PRESENTATION CLEANUP PATCH START ===
def _presentation_join(parts):
    return " · ".join([str(p) for p in parts if p not in (None, "", [], {})])


try:
    _GARMIN_PRESENTATION_CLEANUP_ORIGINAL_COLLECT_DAY_SNAPSHOT
except NameError:
    _GARMIN_PRESENTATION_CLEANUP_ORIGINAL_COLLECT_DAY_SNAPSHOT = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _GARMIN_PRESENTATION_CLEANUP_ORIGINAL_COLLECT_DAY_SNAPSHOT(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})
    raw = snap.setdefault("raw_sources", {})

    # Body Battery: texto humano más útil
    bb_actual = metrics.get("body_battery_actual")
    bb_max = metrics.get("body_battery_max")
    bb_min = metrics.get("body_battery_min")
    bb_charged = metrics.get("body_battery_charged")
    bb_drained = metrics.get("body_battery_drained")

    bb_parts = []
    if bb_actual is not None:
        bb_parts.append(f"Body Battery {bb_actual}")
    if bb_max is not None:
        bb_parts.append(f"máx {bb_max}")
    if bb_min is not None:
        bb_parts.append(f"mín {bb_min}")
    if bb_charged is not None:
        bb_parts.append(f"carga {bb_charged}")
    if bb_drained is not None:
        bb_parts.append(f"descarga {bb_drained}")

    bb_text = _presentation_join(bb_parts)
    if bb_text:
        metrics["body_battery_texto"] = bb_text
        metrics["body_battery_resumen_humano"] = bb_text

    # Predisposición: resumen humano de factores
    pred_parts = []
    pred_score = metrics.get("predisposicion_para_entrenar")
    pred_estado = metrics.get("predisposicion_para_entrenar_estado")
    pred_sueno = metrics.get("predisposicion_factor_sueno_score")
    pred_rec = metrics.get("predisposicion_factor_recuperacion_raw")
    pred_vfc = metrics.get("predisposicion_factor_vfc_ms")
    pred_carga = metrics.get("predisposicion_factor_carga_aguda")

    if pred_score is not None or pred_estado:
        head = _presentation_join([pred_score, pred_estado]).replace(" · ", " — ")
        if head:
            pred_parts.append(head)
    if pred_sueno is not None:
        pred_parts.append(f"sueño {pred_sueno}")
    if pred_rec is not None:
        pred_parts.append(f"recuperación raw {pred_rec}")
    if pred_vfc is not None:
        pred_parts.append(f"VFC factor {pred_vfc}")
    if pred_carga is not None:
        pred_parts.append(f"carga aguda {pred_carga}")

    pred_text = _presentation_join(pred_parts)
    if pred_text:
        metrics["predisposicion_factores_resumen_humano"] = pred_text

    # Peso: indicar fuente real
    body = raw.get("body_composition_raw") or {}
    user = ((raw.get("user_profile_raw") or {}).get("userData")) or {}
    total_average = body.get("totalAverage") or {}

    daily_weight = total_average.get("weight")
    profile_weight = user.get("weight")

    if daily_weight is not None:
        metrics["peso_referencia_texto"] = "Peso de composición corporal del día"
    elif profile_weight is not None:
        metrics["peso_referencia_texto"] = "Peso tomado del perfil de Garmin (sin medición corporal del día)"

    # Edad física: aclarar procedencia
    fitness_age_raw = raw.get("fitness_age_raw") or {}
    bmi_component = (fitness_age_raw.get("components") or {}).get("bmi") or {}
    bmi_last_measurement = bmi_component.get("lastMeasurementDate")

    if metrics.get("fitness_age") is not None:
        txt = "Edad física calculada por Garmin"
        if bmi_last_measurement:
            txt += f" · IMC con última medición {bmi_last_measurement}"
        metrics["fitness_age_referencia_texto"] = txt

    return snap


if "ES_FIELD_LABELS" in globals():
    ES_FIELD_LABELS.update({
        "predisposicion_factores_resumen_humano": "Resumen humano de factores de Predisposición",
        "peso_referencia_texto": "Referencia del peso",
        "fitness_age_referencia_texto": "Referencia de edad física",
    })
# === GARMIN PRESENTATION CLEANUP PATCH END ===


# === GARMIN ACCLIMATACION SPO2 PATCH START ===
def _first_non_none_local(*values):
    for v in values:
        if v is not None:
            return v
    return None


try:
    _GARMIN_ACCLIMATACION_SPO2_ORIGINAL_COLLECT_DAY_SNAPSHOT
except NameError:
    _GARMIN_ACCLIMATACION_SPO2_ORIGINAL_COLLECT_DAY_SNAPSHOT = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _GARMIN_ACCLIMATACION_SPO2_ORIGINAL_COLLECT_DAY_SNAPSHOT(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})
    raw = snap.setdefault("raw_sources", {})

    sleep_raw = raw.get("sleep_raw") or {}
    daily_sleep = sleep_raw.get("dailySleepDTO") or {}
    sleep_spo2_summary = sleep_raw.get("wellnessSpO2SleepSummaryDTO") or {}
    spo2_raw = raw.get("spo2_raw") or {}
    summary_raw = raw.get("summary_raw") or {}

    promedio_spo2 = _first_non_none_local(
        sleep_spo2_summary.get("averageSPO2"),
        daily_sleep.get("averageSpO2Value"),
        spo2_raw.get("avgSleepSpO2"),
    )
    spo2_minima = _first_non_none_local(
        sleep_spo2_summary.get("lowestSPO2"),
        daily_sleep.get("lowestSpO2Value"),
        spo2_raw.get("lowestSpO2"),
    )
    spo2_ultima = _first_non_none_local(
        spo2_raw.get("latestSpO2"),
        summary_raw.get("latestSpo2"),
    )
    spo2_media_general = _first_non_none_local(
        spo2_raw.get("averageSpO2"),
        summary_raw.get("averageSpo2"),
    )
    altitud_media = summary_raw.get("averageMonitoringEnvironmentAltitude")

    metrics["aclimatacion_spo2_promedio"] = promedio_spo2
    metrics["aclimatacion_spo2_minima"] = spo2_minima
    metrics["aclimatacion_spo2_ultima"] = spo2_ultima
    metrics["aclimatacion_spo2_media_general"] = spo2_media_general
    metrics["aclimatacion_altitud_media_entorno"] = altitud_media
    metrics["aclimatacion_spo2_hora_ultima_local"] = spo2_raw.get("latestSpO2TimestampLocal")
    metrics["aclimatacion_spo2_sueno_inicio_local"] = _first_non_none_local(
        spo2_raw.get("sleepStartTimestampLocal"),
        sleep_spo2_summary.get("sleepMeasurementStartGMT"),
    )
    metrics["aclimatacion_spo2_sueno_fin_local"] = _first_non_none_local(
        spo2_raw.get("sleepEndTimestampLocal"),
        sleep_spo2_summary.get("sleepMeasurementEndGMT"),
    )

    parts = []
    if promedio_spo2 is not None:
        parts.append(f"Promedio de SpO₂ {int(round(promedio_spo2))}%")
    if spo2_minima is not None:
        parts.append(f"mínimo {int(round(spo2_minima))}%")
    if spo2_ultima is not None:
        parts.append(f"última {int(round(spo2_ultima))}%")
    if altitud_media is not None:
        parts.append(f"altitud media {int(round(altitud_media))} m")

    resumen = " · ".join(parts)
    if resumen:
        metrics["aclimatacion_spo2_resumen_humano"] = resumen

    return snap


if "ES_FIELD_LABELS" in globals():
    ES_FIELD_LABELS.update({
        "aclimatacion_spo2_promedio": "Promedio de SpO₂ de aclimatación",
        "aclimatacion_spo2_minima": "SpO₂ mínima de aclimatación",
        "aclimatacion_spo2_ultima": "Última SpO₂ de aclimatación",
        "aclimatacion_spo2_media_general": "SpO₂ media general",
        "aclimatacion_altitud_media_entorno": "Altitud media del entorno",
        "aclimatacion_spo2_hora_ultima_local": "Hora local de la última SpO₂",
        "aclimatacion_spo2_sueno_inicio_local": "Inicio local de sueño para SpO₂",
        "aclimatacion_spo2_sueno_fin_local": "Fin local de sueño para SpO₂",
        "aclimatacion_spo2_resumen_humano": "Resumen humano de aclimatación por pulsioximetría",
    })
# === GARMIN ACCLIMATACION SPO2 PATCH END ===


# === GARMIN LACTATO PARCIAL PATCH START ===
try:
    _GARMIN_LACTATO_PARCIAL_ORIGINAL_COLLECT_DAY_SNAPSHOT
except NameError:
    _GARMIN_LACTATO_PARCIAL_ORIGINAL_COLLECT_DAY_SNAPSHOT = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _GARMIN_LACTATO_PARCIAL_ORIGINAL_COLLECT_DAY_SNAPSHOT(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})
    raw = snap.setdefault("raw_sources", {})

    user = ((raw.get("user_profile_raw") or {}).get("userData")) or {}

    lact_hr = user.get("lactateThresholdHeartRate")
    lact_speed = user.get("lactateThresholdSpeed")
    lact_auto = user.get("thresholdHeartRateAutoDetected")

    metrics["umbral_lactato_fc_ppm"] = lact_hr
    metrics["umbral_lactato_autodetectado"] = lact_auto
    metrics["umbral_lactato_ritmo_disponible"] = False
    metrics["umbral_lactato_potencia_disponible"] = False
    metrics["umbral_lactato_wkg_disponible"] = False
    metrics["umbral_lactato_speed_raw"] = lact_speed

    parts = []
    if lact_hr is not None:
        parts.append(f"{int(round(lact_hr))} ppm")
    if lact_auto is True:
        parts.append("autodetectado")
    elif lact_auto is False:
        parts.append("no autodetectado")
    parts.append("ritmo/potencia/W/kg no disponibles con las fuentes actuales")

    metrics["umbral_lactato_resumen_humano"] = " · ".join(parts)

    return snap


if "ES_FIELD_LABELS" in globals():
    ES_FIELD_LABELS.update({
        "umbral_lactato_fc_ppm": "Umbral de lactato (frecuencia cardiaca)",
        "umbral_lactato_autodetectado": "Umbral de lactato autodetectado",
        "umbral_lactato_ritmo_disponible": "Ritmo de umbral disponible",
        "umbral_lactato_potencia_disponible": "Potencia de umbral disponible",
        "umbral_lactato_wkg_disponible": "Potencia relativa de umbral disponible",
        "umbral_lactato_speed_raw": "Velocidad bruta de umbral de lactato",
        "umbral_lactato_resumen_humano": "Resumen humano de umbral de lactato",
    })
# === GARMIN LACTATO PARCIAL PATCH END ===


# === GARMIN UI TEXTS PATCH START ===
def _gfmt_int(v):
    try:
        return f"{int(round(float(v))):,}".replace(",", ".")
    except Exception:
        return None

def _gfmt_km(v):
    try:
        return f"{float(v):.1f}".replace(".", ",") + " km"
    except Exception:
        return None

def _gsec_to_text(seconds):
    try:
        seconds = int(seconds)
    except Exception:
        return None
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h and m:
        return f"{h}h {m}min"
    if h:
        return f"{h}h"
    return f"{m}min"


try:
    _GARMIN_UI_TEXTS_ORIGINAL_COLLECT_DAY_SNAPSHOT
except NameError:
    _GARMIN_UI_TEXTS_ORIGINAL_COLLECT_DAY_SNAPSHOT = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _GARMIN_UI_TEXTS_ORIGINAL_COLLECT_DAY_SNAPSHOT(*args, **kwargs)
    metrics = snap.setdefault("metrics", {})
    raw = snap.setdefault("raw_sources", {})

    summary = raw.get("summary_raw") or {}
    load_balance_map = (((raw.get("training_status_raw") or {}).get("mostRecentTrainingLoadBalance") or {}).get("metricsTrainingLoadBalanceDTOMap")) or {}
    load_balance = None
    if isinstance(load_balance_map, dict):
        for block in load_balance_map.values():
            if isinstance(block, dict):
                load_balance = block
                break
    load_balance = load_balance or {}

    # Calorías
    active_kcal = metrics.get("active_kcal")
    total_kcal = metrics.get("total_kcal")
    rest_kcal = summary.get("bmrKilocalories")
    if rest_kcal is None and active_kcal is not None and total_kcal is not None:
        rest_kcal = float(total_kcal) - float(active_kcal)

    metrics["calorias_activas"] = active_kcal
    metrics["calorias_en_reposo"] = rest_kcal
    metrics["calorias_totales"] = total_kcal

    if active_kcal is not None and rest_kcal is not None and total_kcal is not None:
        metrics["calorias_resumen_humano"] = (
            f"{_gfmt_int(active_kcal)} Calorías activas + "
            f"{_gfmt_int(rest_kcal)} Calorías en reposo = "
            f"{_gfmt_int(total_kcal)} Total de calorías quemadas"
        )

    # Pasos
    steps = metrics.get("steps")
    steps_goal = metrics.get("steps_goal")
    distance_km = metrics.get("distance_km")
    pasos_parts = []
    if steps is not None:
        pasos_parts.append(f"{_gfmt_int(steps)} pasos")
    if steps_goal is not None:
        pasos_parts.append(f"objetivo {_gfmt_int(steps_goal)}")
    if distance_km is not None:
        pasos_parts.append(f"distancia {_gfmt_km(distance_km)}")
    if pasos_parts:
        metrics["pasos_resumen_humano"] = " · ".join(pasos_parts)

    # Pisos
    floors_up = summary.get("floorsAscended")
    floors_down = summary.get("floorsDescended")
    floors_goal = summary.get("userFloorsAscendedGoal")
    metrics["pisos_subidos"] = floors_up
    metrics["pisos_bajados"] = floors_down
    metrics["pisos_objetivo"] = floors_goal
    pisos_parts = []
    if floors_up is not None:
        pisos_parts.append(f"{_gfmt_int(floors_up)} subidos")
    if floors_down is not None:
        pisos_parts.append(f"{_gfmt_int(floors_down)} bajados")
    if floors_goal is not None:
        pisos_parts.append(f"objetivo {_gfmt_int(floors_goal)}")
    if pisos_parts:
        metrics["pisos_resumen_humano"] = " · ".join(pisos_parts)

    # Minutos de intensidad
    intensity = raw.get("intensity_minutes_raw") or {}
    weekly_total = intensity.get("weeklyTotal")
    weekly_mod = intensity.get("weeklyModerate")
    weekly_vig = intensity.get("weeklyVigorous")
    week_goal = intensity.get("weekGoal") or summary.get("intensityMinutesGoal")

    metrics["minutos_intensidad_total_semanal"] = weekly_total
    metrics["minutos_intensidad_moderados_semanal"] = weekly_mod
    metrics["minutos_intensidad_altos_semanal"] = weekly_vig
    metrics["minutos_intensidad_objetivo_semanal"] = week_goal

    im_parts = []
    if weekly_total is not None:
        im_parts.append(f"{_gfmt_int(weekly_total)} minutos de intensidad")
    if weekly_mod is not None:
        im_parts.append(f"{_gfmt_int(weekly_mod)} moderados")
    if weekly_vig is not None:
        im_parts.append(f"{_gfmt_int(weekly_vig)} altos")
    if week_goal is not None:
        im_parts.append(f"objetivo semanal {_gfmt_int(week_goal)}")
    if im_parts:
        metrics["minutos_intensidad_resumen_humano"] = " · ".join(im_parts)

    # Estrés
    stress_avg = metrics.get("stress_avg")
    rest_dur = _gsec_to_text(summary.get("restStressDuration"))
    low_dur = _gsec_to_text(summary.get("lowStressDuration"))
    med_dur = _gsec_to_text(summary.get("mediumStressDuration"))
    high_dur = _gsec_to_text(summary.get("highStressDuration"))

    estres_parts = []
    if stress_avg is not None:
        estres_parts.append(f"Nivel de estrés {_gfmt_int(stress_avg)}")
    if rest_dur:
        estres_parts.append(f"Descanso {rest_dur}")
    if low_dur:
        estres_parts.append(f"Bajo {low_dur}")
    if med_dur:
        estres_parts.append(f"Medio {med_dur}")
    if high_dur:
        estres_parts.append(f"Alta {high_dur}")
    if estres_parts:
        metrics["estres_resumen_humano"] = " · ".join(estres_parts)

    # Foco de carga
    foco = None
    al = load_balance.get("monthlyLoadAerobicLow")
    ah = load_balance.get("monthlyLoadAerobicHigh")
    an = load_balance.get("monthlyLoadAnaerobic")
    al_max = load_balance.get("monthlyLoadAerobicLowTargetMax")
    ah_max = load_balance.get("monthlyLoadAerobicHighTargetMax")
    an_max = load_balance.get("monthlyLoadAnaerobicTargetMax")

    try:
        if None not in (al, ah, an, al_max, ah_max, an_max):
            if al > al_max and ah > ah_max and an > an_max:
                foco = "Por encima de los objetivos"
    except Exception:
        pass

    if foco:
        metrics["foco_de_carga_texto"] = foco

    # Estado de entreno: resumen más Garmin
    training_status_es = metrics.get("training_status_es")
    vo2 = metrics.get("vo2max")
    vo2_label = metrics.get("vo2max_label")
    vfc_factor = metrics.get("predisposicion_factor_vfc_ms")
    acute = metrics.get("acute_load")
    acute_es = metrics.get("acute_load_status_es")

    et_parts = []
    if training_status_es:
        et_parts.append(training_status_es)
    if vo2 is not None:
        vo2_txt = f"VO2 máximo {int(round(float(vo2)))}"
        if vo2_label:
            vo2_txt += f" ({vo2_label})"
        et_parts.append(vo2_txt)
    if vfc_factor is not None:
        estado_vfc = metrics.get("estado_vfc")
        vfc_txt = f"Estado de VFC {int(round(float(vfc_factor)))} ms"
        if estado_vfc:
            vfc_txt += f" ({estado_vfc})"
        et_parts.append(vfc_txt)
    if acute is not None:
        acute_txt = f"Carga aguda {int(round(float(acute)))}"
        if acute_es:
            acute_txt += f" ({acute_es})"
        et_parts.append(acute_txt)
    if foco:
        et_parts.append(f"Foco de carga {foco}")
    if et_parts:
        metrics["estado_entreno_resumen_humano"] = " · ".join(et_parts)

    # Labels visibles
    if "ES_FIELD_LABELS" in globals():
        ES_FIELD_LABELS.update({
            "calorias_activas": "Calorías activas",
            "calorias_en_reposo": "Calorías en reposo",
            "calorias_totales": "Total de calorías quemadas",
            "calorias_resumen_humano": "Resumen humano de calorías",
            "pasos_resumen_humano": "Resumen humano de pasos",
            "pisos_subidos": "Subidos",
            "pisos_bajados": "Bajados",
            "pisos_objetivo": "Objetivo de pisos",
            "pisos_resumen_humano": "Resumen humano de pisos",
            "minutos_intensidad_total_semanal": "Minutos de intensidad semanales",
            "minutos_intensidad_moderados_semanal": "Minutos moderados semanales",
            "minutos_intensidad_altos_semanal": "Minutos altos semanales",
            "minutos_intensidad_objetivo_semanal": "Objetivo semanal de minutos de intensidad",
            "minutos_intensidad_resumen_humano": "Resumen humano de minutos de intensidad",
            "estres_resumen_humano": "Resumen humano de estrés",
            "foco_de_carga_texto": "Foco de carga",
            "estado_entreno_resumen_humano": "Resumen humano de estado de entreno",
        })

    return snap
# === GARMIN UI TEXTS PATCH END ===


# === MCPX ACTIVITY DEEP PATCH START ===
_ACTIVITY_SUMMARY_KEYS = [
    "distance",
    "duration",
    "elapsedDuration",
    "movingDuration",
    "calories",
    "activityTrainingLoad",
    "trainingEffect",
    "anaerobicTrainingEffect",
    "trainingEffectLabel",
    "aerobicTrainingEffectMessage",
    "anaerobicTrainingEffectMessage",
    "averageHR",
    "maxHR",
    "minHR",
    "averageSpeed",
    "averageMovingSpeed",
    "maxSpeed",
    "avgGradeAdjustedSpeed",
    "averagePower",
    "maxPower",
    "minPower",
    "normalizedPower",
    "totalWork",
    "averageRunCadence",
    "maxRunCadence",
    "groundContactTime",
    "verticalOscillation",
    "verticalRatio",
    "strideLength",
    "steps",
    "averageTemperature",
    "maxTemperature",
    "minTemperature",
    "avgElevation",
    "maxElevation",
    "minElevation",
    "elevationGain",
    "elevationLoss",
    "beginPotentialStamina",
    "endPotentialStamina",
    "minAvailableStamina",
    "differenceBodyBattery",
    "waterEstimated",
    "moderateIntensityMinutes",
    "vigorousIntensityMinutes",
]

_ACTIVITY_TRANSPORT_TYPES = {"motorcycling", "driving", "car", "automotive"}
_ACTIVITY_ENDURANCE_TYPES = {"running", "treadmill_running", "walking", "hiking", "trail_running", "track_running"}
_ACTIVITY_STRENGTH_TYPES = {"strength_training"}
_ACTIVITY_CYCLING_TYPES = {"cycling", "indoor_cycling", "mountain_biking", "road_biking", "virtual_ride"}
_ACTIVITY_SWIM_TYPES = {"lap_swimming", "open_water_swimming", "swimming"}


def _activity_type_key_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("activityTypeDTO", "activityType"):
        value = payload.get(key)
        if isinstance(value, dict) and value.get("typeKey"):
            return str(value.get("typeKey"))
    return None


def _activity_family(activity_type: str | None) -> str:
    if not activity_type:
        return "other"
    if activity_type in _ACTIVITY_ENDURANCE_TYPES:
        return "endurance"
    if activity_type in _ACTIVITY_STRENGTH_TYPES:
        return "strength"
    if activity_type in _ACTIVITY_CYCLING_TYPES:
        return "cycling"
    if activity_type in _ACTIVITY_SWIM_TYPES:
        return "swimming"
    if activity_type in _ACTIVITY_TRANSPORT_TYPES:
        return "transport"
    return activity_type


def _pick_activity_summary(summary: Any) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    return {key: summary.get(key) for key in _ACTIVITY_SUMMARY_KEYS if summary.get(key) is not None}


def _pick_activity_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    keys = [
        "lapCount",
        "hasChartData",
        "hasPolyline",
        "hasHrTimeInZones",
        "hasPowerTimeInZones",
        "hasSplits",
        "hasIntensityIntervals",
        "manufacturer",
        "fileFormat",
        "elevationCorrected",
        "trimmed",
        "personalRecord",
        "favorite",
        "associatedWorkoutId",
        "videoUrl",
    ]
    return {key: metadata.get(key) for key in keys if metadata.get(key) is not None}


def _extract_metric_descriptors(details: Any) -> list[dict[str, Any]]:
    if not isinstance(details, dict):
        return []
    out: list[dict[str, Any]] = []
    for descriptor in details.get("metricDescriptors") or []:
        if not isinstance(descriptor, dict):
            continue
        unit = descriptor.get("unit") or {}
        out.append({
            "metrics_index": descriptor.get("metricsIndex"),
            "key": descriptor.get("key"),
            "unit": unit.get("key") if isinstance(unit, dict) else None,
        })
    return out


def _extract_detail_counts(details: Any) -> dict[str, Any]:
    if not isinstance(details, dict):
        return {}
    polyline = None
    geo = details.get("geoPolylineDTO")
    if isinstance(geo, dict):
        polyline = geo.get("polyline")
    return {
        "details_available": details.get("detailsAvailable"),
        "measurement_count": details.get("measurementCount"),
        "metrics_count": details.get("metricsCount"),
        "total_metrics_count": details.get("totalMetricsCount"),
        "heart_rate_samples": len(details.get("heartRateDTOs") or []) if isinstance(details.get("heartRateDTOs"), list) else 0,
        "polyline_points": len(polyline) if isinstance(polyline, list) else 0,
    }


def _extract_metric_values_from_row(row: Any) -> list[Any]:
    if isinstance(row, dict):
        metrics = row.get("metrics")
        return metrics if isinstance(metrics, list) else []
    return row if isinstance(row, list) else []


def _compact_activity_time_series(details: Any, max_samples: int = 200) -> dict[str, Any]:
    if not isinstance(details, dict):
        return {
            "metric_descriptors": [],
            "sample_count": 0,
            "samples_returned": 0,
            "samples": [],
        }

    max_samples = max(1, min(2000, int(max_samples)))
    descriptors = _extract_metric_descriptors(details)
    rows = details.get("activityDetailMetrics") or []
    samples: list[dict[str, Any]] = []

    for row in rows[:max_samples]:
        values = _extract_metric_values_from_row(row)
        mapped: dict[str, Any] = {}
        for descriptor in descriptors:
            raw_index = descriptor.get("metrics_index")
            try:
                index = int(raw_index)
            except Exception:
                continue
            if index < 0 or index >= len(values):
                continue
            value = values[index]
            if value is None:
                continue
            key = descriptor.get("key") or f"metric_{index}"
            mapped[key] = value
        if mapped:
            samples.append(mapped)

    return {
        "metric_descriptors": descriptors,
        "sample_count": len(rows) if isinstance(rows, list) else 0,
        "samples_returned": len(samples),
        "samples": samples,
    }


def _extract_split_counts(splits: Any, typed_splits: Any, split_summaries: Any) -> dict[str, Any]:
    lap_count = 0
    typed_count = 0
    split_summary_count = 0

    if isinstance(splits, dict) and isinstance(splits.get("lapDTOs"), list):
        lap_count = len(splits.get("lapDTOs") or [])
    if isinstance(typed_splits, dict) and isinstance(typed_splits.get("splits"), list):
        typed_count = len(typed_splits.get("splits") or [])
    if isinstance(split_summaries, dict) and isinstance(split_summaries.get("splitSummaries"), list):
        split_summary_count = len(split_summaries.get("splitSummaries") or [])

    return {
        "laps": lap_count,
        "typed_splits": typed_count,
        "split_summaries": split_summary_count,
    }


def _exercise_set_count(exercise_sets: Any) -> int:
    if isinstance(exercise_sets, dict) and isinstance(exercise_sets.get("exerciseSets"), list):
        return len(exercise_sets.get("exerciseSets") or [])
    return 0


def _to_float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _normalize_strength_weight_to_kg(value: Any) -> float | None:
    raw = _to_float_or_none(value)
    if raw is None:
        return None
    # En Garmin fuerza suele venir en gramos: 45000 -> 45.0 kg
    if raw >= 1000:
        return raw / 1000.0
    return raw


def _best_exercise_guess(item: dict[str, Any]) -> tuple[str, float | None]:
    exercises = item.get("exercises") or []
    if not isinstance(exercises, list) or not exercises:
        return ("UNKNOWN", None)

    best = None
    best_prob = None
    for ex in exercises:
        if not isinstance(ex, dict):
            continue
        cat = ex.get("category") or ex.get("name") or "UNKNOWN"
        prob = _to_float_or_none(ex.get("probability"))
        if best is None:
            best = cat
            best_prob = prob
            continue
        if prob is not None and (best_prob is None or prob > best_prob):
            best = cat
            best_prob = prob

    return (best or "UNKNOWN", best_prob)


def _summarize_strength_sets(exercise_sets_payload: Any) -> dict[str, Any] | None:
    if not isinstance(exercise_sets_payload, dict):
        return None

    exercise_sets = exercise_sets_payload.get("exerciseSets") or []
    total_sets_raw = exercise_sets_payload.get("totalSets")
    active_sets_raw = exercise_sets_payload.get("activeSets")

    per_set = []
    grouped: dict[str, dict[str, Any]] = {}

    total_reps = 0.0
    total_volume_kg = 0.0
    max_weight_kg = None
    active_sets_count = 0
    active_time_s = 0.0
    rest_time_s = 0.0

    if isinstance(exercise_sets, list):
        for idx, item in enumerate(exercise_sets):
            if not isinstance(item, dict):
                continue

            reps = _to_float_or_none(item.get("repetitionCount")) or 0.0
            weight_kg = _normalize_strength_weight_to_kg(item.get("weight")) or 0.0
            duration_s = _to_float_or_none(item.get("duration"))
            set_type = item.get("setType")
            start_time = item.get("startTime")
            guess, prob = _best_exercise_guess(item)
            volume_kg = reps * weight_kg

            if set_type == "ACTIVE":
                active_sets_count += 1
                if duration_s is not None:
                    active_time_s += duration_s
            elif set_type == "REST":
                if duration_s is not None:
                    rest_time_s += duration_s

            total_reps += reps
            total_volume_kg += volume_kg
            if max_weight_kg is None or weight_kg > max_weight_kg:
                max_weight_kg = weight_kg

            per_set.append({
                "set_index": idx,
                "exercise_guess": guess,
                "exercise_guess_probability": prob,
                "set_type": set_type,
                "start_time": start_time,
                "duration_s": duration_s,
                "reps": reps,
                "weight_kg": weight_kg,
                "volume_kg": volume_kg,
                "exercise_candidates": item.get("exercises"),
            })

            if set_type == "ACTIVE":
                row = grouped.setdefault(guess, {
                    "exercise": guess,
                    "sets": 0,
                    "active_sets": 0,
                    "reps": 0.0,
                    "max_weight_kg": None,
                    "volume_kg": 0.0,
                })
                row["sets"] += 1
                row["active_sets"] += 1
                row["reps"] += reps
                row["volume_kg"] += volume_kg
                if row["max_weight_kg"] is None or weight_kg > row["max_weight_kg"]:
                    row["max_weight_kg"] = weight_kg

    top_exercises = sorted(
        grouped.values(),
        key=lambda x: (x.get("volume_kg") or 0.0, x.get("sets") or 0),
        reverse=True,
    )

    return {
        "exercise_set_count": _exercise_set_count(exercise_sets_payload),
        "total_sets_raw": total_sets_raw,
        "active_sets_raw": active_sets_raw,
        "active_sets_count_estimated": active_sets_count,
        "active_time_s_estimated": active_time_s,
        "rest_time_s_estimated": rest_time_s,
        "total_reps_estimated": total_reps,
        "total_volume_kg_estimated": total_volume_kg,
        "max_weight_kg_seen": max_weight_kg,
        "top_exercises": top_exercises[:15],
        "per_set": per_set,
    }


def _sleep_with_jitter(base_seconds: float) -> None:
    import random
    import time
    time.sleep(base_seconds + random.uniform(0, 0.35))


def _call_with_retries(api: Garmin, method_name: str, *args: Any, retries: int = 2, **kwargs: Any) -> tuple[Any, str | None]:
    last_err: str | None = None

    for attempt in range(retries + 1):
        value, err = _optional_call_first(api, (method_name,), *args, **kwargs)
        if value is not None:
            return value, None

        last_err = err
        err_text = (err or "").lower()

        retryable = any(token in err_text for token in [
            "502",
            "503",
            "504",
            "bad gateway",
            "gateway timeout",
            "cloudflare",
            "temporarily unavailable",
            "connection",
            "timeout",
        ])

        if not retryable or attempt >= retries:
            return value, last_err

        _sleep_with_jitter(0.8 * (attempt + 1))

    return None, last_err


def _fetch_activity_bundle(api: Garmin, activity_id: str, include_time_series: bool = False, max_samples: int = 200) -> dict[str, Any]:
    activity, activity_err = _call_with_retries(api, "get_activity", activity_id, retries=1)
    details, details_err = _call_with_retries(api, "get_activity_details", activity_id, retries=2)
    splits, splits_err = _call_with_retries(api, "get_activity_splits", activity_id, retries=1)
    typed_splits, typed_splits_err = _call_with_retries(api, "get_activity_typed_splits", activity_id, retries=1)
    split_summaries, split_summaries_err = _call_with_retries(api, "get_activity_split_summaries", activity_id, retries=1)
    weather, weather_err = _call_with_retries(api, "get_activity_weather", activity_id, retries=1)
    hr_zones, hr_zones_err = _call_with_retries(api, "get_activity_hr_in_timezones", activity_id, retries=1)
    power_zones, power_zones_err = _call_with_retries(api, "get_activity_power_in_timezones", activity_id, retries=1)
    exercise_sets, exercise_sets_err = _call_with_retries(api, "get_activity_exercise_sets", activity_id, retries=1)
    gear, gear_err = _call_with_retries(api, "get_activity_gear", activity_id, retries=1)

    activity_type = _activity_type_key_from_payload(activity or {})
    summary = (activity or {}).get("summaryDTO") if isinstance(activity, dict) else {}
    metadata = (activity or {}).get("metadataDTO") if isinstance(activity, dict) else {}

    bundle: dict[str, Any] = {
        "activity_id": activity_id,
        "activity_name": (activity or {}).get("activityName") if isinstance(activity, dict) else None,
        "activity_type": activity_type,
        "activity_family": _activity_family(activity_type),
        "start_time_local": (summary or {}).get("startTimeLocal") or ((activity or {}).get("startTimeLocal") if isinstance(activity, dict) else None),
        "summary": _pick_activity_summary(summary),
        "metadata": _pick_activity_metadata(metadata),
        "detail_metric_descriptors": _extract_metric_descriptors(details),
        "detail_counts": _extract_detail_counts(details),
        "split_counts": _extract_split_counts(splits, typed_splits, split_summaries),
        "laps": (splits or {}).get("lapDTOs") if isinstance(splits, dict) else None,
        "events": (splits or {}).get("eventDTOs") if isinstance(splits, dict) else None,
        "typed_splits": (typed_splits or {}).get("splits") if isinstance(typed_splits, dict) else None,
        "split_summaries": (split_summaries or {}).get("splitSummaries") if isinstance(split_summaries, dict) else None,
        "weather": weather if isinstance(weather, dict) else None,
        "hr_time_in_zones": hr_zones if isinstance(hr_zones, list) else None,
        "power_time_in_zones": power_zones if isinstance(power_zones, list) else None,
        "exercise_sets": (exercise_sets or {}).get("exerciseSets") if isinstance(exercise_sets, dict) else None,
        "exercise_set_count": _exercise_set_count(exercise_sets),
        "strength_summary": _summarize_strength_sets(exercise_sets),
        "gear": gear if isinstance(gear, list) else None,
        "gear_count": len(gear) if isinstance(gear, list) else 0,
        "available_sections": {
            "activity": activity is not None,
            "details": details is not None,
            "splits": splits is not None,
            "typed_splits": typed_splits is not None,
            "split_summaries": split_summaries is not None,
            "weather": weather is not None,
            "hr_zones": hr_zones is not None,
            "power_zones": power_zones is not None,
            "exercise_sets": exercise_sets is not None,
            "gear": gear is not None,
        },
        "source_errors": {
            "activity": activity_err,
            "details": details_err,
            "splits": splits_err,
            "typed_splits": typed_splits_err,
            "split_summaries": split_summaries_err,
            "weather": weather_err,
            "hr_zones": hr_zones_err,
            "power_zones": power_zones_err,
            "exercise_sets": exercise_sets_err,
            "gear": gear_err,
        },
    }

    if include_time_series:
        bundle["time_series"] = _compact_activity_time_series(details, max_samples=max_samples)

    return bundle


@mcp.tool
def get_activity_full(activity_id: str, include_time_series: bool = False, max_samples: int = 200) -> dict[str, Any]:
    """Actividad completa con resumen, vueltas, clima, zonas, material y series temporales opcionales."""
    max_samples = max(1, min(2000, int(max_samples)))
    with FETCH_LOCK:
        api = _get_api()
        return _fetch_activity_bundle(api, str(activity_id), include_time_series=include_time_series, max_samples=max_samples)


@mcp.tool
def get_activity_time_series(activity_id: str, max_samples: int = 300) -> dict[str, Any]:
    """Serie temporal compacta de una actividad con métricas por muestra."""
    max_samples = max(1, min(2000, int(max_samples)))
    with FETCH_LOCK:
        api = _get_api()
        details, err = _call_with_retries(api, "get_activity_details", str(activity_id), retries=2)
        if details is None:
            raise RuntimeError(err or "No pude leer los detalles de la actividad")
        result = _compact_activity_time_series(details, max_samples=max_samples)
        result["activity_id"] = str(activity_id)
        result["detail_counts"] = _extract_detail_counts(details)
        return result


@mcp.tool
def get_recent_activities_full(limit: int = 8) -> list[dict[str, Any]]:
    """Actividades recientes con resumen completo, vueltas, clima, zonas, material y sets."""
    limit = max(1, min(12, int(limit)))
    with FETCH_LOCK:
        api = _get_api()
        activities, err = _optional_call_first(api, ("get_activities",), 0, limit)
        if activities is None:
            raise RuntimeError(err or "No pude leer las actividades recientes")

        activity_ids: list[str] = []
        for activity in activities[:limit]:
            if not isinstance(activity, dict):
                continue
            activity_id = activity.get("activityId")
            if activity_id is None:
                continue
            activity_ids.append(str(activity_id))

        return [_fetch_activity_bundle(api, activity_id, include_time_series=False) for activity_id in activity_ids]
# === MCPX ACTIVITY DEEP PATCH END ===


# === MCPX ALL SPORTS RAW TOOLS START ===

def _available_summary_keys(activity: Any) -> list[str]:
    if not isinstance(activity, dict):
        return []
    summary = activity.get("summaryDTO") or {}
    if not isinstance(summary, dict):
        return []
    return sorted(summary.keys())


def _available_metadata_keys(activity: Any) -> list[str]:
    if not isinstance(activity, dict):
        return []
    metadata = activity.get("metadataDTO") or {}
    if not isinstance(metadata, dict):
        return []
    return sorted(metadata.keys())


def _available_detail_metric_keys(details: Any) -> list[str]:
    out: list[str] = []
    if not isinstance(details, dict):
        return out
    for d in details.get("metricDescriptors") or []:
        if not isinstance(d, dict):
            continue
        key = d.get("key")
        if key:
            out.append(str(key))
    return sorted(out)


def _fetch_activity_all_data(api: Garmin, activity_id: str, include_time_series: bool = False, max_samples: int = 500) -> dict[str, Any]:
    activity, activity_err = _call_with_retries(api, "get_activity", activity_id, retries=1)
    details, details_err = _call_with_retries(api, "get_activity_details", activity_id, retries=2)
    splits, splits_err = _call_with_retries(api, "get_activity_splits", activity_id, retries=1)
    typed_splits, typed_splits_err = _call_with_retries(api, "get_activity_typed_splits", activity_id, retries=1)
    split_summaries, split_summaries_err = _call_with_retries(api, "get_activity_split_summaries", activity_id, retries=1)
    weather, weather_err = _call_with_retries(api, "get_activity_weather", activity_id, retries=1)
    hr_zones, hr_zones_err = _call_with_retries(api, "get_activity_hr_in_timezones", activity_id, retries=1)
    power_zones, power_zones_err = _call_with_retries(api, "get_activity_power_in_timezones", activity_id, retries=1)
    exercise_sets, exercise_sets_err = _call_with_retries(api, "get_activity_exercise_sets", activity_id, retries=1)
    gear, gear_err = _call_with_retries(api, "get_activity_gear", activity_id, retries=1)

    compact = _fetch_activity_bundle(api, activity_id, include_time_series=include_time_series, max_samples=max_samples)

    compact["available_summary_keys"] = _available_summary_keys(activity)
    compact["available_metadata_keys"] = _available_metadata_keys(activity)
    compact["available_detail_metric_keys"] = _available_detail_metric_keys(details)

    compact["raw_payloads"] = {
        "activity_raw": activity,
        "details_raw": details,
        "splits_raw": splits,
        "typed_splits_raw": typed_splits,
        "split_summaries_raw": split_summaries,
        "weather_raw": weather,
        "hr_time_in_zones_raw": hr_zones,
        "power_time_in_zones_raw": power_zones,
        "exercise_sets_raw": exercise_sets,
        "gear_raw": gear,
    }

    compact["raw_payload_errors"] = {
        "activity": activity_err,
        "details": details_err,
        "splits": splits_err,
        "typed_splits": typed_splits_err,
        "split_summaries": split_summaries_err,
        "weather": weather_err,
        "hr_zones": hr_zones_err,
        "power_zones": power_zones_err,
        "exercise_sets": exercise_sets_err,
        "gear": gear_err,
    }

    return compact


@mcp.tool
def get_activity_all_data(activity_id: str, include_time_series: bool = False, max_samples: int = 500) -> dict[str, Any]:
    """Devuelve todos los payloads crudos y el bundle compacto de una actividad, sin filtrar por deporte."""
    max_samples = max(1, min(2000, int(max_samples)))
    with FETCH_LOCK:
        api = _get_api()
        return _fetch_activity_all_data(api, str(activity_id), include_time_series=include_time_series, max_samples=max_samples)


@mcp.tool
def get_recent_activities_catalog(limit: int = 12) -> list[dict[str, Any]]:
    """Catálogo reciente de actividades para elegir activity_id y deporte."""
    limit = max(1, min(30, int(limit)))
    with FETCH_LOCK:
        api = _get_api()
        activities, err = _optional_call_first(api, ("get_activities",), 0, limit)
        if activities is None:
            raise RuntimeError(err or "No pude leer las actividades recientes")

        out: list[dict[str, Any]] = []
        for activity in activities[:limit]:
            if not isinstance(activity, dict):
                continue
            activity_type = activity.get("activityType") or activity.get("activityTypeDTO") or {}
            out.append({
                "activity_id": activity.get("activityId"),
                "activity_name": activity.get("activityName"),
                "activity_type": activity_type.get("typeKey"),
                "activity_family": _activity_family(activity_type.get("typeKey")),
                "start_time_local": activity.get("startTimeLocal"),
            })
        return out


@mcp.tool
def get_recent_activities_all_data(limit: int = 3, include_time_series: bool = False, max_samples: int = 300) -> list[dict[str, Any]]:
    """Devuelve todos los payloads crudos para varias actividades recientes. Úsalo con límites pequeños."""
    limit = max(1, min(8, int(limit)))
    max_samples = max(1, min(2000, int(max_samples)))
    with FETCH_LOCK:
        api = _get_api()
        activities, err = _optional_call_first(api, ("get_activities",), 0, limit)
        if activities is None:
            raise RuntimeError(err or "No pude leer las actividades recientes")

        out: list[dict[str, Any]] = []
        for activity in activities[:limit]:
            if not isinstance(activity, dict):
                continue
            activity_id = activity.get("activityId")
            if activity_id is None:
                continue
            out.append(_fetch_activity_all_data(api, str(activity_id), include_time_series=include_time_series, max_samples=max_samples))
        return out

# === MCPX ALL SPORTS RAW TOOLS END ===


# === MCPX SPORT PROFILE TOOLS START ===

def _pick_keys(source: Any, keys: list[str]) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    return {k: source.get(k) for k in keys if source.get(k) is not None}


def _sport_profile_running_like(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    return {
        "sport_profile_type": "running_like",
        "primary_metrics": _pick_keys(summary, [
            "distance",
            "duration",
            "elapsedDuration",
            "movingDuration",
            "averageHR",
            "maxHR",
            "averageSpeed",
            "averageMovingSpeed",
            "maxSpeed",
            "averagePower",
            "maxPower",
            "normalizedPower",
            "averageRunCadence",
            "maxRunCadence",
            "groundContactTime",
            "verticalOscillation",
            "verticalRatio",
            "strideLength",
            "steps",
            "elevationGain",
            "elevationLoss",
            "avgElevation",
            "averageTemperature",
            "maxTemperature",
            "minTemperature",
            "activityTrainingLoad",
            "trainingEffect",
            "anaerobicTrainingEffect",
            "trainingEffectLabel",
            "beginPotentialStamina",
            "endPotentialStamina",
            "minAvailableStamina",
            "moderateIntensityMinutes",
            "vigorousIntensityMinutes",
            "waterEstimated",
        ]),
        "detail_metric_keys": bundle.get("available_detail_metric_keys") or [],
        "detail_counts": bundle.get("detail_counts") or {},
        "split_counts": bundle.get("split_counts") or {},
        "hr_time_in_zones": bundle.get("hr_time_in_zones"),
        "power_time_in_zones": bundle.get("power_time_in_zones"),
        "weather": bundle.get("weather"),
        "gear": bundle.get("gear"),
    }


def _sport_profile_strength(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    strength_summary = bundle.get("strength_summary") or {}
    return {
        "sport_profile_type": "strength",
        "primary_metrics": _pick_keys(summary, [
            "duration",
            "elapsedDuration",
            "movingDuration",
            "averageHR",
            "maxHR",
            "averageTemperature",
            "maxTemperature",
            "minTemperature",
            "activityTrainingLoad",
            "trainingEffect",
            "anaerobicTrainingEffect",
            "trainingEffectLabel",
            "moderateIntensityMinutes",
            "vigorousIntensityMinutes",
            "calories",
            "waterEstimated",
            "steps",
        ]),
        "strength_summary": strength_summary,
        "hr_time_in_zones": bundle.get("hr_time_in_zones"),
        "weather": bundle.get("weather"),
    }


def _sport_profile_cycling(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    return {
        "sport_profile_type": "cycling",
        "primary_metrics": _pick_keys(summary, [
            "distance",
            "duration",
            "elapsedDuration",
            "movingDuration",
            "averageHR",
            "maxHR",
            "averageSpeed",
            "averageMovingSpeed",
            "maxSpeed",
            "averagePower",
            "maxPower",
            "normalizedPower",
            "totalWork",
            "elevationGain",
            "elevationLoss",
            "avgElevation",
            "averageTemperature",
            "activityTrainingLoad",
            "trainingEffect",
            "anaerobicTrainingEffect",
            "trainingEffectLabel",
            "moderateIntensityMinutes",
            "vigorousIntensityMinutes",
            "waterEstimated",
        ]),
        "detail_metric_keys": bundle.get("available_detail_metric_keys") or [],
        "hr_time_in_zones": bundle.get("hr_time_in_zones"),
        "power_time_in_zones": bundle.get("power_time_in_zones"),
        "weather": bundle.get("weather"),
        "gear": bundle.get("gear"),
    }


def _sport_profile_swimming(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    return {
        "sport_profile_type": "swimming",
        "primary_metrics": _pick_keys(summary, [
            "distance",
            "duration",
            "elapsedDuration",
            "movingDuration",
            "averageHR",
            "maxHR",
            "averageSpeed",
            "maxSpeed",
            "calories",
            "activityTrainingLoad",
            "trainingEffect",
            "anaerobicTrainingEffect",
            "trainingEffectLabel",
            "moderateIntensityMinutes",
            "vigorousIntensityMinutes",
        ]),
        "detail_metric_keys": bundle.get("available_detail_metric_keys") or [],
        "hr_time_in_zones": bundle.get("hr_time_in_zones"),
    }


def _sport_profile_transport(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    return {
        "sport_profile_type": "transport",
        "primary_metrics": _pick_keys(summary, [
            "distance",
            "duration",
            "elapsedDuration",
            "movingDuration",
            "averageSpeed",
            "maxSpeed",
            "calories",
            "steps",
        ]),
        "note": "Actividad informativa, no perfil principal de entrenamiento."
    }


def _sport_profile_other(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    return {
        "sport_profile_type": "other",
        "primary_metrics": summary,
        "detail_metric_keys": bundle.get("available_detail_metric_keys") or [],
        "hr_time_in_zones": bundle.get("hr_time_in_zones"),
        "power_time_in_zones": bundle.get("power_time_in_zones"),
        "weather": bundle.get("weather"),
        "gear": bundle.get("gear"),
    }


def _build_sport_profile(bundle: dict[str, Any]) -> dict[str, Any]:
    activity_type = bundle.get("activity_type")
    family = bundle.get("activity_family")

    if family == "strength":
        return _sport_profile_strength(bundle)
    if family == "cycling":
        return _sport_profile_cycling(bundle)
    if family == "swimming":
        return _sport_profile_swimming(bundle)
    if family == "transport":
        return _sport_profile_transport(bundle)
    if family == "endurance" or activity_type in {"walking", "cardio", "elliptical", "treadmill_running", "running", "hiking"}:
        return _sport_profile_running_like(bundle)
    return _sport_profile_other(bundle)


@mcp.tool
def get_activity_sport_profile(activity_id: str, include_time_series: bool = False, max_samples: int = 300) -> dict[str, Any]:
    """Perfil interpretado por deporte usando todos los datos disponibles de la actividad."""
    max_samples = max(1, min(2000, int(max_samples)))
    with FETCH_LOCK:
        api = _get_api()
        bundle = _fetch_activity_all_data(api, str(activity_id), include_time_series=include_time_series, max_samples=max_samples)
        profile = _build_sport_profile(bundle)
        return {
            "activity_id": bundle.get("activity_id"),
            "activity_name": bundle.get("activity_name"),
            "activity_type": bundle.get("activity_type"),
            "activity_family": bundle.get("activity_family"),
            "start_time_local": bundle.get("start_time_local"),
            "sport_profile": profile,
            "source_errors": bundle.get("source_errors"),
            "raw_payload_errors": bundle.get("raw_payload_errors"),
        }


@mcp.tool
def get_recent_activity_sport_profiles(limit: int = 8) -> list[dict[str, Any]]:
    """Perfiles interpretados por deporte para actividades recientes."""
    limit = max(1, min(12, int(limit)))
    with FETCH_LOCK:
        api = _get_api()
        activities, err = _optional_call_first(api, ("get_activities",), 0, limit)
        if activities is None:
            raise RuntimeError(err or "No pude leer las actividades recientes")

        out: list[dict[str, Any]] = []
        for activity in activities[:limit]:
            if not isinstance(activity, dict):
                continue
            activity_id = activity.get("activityId")
            if activity_id is None:
                continue
            bundle = _fetch_activity_all_data(api, str(activity_id), include_time_series=False, max_samples=300)
            out.append({
                "activity_id": bundle.get("activity_id"),
                "activity_name": bundle.get("activity_name"),
                "activity_type": bundle.get("activity_type"),
                "activity_family": bundle.get("activity_family"),
                "start_time_local": bundle.get("start_time_local"),
                "sport_profile": _build_sport_profile(bundle),
                "source_errors": bundle.get("source_errors"),
                "raw_payload_errors": bundle.get("raw_payload_errors"),
            })
        return out

# === MCPX SPORT PROFILE TOOLS END ===


# === MCPX VISIBLE METRICS PATCH START ===

def _raw_summary_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    raw_payloads = bundle.get("raw_payloads") or {}
    activity_raw = raw_payloads.get("activity_raw") or {}
    summary = activity_raw.get("summaryDTO") or {}
    return summary if isinstance(summary, dict) else {}


def _format_speed_as_pace(value: Any) -> str | None:
    try:
        mps = float(value)
        if mps <= 0:
            return None
        total_seconds = 1000.0 / mps
        minutes = int(total_seconds // 60)
        seconds = int(round(total_seconds % 60))
        if seconds == 60:
            minutes += 1
            seconds = 0
        return f"{minutes}:{seconds:02d} /km"
    except Exception:
        return None


def _format_celsius(value: Any) -> str | None:
    try:
        return f"{float(value):.1f} °C"
    except Exception:
        return None


def _format_meters(value: Any) -> str | None:
    try:
        return f"{float(value):.2f} m"
    except Exception:
        return None


def _format_centimeters(value: Any) -> str | None:
    try:
        return f"{float(value):.2f} cm"
    except Exception:
        return None


def _format_milliseconds(value: Any) -> str | None:
    try:
        return f"{float(value):.1f} ms"
    except Exception:
        return None


def _format_spm(value: Any) -> str | None:
    try:
        return f"{float(value):.1f} spm"
    except Exception:
        return None


def _format_watts(value: Any) -> str | None:
    try:
        return f"{float(value):.0f} W"
    except Exception:
        return None


def _format_kilograms(value: Any) -> str | None:
    try:
        return f"{float(value):.0f} kg"
    except Exception:
        return None


def _format_ppm(value: Any) -> str | None:
    try:
        return f"{float(value):.0f} ppm"
    except Exception:
        return None


def _format_percent_plain(value: Any) -> str | None:
    try:
        return f"{float(value):.2f}"
    except Exception:
        return None


def _drop_none_deep(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            cleaned = _drop_none_deep(v)
            if cleaned is None:
                continue
            if cleaned == {} or cleaned == []:
                continue
            out[k] = cleaned
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            cleaned = _drop_none_deep(item)
            if cleaned is None:
                continue
            out.append(cleaned)
        return out
    return value


def _training_label_es(value: Any) -> Any:
    mapping = {
        "VO2MAX": "VO2 máximo",
        "LACTATE_THRESHOLD": "Umbral de lactato",
        "TEMPO": "Tempo",
        "ANAEROBIC_CAPACITY": "Capacidad anaeróbica",
        "AEROBIC_BASE": "Base aeróbica",
        "RECOVERY": "Recuperación",
        "THRESHOLD": "Umbral",
    }
    if value is None:
        return None
    return mapping.get(str(value), value)


def _format_seconds_mmss(value: Any) -> str | None:
    try:
        total = int(round(float(value)))
    except Exception:
        return None
    m = total // 60
    s = total % 60
    return f"{m}:{s:02d}"


def _format_percentage(value: Any) -> str | None:
    try:
        return f"{float(value):.0f}%"
    except Exception:
        return None


def _hr_zone_label_es(zone_number: Any) -> str | None:
    mapping = {
        1: "Calentamiento",
        2: "Suave",
        3: "Aeróbica",
        4: "Umbral",
        5: "Máximo",
    }
    try:
        return mapping.get(int(zone_number))
    except Exception:
        return None


def _power_zone_label_es(zone_number: Any) -> str | None:
    mapping = {
        1: "Fácil",
        2: "Moderado",
        3: "Tempo",
        4: "Intervalo largo",
        5: "Intervalo corto",
    }
    try:
        return mapping.get(int(zone_number))
    except Exception:
        return None


def _format_zone_rows(rows: Any, zone_type: str = "hr") -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    total_secs = 0.0
    for row in rows:
        if isinstance(row, dict):
            try:
                total_secs += float(row.get("secsInZone") or 0)
            except Exception:
                pass

    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        zone_number = row.get("zoneNumber")
        secs = row.get("secsInZone")
        low = row.get("zoneLowBoundary")

        try:
            pct = (float(secs) / total_secs * 100.0) if total_secs > 0 else 0.0
        except Exception:
            pct = None

        label = _hr_zone_label_es(zone_number) if zone_type == "hr" else _power_zone_label_es(zone_number)

        out.append({
            "Zona": f"Zona {zone_number}" if zone_number is not None else None,
            "Límite inferior": low,
            "Etiqueta": label,
            "Tiempo": _format_seconds_mmss(secs),
            "Porcentaje": _format_percentage(pct) if pct is not None else None,
            "secs_raw": secs,
        })

    return out


def _format_distance_km(value: Any) -> str | None:
    try:
        return f"{float(value)/1000.0:.2f} km"
    except Exception:
        return None


def _format_distance_km_plain(value: Any) -> float | None:
    try:
        return round(float(value) / 1000.0, 2)
    except Exception:
        return None


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _extract_lap_list(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    laps = bundle.get("laps")
    return laps if isinstance(laps, list) else []


def _visible_laps_or_segments(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    laps = _extract_lap_list(bundle)
    out = []

    for idx, lap in enumerate(laps, 1):
        if not isinstance(lap, dict):
            continue

        out.append({
            "Vuelta": idx,
            "Tiempo": _format_seconds_mmss(lap.get("duration")),
            "Tiempo acumulado": _format_seconds_mmss(lap.get("elapsedDuration")),
            "Distancia": _format_distance_km(lap.get("distance")),
            "Ritmo medio": _format_speed_as_pace(lap.get("averageSpeed")),
            "GAP medio": _format_speed_as_pace(lap.get("averageGradeAdjustedSpeed")),
            "Frecuencia cardiaca media": _format_ppm(lap.get("averageHR")),
            "FC máxima": _format_ppm(lap.get("maxHR")),
            "Ascenso total": _format_meters(lap.get("elevationGain")),
            "Descenso total": _format_meters(lap.get("elevationLoss")),
            "Potencia media": _format_watts(lap.get("averagePower")),
            "Potencia máxima": _format_watts(lap.get("maxPower")),
            "Cadencia de carrera media": _format_spm(lap.get("averageRunCadence")),
            "Cadencia de carrera máxima": _format_spm(lap.get("maxRunCadence")),
        })

    return _drop_none_deep(out)


def _seconds_to_hms(seconds: Any) -> str | None:
    try:
        total = int(round(float(seconds)))
    except Exception:
        return None
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _weighted_intensity_total(moderate: Any, vigorous: Any) -> float | None:
    try:
        mod = float(moderate or 0)
        vig = float(vigorous or 0)
        return mod + (vig * 2)
    except Exception:
        return None


def _visible_metrics_running_like(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    result = {
        "Altura": {
            "Altura media": _format_meters(summary.get("avgElevation")),
            "Altura máxima": _format_meters(summary.get("maxElevation")),
            "Altura mínima": _format_meters(summary.get("minElevation")),
            "Ascenso total": _format_meters(summary.get("elevationGain")),
            "Descenso total": _format_meters(summary.get("elevationLoss")),
        },
        "Ritmo": {
            "Ritmo medio": _format_speed_as_pace(summary.get("averageSpeed")),
            "Ritmo en movimiento": _format_speed_as_pace(summary.get("averageMovingSpeed")),
            "Ritmo máximo": _format_speed_as_pace(summary.get("maxSpeed")),
            "Ritmo ajustado por pendiente": _format_speed_as_pace(summary.get("avgGradeAdjustedSpeed")),
        },
        "Frecuencia cardiaca": {
            "Frecuencia cardiaca media": _format_ppm(summary.get("averageHR")),
            "Frecuencia cardiaca máxima": _format_ppm(summary.get("maxHR")),
            "Frecuencia cardiaca mínima": _format_ppm(summary.get("minHR")),
            "Tiempo de las zonas": _format_zone_rows(bundle.get("hr_time_in_zones"), zone_type="hr"),
        },
        "Condición de rendimiento": {
            "Serie temporal disponible": "directPerformanceCondition" in (bundle.get("available_detail_metric_keys") or []),
        },
        "Longitud de zancada": {
            "Longitud de zancada media": _format_centimeters(summary.get("strideLength")),
        },
        "Cadencia de carrera": {
            "Cadencia de carrera media": _format_spm(summary.get("averageRunCadence")),
            "Cadencia de carrera máxima": _format_spm(summary.get("maxRunCadence")),
        },
        "Potencia: Vatios": {
            "Potencia media": _format_watts(summary.get("averagePower")),
            "Potencia máxima": _format_watts(summary.get("maxPower")),
            "Potencia normalizada": _format_watts(summary.get("normalizedPower")),
            "Trabajo total": summary.get("totalWork"),
            "Tiempo de las zonas": _format_zone_rows(bundle.get("power_time_in_zones"), zone_type="power"),
        },
        "Ratio vertical": {
            "Ratio vertical medio": _format_percent_plain(summary.get("verticalRatio")),
        },
        "Tiempo de contacto con el suelo": {
            "Tiempo de contacto con el suelo medio": _format_milliseconds(summary.get("groundContactTime")),
        },
        "Temperatura": {
            "Temperatura media": _format_celsius(summary.get("averageTemperature")),
            "Temperatura mínima": _format_celsius(summary.get("minTemperature")),
            "Temperatura máxima": _format_celsius(summary.get("maxTemperature")),
        },
        "Energía disponible": {
            "Energía disponible mínima": summary.get("minAvailableStamina"),
        },
        "Energía disponible potencial": {
            "Energía disponible potencial al inicio": summary.get("beginPotentialStamina"),
            "Energía disponible potencial al final": summary.get("endPotentialStamina"),
        },
        "Vueltas": _visible_laps_or_segments(bundle),
    }
    return _drop_none_deep(result)


def _visible_metrics_strength(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    raw_summary = _raw_summary_from_bundle(bundle)
    strength_summary = bundle.get("strength_summary") or {}

    moderate = summary.get("moderateIntensityMinutes")
    vigorous = summary.get("vigorousIntensityMinutes")
    intensity_total = _weighted_intensity_total(moderate, vigorous)

    total_time_s = summary.get("duration")
    active_time_s = strength_summary.get("active_time_s_estimated")
    rest_time_s = strength_summary.get("rest_time_s_estimated")

    total_calories = raw_summary.get("calories", summary.get("calories"))
    resting_calories = raw_summary.get("bmrCalories")
    active_calories = None
    try:
        if total_calories is not None and resting_calories is not None:
            active_calories = float(total_calories) - float(resting_calories)
    except Exception:
        active_calories = None

    result = {
        "Tiempo": {
            "Tiempo total": _seconds_to_hms(total_time_s),
            "Tiempo de trabajo": _seconds_to_hms(active_time_s),
            "Tiempo de descanso": _seconds_to_hms(rest_time_s),
        },
        "Efecto de entrenamiento": {
            "Beneficio principal": _training_label_es(summary.get("trainingEffectLabel")),
            "Aeróbica": summary.get("trainingEffect"),
            "Anaeróbica": summary.get("anaerobicTrainingEffect"),
            "Carga de ejercicio": round(float(summary.get("activityTrainingLoad")), 0) if summary.get("activityTrainingLoad") is not None else None,
        },
        "Frecuencia cardiaca": {
            "Frecuencia cardiaca media": _format_ppm(summary.get("averageHR")),
            "FC máxima": _format_ppm(summary.get("maxHR")),
            "Tiempo de las zonas": _format_zone_rows(bundle.get("hr_time_in_zones"), zone_type="hr"),
        },
        "Detalles de la sesión de entrenamiento": {
            "Repeticiones totales": round(float(strength_summary.get("total_reps_estimated")), 0) if strength_summary.get("total_reps_estimated") is not None else None,
            "Series totales": strength_summary.get("active_sets_count_estimated"),
            "Volumen": _format_kilograms(strength_summary.get("total_volume_kg_estimated")),
            "Peso máximo visto": _format_kilograms(strength_summary.get("max_weight_kg_seen")),
            "Bloques de trabajo": [
                {
                    "series": item.get("active_sets") or item.get("sets"),
                    "repeticiones": round(float(item.get("reps")), 0) if item.get("reps") is not None else None,
                    "peso máximo": _format_kilograms(item.get("max_weight_kg")),
                    "volumen": _format_kilograms(item.get("volume_kg")),
                }
                for item in (strength_summary.get("top_exercises") or [])
            ],
        },
        "Temperatura": {
            "Temperatura media": _format_celsius(summary.get("averageTemperature")),
            "Temperatura mínima": _format_celsius(summary.get("minTemperature")),
            "Temperatura máxima": _format_celsius(summary.get("maxTemperature")),
        },
        "Minutos de intensidad": {
            "Moderado": moderate,
            "Alta": vigorous,
            "Total": intensity_total,
        },
        "Body Battery": {
            "Impacto neto": summary.get("differenceBodyBattery"),
        },
        "Nutrición e hidratación": {
            "Calorías en reposo": resting_calories,
            "Calorías activas": active_calories,
            "Total de calorías quemadas": total_calories,
            "Pérdida estimada de líquidos": summary.get("waterEstimated"),
        },
    }
    return _drop_none_deep(result)


def _visible_metrics_cycling(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    return {
        "Altura": {
            "Altura media": summary.get("avgElevation"),
            "Altura máxima": summary.get("maxElevation"),
            "Altura mínima": summary.get("minElevation"),
            "Ascenso total": summary.get("elevationGain"),
            "Descenso total": summary.get("elevationLoss"),
        },
        "Velocidad": {
            "Velocidad media": summary.get("averageSpeed"),
            "Velocidad en movimiento": summary.get("averageMovingSpeed"),
            "Velocidad máxima": summary.get("maxSpeed"),
        },
        "Frecuencia cardiaca": {
            "Frecuencia cardiaca media": summary.get("averageHR"),
            "Frecuencia cardiaca máxima": summary.get("maxHR"),
            "Tiempo de las zonas": bundle.get("hr_time_in_zones"),
        },
        "Potencia: Vatios": {
            "Potencia media": summary.get("averagePower"),
            "Potencia máxima": summary.get("maxPower"),
            "Potencia normalizada": summary.get("normalizedPower"),
            "Trabajo total": summary.get("totalWork"),
            "Tiempo de las zonas": bundle.get("power_time_in_zones"),
        },
        "Temperatura": {
            "Temperatura media": summary.get("averageTemperature"),
            "Temperatura mínima": summary.get("minTemperature"),
            "Temperatura máxima": summary.get("maxTemperature"),
        },
    }


def _visible_metrics_swimming(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    return {
        "Ritmo": {
            "Ritmo medio": summary.get("averageSpeed"),
            "Ritmo máximo": summary.get("maxSpeed"),
        },
        "Frecuencia cardiaca": {
            "Frecuencia cardiaca media": summary.get("averageHR"),
            "Frecuencia cardiaca máxima": summary.get("maxHR"),
            "Tiempo de las zonas": bundle.get("hr_time_in_zones"),
        },
        "Carga": {
            "Carga de ejercicio": summary.get("activityTrainingLoad"),
            "Efecto de entrenamiento aeróbico": summary.get("trainingEffect"),
            "Efecto de entrenamiento anaeróbico": summary.get("anaerobicTrainingEffect"),
            "Beneficio principal": summary.get("trainingEffectLabel"),
        },
    }


def _format_km(value: Any) -> str | None:
    try:
        return f"{float(value)/1000.0:.2f} km"
    except Exception:
        return None


def _format_kmh(value: Any) -> str | None:
    try:
        return f"{float(value)*3.6:.1f} km/h"
    except Exception:
        return None


def _format_plain_minutes(value: Any) -> Any:
    try:
        return int(round(float(value)))
    except Exception:
        return value


def _get_first_typed_split_of_type(bundle: dict[str, Any], split_type: str) -> dict[str, Any] | None:
    typed = bundle.get("typed_splits")
    if not isinstance(typed, list):
        return None
    for item in typed:
        if not isinstance(item, dict):
            continue
        if str(item.get("splitType") or "").upper() == split_type.upper():
            return item
    return None


def _sum_typed_split_duration(bundle: dict[str, Any], split_type: str) -> float | None:
    typed = bundle.get("typed_splits")
    if not isinstance(typed, list):
        return None
    total = 0.0
    found = False
    for item in typed:
        if not isinstance(item, dict):
            continue
        if str(item.get("splitType") or "").upper() != split_type.upper():
            continue
        try:
            total += float(item.get("duration") or 0)
            found = True
        except Exception:
            pass
    return total if found else None


def _raw_activity_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    raw_payloads = bundle.get("raw_payloads") or {}
    activity_raw = raw_payloads.get("activity_raw") or {}
    return activity_raw if isinstance(activity_raw, dict) else {}


def _format_execution_score(raw_activity: dict[str, Any]) -> Any:
    for key in ("userProficiency", "executionScore", "skillLevel"):
        if raw_activity.get(key) is not None:
            return raw_activity.get(key)
    return None


def _visible_metrics_endurance_full(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    raw_summary = _raw_summary_from_bundle(bundle).get("summaryDTO") or {}
    raw_activity = _raw_activity_from_bundle(bundle)

    total_calories = raw_summary.get("calories", summary.get("calories"))
    resting_calories = raw_summary.get("bmrCalories")
    active_calories = None
    net_calories = None
    try:
        if total_calories is not None and resting_calories is not None:
            active_calories = float(total_calories) - float(resting_calories)
            net_calories = -float(total_calories)
    except Exception:
        pass

    liquid_loss = summary.get("waterEstimated")
    liquid_net = None
    try:
        if liquid_loss is not None:
            liquid_net = -float(liquid_loss)
    except Exception:
        pass

    moderate = summary.get("moderateIntensityMinutes")
    vigorous = summary.get("vigorousIntensityMinutes")
    intensity_total = _weighted_intensity_total(moderate, vigorous)

    running_time = _sum_typed_split_duration(bundle, "RUN")
    walking_time = _sum_typed_split_duration(bundle, "WALK")
    inactive_time = _sum_typed_split_duration(bundle, "INACTIVE")

    interval_run = _get_first_typed_split_of_type(bundle, "INTERVAL_ACTIVE")
    if interval_run is None:
        interval_run = _get_first_typed_split_of_type(bundle, "RUN")

    result = {
        "Distancia": {
            "Distancia": _format_km(summary.get("distance")),
        },
        "Nutrición e hidratación": {
            "Calorías en reposo": resting_calories,
            "Calorías activas": active_calories,
            "Total de calorías quemadas": total_calories,
            "Calorías consumidas": None,
            "Calorías netas": net_calories,
            "Pérdida estimada de líquidos": liquid_loss,
            "Líquido ingerido": None,
            "Líquido neto": liquid_net,
        },
        "Puntuación de ejecución": {
            "Puntuación": _format_execution_score(raw_activity),
        },
        "Autoevaluación": {
            "Cómo te has sentido": raw_activity.get("userFeedback") or raw_activity.get("feel") or raw_activity.get("perceivedExerciseFeedback"),
            "Nivel de esfuerzo percibido": raw_activity.get("perceivedExerciseIntensity") or raw_activity.get("rpe") or raw_activity.get("userRpe"),
        },
        "Energía disponible": {
            "Potencial inicial": summary.get("beginPotentialStamina"),
            "Potencial final": summary.get("endPotentialStamina"),
            "Energía disponible mín.": summary.get("minAvailableStamina"),
        },
        "Efecto de entrenamiento": {
            "Beneficio principal": _training_label_es(summary.get("trainingEffectLabel")),
            "Aeróbica": summary.get("trainingEffect"),
            "Anaeróbica": summary.get("anaerobicTrainingEffect"),
            "Carga de ejercicio": round(float(summary.get("activityTrainingLoad")), 0) if summary.get("activityTrainingLoad") is not None else None,
        },
        "Potencia": {
            "Potencia media": _format_watts(summary.get("averagePower")),
            "Potencia máxima": _format_watts(summary.get("maxPower")),
            "Datos del viento": "Activado" if raw_activity.get("metadataDTO", {}).get("hasRunPowerWindData") else "Desactivado",
        },
        "Altura": {
            "Ascenso total": _format_meters(summary.get("elevationGain")),
            "Descenso total": _format_meters(summary.get("elevationLoss")),
            "Altura mínima": _format_meters(summary.get("minElevation")),
            "Altura máxima": _format_meters(summary.get("maxElevation")),
        },
        "Frecuencia cardiaca": {
            "ppM": {
                "Frecuencia cardiaca media": _format_ppm(summary.get("averageHR")),
                "FC máxima": _format_ppm(summary.get("maxHR")),
            },
            "% de máxima": {
                "Frecuencia cardiaca media": None,
                "FC máxima": None,
            },
            "Zonas": _format_zone_rows(bundle.get("hr_time_in_zones"), zone_type="hr"),
        },
        "Tiempo": {
            "Tiempo": _seconds_to_hms(summary.get("duration")),
            "Tiempo en movimiento": _seconds_to_hms(summary.get("movingDuration")),
            "Tiempo transcurrido": _seconds_to_hms(summary.get("elapsedDuration")),
        },
        "Detección de carrera/caminar": {
            "Tiempo de carrera": _seconds_to_hms(running_time),
            "Tiempo de caminar": _seconds_to_hms(walking_time),
            "Tiempo de inactividad": _seconds_to_hms(inactive_time),
        },
        "Ritmo/velocidad": {
            "Ritmo": {
                "Ritmo medio": _format_speed_as_pace(summary.get("averageSpeed")),
                "Ritmo medio en movimiento": _format_speed_as_pace(summary.get("averageMovingSpeed")),
                "Ritmo óptimo": _format_speed_as_pace(summary.get("maxSpeed")),
                "Ritmo medio adaptado a la pendiente": _format_speed_as_pace(summary.get("avgGradeAdjustedSpeed")),
            },
            "Velocidad": {
                "Velocidad media": _format_kmh(summary.get("averageSpeed")),
                "Velocidad media en movimiento": _format_kmh(summary.get("averageMovingSpeed")),
                "Velocidad máxima": _format_kmh(summary.get("maxSpeed")),
                "Velocidad media adaptada a la pendiente": _format_kmh(summary.get("avgGradeAdjustedSpeed")),
            },
        },
        "Intervalos de entrenamiento": {
            "Tiempo: Carrera": _seconds_to_hms(interval_run.get("duration") if isinstance(interval_run, dict) else None),
            "Distancia: Carrera": _format_km(interval_run.get("distance") if isinstance(interval_run, dict) else None),
            "Carrera Ritmo": _format_speed_as_pace(interval_run.get("averageSpeed") if isinstance(interval_run, dict) else None),
        },
        "Dinámica de carrera": {
            "Cadencia de carrera media": _format_spm(summary.get("averageRunCadence")),
            "Cadencia de carrera máxima": _format_spm(summary.get("maxRunCadence")),
            "Longitud media de zancada": _format_centimeters(summary.get("strideLength")),
            "Relación vertical media": _format_percent_plain(summary.get("verticalRatio")),
            "Oscilación vertical media": _format_centimeters(summary.get("verticalOscillation")),
            "Tiempo medio de contacto con el suelo": _format_milliseconds(summary.get("groundContactTime")),
        },
        "Temperatura": {
            "Temperatura media": _format_celsius(summary.get("averageTemperature")),
            "Temperatura mínima": _format_celsius(summary.get("minTemperature")),
            "Temperatura máxima": _format_celsius(summary.get("maxTemperature")),
        },
        "Minutos de intensidad": {
            "Moderado": moderate,
            "Alta": vigorous,
            "Total": intensity_total,
        },
        "Body Battery": {
            "Impacto neto": summary.get("differenceBodyBattery"),
        },
        "Vueltas": _visible_laps_or_segments(bundle),
        "Zonas de potencia": _format_zone_rows(bundle.get("power_time_in_zones"), zone_type="power"),
    }

    return _drop_none_deep(result)


def _build_visible_metrics(bundle: dict[str, Any]) -> dict[str, Any]:
    family = bundle.get("activity_family")
    activity_type = bundle.get("activity_type")

    if family == "strength":
        return _visible_metrics_strength(bundle)
    if family == "cycling":
        return _visible_metrics_cycling(bundle)
    if family == "swimming":
        return _visible_metrics_swimming(bundle)
    if family == "endurance" or activity_type in {"running", "treadmill_running", "walking", "hiking", "cardio", "elliptical"}:
        return _visible_metrics_endurance_full(bundle)
    return {}


@mcp.tool
def get_activity_visible_profile(activity_id: str, include_time_series: bool = False, max_samples: int = 300) -> dict[str, Any]:
    """Perfil con nombres visibles estilo Garmin Connect según el tipo de actividad."""
    max_samples = max(1, min(2000, int(max_samples)))
    with FETCH_LOCK:
        api = _get_api()
        bundle = _fetch_activity_all_data(api, str(activity_id), include_time_series=include_time_series, max_samples=max_samples)
        return {
            "activity_id": bundle.get("activity_id"),
            "activity_name": bundle.get("activity_name"),
            "activity_type": bundle.get("activity_type"),
            "activity_family": bundle.get("activity_family"),
            "start_time_local": bundle.get("start_time_local"),
            "visible_metrics": _build_visible_metrics(bundle),
            "source_errors": bundle.get("source_errors"),
            "raw_payload_errors": bundle.get("raw_payload_errors"),
        }

# === MCPX VISIBLE METRICS PATCH END ===


# === MCPX HYBRID OVERVIEW TOOL START ===

def _num_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _round_or_none(value: Any, ndigits: int = 1) -> float | None:
    num = _num_or_none(value)
    if num is None:
        return None
    return round(num, ndigits)


def _duration_min_from_summary(summary: dict[str, Any]) -> float | None:
    if not isinstance(summary, dict):
        return None
    duration = _num_or_none(summary.get("duration"))
    if duration is None:
        return None
    return round(duration / 60.0, 1)


def _distance_km_from_summary(summary: dict[str, Any]) -> float | None:
    if not isinstance(summary, dict):
        return None
    distance = _num_or_none(summary.get("distance"))
    if distance is None:
        return None
    return round(distance / 1000.0, 2)


def _bundle_hybrid_session(bundle: dict[str, Any]) -> dict[str, Any]:
    summary = bundle.get("summary") or {}
    strength_summary = bundle.get("strength_summary") or {}

    return {
        "activity_id": bundle.get("activity_id"),
        "activity_name": bundle.get("activity_name"),
        "activity_type": bundle.get("activity_type"),
        "activity_family": bundle.get("activity_family"),
        "start_time_local": bundle.get("start_time_local"),
        "duration_min": _duration_min_from_summary(summary),
        "distance_km": _distance_km_from_summary(summary),
        "training_load": _round_or_none(summary.get("activityTrainingLoad"), 1),
        "training_effect_aerobic": _round_or_none(summary.get("trainingEffect"), 1),
        "training_effect_anaerobic": _round_or_none(summary.get("anaerobicTrainingEffect"), 1),
        "training_effect_label": summary.get("trainingEffectLabel"),
        "average_hr": _round_or_none(summary.get("averageHR"), 0),
        "max_hr": _round_or_none(summary.get("maxHR"), 0),
        "average_power": _round_or_none(summary.get("averagePower"), 0),
        "normalized_power": _round_or_none(summary.get("normalizedPower"), 0),
        "average_run_cadence": _round_or_none(summary.get("averageRunCadence"), 1),
        "ground_contact_time_ms": _round_or_none(summary.get("groundContactTime"), 1),
        "vertical_oscillation_cm": _round_or_none(summary.get("verticalOscillation"), 2),
        "vertical_ratio": _round_or_none(summary.get("verticalRatio"), 2),
        "stride_length_cm": _round_or_none(summary.get("strideLength"), 2),
        "stamina_begin": _round_or_none(summary.get("beginPotentialStamina"), 0),
        "stamina_end": _round_or_none(summary.get("endPotentialStamina"), 0),
        "stamina_min": _round_or_none(summary.get("minAvailableStamina"), 0),
        "moderate_intensity_minutes": _round_or_none(summary.get("moderateIntensityMinutes"), 0),
        "vigorous_intensity_minutes": _round_or_none(summary.get("vigorousIntensityMinutes"), 0),
        "exercise_set_count": bundle.get("exercise_set_count"),
        "active_sets_estimated": strength_summary.get("active_sets_count_estimated"),
        "total_reps_estimated": _round_or_none(strength_summary.get("total_reps_estimated"), 0),
        "total_volume_kg_estimated": _round_or_none(strength_summary.get("total_volume_kg_estimated"), 0),
        "max_weight_kg_seen": _round_or_none(strength_summary.get("max_weight_kg_seen"), 0),
        "source_errors": bundle.get("source_errors"),
    }


def _accumulate_type_totals(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, dict[str, Any]] = {}

    for item in sessions:
        activity_type = item.get("activity_type") or "unknown"
        row = by_type.setdefault(activity_type, {
            "activity_type": activity_type,
            "activity_family": item.get("activity_family"),
            "sessions": 0,
            "total_duration_min": 0.0,
            "total_distance_km": 0.0,
            "total_training_load": 0.0,
        })

        row["sessions"] += 1
        row["total_duration_min"] += float(item.get("duration_min") or 0.0)
        row["total_distance_km"] += float(item.get("distance_km") or 0.0)
        row["total_training_load"] += float(item.get("training_load") or 0.0)

    out = []
    for row in by_type.values():
        out.append({
            "activity_type": row["activity_type"],
            "activity_family": row["activity_family"],
            "sessions": row["sessions"],
            "total_duration_min": round(row["total_duration_min"], 1),
            "total_distance_km": round(row["total_distance_km"], 2),
            "total_training_load": round(row["total_training_load"], 1),
        })

    out.sort(key=lambda x: (-x["total_training_load"], x["activity_type"]))
    return {
        "by_type": out,
        "total_sessions": sum(x["sessions"] for x in out),
        "total_duration_min": round(sum(x["total_duration_min"] for x in out), 1),
        "total_distance_km": round(sum(x["total_distance_km"] for x in out), 2),
        "total_training_load": round(sum(x["total_training_load"] for x in out), 1),
    }


@mcp.tool
def get_hybrid_recent_overview(limit: int = 12) -> dict[str, Any]:
    """Resumen agregado reciente para entrenamiento híbrido usando actividades completas."""
    limit = max(1, min(20, int(limit)))

    with FETCH_LOCK:
        api = _get_api()
        activities, err = _optional_call_first(api, ("get_activities",), 0, limit)
        if activities is None:
            raise RuntimeError(err or "No pude leer las actividades recientes")

        bundles: list[dict[str, Any]] = []
        for activity in activities[:limit]:
            if not isinstance(activity, dict):
                continue
            activity_id = activity.get("activityId")
            if activity_id is None:
                continue
            bundles.append(_fetch_activity_bundle(api, str(activity_id), include_time_series=False))

    sessions = [_bundle_hybrid_session(bundle) for bundle in bundles]

    running_like = [x for x in sessions if x.get("activity_type") in {"running", "treadmill_running", "walking", "hiking", "cardio", "elliptical"}]
    strength = [x for x in sessions if x.get("activity_type") == "strength_training"]

    return {
        "overview": _accumulate_type_totals(sessions),
        "sessions": sessions,
        "running_like_sessions": running_like,
        "strength_sessions": strength,
    }

# === MCPX HYBRID OVERVIEW TOOL END ===


# === MCPX HYBRID COACH SNAPSHOT START ===

def _coach_num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _coach_round(value: Any, ndigits: int = 1) -> float | None:
    num = _coach_num(value)
    if num is None:
        return None
    return round(num, ndigits)


def _coach_pick_latest_by_type(sessions: list[dict[str, Any]], activity_type: str) -> dict[str, Any] | None:
    for item in sessions:
        if item.get("activity_type") == activity_type:
            return item
    return None


def _coach_pick_latest_running_like(sessions: list[dict[str, Any]]) -> dict[str, Any] | None:
    wanted = {"running", "treadmill_running", "walking", "hiking", "cardio", "elliptical"}
    for item in sessions:
        if item.get("activity_type") in wanted:
            return item
    return None


def _coach_first_present(d: dict[str, Any], *keys: str) -> Any:
    if not isinstance(d, dict):
        return None
    for key in keys:
        if d.get(key) is not None:
            return d.get(key)
    return None


def _coach_status_es(value: Any) -> Any:
    mapping = {
        "BALANCED": "Equilibrado",
        "LOW": "Bajo",
        "MODERATE": "Moderada",
        "HIGH": "Alto",
        "OPTIMAL": "Óptimo",
        "MAINTAINING": "Mantenimiento",
        "PRODUCTIVE": "Productivo",
        "RECOVERY": "Recuperación",
        "UNBALANCED": "Desequilibrado",
        "VO2MAX": "VO2 máximo",
        "LACTATE_THRESHOLD": "Umbral de lactato",
        "ANAEROBIC_CAPACITY": "Capacidad anaeróbica",
        "TEMPO": "Tempo",
        "AEROBIC_BASE": "Base aeróbica",
    }
    if value is None:
        return None
    return mapping.get(str(value), value)


def _coach_clean_session_fields(session: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(session, dict):
        return session

    out = dict(session)
    activity_type = out.get("activity_type")

    if activity_type != "strength_training":
        for key in [
            "exercise_set_count",
            "active_sets_estimated",
            "total_reps_estimated",
            "total_volume_kg_estimated",
            "max_weight_kg_seen",
        ]:
            if out.get(key) in (0, 0.0):
                out[key] = None

    if activity_type == "strength_training":
        for key in [
            "average_power",
            "normalized_power",
            "average_run_cadence",
            "ground_contact_time_ms",
            "vertical_oscillation_cm",
            "vertical_ratio",
            "stride_length_cm",
            "stamina_begin",
            "stamina_end",
            "stamina_min",
        ]:
            out[key] = None

    out["training_effect_label_es"] = _coach_status_es(out.get("training_effect_label"))
    return out


def _coach_build_takeaways(overview: dict[str, Any], day_metrics: dict[str, Any], latest_run: dict[str, Any] | None, latest_strength: dict[str, Any] | None) -> list[str]:
    tips: list[str] = []

    total_load = _coach_num((overview.get("overview") or {}).get("total_training_load"))
    if total_load is not None:
        tips.append(f"Carga reciente total: {round(total_load, 1)}")

    bb = _coach_num(day_metrics.get("body_battery_current"))
    readiness = _coach_num(day_metrics.get("training_readiness"))
    sleep_score = _coach_num(day_metrics.get("sleep_score"))
    hrv_last = _coach_num(day_metrics.get("hrv_last_night"))
    stress_avg = _coach_num(day_metrics.get("stress_avg"))

    if bb is not None:
        tips.append(f"Body Battery actual: {round(bb)}")
    if readiness is not None:
        tips.append(f"Predisposición para entrenar: {round(readiness)}")
    if sleep_score is not None:
        tips.append(f"Puntuación de sueño: {round(sleep_score)}")
    if hrv_last is not None:
        tips.append(f"VFC nocturna: {round(hrv_last)} ms")
    if stress_avg is not None:
        tips.append(f"Estrés medio diario: {round(stress_avg)}")

    if latest_run:
        run_load = latest_run.get("training_load")
        run_te = latest_run.get("training_effect_aerobic")
        run_gct = latest_run.get("ground_contact_time_ms")
        run_vr = latest_run.get("vertical_ratio")
        run_stamina_end = latest_run.get("stamina_end")
        run_type = latest_run.get("activity_type")
        if run_load is not None:
            tips.append(f"Última sesión endurance ({run_type}) carga: {run_load}")
        if run_te is not None:
            tips.append(f"Último TE aeróbico endurance: {run_te}")
        if run_gct is not None:
            tips.append(f"Último GCT endurance: {run_gct} ms")
        if run_vr is not None:
            tips.append(f"Último ratio vertical endurance: {run_vr}")
        if run_stamina_end is not None:
            tips.append(f"Energía disponible final de la última sesión endurance: {run_stamina_end}")

    if latest_strength:
        strength_load = latest_strength.get("training_load")
        reps = latest_strength.get("total_reps_estimated")
        volume = latest_strength.get("total_volume_kg_estimated")
        sets_ = latest_strength.get("active_sets_estimated")
        if strength_load is not None:
            tips.append(f"Última fuerza carga: {strength_load}")
        if sets_ is not None:
            tips.append(f"Última fuerza sets activos: {sets_}")
        if reps is not None:
            tips.append(f"Última fuerza repeticiones estimadas: {reps}")
        if volume is not None:
            tips.append(f"Última fuerza volumen estimado: {volume} kg")

    return tips


@mcp.tool
def get_hybrid_coach_snapshot(limit: int = 12, target_date: str | None = None) -> dict[str, Any]:
    """Resumen híbrido listo para coaching con carga reciente + contexto diario."""
    limit = max(1, min(20, int(limit)))

    if not target_date:
        target_date = date.today().isoformat()

    recent = get_hybrid_recent_overview(limit)
    sessions = recent.get("sessions") or []

    latest_run = _coach_pick_latest_running_like(sessions)
    latest_strength = _coach_pick_latest_by_type(sessions, "strength_training")

    try:
        daily = _collect_day_snapshot(target_date, include_recent_activities=False)
    except Exception as exc:
        daily = {
            "target_date": target_date,
            "metrics": {},
            "raw_sources": {},
            "error": str(exc),
        }

    metrics = daily.get("metrics") or {}

    daily_context = {
        "training_readiness": _coach_first_present(
            metrics,
            "training_readiness",
            "predisposicion_para_entrenar",
        ),
        "training_readiness_label": _coach_first_present(
            metrics,
            "training_readiness_label",
            "predisposicion_para_entrenar_estado",
        ),
        "sleep_score": _coach_first_present(metrics, "sleep_score"),
        "sleep_duration_h": _coach_first_present(metrics, "sleep_duration_h"),
        "hrv_last_night": _coach_first_present(metrics, "hrv_last_night"),
        "hrv_weekly_avg": _coach_first_present(metrics, "hrv_weekly_avg"),
        "body_battery_current": _coach_first_present(metrics, "body_battery_current", "body_battery_actual"),
        "body_battery_max": _coach_first_present(metrics, "body_battery_max"),
        "body_battery_min": _coach_first_present(metrics, "body_battery_min"),
        "resting_hr": _coach_first_present(metrics, "resting_hr"),
        "resting_hr_7d": _coach_first_present(metrics, "resting_hr_7d_avg", "resting_hr_7d"),
        "stress_avg": _coach_first_present(metrics, "stress_avg"),
        "stress_label": _coach_status_es(_coach_first_present(metrics, "stress_label")),
        "active_kcal": _coach_first_present(metrics, "active_kcal", "calorias_activas"),
        "total_kcal": _coach_first_present(metrics, "total_kcal", "calorias_totales"),
        "steps": _coach_first_present(metrics, "steps"),
        "distance_km": _coach_first_present(metrics, "distance_km"),
        "intensity_minutes_weekly": _coach_first_present(
            metrics,
            "intensity_minutes_weekly_total",
            "minutos_intensidad_total_semanal",
        ),
        "training_status": _coach_first_present(metrics, "training_status"),
        "training_status_es": _coach_first_present(metrics, "training_status_es"),
        "vo2max": _coach_first_present(metrics, "vo2max"),
        "vo2max_label": _coach_first_present(metrics, "vo2max_label"),
        "acute_load": _coach_first_present(metrics, "acute_load"),
        "acute_load_status": _coach_first_present(metrics, "acute_load_status"),
        "acute_load_status_es": _coach_first_present(metrics, "acute_load_status_es"),
    }

    result = {
        "target_date": target_date,
        "overview": recent.get("overview"),
        "latest_sessions": {
            "running_like": _coach_clean_session_fields(latest_run),
            "strength": _coach_clean_session_fields(latest_strength),
        },
        "daily_context": daily_context,
        "coach_takeaways": _coach_build_takeaways(
            recent,
            daily_context,
            _coach_clean_session_fields(latest_run),
            _coach_clean_session_fields(latest_strength),
        ),
    }

    return result

# === MCPX HYBRID COACH SNAPSHOT END ===


# === MCPX HYBRID COACH DECISION START ===

def _decision_num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _decision_pick_primary_driver(ctx: dict[str, Any], latest_run: dict[str, Any] | None, latest_strength: dict[str, Any] | None) -> str:
    readiness = _decision_num(ctx.get("training_readiness"))
    bb = _decision_num(ctx.get("body_battery_current"))
    sleep = _decision_num(ctx.get("sleep_score"))
    hrv = _decision_num(ctx.get("hrv_last_night"))
    acute = _decision_num(ctx.get("acute_load"))

    if readiness is not None and readiness <= 45:
        return "Predisposición para entrenar baja o moderada-baja"
    if bb is not None and bb <= 35:
        return "Body Battery bajo"
    if sleep is not None and sleep <= 65:
        return "Sueño mejorable"
    if latest_run and _decision_num(latest_run.get("training_load")) and _decision_num(latest_run.get("training_load")) >= 220:
        return "La última sesión endurance fue exigente"
    if latest_strength and _decision_num(latest_strength.get("training_load")) and _decision_num(latest_strength.get("training_load")) >= 60:
        return "La última sesión de fuerza dejó carga relevante"
    if acute is not None:
        return "Carga aguda reciente"
    if hrv is not None:
        return "Contexto de VFC reciente"
    return "Contexto general de recuperación"


def _decision_collect_reasons(ctx: dict[str, Any], latest_run: dict[str, Any] | None, latest_strength: dict[str, Any] | None) -> list[str]:
    reasons: list[str] = []

    readiness = _decision_num(ctx.get("training_readiness"))
    bb = _decision_num(ctx.get("body_battery_current"))
    sleep = _decision_num(ctx.get("sleep_score"))
    hrv = _decision_num(ctx.get("hrv_last_night"))
    stress = _decision_num(ctx.get("stress_avg"))
    acute = _decision_num(ctx.get("acute_load"))
    acute_status_es = ctx.get("acute_load_status_es")
    training_status_es = ctx.get("training_status_es")

    if readiness is not None:
        reasons.append(f"Predisposición para entrenar: {round(readiness)}")
    if bb is not None:
        reasons.append(f"Body Battery actual: {round(bb)}")
    if sleep is not None:
        reasons.append(f"Puntuación de sueño: {round(sleep)}")
    if hrv is not None:
        reasons.append(f"VFC nocturna: {round(hrv)} ms")
    if stress is not None:
        reasons.append(f"Estrés medio: {round(stress)}")
    if acute is not None:
        if acute_status_es:
            reasons.append(f"Carga aguda: {round(acute)} ({acute_status_es})")
        else:
            reasons.append(f"Carga aguda: {round(acute)}")
    if training_status_es:
        reasons.append(f"Estado de entreno: {training_status_es}")

    if latest_run:
        run_load = _decision_num(latest_run.get("training_load"))
        run_te = _decision_num(latest_run.get("training_effect_aerobic"))
        run_stamina_end = _decision_num(latest_run.get("stamina_end"))
        if run_load is not None:
            reasons.append(f"Última sesión endurance carga: {round(run_load, 1)}")
        if run_te is not None:
            reasons.append(f"Último TE aeróbico endurance: {round(run_te, 1)}")
        if run_stamina_end is not None:
            reasons.append(f"Energía disponible final endurance: {round(run_stamina_end)}")

    if latest_strength:
        strength_load = _decision_num(latest_strength.get("training_load"))
        sets_ = _decision_num(latest_strength.get("active_sets_estimated"))
        volume = _decision_num(latest_strength.get("total_volume_kg_estimated"))
        if strength_load is not None:
            reasons.append(f"Última fuerza carga: {round(strength_load, 1)}")
        if sets_ is not None:
            reasons.append(f"Última fuerza sets activos: {round(sets_)}")
        if volume is not None:
            reasons.append(f"Última fuerza volumen estimado: {round(volume)} kg")

    return reasons


def _decision_collect_risks(ctx: dict[str, Any], latest_run: dict[str, Any] | None, latest_strength: dict[str, Any] | None) -> list[str]:
    risks: list[str] = []

    readiness = _decision_num(ctx.get("training_readiness"))
    bb = _decision_num(ctx.get("body_battery_current"))
    sleep = _decision_num(ctx.get("sleep_score"))
    stress = _decision_num(ctx.get("stress_avg"))

    if readiness is not None and readiness <= 45:
        risks.append("La predisposición para entrenar no es alta.")
    if bb is not None and bb <= 35:
        risks.append("El Body Battery es bajo para meter calidad agresiva.")
    if sleep is not None and sleep <= 65:
        risks.append("El sueño no ha sido especialmente reparador.")
    if stress is not None and stress >= 40:
        risks.append("El estrés medio diario no es bajo.")

    if latest_run:
        gct = _decision_num(latest_run.get("ground_contact_time_ms"))
        vr = _decision_num(latest_run.get("vertical_ratio"))
        run_load = _decision_num(latest_run.get("training_load"))
        if run_load is not None and run_load >= 220:
            risks.append("La última sesión endurance dejó una carga alta.")
        if gct is not None and gct >= 295:
            risks.append("El tiempo de contacto con el suelo reciente es relativamente alto.")
        if vr is not None and vr >= 9.0:
            risks.append("La relación vertical reciente es exigente para sostener más intensidad.")

    if latest_strength:
        sets_ = _decision_num(latest_strength.get("active_sets_estimated"))
        volume = _decision_num(latest_strength.get("total_volume_kg_estimated"))
        if sets_ is not None and sets_ >= 18:
            risks.append("La última sesión de fuerza tuvo bastante volumen de trabajo.")
        if volume is not None and volume >= 10000:
            risks.append("El volumen total de fuerza reciente es alto.")

    return risks


def _decision_level(ctx: dict[str, Any], latest_run: dict[str, Any] | None, latest_strength: dict[str, Any] | None) -> tuple[str, str, str]:
    readiness = _decision_num(ctx.get("training_readiness"))
    bb = _decision_num(ctx.get("body_battery_current"))
    sleep = _decision_num(ctx.get("sleep_score"))

    latest_run_load = _decision_num((latest_run or {}).get("training_load"))
    latest_strength_load = _decision_num((latest_strength or {}).get("training_load"))

    if (readiness is not None and readiness <= 45) or (bb is not None and bb <= 28) or (sleep is not None and sleep <= 50):
        return (
            "descanso_recuperacion",
            "Descanso o recuperación",
            "Hoy priorizaría recuperación, movilidad o paseo suave."
        )

    if (
        (readiness is not None and readiness <= 60)
        or (bb is not None and bb <= 45)
        or (sleep is not None and sleep <= 65)
        or (latest_run_load is not None and latest_run_load >= 220)
        or (latest_strength_load is not None and latest_strength_load >= 60)
    ):
        return (
            "suave_controlado",
            "Día suave o controlado",
            "Hoy encaja mejor una sesión suave, técnica o trabajo aeróbico controlado."
        )

    return (
        "intensidad_controlada",
        "Intensidad controlada",
        "Hoy podrías meter calidad, pero con control de volumen y sin encadenar fatiga innecesaria."
    )


def _decision_recommendation_text(level_key: str, latest_run: dict[str, Any] | None, latest_strength: dict[str, Any] | None) -> str:
    if level_key == "descanso_recuperacion":
        return (
            "Haz descanso, movilidad o paseo muy suave de 20-40 min. "
            "Nada de calidad ni fuerza dura."
        )

    if level_key == "suave_controlado":
        if latest_run and latest_strength:
            return (
                "Haz endurance suave en Z2 real 30-45 min o una fuerza ligera/técnica recortando volumen. "
                "Evita combinar fuerza pesada con trabajo intenso de carrera."
            )
        return (
            "Haz una sesión suave y controlada, priorizando técnica, base aeróbica o fuerza ligera."
        )

    return (
        "Puedes hacer una sesión de calidad controlada. "
        "Mejor una sola pieza principal: tempo/umbral en cinta o carrera, o fuerza principal con volumen contenido."
    )


@mcp.tool
def get_hybrid_coach_decision(limit: int = 12, target_date: str | None = None) -> dict[str, Any]:
    """Devuelve una decisión diaria lista para entrenador a partir del snapshot híbrido."""
    snap = get_hybrid_coach_snapshot(limit=limit, target_date=target_date)

    ctx = snap.get("daily_context") or {}
    latest = snap.get("latest_sessions") or {}
    latest_run = latest.get("running_like")
    latest_strength = latest.get("strength")

    level_key, level_title, summary_text = _decision_level(ctx, latest_run, latest_strength)

    result = {
        "target_date": snap.get("target_date"),
        "decision": {
            "level_key": level_key,
            "level_title": level_title,
            "summary": summary_text,
            "primary_driver": _decision_pick_primary_driver(ctx, latest_run, latest_strength),
            "recommended_action": _decision_recommendation_text(level_key, latest_run, latest_strength),
        },
        "reasons": _decision_collect_reasons(ctx, latest_run, latest_strength),
        "risks": _decision_collect_risks(ctx, latest_run, latest_strength),
        "daily_context": ctx,
        "latest_sessions": latest,
        "overview": snap.get("overview"),
    }

    return result

# === MCPX HYBRID COACH DECISION END ===


# === MCPX HYBRID USER BRIEFING START ===

def _brief_num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _brief_int(value: Any) -> int | None:
    num = _brief_num(value)
    if num is None:
        return None
    return int(round(num))


def _brief_primary_message(decision: dict[str, Any], ctx: dict[str, Any]) -> str:
    title = decision.get("level_title") or "Día sin clasificar"
    readiness = _brief_int(ctx.get("training_readiness"))
    bb = _brief_int(ctx.get("body_battery_current"))
    sleep = _brief_int(ctx.get("sleep_score"))

    parts = [title]
    if readiness is not None:
        parts.append(f"predisposición {readiness}")
    if bb is not None:
        parts.append(f"Body Battery {bb}")
    if sleep is not None:
        parts.append(f"sueño {sleep}")
    return " · ".join(parts)


def _brief_plan(decision: dict[str, Any], ctx: dict[str, Any], latest_run: dict[str, Any] | None, latest_strength: dict[str, Any] | None) -> dict[str, Any]:
    level_key = decision.get("level_key")
    acute = _brief_int(ctx.get("acute_load"))
    acute_es = ctx.get("acute_load_status_es")
    latest_run_load = _brief_num((latest_run or {}).get("training_load"))
    latest_strength_load = _brief_num((latest_strength or {}).get("training_load"))

    if level_key == "descanso_recuperacion":
        return {
            "tipo": "recuperación",
            "objetivo": "bajar fatiga y facilitar recuperación",
            "duracion_recomendada_min": "20-40",
            "intensidad": "muy suave",
            "sesion_sugerida": "movilidad, paseo suave o descanso completo",
            "detalle": [
                "Nada de series ni fuerza dura.",
                "Si haces algo, que sea fácil de cortar y sin perseguir métricas.",
                "Prioriza llegar fresco a mañana."
            ],
            "contexto_carga": f"Carga aguda {acute} ({acute_es})" if acute is not None and acute_es else acute,
        }

    if level_key == "suave_controlado":
        sesion = "endurance suave en Z2 real 30-45 min"
        if latest_run_load is not None and latest_run_load >= 220:
            sesion = "rodaje muy controlado o cinta suave 30-40 min"
        elif latest_strength_load is not None and latest_strength_load >= 60:
            sesion = "fuerza técnica ligera o endurance suave sin meter calidad"

        return {
            "tipo": "suave_controlado",
            "objetivo": "sumar trabajo útil sin añadir fatiga innecesaria",
            "duracion_recomendada_min": "30-45",
            "intensidad": "suave / controlada",
            "sesion_sugerida": sesion,
            "detalle": [
                "Mantén margen respiratorio claro.",
                "No conviertas una sesión suave en una sesión media.",
                "Mejor una sola pieza principal y terminar con sensación de reserva."
            ],
            "contexto_carga": f"Carga aguda {acute} ({acute_es})" if acute is not None and acute_es else acute,
        }

    return {
        "tipo": "intensidad_controlada",
        "objetivo": "aprovechar el día sin desbordar la recuperación",
        "duracion_recomendada_min": "35-60",
        "intensidad": "calidad controlada",
        "sesion_sugerida": "tempo/umbral controlado o fuerza principal con volumen contenido",
        "detalle": [
            "Haz una sola parte exigente.",
            "Controla el volumen más que la intensidad pico.",
            "No mezcles fuerza pesada con una carrera dura el mismo día."
        ],
        "contexto_carga": f"Carga aguda {acute} ({acute_es})" if acute is not None and acute_es else acute,
    }


def _brief_avoid_list(decision: dict[str, Any], latest_run: dict[str, Any] | None, latest_strength: dict[str, Any] | None) -> list[str]:
    level_key = decision.get("level_key")
    out: list[str] = []

    if level_key == "descanso_recuperacion":
        out.extend([
            "series intensas",
            "fuerza pesada",
            "doble sesión",
        ])
    elif level_key == "suave_controlado":
        out.extend([
            "encadenar fuerza pesada con carrera intensa",
            "rodaje que se te vaya a Z4-Z5",
            "más volumen del previsto por sensaciones de inicio",
        ])
    else:
        out.extend([
            "hacer dos sesiones duras en el mismo día",
            "alargar volumen por encima de lo planificado",
        ])

    run_load = _brief_num((latest_run or {}).get("training_load"))
    if run_load is not None and run_load >= 220:
        out.append("repetir otra sesión endurance muy exigente demasiado pronto")

    strength_vol = _brief_num((latest_strength or {}).get("total_volume_kg_estimated"))
    if strength_vol is not None and strength_vol >= 10000:
        out.append("meter otra fuerza de mucho volumen sin recorte")

    dedup = []
    seen = set()
    for item in out:
        if item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup


def _brief_nutrition_recovery(decision: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    level_key = decision.get("level_key")
    bb = _brief_int(ctx.get("body_battery_current"))
    sleep = _brief_int(ctx.get("sleep_score"))
    active_kcal = _brief_int(ctx.get("active_kcal"))

    if level_key == "descanso_recuperacion":
        return {
            "pre": "Comida normal y estable, sin necesidad de cargar hidratos de forma agresiva.",
            "post": "Prioriza proteína suficiente y una comida completa si haces movilidad o paseo.",
            "hidratacion": "Bebe de forma regular durante el día; no hace falta estrategia agresiva.",
            "sueno": "Prioridad alta a dormir antes y mejor.",
            "nota": f"Body Battery {bb}" if bb is not None else None,
        }

    if level_key == "suave_controlado":
        return {
            "pre": "Llega con algo de energía disponible; evita entrenar vacío si la sesión cae en una franja larga.",
            "post": "Proteína + hidrato moderado tras la sesión para recuperar sin castigar el sueño.",
            "hidratacion": "Rehidrata de forma simple y constante; si sudas mucho, mete sodio.",
            "sueno": "Hoy el sueño es un objetivo del plan, no un detalle.",
            "nota": f"Sueño {sleep} / kcal activas {active_kcal}" if sleep is not None or active_kcal is not None else None,
        }

    return {
        "pre": "Llega alimentado y sin ayunos largos si vas a meter calidad.",
        "post": "Proteína + hidratos dentro de la primera hora si la sesión ha sido seria.",
        "hidratacion": "Rehidrata y repón sales si la sesión es larga o calurosa.",
        "sueno": "Protege el sueño para consolidar la carga.",
        "nota": f"Body Battery {bb} · sueño {sleep}" if bb is not None or sleep is not None else None,
    }


@mcp.tool
def get_hybrid_user_briefing(limit: int = 12, target_date: str | None = None) -> dict[str, Any]:
    """Resumen listo para usuario final: qué toca hoy, por qué, qué evitar y cómo recuperar."""
    decision_pack = get_hybrid_coach_decision(limit=limit, target_date=target_date)

    decision = decision_pack.get("decision") or {}
    ctx = decision_pack.get("daily_context") or {}
    latest = decision_pack.get("latest_sessions") or {}
    latest_run = latest.get("running_like")
    latest_strength = latest.get("strength")

    return {
        "target_date": decision_pack.get("target_date"),
        "mensaje_principal": _brief_primary_message(decision, ctx),
        "que_toca_hoy": _brief_plan(decision, ctx, latest_run, latest_strength),
        "por_que": decision_pack.get("reasons") or [],
        "riesgos_a_vigilar": decision_pack.get("risks") or [],
        "evitar_hoy": _brief_avoid_list(decision, latest_run, latest_strength),
        "nutricion_y_recuperacion": _brief_nutrition_recovery(decision, ctx),
        "driver_principal": decision.get("primary_driver"),
        "accion_recomendada": decision.get("recommended_action"),
        "resumen_decision": decision.get("summary"),
    }

# === MCPX HYBRID USER BRIEFING END ===


# === MCPX HYBRID NUTRITION BRIEFING START ===

def _nutrition_num(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _nutrition_int(value: Any) -> int | None:
    num = _nutrition_num(value)
    if num is None:
        return None
    return int(round(num))


def _nutrition_reference_for_activity(activity_id: Any) -> dict[str, Any] | None:
    if not activity_id:
        return None
    try:
        full = get_activity_full(str(activity_id), include_time_series=False)
    except Exception:
        return None

    summary = full.get("summary") or {}
    return {
        "activity_id": str(activity_id),
        "water_estimated_ml": _nutrition_int(summary.get("waterEstimated")),
        "calories_total": _nutrition_int(summary.get("calories")),
        "duration_min": round(float(summary.get("duration") or 0) / 60.0, 1) if summary.get("duration") is not None else None,
        "training_load": _nutrition_num(summary.get("activityTrainingLoad")),
        "activity_type": full.get("activity_type"),
        "activity_name": full.get("activity_name"),
    }


def _nutrition_focus(decision: dict[str, Any], ctx: dict[str, Any], latest_strength: dict[str, Any] | None) -> str:
    level_key = decision.get("level_key")
    bb = _nutrition_int(ctx.get("body_battery_current"))
    sleep = _nutrition_int(ctx.get("sleep_score"))
    strength_volume = _nutrition_num((latest_strength or {}).get("total_volume_kg_estimated"))

    if level_key == "descanso_recuperacion":
        return "recuperación y sueño"
    if strength_volume is not None and strength_volume >= 10000:
        return "recuperación muscular + recarga moderada"
    if (bb is not None and bb <= 40) or (sleep is not None and sleep <= 65):
        return "disponibilidad energética estable y recuperación"
    return "energía útil para entrenar sin pasarte"


def _nutrition_pre_training(decision: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    level_key = decision.get("level_key")
    bb = _nutrition_int(ctx.get("body_battery_current"))
    sleep = _nutrition_int(ctx.get("sleep_score"))

    if level_key == "descanso_recuperacion":
        return {
            "objetivo": "llegar estable al día sin buscar una carga agresiva",
            "recomendacion": "Haz una comida normal y completa. No hace falta estrategia específica preentreno si solo haces movilidad o paseo.",
            "ejemplos": [
                "yogur o queso fresco + fruta",
                "tostadas con jamón, pavo o huevos",
                "comida normal con arroz/patata y proteína"
            ],
        }

    if level_key == "suave_controlado":
        extra = "Evita entrenar completamente vacío." if (bb is not None and bb <= 40) or (sleep is not None and sleep <= 65) else "No necesitas una carga alta de hidratos."
        return {
            "objetivo": "tener energía disponible sin pesadez",
            "recomendacion": "Si entrenas tras muchas horas sin comer, mete 20-40 g de hidratos y algo fácil de digerir 30-90 min antes.",
            "ejemplos": [
                "plátano + yogur",
                "tostada con miel o mermelada",
                "fruta + batido o vaso de leche"
            ],
            "nota": extra,
        }

    return {
        "objetivo": "llegar con glucógeno disponible para calidad",
        "recomendacion": "Mete 30-60 g de hidratos 1-3 h antes y evita ayunos largos si la sesión va a ser exigente.",
        "ejemplos": [
            "arroz o avena + proteína ligera",
            "pan o tostadas + fruta",
            "yogur + cereales + fruta"
        ],
    }


def _nutrition_post_training(decision: dict[str, Any], latest_run_ref: dict[str, Any] | None, latest_strength_ref: dict[str, Any] | None) -> dict[str, Any]:
    level_key = decision.get("level_key")

    if level_key == "descanso_recuperacion":
        return {
            "objetivo": "recuperar sin sobrecompensar",
            "recomendacion": "Con una comida completa rica en proteína y vegetales suele bastar si el trabajo es muy suave.",
            "ejemplos": [
                "tortilla o pollo con patata/arroz",
                "yogur alto en proteína + fruta",
                "legumbre + proteína + verduras"
            ],
        }

    if level_key == "suave_controlado":
        note = None
        if latest_run_ref and latest_run_ref.get("water_estimated_ml"):
            note = f"Tu última sesión endurance estimó {latest_run_ref['water_estimated_ml']} ml de pérdida."
        return {
            "objetivo": "recuperar sin castigar el sueño ni meter déficit",
            "recomendacion": "Después entrena con 25-35 g de proteína y 30-60 g de hidratos si la sesión finalmente tiene algo de volumen.",
            "ejemplos": [
                "batido o yogur alto en proteína + fruta + cereales",
                "arroz/patata/pan + pollo, atún o huevos",
                "queso fresco batido + fruta + avena"
            ],
            "nota": note,
        }

    note = None
    if latest_strength_ref and latest_strength_ref.get("calories_total"):
        note = f"La última fuerza gastó ~{latest_strength_ref['calories_total']} kcal totales."
    return {
        "objetivo": "reponer glucógeno y facilitar recuperación",
        "recomendacion": "Después de calidad prioriza 25-40 g de proteína y 60-90 g de hidratos dentro de la primera hora o en la comida siguiente.",
        "ejemplos": [
            "arroz/pasta/patata + proteína magra",
            "batido + fruta + pan o cereales",
            "comida completa con hidrato principal y proteína suficiente"
        ],
        "nota": note,
    }


def _nutrition_hydration(decision: dict[str, Any], latest_run_ref: dict[str, Any] | None, latest_strength_ref: dict[str, Any] | None) -> dict[str, Any]:
    level_key = decision.get("level_key")

    refs = []
    for item in (latest_run_ref, latest_strength_ref):
        if isinstance(item, dict) and item.get("water_estimated_ml") is not None:
            refs.append(int(item["water_estimated_ml"]))

    ref_text = None
    if refs:
        ref_text = f"Pérdidas recientes estimadas: {max(refs)} ml en una sesión."

    if level_key == "descanso_recuperacion":
        return {
            "recomendacion": "Hidrátate de forma estable durante el día. No hace falta estrategia agresiva.",
            "sodio": "Útil si sudas mucho o vienes de días de calor.",
            "referencia": ref_text,
        }

    if level_key == "suave_controlado":
        return {
            "recomendacion": "Suma agua de forma constante antes y después. Si sudas bastante, añade sodio o una bebida con sales.",
            "sodio": "Moderado-alto si la sesión se alarga o hace calor.",
            "referencia": ref_text,
        }

    return {
        "recomendacion": "Llega bien hidratado y repón agua + sodio después, especialmente si hay calor o sudor alto.",
        "sodio": "Recomendable si la sesión es exigente o larga.",
        "referencia": ref_text,
    }


def _nutrition_avoid_today(decision: dict[str, Any], ctx: dict[str, Any]) -> list[str]:
    level_key = decision.get("level_key")
    bb = _nutrition_int(ctx.get("body_battery_current"))
    sleep = _nutrition_int(ctx.get("sleep_score"))

    out = []

    if level_key in {"descanso_recuperacion", "suave_controlado"}:
        out.append("entrenar en ayunas si llegas vacío o con poca energía")
        out.append("recortar demasiado hidratos y luego pedirle calidad al cuerpo")

    out.append("hacer una sesión mejor de lo planificado y no comer después")
    out.append("dejar la hidratación para el final del día")

    if bb is not None and bb <= 40:
        out.append("acumular déficit energético con Body Battery bajo")
    if sleep is not None and sleep <= 65:
        out.append("cenar pobre en proteína o hidratos tras un día ya tocado por el sueño")

    dedup = []
    seen = set()
    for item in out:
        if item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup


def _nutrition_reasoning(ctx: dict[str, Any], latest_run: dict[str, Any] | None, latest_strength: dict[str, Any] | None) -> list[str]:
    out = []

    readiness = _nutrition_int(ctx.get("training_readiness"))
    bb = _nutrition_int(ctx.get("body_battery_current"))
    sleep = _nutrition_int(ctx.get("sleep_score"))
    active_kcal = _nutrition_int(ctx.get("active_kcal"))
    weekly_intensity = _nutrition_int(ctx.get("intensity_minutes_weekly"))

    if readiness is not None:
        out.append(f"Predisposición para entrenar {readiness}")
    if bb is not None:
        out.append(f"Body Battery {bb}")
    if sleep is not None:
        out.append(f"Sueño {sleep}")
    if active_kcal is not None:
        out.append(f"Calorías activas del día {active_kcal}")
    if weekly_intensity is not None:
        out.append(f"Minutos de intensidad semanales {weekly_intensity}")

    if latest_run and latest_run.get("training_load") is not None:
        out.append(f"Última sesión endurance carga {latest_run['training_load']}")
    if latest_strength and latest_strength.get("total_volume_kg_estimated") is not None:
        out.append(f"Última fuerza volumen {int(round(float(latest_strength['total_volume_kg_estimated'])))} kg")

    return out


@mcp.tool
def get_hybrid_nutrition_briefing(limit: int = 12, target_date: str | None = None) -> dict[str, Any]:
    """Plan nutricional diario práctico usando la decisión híbrida y el contexto reciente."""
    decision_pack = get_hybrid_coach_decision(limit=limit, target_date=target_date)

    decision = decision_pack.get("decision") or {}
    ctx = decision_pack.get("daily_context") or {}
    latest = decision_pack.get("latest_sessions") or {}
    latest_run = latest.get("running_like")
    latest_strength = latest.get("strength")

    latest_run_ref = _nutrition_reference_for_activity((latest_run or {}).get("activity_id"))
    latest_strength_ref = _nutrition_reference_for_activity((latest_strength or {}).get("activity_id"))

    return {
        "target_date": decision_pack.get("target_date"),
        "foco_nutricional": _nutrition_focus(decision, ctx, latest_strength),
        "antes_de_entrenar": _nutrition_pre_training(decision, ctx),
        "despues_de_entrenar": _nutrition_post_training(decision, latest_run_ref, latest_strength_ref),
        "hidratacion": _nutrition_hydration(decision, latest_run_ref, latest_strength_ref),
        "evitar_hoy": _nutrition_avoid_today(decision, ctx),
        "por_que": _nutrition_reasoning(ctx, latest_run, latest_strength),
        "decision_base": {
            "driver_principal": decision.get("primary_driver"),
            "accion_recomendada": decision.get("recommended_action"),
            "resumen_decision": decision.get("summary"),
        }
    }

# === MCPX HYBRID NUTRITION BRIEFING END ===


# === HISTORICAL DATA TOOLS START ===

_HISTORY_MAX_ACTIVITIES_PER_PAGE = 100
_HISTORY_MAX_WELLNESS_DAYS = 30
_HISTORY_SLEEP_BETWEEN_DAYS_S = 0.35


def _compact_activity_for_history(activity: dict) -> dict:
    """Normalización compacta optimizada para listas históricas largas."""
    activity_type = (
        activity.get("activityType") or activity.get("activityTypeDTO") or {}
    )
    type_key = activity_type.get("typeKey")
    summary = activity.get("summaryDTO") or {}

    duration_s = activity.get("duration") or summary.get("duration")
    distance_m = activity.get("distance") or summary.get("distance")

    return {
        "activity_id": activity.get("activityId"),
        "name": activity.get("activityName"),
        "type": type_key,
        "type_es": _ACTIVITY_TYPE_ES.get(type_key, type_key) if type_key else None,
        "activity_family": _activity_family(type_key),
        "start_time_local": (
            activity.get("startTimeLocal") or summary.get("startTimeLocal")
        ),
        "duration_min": round(float(duration_s) / 60, 1) if duration_s is not None else None,
        "distance_km": round(float(distance_m) / 1000, 2) if distance_m is not None else None,
        "avg_hr": activity.get("averageHR") or summary.get("averageHR"),
        "max_hr": activity.get("maxHR") or summary.get("maxHR"),
        "calories": activity.get("calories") or summary.get("calories"),
        "training_load": (
            activity.get("activityTrainingLoad")
            or activity.get("trainingLoad")
            or summary.get("activityTrainingLoad")
        ),
        "elevation_gain_m": activity.get("elevationGain") or summary.get("elevationGain"),
        "training_effect": summary.get("trainingEffect"),
    }


@mcp.tool
def get_activities_paged(limit: int = 100, offset: int = 0) -> dict:
    """Acceso paginado a todo el historial de actividades Garmin.
    limit máximo 100. Usa offset en múltiplos de limit para navegar el historial completo.
    Ejemplo: offset=0 primeras 100, offset=100 siguientes 100, etc.
    has_more=true indica que hay más actividades disponibles.
    """
    limit = max(1, min(_HISTORY_MAX_ACTIVITIES_PER_PAGE, int(limit)))
    offset = max(0, int(offset))

    with FETCH_LOCK:
        api = _get_api()
        activities, err = _optional_call_first(api, ("get_activities",), offset, limit)

    if activities is None:
        raise RuntimeError(err or "No pude leer el historial de actividades")

    if not isinstance(activities, list):
        activities = []

    normalized = [
        _compact_activity_for_history(a)
        for a in activities
        if isinstance(a, dict)
    ]

    return {
        "offset": offset,
        "limit": limit,
        "count": len(normalized),
        "has_more": len(normalized) == limit,
        "next_offset": offset + len(normalized),
        "activities": normalized,
    }


@mcp.tool
def get_activities_in_range(
    start_date: str,
    end_date: str = None,
    activity_type: str = None,
) -> dict:
    """Actividades entre dos fechas (formato YYYY-MM-DD).
    activity_type es opcional: running, strength_training, cycling, etc.
    Sin end_date usa hoy. Lista ordenada de más reciente a más antigua.
    Para rangos muy amplios (más de 1 año) prefiere get_activities_paged con paginación.
    """
    start = _parse_date(start_date)
    end = _parse_date(end_date) if end_date else _today_local().isoformat()

    if start > end:
        start, end = end, start

    with FETCH_LOCK:
        api = _get_api()
        if activity_type:
            activities, err = _optional_call_first(
                api, ("get_activities_by_date",), start, end, activity_type
            )
        else:
            activities, err = _optional_call_first(
                api, ("get_activities_by_date",), start, end
            )

    if activities is None:
        raise RuntimeError(err or f"No pude leer actividades entre {start} y {end}")

    if not isinstance(activities, list):
        activities = []

    normalized = [
        _compact_activity_for_history(a)
        for a in activities
        if isinstance(a, dict)
    ]
    normalized.sort(key=lambda x: x.get("start_time_local") or "", reverse=True)

    return {
        "start_date": start,
        "end_date": end,
        "activity_type_filter": activity_type,
        "count": len(normalized),
        "activities": normalized,
    }


def _compact_wellness_for_range(api, target_date: str) -> dict:
    """Snapshot wellness ligero para una fecha.
    No usa FETCH_LOCK ni llama a _get_api() — debe invocarse con api ya obtenido.
    """
    summary, _ = _optional_call_first(
        api, ("get_user_summary", "get_stats"), target_date
    )
    sleep, _ = _optional_call_first(api, ("get_sleep_data",), target_date)
    hrv, _ = _optional_call_first(api, ("get_hrv_data",), target_date)

    sm = summary or {}
    sleep_dto = ((sleep or {}).get("dailySleepDTO")) or {}
    hrv_summary = ((hrv or {}).get("hrvSummary")) or {}

    sleep_score = None
    try:
        sleep_score = sleep_dto["sleepScores"]["overall"]["value"]
    except Exception:
        pass

    sleep_seconds = sleep_dto.get("sleepTimeSeconds")
    distance_m = sm.get("totalDistanceMeters")

    return {
        "date": target_date,
        "steps": sm.get("totalSteps"),
        "distance_km": round(float(distance_m) / 1000, 2) if distance_m is not None else None,
        "active_kcal": sm.get("activeKilocalories"),
        "total_kcal": sm.get("totalKilocalories"),
        "resting_hr": _resting_hr(summary),
        "stress_avg": sm.get("averageStressLevel"),
        "stress_label": sm.get("stressQualifier"),
        "body_battery_high": sm.get("bodyBatteryHighestValue"),
        "body_battery_low": sm.get("bodyBatteryLowestValue"),
        "body_battery_end": sm.get("bodyBatteryMostRecentValue"),
        "sleep_score": sleep_score,
        "sleep_hours": round(float(sleep_seconds) / 3600, 1) if sleep_seconds is not None else None,
        "hrv_last_night": hrv_summary.get("lastNightAvg"),
        "hrv_status": hrv_summary.get("status"),
    }


@mcp.tool
def get_daily_wellness(target_date: str) -> dict:
    """Obtiene métricas completas de un día específico.
    Incluye: pasos, distancia, calorías, FC en reposo, estrés, Body Battery, VFC y más.
    Formato de fecha: YYYY-MM-DD (ejemplo: 2017-06-15)
    """
    parsed_date = _parse_date(target_date)
    return _collect_day_snapshot(parsed_date, include_recent_activities=False)


@mcp.tool
def get_wellness_range(
    start_date: str,
    end_date: str = None,
) -> dict:
    """Resumen wellness diario compacto para un rango de fechas.
    Incluye pasos, distancia, calorías, FC en reposo, estrés, Body Battery, sueño y VFC.
    Máximo 30 días por llamada. Para periodos mayores llama varias veces desplazando start_date.
    Ejemplo 3 meses: llamada 1 start=2025-01-01 end=2025-01-30,
                     llamada 2 start=2025-01-31 end=2025-03-01, etc.
    """
    start_dt = date.fromisoformat(_parse_date(start_date))
    end_dt = date.fromisoformat(
        _parse_date(end_date) if end_date else _today_local().isoformat()
    )

    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    total_days = (end_dt - start_dt).days + 1
    clipped = total_days > _HISTORY_MAX_WELLNESS_DAYS
    if clipped:
        end_dt = start_dt + timedelta(days=_HISTORY_MAX_WELLNESS_DAYS - 1)
        total_days = _HISTORY_MAX_WELLNESS_DAYS

    with FETCH_LOCK:
        api = _get_api()

    days_data = []
    errors = []

    for i in range(total_days):
        target = (start_dt + timedelta(days=i)).isoformat()
        try:
            with FETCH_LOCK:
                day = _compact_wellness_for_range(api, target)
            days_data.append(day)
        except Exception as exc:
            errors.append({"date": target, "error": str(exc)})
        if i < total_days - 1:
            time.sleep(_HISTORY_SLEEP_BETWEEN_DAYS_S)

    return {
        "start_date": start_dt.isoformat(),
        "end_date": end_dt.isoformat(),
        "days_requested": total_days,
        "days_returned": len(days_data),
        "clipped_to_max": clipped,
        "max_days_per_call": _HISTORY_MAX_WELLNESS_DAYS,
        "note": (
            f"Rango recortado a {_HISTORY_MAX_WELLNESS_DAYS} dias. "
            f"Llama de nuevo con start_date={end_dt.isoformat()} para continuar."
        ) if clipped else None,
        "days": days_data,
        "errors": errors if errors else None,
    }


@mcp.tool
def get_race_predictions(
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """Predicciones de tiempo de carrera de Garmin para 5K, 10K, media maratón y maratón.
    Sin fechas devuelve las predicciones actuales.
    Formato fechas: YYYY-MM-DD.
    """
    sd = _parse_date(start_date) if start_date else None
    ed = _parse_date(end_date) if end_date else None

    with FETCH_LOCK:
        api = _get_api()
        if sd and ed:
            data, err = _optional_call_first(api, ("get_race_predictions",), sd, ed)
        else:
            data, err = _optional_call_first(api, ("get_race_predictions",))

    if data is None:
        raise RuntimeError(err or "No se pudieron obtener predicciones de carrera")

    return {"race_predictions": data, "start_date": sd, "end_date": ed}


@mcp.tool
def get_personal_records() -> dict:
    """Récords personales del usuario por distancia y tipo de actividad.
    Incluye mejores tiempos en carrera, ciclismo y otros deportes registrados en Garmin.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_personal_record", "get_personal_records"))

    if data is None:
        raise RuntimeError(err or "No se pudieron obtener los récords personales")

    return {"personal_records": data}


@mcp.tool
def get_fitness_age(target_date: str = None) -> dict:
    """Edad física (Fitness Age) calculada por Garmin.
    Compara tu condición física con tu edad cronológica.
    Formato fecha: YYYY-MM-DD (por defecto hoy).
    """
    parsed = _parse_date(target_date)

    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(
            api, ("get_fitnessage_data", "get_fitness_age"), parsed
        )

    if data is None:
        raise RuntimeError(err or "No se pudo obtener la edad física")

    return {"fitness_age_data": data, "date": parsed}


@mcp.tool
def get_endurance_score(
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """Puntuación de resistencia aeróbica (Endurance Score) de Garmin.
    Rango de fechas para ver la evolución. Sin fechas usa los últimos 28 días.
    Formato: YYYY-MM-DD.
    """
    ed = _parse_date(end_date) if end_date else _today_local().isoformat()
    sd = _parse_date(start_date) if start_date else (
        date.fromisoformat(ed) - timedelta(days=27)
    ).isoformat()

    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_endurance_score",), sd, ed)

    if data is None:
        raise RuntimeError(err or "No se pudo obtener el Endurance Score")

    return {"endurance_score": data, "start_date": sd, "end_date": ed}


@mcp.tool
def get_hill_score(
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """Puntuación de rendimiento en montaña/desnivel (Hill Score) de Garmin.
    Evalúa tu capacidad en subidas. Sin fechas usa los últimos 28 días.
    Formato: YYYY-MM-DD.
    """
    ed = _parse_date(end_date) if end_date else _today_local().isoformat()
    sd = _parse_date(start_date) if start_date else (
        date.fromisoformat(ed) - timedelta(days=27)
    ).isoformat()

    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_hill_score",), sd, ed)

    if data is None:
        raise RuntimeError(err or "No se pudo obtener el Hill Score")

    return {"hill_score": data, "start_date": sd, "end_date": ed}


@mcp.tool
def get_goals(status: str = "active") -> dict:
    """Objetivos de entrenamiento del usuario en Garmin Connect.
    status: 'active' (activos), 'future' (futuros) o 'past' (pasados).
    """
    if status not in ("active", "future", "past"):
        status = "active"

    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_goals",), status, 1, 50)

    if data is None:
        raise RuntimeError(err or "No se pudieron obtener los objetivos")

    return {"goals": data, "status_filter": status}


@mcp.tool
def get_gear(include_stats: bool = True) -> dict:
    """Material deportivo registrado en Garmin (zapatillas, bicicletas, etc.) con kilometraje y estadísticas.
    include_stats=True añade actividades y distancias acumuladas por cada pieza de material.
    """
    with FETCH_LOCK:
        api = _get_api()
        profile, _ = _optional_call_first(api, ("get_user_profile",))
        profile_number = None
        if isinstance(profile, dict):
            profile_number = (
                (profile.get("userData") or {}).get("profileNumber")
                or (profile.get("userData") or {}).get("id")
                or profile.get("profileNumber")
                or profile.get("id")
            )

        if profile_number is None:
            raise RuntimeError("No se pudo obtener el número de perfil de usuario")

        gear_list, err = _optional_call_first(api, ("get_gear",), profile_number)

        if gear_list is None:
            raise RuntimeError(err or "No se pudo obtener el material deportivo")

        if include_stats and isinstance(gear_list, list):
            for item in gear_list:
                uuid = item.get("uuid") or item.get("gearPk")
                if uuid:
                    stats, _ = _optional_call_first(api, ("get_gear_stats",), uuid)
                    if stats is not None:
                        item["stats"] = stats

    return {"gear": gear_list, "profile_number": profile_number}


@mcp.tool
def get_activity_evaluation(activity_id: str) -> dict:
    """Evaluación de entrenador virtual de Garmin para una actividad específica.
    Incluye retroalimentación sobre el rendimiento, esfuerzo y consejos de recuperación.
    activity_id: identificador numérico de la actividad.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_activity_evaluation",), activity_id)

    if data is None:
        raise RuntimeError(err or f"No se pudo obtener la evaluación de la actividad {activity_id}")

    return {"activity_id": activity_id, "evaluation": data}


@mcp.tool
def get_weigh_ins(
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """Historial de pesajes registrados en Garmin Connect.
    Sin fechas devuelve los últimos 30 días. Formato: YYYY-MM-DD.
    """
    ed = _parse_date(end_date) if end_date else _today_local().isoformat()
    sd = _parse_date(start_date) if start_date else (
        date.fromisoformat(ed) - timedelta(days=29)
    ).isoformat()

    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_weigh_ins",), sd, ed)

    if data is None:
        raise RuntimeError(err or "No se pudieron obtener los pesajes")

    return {"weigh_ins": data, "start_date": sd, "end_date": ed}


@mcp.tool
def add_weigh_in(
    weight_kg: float,
    target_date: str = None,
) -> dict:
    """Registra un nuevo pesaje en Garmin Connect.
    weight_kg: peso en kilogramos (puede ser decimal, ej: 75.5).
    target_date: fecha en formato YYYY-MM-DD (por defecto hoy).
    """
    parsed = _parse_date(target_date) if target_date else _today_local().isoformat()
    weight_int = round(weight_kg * 1000)

    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(
            api, ("add_weigh_in",), weight_int, "kg", parsed
        )

    if data is None:
        raise RuntimeError(err or "No se pudo registrar el pesaje")

    return {"ok": True, "weight_kg": weight_kg, "date": parsed, "response": data}


# === EXTRA API TOOLS START ===

@mcp.tool
def get_activity_splits(activity_id: str) -> dict:
    """Splits kilométricos/por milla detallados de una actividad.
    Incluye ritmo, FC, distancia y tiempo por cada split.
    activity_id: identificador numérico de la actividad.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_activity_splits",), activity_id)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener los splits de {activity_id}")
    return {"activity_id": activity_id, "splits": data}


@mcp.tool
def get_activity_split_summaries(activity_id: str) -> dict:
    """Resumen de splits de una actividad (por fase o segmento).
    Complementa get_activity_splits con totales por bloque.
    activity_id: identificador numérico de la actividad.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_activity_split_summaries",), activity_id)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener los resúmenes de splits de {activity_id}")
    return {"activity_id": activity_id, "split_summaries": data}


@mcp.tool
def get_activity_hr_in_timezones(activity_id: str) -> dict:
    """Distribución del tiempo por zona de frecuencia cardíaca en una actividad.
    Muestra cuánto tiempo se pasó en cada zona Z1-Z5.
    activity_id: identificador numérico de la actividad.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_activity_hr_in_timezones",), activity_id)
    if data is None:
        raise RuntimeError(err or f"No se pudo obtener la distribución de FC por zonas de {activity_id}")
    return {"activity_id": activity_id, "hr_in_timezones": data}


@mcp.tool
def get_activity_exercise_sets(activity_id: str) -> dict:
    """Series de ejercicios de un entrenamiento de fuerza.
    Incluye nombre del ejercicio, series, repeticiones, peso y duración.
    activity_id: identificador numérico de la actividad.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_activity_exercise_sets",), activity_id)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener los ejercicios de {activity_id}")
    return {"activity_id": activity_id, "exercise_sets": data}


@mcp.tool
def get_activity_weather(activity_id: str) -> dict:
    """Condiciones meteorológicas durante una actividad.
    Incluye temperatura, humedad, viento y condición general.
    activity_id: identificador numérico de la actividad.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_activity_weather",), activity_id)
    if data is None:
        raise RuntimeError(err or f"No se pudo obtener el tiempo meteorológico de {activity_id}")
    return {"activity_id": activity_id, "weather": data}


@mcp.tool
def get_activity_gear(activity_id: str) -> dict:
    """Material deportivo utilizado en una actividad concreta.
    Útil para saber qué zapatillas o bicicleta se usó en cada entreno.
    activity_id: identificador numérico de la actividad.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_activity_gear",), activity_id)
    if data is None:
        raise RuntimeError(err or f"No se pudo obtener el material de {activity_id}")
    return {"activity_id": activity_id, "gear": data}


@mcp.tool
def get_last_activity() -> dict:
    """Última actividad registrada en Garmin Connect.
    Acceso rápido sin necesidad de conocer el activity_id.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_last_activity",))
    if data is None:
        raise RuntimeError(err or "No se pudo obtener la última actividad")
    return {"last_activity": data}


@mcp.tool
def get_activity_types() -> dict:
    """Lista de todos los tipos de actividad disponibles en Garmin Connect.
    Útil para conocer los valores válidos del filtro activity_type.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_activity_types",))
    if data is None:
        raise RuntimeError(err or "No se pudieron obtener los tipos de actividad")
    return {"activity_types": data}


@mcp.tool
def get_all_day_stress(target_date: str = None) -> dict:
    """Curva de estrés minuto a minuto durante todo el día.
    Permite ver picos y valles de estrés a lo largo del día.
    Formato fecha: YYYY-MM-DD (por defecto hoy).
    """
    parsed = _parse_date(target_date)
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_all_day_stress",), parsed)
    if data is None:
        raise RuntimeError(err or f"No se pudo obtener el estrés del día {parsed}")
    return {"date": parsed, "all_day_stress": data}


@mcp.tool
def get_steps_data(target_date: str = None) -> dict:
    """Serie temporal de pasos a lo largo del día (intervalos de 15 min).
    Permite ver la distribución de actividad durante el día.
    Formato fecha: YYYY-MM-DD (por defecto hoy).
    """
    parsed = _parse_date(target_date)
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_steps_data",), parsed)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener los pasos de {parsed}")
    return {"date": parsed, "steps_data": data}


@mcp.tool
def get_daily_steps(
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """Pasos diarios totales en un rango de fechas.
    Sin fechas usa los últimos 7 días. Formato: YYYY-MM-DD.
    """
    ed = _parse_date(end_date) if end_date else _today_local().isoformat()
    sd = _parse_date(start_date) if start_date else (
        date.fromisoformat(ed) - timedelta(days=6)
    ).isoformat()
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_daily_steps",), sd, ed)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener los pasos diarios entre {sd} y {ed}")
    return {"start_date": sd, "end_date": ed, "daily_steps": data}


@mcp.tool
def get_floors(target_date: str = None) -> dict:
    """Pisos subidos y bajados durante el día.
    Formato fecha: YYYY-MM-DD (por defecto hoy).
    """
    parsed = _parse_date(target_date)
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_floors", "get_floors_data"), parsed)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener los pisos de {parsed}")
    return {"date": parsed, "floors": data}


@mcp.tool
def get_blood_pressure(
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """Registros de presión arterial en un rango de fechas.
    Solo disponible si el dispositivo o la app registra tensión arterial.
    Sin fechas usa los últimos 7 días. Formato: YYYY-MM-DD.
    """
    ed = _parse_date(end_date) if end_date else _today_local().isoformat()
    sd = _parse_date(start_date) if start_date else (
        date.fromisoformat(ed) - timedelta(days=6)
    ).isoformat()
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(
            api, ("get_blood_pressure", "get_blood_pressure_data"), sd, ed
        )
    if data is None:
        raise RuntimeError(err or "No se pudo obtener la presión arterial")
    return {"start_date": sd, "end_date": ed, "blood_pressure": data}


@mcp.tool
def get_stats_and_body(target_date: str = None) -> dict:
    """Resumen combinado de actividad diaria y composición corporal.
    Combina pasos, calorías, distancia y peso en una sola llamada.
    Formato fecha: YYYY-MM-DD (por defecto hoy).
    """
    parsed = _parse_date(target_date)
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_stats_and_body",), parsed)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener stats+cuerpo de {parsed}")
    return {"date": parsed, "stats_and_body": data}


@mcp.tool
def get_progress_summary(
    start_date: str = None,
    end_date: str = None,
    metric: str = "distance",
) -> dict:
    """Progresión de una métrica entre dos fechas.
    metric: 'distance' (distancia), 'duration' (tiempo), 'elevationGain' (desnivel),
            'movingDuration', 'calories', 'bmrCalories', 'steps'.
    Sin fechas usa los últimos 30 días. Formato: YYYY-MM-DD.
    """
    ed = _parse_date(end_date) if end_date else _today_local().isoformat()
    sd = _parse_date(start_date) if start_date else (
        date.fromisoformat(ed) - timedelta(days=29)
    ).isoformat()
    valid = {"distance","duration","elevationGain","movingDuration","calories","bmrCalories","steps"}
    if metric not in valid:
        metric = "distance"
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(
            api, ("get_progress_summary_between_dates",), sd, ed, metric
        )
    if data is None:
        raise RuntimeError(err or f"No se pudo obtener el progreso de {metric}")
    return {"start_date": sd, "end_date": ed, "metric": metric, "progress": data}


@mcp.tool
def get_earned_badges() -> dict:
    """Insignias y logros conseguidos en Garmin Connect.
    Muestra todos los badges desbloqueados hasta la fecha.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_earned_badges",))
    if data is None:
        raise RuntimeError(err or "No se pudieron obtener las insignias")
    return {"earned_badges": data}


@mcp.tool
def get_badge_challenges(start: int = 1, limit: int = 20) -> dict:
    """Retos de insignias activos en Garmin Connect.
    start: índice inicial (paginación). limit: máximo de resultados.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_badge_challenges",), start, limit)
    if data is None:
        raise RuntimeError(err or "No se pudieron obtener los retos de insignias")
    return {"start": start, "limit": limit, "badge_challenges": data}


@mcp.tool
def get_adhoc_challenges(start: int = 1, limit: int = 20) -> dict:
    """Retos espontáneos activos en Garmin Connect.
    start: índice inicial (paginación). limit: máximo de resultados.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_adhoc_challenges",), start, limit)
    if data is None:
        raise RuntimeError(err or "No se pudieron obtener los retos espontáneos")
    return {"start": start, "limit": limit, "adhoc_challenges": data}


@mcp.tool
def get_available_badge_challenges(start: int = 1, limit: int = 20) -> dict:
    """Retos de insignias disponibles para unirse en Garmin Connect.
    start: índice inicial (paginación). limit: máximo de resultados.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_available_badge_challenges",), start, limit)
    if data is None:
        raise RuntimeError(err or "No se pudieron obtener los retos disponibles")
    return {"start": start, "limit": limit, "available_challenges": data}


@mcp.tool
def get_device_last_used() -> dict:
    """Información del último dispositivo Garmin utilizado para sincronizar.
    Incluye modelo, firmware y fecha de última conexión.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_device_last_used",))
    if data is None:
        raise RuntimeError(err or "No se pudo obtener el último dispositivo usado")
    return {"device_last_used": data}


@mcp.tool
def get_gear_stats(gear_uuid: str) -> dict:
    """Estadísticas de uso de una pieza de material concreto (zapatillas, bicicleta…).
    Devuelve actividades totales, distancia acumulada y tiempo de uso.
    gear_uuid: identificador UUID del material (obtenible con get_gear).
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_gear_stats",), gear_uuid)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener las estadísticas del material {gear_uuid}")
    return {"gear_uuid": gear_uuid, "stats": data}


@mcp.tool
def get_gear_defaults() -> dict:
    """Material por defecto asignado a cada tipo de actividad (correr, ciclismo, etc.).
    Útil para saber qué zapatilla o bici tiene Garmin asignada por defecto en cada deporte.
    """
    with FETCH_LOCK:
        api = _get_api()
        profile, _ = _optional_call_first(api, ("get_user_profile",))
        profile_number = None
        if isinstance(profile, dict):
            profile_number = (
                (profile.get("userData") or {}).get("profileNumber")
                or (profile.get("userData") or {}).get("id")
                or profile.get("profileNumber")
                or profile.get("id")
            )
        if profile_number is None:
            raise RuntimeError("No se pudo obtener el número de perfil de usuario")
        data, err = _optional_call_first(api, ("get_gear_defaults",), profile_number)
    if data is None:
        raise RuntimeError(err or "No se pudieron obtener los materiales por defecto")
    return {"profile_number": profile_number, "gear_defaults": data}


@mcp.tool
def get_daily_weigh_ins(target_date: str = None) -> dict:
    """Todos los pesajes registrados en un día concreto.
    Útil cuando hay varios registros en el mismo día.
    Formato fecha: YYYY-MM-DD (por defecto hoy).
    """
    parsed = _parse_date(target_date)
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_daily_weigh_ins",), parsed)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener los pesajes del día {parsed}")
    return {"date": parsed, "daily_weigh_ins": data}


@mcp.tool
def get_inprogress_virtual_challenges(start: int = 1, limit: int = 20) -> dict:
    """Retos virtuales en curso en Garmin Connect (por ejemplo Garmin Challenges de km).
    start: índice inicial (paginación). limit: máximo de resultados.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_inprogress_virtual_challenges",), start, limit)
    if data is None:
        raise RuntimeError(err or "No se pudieron obtener los retos virtuales en curso")
    return {"start": start, "limit": limit, "inprogress_virtual_challenges": data}


@mcp.tool
def get_non_completed_badge_challenges(start: int = 1, limit: int = 20) -> dict:
    """Retos de insignias que aún no se han completado.
    Complementa get_badge_challenges mostrando los pendientes.
    start: índice inicial (paginación). limit: máximo de resultados.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_non_completed_badge_challenges",), start, limit)
    if data is None:
        raise RuntimeError(err or "No se pudieron obtener los retos de insignias pendientes")
    return {"start": start, "limit": limit, "non_completed_badge_challenges": data}


@mcp.tool
def get_device_alarms() -> dict:
    """Alarmas configuradas en los dispositivos Garmin vinculados a la cuenta.
    Devuelve las alarmas activas y sus configuraciones.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_device_alarms",))
    if data is None:
        raise RuntimeError(err or "No se pudieron obtener las alarmas del dispositivo")
    return {"device_alarms": data}


@mcp.tool
def get_user_profile_info() -> dict:
    """Información básica del perfil de usuario: nombre completo y sistema de unidades.
    Útil para saber si Garmin trabaja en km/kg o millas/libras.
    """
    with FETCH_LOCK:
        api = _get_api()
        full_name, name_err = _optional_call_first(api, ("get_full_name",))
        unit_system, unit_err = _optional_call_first(api, ("get_unit_system",))
    return {
        "full_name": full_name,
        "unit_system": unit_system,
        "errors": {k: v for k, v in {"name": name_err, "units": unit_err}.items() if v},
    }


@mcp.tool
def delete_weigh_in(weight_pk: str, target_date: str) -> dict:
    """Elimina un pesaje concreto por su clave primaria.
    weight_pk: identificador del pesaje (campo weightPk de get_weigh_ins o get_daily_weigh_ins).
    target_date: fecha del pesaje en formato YYYY-MM-DD.
    """
    parsed = _parse_date(target_date)
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("delete_weigh_in",), weight_pk, parsed)
    if data is None and err:
        raise RuntimeError(err)
    return {"ok": True, "weight_pk": weight_pk, "date": parsed, "response": data}


@mcp.tool
def delete_weigh_ins(target_date: str, delete_all: bool = False) -> dict:
    """Elimina los pesajes de una fecha concreta.
    delete_all=True elimina todos los registros del día; False elimina solo el más reciente.
    target_date: fecha en formato YYYY-MM-DD.
    """
    parsed = _parse_date(target_date)
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("delete_weigh_ins",), parsed, delete_all)
    if data is None and err:
        raise RuntimeError(err)
    return {"ok": True, "date": parsed, "delete_all": delete_all, "response": data}


@mcp.tool
def set_gear_default(activity_type: str, gear_uuid: str, is_default: bool = True) -> dict:
    """Asigna (o desasigna) una pieza de material como predeterminada para un tipo de actividad.
    activity_type: tipo de actividad Garmin (p.ej. 'running', 'cycling').
    gear_uuid: UUID del material (obtenible con get_gear).
    is_default: True para asignar como predeterminado, False para quitar esa asignación.
    """
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("set_gear_default",), activity_type, gear_uuid, is_default)
    if data is None and err:
        raise RuntimeError(err)
    return {"ok": True, "activity_type": activity_type, "gear_uuid": gear_uuid, "is_default": is_default, "response": data}


@mcp.tool
def get_spo2_data(target_date: str = None) -> dict:
    """Datos de oximetría de pulso (SpO2) del día.
    Muestra el nivel de saturación de oxígeno en sangre registrado por el sensor del reloj.
    Formato fecha: YYYY-MM-DD (por defecto hoy).
    """
    parsed = _parse_date(target_date)
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_spo2_data", "get_pulse_ox_data"), parsed)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener los datos de SpO2 del día {parsed}")
    return {"date": parsed, "spo2": data}


@mcp.tool
def get_respiration_data(target_date: str = None) -> dict:
    """Frecuencia respiratoria registrada durante el día y el sueño.
    Útil para detectar tendencias de recuperación y estado de forma aeróbica.
    Formato fecha: YYYY-MM-DD (por defecto hoy).
    """
    parsed = _parse_date(target_date)
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_respiration_data",), parsed)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener los datos de respiración del día {parsed}")
    return {"date": parsed, "respiration": data}


@mcp.tool
def get_hydration_data(target_date: str = None) -> dict:
    """Registro de hidratación del día (vasos de agua u oz registrados manualmente).
    Muestra el objetivo diario y el progreso hasta ese momento.
    Formato fecha: YYYY-MM-DD (por defecto hoy).
    """
    parsed = _parse_date(target_date)
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(api, ("get_hydration_data",), parsed)
    if data is None:
        raise RuntimeError(err or f"No se pudieron obtener los datos de hidratación del día {parsed}")
    return {"date": parsed, "hydration": data}


@mcp.tool
def get_body_composition(
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """Composición corporal en un rango de fechas: peso, IMC y porcentaje de grasa.
    Sin fechas devuelve los últimos 30 días. Formato: YYYY-MM-DD.
    """
    ed = _parse_date(end_date) if end_date else _today_local().isoformat()
    sd = _parse_date(start_date) if start_date else (
        date.fromisoformat(ed) - timedelta(days=29)
    ).isoformat()
    with FETCH_LOCK:
        api = _get_api()
        data, err = _optional_call_first(
            api, ("get_body_composition", "get_weight_data"), sd, ed
        )
    if data is None:
        raise RuntimeError(err or "No se pudo obtener la composición corporal")
    return {"start_date": sd, "end_date": ed, "body_composition": data}

# === EXTRA API TOOLS END ===

# === HISTORICAL DATA TOOLS END ===

if __name__ == "__main__":
    _run_server()


# === FRONTEND GARMIN CONNECT ES OUTPUT PATCH START ===
_FRONTEND_EXTRA_ES_INSTRUCTIONS = (
    " Para cualquier respuesta visible para el usuario, prioriza siempre salida_frontend_es, resumen_frontend_es y metricas_frontend_es."
    " No cites ni reutilices raw_sources, códigos internos, type keys ni estados en inglés salvo que el usuario pida expresamente el dato bruto."
    " Usa exactamente el vocabulario visible de Garmin Connect en español: Body Battery, Predisposición para entrenar, Estado de VFC, Puntuación de sueño, Carga aguda, Estado de entreno, Tiempo de recuperación, Calorías, Pasos, Minutos de intensidad, Pisos y Estrés."
    " NUNCA escribas 'HRV', 'RHR', 'Training Readiness', 'Training Effect' ni 'Stamina' en la respuesta: usa 'VFC', 'FC en reposo', 'Predisposición para entrenar', 'Efecto de entrenamiento' y 'Energía disponible'."
    " Para actividades, prioriza get_activity_visible_profile y visible_metrics frente a herramientas crudas."
)
try:
    _existing_instructions = getattr(mcp, "instructions", None)
    if isinstance(_existing_instructions, str) and _FRONTEND_EXTRA_ES_INSTRUCTIONS not in _existing_instructions:
        mcp.instructions = _existing_instructions + _FRONTEND_EXTRA_ES_INSTRUCTIONS
except Exception:
    pass

_ACTIVITY_TYPE_ES = {
    "running": "Correr",
    "treadmill_running": "Correr en cinta",
    "walking": "Caminar",
    "hiking": "Senderismo",
    "trail_running": "Trail running",
    "track_running": "Carrera en pista",
    "cycling": "Ciclismo",
    "road_biking": "Ciclismo en carretera",
    "indoor_cycling": "Ciclismo indoor",
    "mountain_biking": "Ciclismo de montaña",
    "virtual_ride": "Ciclismo virtual",
    "strength_training": "Fuerza",
    "cardio": "Cardio",
    "elliptical": "Elíptica",
    "pool_swimming": "Natación en piscina",
    "open_water_swimming": "Natación en aguas abiertas",
    "swimming": "Natación",
}

_ACTIVITY_FAMILY_ES = {
    "endurance": "Resistencia",
    "cycling": "Ciclismo",
    "strength": "Fuerza",
    "swimming": "Natación",
}


def _frontend_non_empty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _frontend_pick(metrics: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = metrics.get(key)
        if _frontend_non_empty(value):
            return value
    return None


def _frontend_compact_dict(items: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, value in items:
        if _frontend_non_empty(value):
            out[label] = value
    return out


def _build_metricas_frontend_es(metrics: dict[str, Any]) -> dict[str, Any]:
    return _frontend_compact_dict([
        ("Body Battery", _frontend_pick(metrics, "body_battery_actual", "body_battery_current")),
        ("Resumen de Body Battery", _frontend_pick(metrics, "body_battery_resumen_humano", "body_battery_texto")),
        ("Predisposición para entrenar", _frontend_pick(metrics, "predisposicion_para_entrenar", "training_readiness_score")),
        ("Estado de Predisposición para entrenar", _frontend_pick(metrics, "predisposicion_para_entrenar_estado", "training_readiness_status_es", "training_readiness_status")),
        ("Resumen de Predisposición para entrenar", _frontend_pick(metrics, "predisposicion_para_entrenar_texto", "predisposicion_factores_resumen_humano")),
        ("Estado de VFC", _frontend_pick(metrics, "estado_vfc", "hrv_status_es", "hrv_status")),
        ("Resumen de VFC", _frontend_pick(metrics, "estado_vfc_resumen_humano")),
        ("Puntuación de sueño", _frontend_pick(metrics, "puntuacion_de_sueno", "sleep_score")),
        ("Duración del sueño", _frontend_pick(metrics, "duracion_de_sueno_texto")),
        ("Resumen de sueño", _frontend_pick(metrics, "sueno_resumen_para_llm", "sueno_resumen_humano", "sueno_texto_seguro")),
        ("Fases del sueño", _frontend_pick(metrics, "sueno_fases_para_llm", "sueno_fases_resumen_humano")),
        ("Tiempo de recuperación", _frontend_pick(metrics, "recuperacion_texto_seguro", "training_readiness_recovery_answer_for_llm", "training_readiness_recovery_safe_text")),
        ("Carga aguda", _frontend_pick(metrics, "acute_load")),
        ("Estado de carga aguda", _frontend_pick(metrics, "acute_load_status_es", "acute_load_status")),
        ("Estado de entreno", _frontend_pick(metrics, "training_status_es", "training_status")),
        ("Resumen de estado de entreno", _frontend_pick(metrics, "estado_entreno_resumen_humano")),
        ("VO2 máximo", _frontend_pick(metrics, "vo2max")),
        ("Pasos", _frontend_pick(metrics, "steps")),
        ("Resumen de pasos", _frontend_pick(metrics, "pasos_resumen_humano")),
        ("Calorías", _frontend_pick(metrics, "calorias_resumen_humano", "total_kcal")),
        ("Minutos de intensidad", _frontend_pick(metrics, "minutos_intensidad_resumen_humano")),
        ("Estrés", _frontend_pick(metrics, "estres_resumen_humano", "stress_avg")),
        ("Última sincronización", _frontend_pick(metrics, "snapshot_obtenido_local")),
        ("Datos disponibles hasta", _frontend_pick(metrics, "datos_hasta_local")),
    ])


def _build_resumen_frontend_es(metrics: dict[str, Any]) -> list[str]:
    lines: list[str] = []

    for key in (
        "body_battery_resumen_humano",
        "predisposicion_factores_resumen_humano",
        "sueno_resumen_para_llm",
        "estado_entreno_resumen_humano",
        "estres_resumen_humano",
        "pasos_resumen_humano",
        "calorias_resumen_humano",
        "minutos_intensidad_resumen_humano",
    ):
        value = metrics.get(key)
        if _frontend_non_empty(value) and value not in lines:
            lines.append(str(value))

    if not lines:
        metricas = _build_metricas_frontend_es(metrics)
        for label, value in metricas.items():
            lines.append(f"{label}: {value}")
            if len(lines) >= 8:
                break

    return lines


def _attach_frontend_view_to_snapshot(snap: Any) -> Any:
    if not isinstance(snap, dict):
        return snap

    metrics = snap.setdefault("metrics", {})
    if not isinstance(metrics, dict):
        return snap

    replacements = {
        "stress_label": metrics.get("stress_label_es"),
        "hrv_status": _frontend_pick(metrics, "estado_vfc", "hrv_status_es"),
        "training_readiness_status": _frontend_pick(metrics, "predisposicion_para_entrenar_estado", "training_readiness_status_es"),
        "training_readiness_message": _frontend_pick(metrics, "predisposicion_para_entrenar_texto", "training_readiness_message_es"),
        "acute_load_status": metrics.get("acute_load_status_es"),
        "training_status": _frontend_pick(metrics, "training_status_es", "estado_entreno_resumen_humano"),
    }
    for base_key, value in replacements.items():
        if _frontend_non_empty(value):
            metrics[base_key] = value

    metricas_frontend_es = _build_metricas_frontend_es(metrics)
    resumen_frontend_es = _build_resumen_frontend_es(metrics)

    metrics["metricas_frontend_es"] = metricas_frontend_es
    metrics["resumen_frontend_es"] = resumen_frontend_es

    salida_frontend_es = {
        "fecha": snap.get("date"),
        "snapshot_obtenido_local": _frontend_pick(metrics, "snapshot_obtenido_local"),
        "datos_disponibles_hasta": _frontend_pick(metrics, "datos_hasta_local"),
        "metricas": metricas_frontend_es,
        "resumen": resumen_frontend_es,
    }

    ordered: dict[str, Any] = {
        "salida_frontend_es": salida_frontend_es,
        "date": snap.get("date"),
        "fetched_at": snap.get("fetched_at"),
        "metrics": metrics,
    }
    for key in ("recent_activities", "source_errors", "raw_sources"):
        if key in snap:
            ordered[key] = snap.get(key)
    for key, value in snap.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


try:
    _FRONTEND_ES_OUTPUT_ORIGINAL_COLLECT_DAY_SNAPSHOT
except NameError:
    _FRONTEND_ES_OUTPUT_ORIGINAL_COLLECT_DAY_SNAPSHOT = _collect_day_snapshot


def _collect_day_snapshot(*args, **kwargs):
    snap = _FRONTEND_ES_OUTPUT_ORIGINAL_COLLECT_DAY_SNAPSHOT(*args, **kwargs)
    return _attach_frontend_view_to_snapshot(snap)


try:
    _FRONTEND_ES_OUTPUT_ORIGINAL_NORMALIZE_ACTIVITY
except NameError:
    _FRONTEND_ES_OUTPUT_ORIGINAL_NORMALIZE_ACTIVITY = _normalize_activity


def _normalize_activity(activity: dict[str, Any]) -> dict[str, Any]:
    out = _FRONTEND_ES_OUTPUT_ORIGINAL_NORMALIZE_ACTIVITY(activity)
    type_key = out.get("type")
    family = out.get("activity_family")

    out["tipo_actividad"] = _ACTIVITY_TYPE_ES.get(type_key, type_key)
    out["familia_actividad"] = _ACTIVITY_FAMILY_ES.get(family, family)

    parts: list[str] = []
    if _frontend_non_empty(out.get("tipo_actividad")):
        parts.append(str(out.get("tipo_actividad")))
    if _frontend_non_empty(out.get("distance_km")):
        parts.append(f'{out.get("distance_km")} km')
    if _frontend_non_empty(out.get("duration_min")):
        parts.append(f'{out.get("duration_min")} min')
    if _frontend_non_empty(out.get("training_load")):
        parts.append(f'carga {out.get("training_load")}')

    out["resumen_frontend_es"] = " · ".join(parts) if parts else None
    return out
# === FRONTEND GARMIN CONNECT ES OUTPUT PATCH END ===


# === STRICT GARMIN CONNECT ES TERMINOLOGY PATCH START ===
_STRICT_GARMIN_CONNECT_ES_TERMS = (
    " Si el usuario escribe en español, toda la respuesta visible debe salir en español por defecto, aunque no lo pida explícitamente."
    " Para datos de Garmin, usa exactamente la terminología visible de Garmin Connect en español y no la reformules con sinónimos."
    " Prioriza estas formas exactas: Body Battery, Predisposición para entrenar, Estado de VFC, Puntuación de sueño, Estado de entreno, Carga aguda, Tiempo de recuperación, Estrés, Calorías, Pasos y Minutos de intensidad."
    " Evita estas reformulaciones salvo que el usuario las pida expresamente o las use primero: Variabilidad de la Frecuencia Cardíaca, Estado de Entrenamiento, Preparación para entrenar, Batería corporal."
    " No uses claves internas ni términos en inglés salvo que el usuario pida el dato bruto."
    " NUNCA uses los acrónimos en inglés 'HRV', 'RHR' ni los términos 'Training Readiness', 'Training Effect' o 'Stamina' en respuestas al usuario."
    " Usa siempre: 'VFC' en lugar de 'HRV', 'FC en reposo' en lugar de 'RHR', 'Predisposición para entrenar' en lugar de 'Training Readiness', 'Efecto de entrenamiento' en lugar de 'Training Effect', y 'Energía disponible' en lugar de 'Stamina'."
    " NUNCA uses términos híbridos español-inglés como 'sobre-reach', 'over-reach' o 'overreaching': usa 'sobreentrenamiento', 'sobrecarga' o 'exceso de carga' según el contexto."
)

try:
    _current_instructions = getattr(mcp, "instructions", None)
    if isinstance(_current_instructions, str) and _STRICT_GARMIN_CONNECT_ES_TERMS not in _current_instructions:
        mcp.instructions = _current_instructions + _STRICT_GARMIN_CONNECT_ES_TERMS
except Exception:
    pass
# === STRICT GARMIN CONNECT ES TERMINOLOGY PATCH END ===
