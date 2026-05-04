"""
Combined Railway entrypoint for the fast live GodForge dashboard.

Runs the public web/API server on Railway's PORT and starts the Discord bot in
the same container so both processes share the mounted /app/data volume.
"""

from __future__ import annotations

import os
import threading

import bot
from web_api import server as web_server


def _run_web():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8787"))
    server = web_server.create_server(host, port)
    print(f"Godforge web dashboard running at http://{host}:{port}")
    server.serve_forever()


def main():
    thread = threading.Thread(target=_run_web, name="godforge-web", daemon=True)
    thread.start()
    bot.main()


if __name__ == "__main__":
    main()
