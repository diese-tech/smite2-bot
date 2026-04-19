"""
Loads JSON data files. Cached in module-level variables; call `reload()`
to force re-read (useful if you edit the JSON files while the bot runs).
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

_gods_cache = None
_builds_cache = None


def _load(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def gods() -> dict:
    global _gods_cache
    if _gods_cache is None:
        _gods_cache = _load("gods.json")
    return _gods_cache


def builds() -> dict:
    global _builds_cache
    if _builds_cache is None:
        _builds_cache = _load("builds.json")
    return _builds_cache


def reload():
    """Clear caches so next access re-reads from disk."""
    global _gods_cache, _builds_cache
    _gods_cache = None
    _builds_cache = None
