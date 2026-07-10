import json
import os
from pathlib import Path

_SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "audio2ogg" / "settings.json"

_SCHEMA_VERSION = 1

_DEFAULTS: dict = {
    "language": "en",
    "output_dir": "",
}


def _validate(raw: dict) -> dict:
    """Keep only known keys with correct types; fall back to default otherwise."""
    result = {}
    for key, default in _DEFAULTS.items():
        value = raw.get(key)
        if value is not None and type(value) is type(default):
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
    # if from_version < 2: raw = _migrate_v1_to_v2(raw)
    return raw
