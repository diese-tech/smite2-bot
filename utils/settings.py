"""
Temporary guild settings persistence for the GodForge web dashboard.

This is a JSON bridge for the live Railway milestone. It is intentionally small
and replaceable once Discord OAuth, guild permissions, and a real database land.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

SETTINGS_PATH = Path("data/guild_settings.json")
DEFAULT_GUILD_ID = "global"

FEATURE_KEYS = ("botEnabled", "randomizerEnabled", "draftsEnabled", "bettingEnabled")
CHANNEL_KEYS = ("matchChannel", "bettingChannel", "adminChannel")
ROLE_KEYS = ("adminRole", "captainRole")
TEXT_FIELDS = CHANNEL_KEYS + ROLE_KEYS


def default_settings(guild_id: str = DEFAULT_GUILD_ID) -> dict:
    return {
        "guild_id": str(guild_id or DEFAULT_GUILD_ID),
        "features": {
            "botEnabled": True,
            "randomizerEnabled": True,
            "draftsEnabled": True,
            "bettingEnabled": True,
        },
        "channels": {
            "matchChannel": "",
            "bettingChannel": "",
            "adminChannel": "",
        },
        "roles": {
            "adminRole": "",
            "captainRole": "",
        },
        "updated_at": None,
        "updated_by": None,
    }


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {"guilds": {}}
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"guilds": {}}
    return data if isinstance(data.get("guilds"), dict) else {"guilds": {}}


def save_settings(data: dict):
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_guild_settings(guild_id: str = DEFAULT_GUILD_ID) -> dict:
    gid = _clean_guild_id(guild_id)
    data = load_settings()
    saved = data.get("guilds", {}).get(gid, {})
    settings = default_settings(gid)
    settings["features"].update(_dict(saved.get("features")))
    settings["channels"].update(_dict(saved.get("channels")))
    settings["roles"].update(_dict(saved.get("roles")))
    settings["updated_at"] = saved.get("updated_at")
    settings["updated_by"] = saved.get("updated_by")
    return settings


def update_guild_settings(guild_id: str, payload: dict, updated_by: str | None = None) -> dict:
    gid = _clean_guild_id(guild_id)
    current = get_guild_settings(gid)

    for key in FEATURE_KEYS:
        if key in _dict(payload.get("features")):
            current["features"][key] = bool(payload["features"][key])

    for key in CHANNEL_KEYS:
        if key in _dict(payload.get("channels")):
            current["channels"][key] = _clean_label(payload["channels"][key], key)

    for key in ROLE_KEYS:
        if key in _dict(payload.get("roles")):
            current["roles"][key] = _clean_label(payload["roles"][key], key)

    current["updated_at"] = int(time.time())
    current["updated_by"] = _clean_label(updated_by or payload.get("updated_by") or "web-admin", "updated_by")

    data = load_settings()
    data.setdefault("guilds", {})[gid] = current
    save_settings(data)
    return current


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _clean_guild_id(value: str | None) -> str:
    gid = str(value or DEFAULT_GUILD_ID).strip() or DEFAULT_GUILD_ID
    if len(gid) > 64 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", gid):
        raise ValueError("Invalid guild id")
    return gid


def _clean_label(value, field_name: str) -> str:
    label = str(value or "").strip()
    if len(label) > 80:
        raise ValueError(f"{field_name} must be 80 characters or fewer")
    if any(ord(char) < 32 for char in label):
        raise ValueError(f"{field_name} cannot contain control characters")
    return label
