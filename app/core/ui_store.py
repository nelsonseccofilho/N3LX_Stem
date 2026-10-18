"""Local UI preferences shared by the Electron window and browser."""

from __future__ import annotations

import json
import re
import shutil
import threading

from app.core.config import DATA_DIR

PATH = DATA_DIR / "ui-store.json"
LOCK = threading.RLock()
KEYS = {
    "stemdeck.folders",
    "stemdeck.deleted_jobs",
    "stemdeck.language",
    "stemdeck:selected-stems",
    "stemdeck:vocal-split-mode",
    "stemdeck:failures",
    "stemdeck:beatgrid-prefs",
    "stemdeck:slow-speed",
    "stemdeck:metronome",
}


def allowed(key: str) -> bool:
    return key in KEYS or bool(re.fullmatch(r"stemdeck:(mix|lyrics):[a-zA-Z0-9_-]{1,80}", key))


def read_values() -> dict:
    with LOCK:
        if not PATH.exists():
            return {}
        value = json.loads(PATH.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Invalid UI store")
        return value


def update_values(updates: dict, *, backup: bool = False) -> None:
    if not isinstance(updates, dict) or len(updates) > 1024 or not all(allowed(k) for k in updates):
        raise ValueError("Unsupported preference key")
    with LOCK:
        value = {**read_values(), **updates}
        text = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(text.encode("utf-8")) > 8 * 1024 * 1024:
            raise ValueError("UI preferences exceed 8 MB")
        PATH.parent.mkdir(parents=True, exist_ok=True)
        if backup and PATH.exists():
            shutil.copy2(PATH, PATH.with_suffix(".before-migration.json"))
        temp = PATH.with_suffix(".tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(PATH)
