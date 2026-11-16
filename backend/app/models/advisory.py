"""Multilingual citizen advisory agent.

Produces short, conservative public-health guidance for a ward in English,
Kannada, Tamil, or Hindi. An LLM writes the text when a provider is
configured; otherwise a reviewed template is used. Either way the output is
cached on disk so repeated dashboard loads do not re-bill the provider.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pandas as pd

from app.core.aqi import UNHEALTHY_BANDS, aqi_band
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.wards import WARD_VULNERABILITY, ward_row, ward_vulnerability_row

logger = get_logger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ADVISORY_CACHE_DIR = ARTIFACT_DIR / "advisory_cache"
CACHE_VERSION = "v3"

DISCLAIMER = (
    "Translations should be reviewed by a native speaker before real-world dispatch; "
    "do not use this advisory for dosage or treatment instructions."
)

LANGUAGE_NAMES = {"en": "English", "kn": "Kannada", "ta": "Tamil", "hi": "Hindi"}
SUPPORTED_LANGUAGES = tuple(LANGUAGE_NAMES)
DELIVERY_CHANNELS = ["app_push", "led_display", "ivr_script"]

#: Defaults applied when a ward has no dedicated vulnerability profile.
DEFAULT_PROFILE = {"school_poi_density": 4.0, "hospital_poi_density": 2.0, "elderly_pct": 8.0}

__all__ = [
    "ADVISORY_CACHE_DIR",
    "DISCLAIMER",
    "LANGUAGE_NAMES",
    "SUPPORTED_LANGUAGES",
    "WARD_VULNERABILITY",
    "generate_advisory_response",
    "normalise_language",
]

_UNSAFE_PATTERNS = re.compile(
    r"\b(mg\b|milligram|dose|dosage|prescri\w*|tablet|inhaler|steroid|antibiotic)",
    re.IGNORECASE,
)


def normalise_language(language: str | None) -> str:
    """Clamp a requested language to one we can actually produce."""
    code = str(language or "en").strip().lower()[:5]
    return code if code in LANGUAGE_NAMES else "en"


def _vulnerability_index(row: pd.Series) -> float:
    score = (
        float(row.school_poi_density) * 0.35
        + float(row.hospital_poi_density) * 0.35
        + float(row.elderly_pct) * 0.30
    )
    return round(min(score / 10.0, 1.0), 3)


def _flags(row: pd.Series) -> dict[str, bool]:
    return {
        "near_school": bool(float(row.school_poi_density) >= 4.0),
        "near_hospital": bool(float(row.hospital_poi_density) >= 2.0),
        "elderly_population_high": bool(float(row.elderly_pct) >= 10.0),
    }


def _cache_path(ward_id: str, band: str, language: str) -> Path:
    ADVISORY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ward = re.sub(r"[^A-Za-z0-9_-]+", "_", str(ward_id)).strip("_") or "unknown"
    safe_band = band.replace(" ", "-")
    return ADVISORY_CACHE_DIR / f"{safe_ward}_{safe_band}_{language}_{CACHE_VERSION}.json"


def _read_cache(path: Path, ttl_seconds: int) -> dict[str, object] | None:
    if ttl_seconds <= 0 or not path.exists():
        return None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Discarding unreadable advisory cache entry %s", path.name)
        return None
    if time.time() - float(cached.get("cached_at", 0)) > ttl_seconds:
        return None
    response = cached.get("response")
    return response if isinstance(response, dict) else None


def _write_cache(path: Path, response: dict[str, object]) -> None:
    """Write atomically so a concurrent reader never sees a partial file."""
    payload = json.dumps({"cached_at": time.time(), "response": response}, ensure_ascii=False, indent=2)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(path)
    except OSError:
        logger.warning("Could not persist advisory cache entry %s", path.name)
        temporary.unlink(missing_ok=True)


def _system_prompt(language: str) -> str:
    return (
        "You are a municipal public-health advisor writing air-quality guidance for residents. "
        f"Write 2 to 3 short sentences in {LANGUAGE_NAMES[language]} and nothing else. "
        "Keep guidance conservative and aligned with WHO and CPCB phrasing. "
        "Never mention dosages, medicines, prescriptions, or treatment plans. "
        "Name the ward, state the air-quality level, and give one or two concrete precautions."
    )


def _user_prompt(ward_name: str, band: str, aqi: float, vulnerability_index: float, flags: dict[str, bool]) -> str:
    audience = [label.replace("_", " ") for label, present in flags.items() if present]
    return (
        f"Ward: {ward_name}\n"
        f"Current AQI: {aqi:.0f} (CPCB band: {band})\n"
        f"Population vulnerability index: {vulnerability_index:.2f} of 1.00\n"
        f"Sensitive context: {', '.join(audience) if audience else 'none flagged'}\n"
        f"Restrictive guidance needed: {'yes' if band in UNHEALTHY_BANDS else 'no'}\n"
        "Write the advisory now."
    )


def _fallback_advisory(ward_name: str, band: str, language: str) -> str:
    if language == "kn":
        return (
            f"{ward_name} ಪ್ರದೇಶದಲ್ಲಿ ಗಾಳಿಯ ಗುಣಮಟ್ಟ {band} ಮಟ್ಟದಲ್ಲಿದೆ. ಸಂವೇದನಾಶೀಲರು ಹೊರಾಂಗಣ ಚಟುವಟಿಕೆಗಳನ್ನು "
            "ಕಡಿಮೆ ಮಾಡಿ, ಕಿಟಕಿಗಳನ್ನು ಮುಚ್ಚಿ, ಮತ್ತು ಹೊರಗೆ ಹೋಗುವಾಗ ಮಾಸ್ಕ್ ಬಳಸುವುದು ಉತ್ತಮ. ಗರ್ಭಿಣಿಯರು, ಮಕ್ಕಳು, "
            "ಮತ್ತು ವೃದ್ಧರು ಸಾಧ್ಯವಾದಷ್ಟು ಒಳಾಂಗಣದಲ್ಲಿ ಇರಲಿ."
        )
    if language == "ta":
        return (
            f"{ward_name} பகுதியில் காற்றின் தரம் {band} நிலையில் உள்ளது. உணர்திறன் உள்ளவர்கள் வெளிப்புற "
            "செயல்பாடுகளை குறைத்து, ஜன்னல்களை மூடி, வெளியே செல்லும்போது முககவசம் பயன்படுத்துவது நல்லது. "
            "குழந்தைகள், முதியவர்கள், மற்றும் கர்ப்பிணிகள் இயன்றவரை உள்ளரங்கில் இருக்க வேண்டும்."
        )
    if language == "hi":
        return (
            f"{ward_name} में हवा की गुणवत्ता {band} स्तर पर है। संवेदनशील लोगों को बाहर की गतिविधियां कम करनी "
            "चाहिए, खिड़कियां बंद रखनी चाहिए और बाहर जाना जरूरी हो तो मास्क पहनना चाहिए। बच्चों, बुजुर्गों और "
            "गर्भवती लोगों को अधिक समय घर के अंदर रहना चाहिए।"
        )
    return (
        f"Air quality in {ward_name} is {band}. Sensitive groups should reduce outdoor activity, keep "
        "windows closed, and use a mask if they must travel. Children, older adults, and pregnant "
        "people should spend more time indoors."
    )


def _generate_with_llm(ward_name: str, band: str, aqi: float, vulnerability_index: float, flags: dict[str, bool], language: str) -> str | None:
    """Ask the configured LLM for the advisory; ``None`` on any failure."""
    from app.agents.llm import get_chat_model, message_text  # lazy, avoids a cycle

    model = get_chat_model()
    if model is None:
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        reply = model.invoke(
            [
                SystemMessage(content=_system_prompt(language)),
                HumanMessage(content=_user_prompt(ward_name, band, aqi, vulnerability_index, flags)),
            ]
        )
        text = message_text(reply)
    except Exception:
        logger.warning("Advisory LLM call failed for %s/%s; using template", ward_name, language, exc_info=True)
        return None

    text = " ".join(str(text).split()).strip()
    if not text:
        return None
    if _UNSAFE_PATTERNS.search(text):
        # Guardrail: never dispatch anything that reads like medical dosing.
        logger.warning("Advisory LLM output rejected by safety filter for %s/%s", ward_name, language)
        return None
    return text


def _resolve_profile(ward_id: str) -> pd.Series:
    """Vulnerability profile for a ward, synthesised from the registry if absent."""
    profile = ward_vulnerability_row(ward_id)
    if profile is not None:
        return profile
    try:
        state = ward_row(ward_id)
    except KeyError as exc:
        raise ValueError(f"No advisory profile for ward_id={ward_id}") from exc
    return pd.Series(
        {
            "ward_id": str(state.ward_id),
            "ward_name": str(state.ward_name),
            "city": "Bengaluru",
            "aqi_forecast": float(state.aqi),
            **DEFAULT_PROFILE,
        }
    )


def generate_advisory_response(ward_id: str, language: str = "en") -> dict[str, object]:
    """Return a cached-or-fresh advisory payload for ``ward_id``.

    Raises ``ValueError`` when the ward is unknown.
    """
    settings = get_settings()
    language = normalise_language(language)
    row = _resolve_profile(str(ward_id))

    aqi = float(row.aqi_forecast)
    band = aqi_band(aqi)
    cache_path = _cache_path(str(ward_id), band, language)

    cached = _read_cache(cache_path, settings.advisory_cache_ttl_seconds)
    if cached is not None:
        return cached

    vulnerability_index = _vulnerability_index(row)
    flags = _flags(row)
    advisory = _generate_with_llm(str(row.ward_name), band, aqi, vulnerability_index, flags, language)
    source = "llm" if advisory else "template"
    if not advisory:
        advisory = _fallback_advisory(str(row.ward_name), band, language)

    response: dict[str, object] = {
        "ward_id": str(ward_id),
        "ward_name": str(row.ward_name),
        "language": language,
        "aqi": round(aqi, 1),
        "aqi_band": band,
        "vulnerability_index": vulnerability_index,
        "advisory": advisory,
        "advisory_source": source,
        "vulnerability_flags": flags,
        "delivery_channels": list(DELIVERY_CHANNELS),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "disclaimer": DISCLAIMER,
    }
    _write_cache(cache_path, response)
    return response
