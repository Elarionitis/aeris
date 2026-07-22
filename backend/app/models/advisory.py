from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from app.models.enforcement import WARD_STATE


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
ADVISORY_CACHE_DIR = ARTIFACT_DIR / "advisory_cache"
DISCLAIMER = "Translations should be reviewed by a native speaker before real-world dispatch; do not use this advisory for dosage or treatment instructions."

LANGUAGE_NAMES = {"kn": "Kannada", "ta": "Tamil", "en": "English", "hi": "Hindi"}

WARD_VULNERABILITY = pd.DataFrame(
    [
        {"ward_id": "BTM", "ward_name": "BTM", "city": "Bengaluru", "aqi_forecast": 168, "school_poi_density": 4.8, "hospital_poi_density": 2.0, "elderly_pct": 8.5},
        {"ward_id": "HSR", "ward_name": "HSR Layout", "city": "Bengaluru", "aqi_forecast": 142, "school_poi_density": 5.6, "hospital_poi_density": 2.8, "elderly_pct": 7.9},
        {"ward_id": "Jayanagar", "ward_name": "Jayanagar", "city": "Bengaluru", "aqi_forecast": 88, "school_poi_density": 6.1, "hospital_poi_density": 4.2, "elderly_pct": 11.2},
        {"ward_id": "Mahadevapura", "ward_name": "Mahadevapura", "city": "Bengaluru", "aqi_forecast": 154, "school_poi_density": 3.9, "hospital_poi_density": 1.7, "elderly_pct": 7.4},
        {"ward_id": "Chennai Central", "ward_name": "Chennai Central", "city": "Chennai", "aqi_forecast": 119, "school_poi_density": 4.9, "hospital_poi_density": 3.6, "elderly_pct": 10.8},
    ]
)


def _aqi_band(aqi: float) -> str:
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 200:
        return "Poor"
    if aqi <= 300:
        return "Very Poor"
    return "Severe"


def _vulnerability_index(row: pd.Series) -> float:
    score = (row.school_poi_density * 0.35) + (row.hospital_poi_density * 0.35) + (row.elderly_pct * 0.3)
    return round(min(score / 10.0, 1.0), 3)


def _flags(row: pd.Series) -> dict[str, bool]:
    return {
        "near_school": bool(row.school_poi_density >= 4.0),
        "near_hospital": bool(row.hospital_poi_density >= 2.0),
        "elderly_population_high": bool(row.elderly_pct >= 10.0),
    }


def _cache_key(ward_id: str, band: str, lang: str) -> Path:
    ADVISORY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return ADVISORY_CACHE_DIR / f"{ward_id}_{band}_{lang}_v2.json"


def _build_system_prompt(language: str) -> str:
    language_name = LANGUAGE_NAMES.get(language, language)
    return (
        "You are a public health advisor. Write 2 to 3 short sentences in "
        f"{language_name}. Keep guidance conservative, aligned with WHO/CPCB language, and do not mention dosages, prescriptions, or treatment plans. "
        "If translating, preserve the meaning exactly and avoid medical specificity."
    )


def _compose_fallback_advisory(ward_name: str, band: str, vulnerability_index: float, language: str) -> str:
    if language == "kn":
        return f"{ward_name} ಪ್ರದೇಶದಲ್ಲಿ AQI {band} ಮಟ್ಟದಲ್ಲಿದೆ. ಸಂವೇದನಾಶೀಲರು ಹೊರಾಂಗಣ ಚಟುವಟಿಕೆಗಳನ್ನು ಕಡಿಮೆ ಮಾಡಿ, ಕಿಟಕಿಗಳನ್ನು ಮುಚ್ಚಿ, ಮತ್ತು ಮಾಸ್ಕ್ ಬಳಸುವುದು ಉತ್ತಮ. ಗರ್ಭಿಣಿಯರು, ಮಕ್ಕಳು, ಮತ್ತು ವೃದ್ಧರು ಸಾಧ್ಯವಾದಷ್ಟು ಒಳಾಂಗಣದಲ್ಲಿ ಇರಲಿ."
    if language == "ta":
        return f"{ward_name} பகுதியில் AQI {band} நிலையில் உள்ளது. உணர்திறன் உள்ளவர்கள் வெளிப்புற செயல்பாடுகளை குறைத்து, ஜன்னல்களை மூடி, முககவசம் பயன்படுத்துவது நல்லது. குழந்தைகள், முதியவர்கள், மற்றும் கர்ப்பிணிகள் இயன்றவரை உள்ளரங்கில் இருக்க வேண்டும்."
    if language == "hi":
        return f"{ward_name} में AQI {band} स्तर पर है। संवेदनशील लोगों को बाहर की गतिविधियां कम करनी चाहिए, खिड़कियां बंद रखनी चाहिए और बाहर जाना जरूरी हो तो मास्क पहनना चाहिए। बच्चों, बुजुर्गों और गर्भवती लोगों को अधिक समय घर के अंदर रहना चाहिए।"
    return f"AQI in {ward_name} is {band}. Sensitive groups should reduce outdoor activity, keep windows closed, and use a mask if they must travel. Children, older adults, and pregnant people should spend more time indoors."


def _call_anthropic(prompt: str, language: str, ward_name: str, band: str) -> str | None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 220,
            "system": _build_system_prompt(language),
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Ward: {ward_name}. AQI band: {band}. Vulnerability index: {prompt}. "
                        "Write the advisory now."
                    ),
                }
            ],
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    blocks = payload.get("content", [])
    text = " ".join(block.get("text", "") for block in blocks if isinstance(block, dict))
    return text.strip() or None


def generate_advisory_response(ward_id: str, language: str = "en") -> dict[str, object]:
    ward = WARD_VULNERABILITY.loc[WARD_VULNERABILITY["ward_id"].astype(str) == str(ward_id)]
    if ward.empty:
        state = WARD_STATE.loc[WARD_STATE["ward_id"].astype(str) == str(ward_id)]
        if state.empty:
            raise ValueError(f"No advisory profile for ward_id={ward_id}")
        source = state.iloc[0]
        row = pd.Series(
            {
                "ward_id": str(source.ward_id),
                "ward_name": str(source.ward_name),
                "city": "Bengaluru",
                "aqi_forecast": float(source.aqi),
                "school_poi_density": 4.0,
                "hospital_poi_density": 2.0,
                "elderly_pct": 8.0,
            }
        )
    else:
        row = ward.iloc[0]
    band = _aqi_band(float(row.aqi_forecast))
    cache_file = _cache_key(str(ward_id), band, language)
    if cache_file.exists():
        cached = json.loads(cache_file.read_text())
        if time.time() - cached.get("cached_at", 0) <= 3600:
            return cached["response"]
    vulnerability_index = _vulnerability_index(row)
    advisory = _call_anthropic(f"{vulnerability_index}", language, str(row.ward_name), band)
    if advisory is None:
        advisory = _compose_fallback_advisory(str(row.ward_name), band, vulnerability_index, language)
    response = {
        "ward_id": str(ward_id),
        "language": language,
        "aqi_band": band,
        "vulnerability_index": vulnerability_index,
        "advisory": advisory,
        "vulnerability_flags": _flags(row),
        "delivery_channels": ["app_push", "led_display", "ivr_script"],
        "disclaimer": DISCLAIMER,
    }
    cache_file.write_text(json.dumps({"cached_at": time.time(), "response": response}, ensure_ascii=False, indent=2))
    return response
