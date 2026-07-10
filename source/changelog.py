import json
import sys
from pathlib import Path


def load() -> list[dict]:
    meipass = getattr(sys, "_MEIPASS", None)
    candidates = []
    if meipass:
        candidates.append(Path(meipass) / "changelog.json")
    candidates.append(Path(__file__).resolve().parent.parent / "changelog.json")

    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass

    return []
