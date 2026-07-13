import json
import os
from pathlib import Path

from .constants import QUALITY_QA, SAMPLE_RATE_CHOICES

_SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "audio2ogg" / "settings.json"

_SCHEMA_VERSION = 6

_DEFAULTS: dict = {
    "language": "en",
    "output_dir": "",
    "quality": "medium",
    "channels": "original",
    "sample_rate": "48000",
}

_VALID_QUALITY = set(QUALITY_QA)
_VALID_CHANNELS = {"original", "1", "2"}
_VALID_SAMPLE_RATES = {value for value, _ in SAMPLE_RATE_CHOICES}


def _int_to_quality(value: int) -> str:
    if value <= 3:
        return "low"
    if value <= 6:
        return "medium"
    return "high"


def _validate(raw: dict) -> dict:
    """Keep only known keys with correct types; fall back to default otherwise."""
    result = {}
    for key, default in _DEFAULTS.items():
        value = raw.get(key)
        if key == "quality":
            result[key] = value if value in _VALID_QUALITY else default
        elif key == "channels":
            result[key] = value if value in _VALID_CHANNELS else default
        elif key == "sample_rate":
            result[key] = value if value in _VALID_SAMPLE_RATES else default
        elif value is not None and type(value) is type(default):
            result[key] = value
        else:
            result[key] = default
    return result


def load() -> dict:
    try:
        raw = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return dict(_DEFAULTS)

        saved_version = raw.get("_version", 0)
        data = _migrate(raw, saved_version)
        return _validate(data)
    except Exception:
        return dict(_DEFAULTS)


def save(data: dict) -> None:
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"_version": _SCHEMA_VERSION, **{k: data[k] for k in _DEFAULTS if k in data}}
        _SETTINGS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _migrate(raw: dict, from_version: int) -> dict:
    """Apply sequential migrations when schema version increases."""
    if from_version < 2:
        raw.setdefault("quality", _DEFAULTS["quality"])
        raw.setdefault("channels", _DEFAULTS["channels"])
        raw.setdefault("sample_rate", _DEFAULTS["sample_rate"])
    if from_version < 3:
        quality = raw.get("quality", _DEFAULTS["quality"])
        if isinstance(quality, int):
            raw["quality"] = _int_to_quality(quality)
        elif quality not in _VALID_QUALITY:
            raw["quality"] = _DEFAULTS["quality"]
    if from_version < 4:
        if raw.get("sample_rate") == "original":
            raw["sample_rate"] = _DEFAULTS["sample_rate"]
    return raw
