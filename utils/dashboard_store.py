"""
Dashboard persistence adapter.

JSON remains the default so the live bot is not surprised. Set
GODFORGE_STORAGE=sqlite to use the stdlib SQLite document store instead.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(os.getenv("GODFORGE_DB_PATH", "data/godforge_dashboard.db"))


def sqlite_enabled() -> bool:
    return os.getenv("GODFORGE_STORAGE", "").strip().lower() == "sqlite"


def load_document(namespace: str, key: str, default):
    if not sqlite_enabled():
        return default

    with _connect() as conn:
        row = conn.execute(
            "select payload from dashboard_documents where namespace = ? and doc_key = ?",
            (namespace, key),
        ).fetchone()

    if row is None:
        return default

    try:
        return json.loads(row["payload"])
    except json.JSONDecodeError:
        return default


def save_document(namespace: str, key: str, payload):
    if not sqlite_enabled():
        return False

    encoded = json.dumps(payload, separators=(",", ":"))
    with _connect() as conn:
        conn.execute(
            """
            insert into dashboard_documents(namespace, doc_key, payload, updated_at)
            values (?, ?, ?, ?)
            on conflict(namespace, doc_key)
            do update set payload = excluded.payload, updated_at = excluded.updated_at
            """,
            (namespace, key, encoded, int(time.time())),
        )
    return True


def storage_status() -> dict:
    if not sqlite_enabled():
        return {"kind": "json", "path": "data/*.json", "available": True}

    try:
        _ensure_schema()
        return {"kind": "sqlite", "path": str(DB_PATH), "available": True}
    except sqlite3.Error as exc:
        return {"kind": "sqlite", "path": str(DB_PATH), "available": False, "error": str(exc)}


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn=None):
    owns_connection = conn is None
    if conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)

    try:
        conn.execute(
            """
            create table if not exists dashboard_documents (
              namespace text not null,
              doc_key text not null,
              payload text not null,
              updated_at integer not null,
              primary key(namespace, doc_key)
            )
            """
        )
        conn.commit()
    finally:
        if owns_connection:
            conn.close()
