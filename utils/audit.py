"""
Temporary admin activity log for the GodForge web dashboard.

The log is JSON-backed for the Railway milestone and intentionally replaceable
with database-backed audit rows later.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from utils import dashboard_store

AUDIT_PATH = Path("data/admin_audit.json")
MAX_EVENTS = 200


def load_events(limit: int = 50) -> list[dict]:
    events = _load_raw().get("events", [])
    try:
        count = max(1, min(200, int(limit)))
    except (TypeError, ValueError):
        count = 50
    return list(reversed(events[-count:]))


def record_event(action: str, target: str = "", status: str = "ok", metadata: dict | None = None, actor: str = "web-admin") -> dict:
    event = {
        "ts": int(time.time()),
        "actor": _clean(actor, 80),
        "action": _clean(action, 80),
        "target": _clean(target, 120),
        "status": _clean(status, 32),
        "metadata": _clean_metadata(metadata or {}),
    }
    data = _load_raw()
    events = data.setdefault("events", [])
    events.append(event)
    data["events"] = events[-MAX_EVENTS:]
    _save_raw(data)
    return event


def _load_raw() -> dict:
    stored = dashboard_store.load_document("audit", "events", None)
    if stored is not None:
        return stored if isinstance(stored.get("events"), list) else {"events": []}

    if not AUDIT_PATH.exists():
        return {"events": []}
    try:
        with open(AUDIT_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"events": []}
    return data if isinstance(data.get("events"), list) else {"events": []}


def _save_raw(data: dict):
    if dashboard_store.save_document("audit", "events", data):
        return

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _clean(value, max_length: int) -> str:
    text = str(value or "").strip()
    text = "".join(char for char in text if ord(char) >= 32)
    return text[:max_length]


def _clean_metadata(metadata: dict) -> dict:
    clean = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            clean[_clean(key, 40)] = _clean(value, 120) if isinstance(value, str) else value
    return clean
