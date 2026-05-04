"""
Temporary custom command configuration persistence for the web dashboard.

Bot-side execution is intentionally not wired yet. These JSON-backed records
stage the schema and admin surface for future Discord guild-scoped commands.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

COMMANDS_PATH = Path("data/custom_commands.json")
DEFAULT_GUILD_ID = "global"

ROLE_GATES = {"Everyone", "Captains", "Admins"}


def load_commands(guild_id: str = DEFAULT_GUILD_ID) -> list[dict]:
    gid = _clean_guild_id(guild_id)
    return _load_raw().get("guilds", {}).get(gid, [])


def upsert_command(guild_id: str, payload: dict) -> dict:
    gid = _clean_guild_id(guild_id)
    command = _clean_command(payload)
    command["updated_at"] = int(time.time())

    data = _load_raw()
    commands = data.setdefault("guilds", {}).setdefault(gid, [])
    commands = [item for item in commands if item["trigger"].lower() != command["trigger"].lower()]
    commands.append(command)
    commands.sort(key=lambda item: item["trigger"].lower())
    data["guilds"][gid] = commands
    _save_raw(data)
    return command


def delete_command(guild_id: str, trigger: str) -> bool:
    gid = _clean_guild_id(guild_id)
    clean_trigger = _clean_trigger(trigger)
    data = _load_raw()
    commands = data.setdefault("guilds", {}).get(gid, [])
    kept = [item for item in commands if item["trigger"].lower() != clean_trigger.lower()]
    data["guilds"][gid] = kept
    _save_raw(data)
    return len(kept) != len(commands)


def _load_raw() -> dict:
    if not COMMANDS_PATH.exists():
        return {"guilds": {}}
    try:
        with open(COMMANDS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"guilds": {}}
    return data if isinstance(data.get("guilds"), dict) else {"guilds": {}}


def _save_raw(data: dict):
    COMMANDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COMMANDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _clean_command(payload: dict) -> dict:
    trigger = _clean_trigger(payload.get("trigger", ""))
    response = _clean_text(payload.get("response", ""), "response", 600)
    channel = _clean_text(payload.get("channel", ""), "channel", 80)
    role_gate = _clean_text(payload.get("role_gate") or payload.get("roleGate") or "Everyone", "role_gate", 40)
    cooldown = _clean_text(payload.get("cooldown", "0s"), "cooldown", 20)

    if role_gate not in ROLE_GATES:
        raise ValueError("Invalid role gate")
    if not response:
        raise ValueError("Missing required field: response")

    return {
        "trigger": trigger,
        "response": response,
        "channel": channel,
        "role_gate": role_gate,
        "cooldown": cooldown,
        "enabled": bool(payload.get("enabled", True)),
    }


def _clean_trigger(trigger: str) -> str:
    value = str(trigger or "").strip().lower()
    if not re.fullmatch(r"\.[a-z][a-z0-9_-]{1,31}", value):
        raise ValueError("Trigger must start with . and use 2-32 lowercase letters, numbers, dashes, or underscores")
    if value in {".rg", ".roll5", ".build", ".bet", ".wallet", ".ledger", ".match", ".draft"}:
        raise ValueError("Trigger conflicts with a built-in GodForge command")
    return value


def _clean_guild_id(value: str | None) -> str:
    gid = str(value or DEFAULT_GUILD_ID).strip() or DEFAULT_GUILD_ID
    if len(gid) > 64 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", gid):
        raise ValueError("Invalid guild id")
    return gid


def _clean_text(value, field_name: str, max_length: int) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer")
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise ValueError(f"{field_name} cannot contain control characters")
    return text
