"""
Integration tests for the web admin API bridge.

These tests exercise the HTTP surface directly with temporary JSON files and no
real Discord connection.
"""

import json
import threading
import urllib.error
import urllib.request

from utils import ledger as ledger_utils
from utils import wallet as wallet_utils
from utils import audit as audit_utils
from web_api import server as web_server


def _start_server():
    httpd = web_server.create_server("127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _stop_server(httpd):
    httpd.shutdown()
    httpd.server_close()


def _request(method, url, payload=None, cookie=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if cookie:
        request.add_header("Cookie", cookie)

    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return response.status, parsed, response.headers
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        parsed = json.loads(body) if body else {}
        return exc.code, parsed, exc.headers


def _login(base):
    status, payload, headers = _request(
        "POST",
        f"{base}/api/auth/login",
        {"password": "secret-test"},
    )
    assert status == 200
    assert payload["authenticated"] is True
    return headers["Set-Cookie"].split(";", 1)[0]


def test_public_health_and_tool_endpoints_do_not_require_auth(monkeypatch, tmp_ledger, tmp_wallets):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    httpd, base = _start_server()
    try:
        for path in (
            "/api/health",
            "/api/gods/roll?role=jungle&source=website",
            "/api/gods/roll5?role=jungle&source=website",
            "/api/builds/roll?role=adc&type=standard&count=6",
        ):
            status, payload, _ = _request("GET", f"{base}{path}")
            assert status == 200
            assert payload["ok"] is True
    finally:
        _stop_server(httpd)


def test_protected_admin_endpoints_reject_unauthenticated_writes(monkeypatch, tmp_ledger, tmp_wallets):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    httpd, base = _start_server()
    try:
        status, payload, _ = _request(
            "POST",
            f"{base}/api/match/create",
            {"team1": "Solaris", "team2": "Onyx"},
        )

        assert status == 401
        assert "login" in payload["error"].lower()
        assert ledger_utils.load_ledger()["matches"] == []
    finally:
        _stop_server(httpd)


def test_wrong_password_does_not_unlock_admin_endpoints(monkeypatch, tmp_ledger, tmp_wallets):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    httpd, base = _start_server()
    try:
        status, payload, headers = _request(
            "POST",
            f"{base}/api/auth/login",
            {"password": "wrong"},
        )
        assert status == 401
        assert "Set-Cookie" not in headers

        status, payload, _ = _request("GET", f"{base}/api/wallets")
        assert status == 401
    finally:
        _stop_server(httpd)


def test_tampered_admin_cookie_is_rejected(monkeypatch, tmp_ledger, tmp_wallets):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    httpd, base = _start_server()
    try:
        cookie = f"{web_server.SESSION_COOKIE}=not-a-real-session"

        status, payload, _ = _request("GET", f"{base}/api/admin/status", cookie=cookie)

        assert status == 401
        assert "login" in payload["error"].lower()
    finally:
        _stop_server(httpd)


def test_static_file_lookup_rejects_path_traversal():
    assert web_server._static_path("/index.html").name == "index.html"
    assert web_server._static_path("/../bot.py") is None
    assert web_server._static_path("/..%2Fbot.py") is None


def test_admin_status_reports_data_counts_and_requires_auth(monkeypatch, tmp_ledger, tmp_wallets):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    ledger_utils.create_match("Solaris", "Onyx")
    wallet_utils.ensure_wallet(111, "AtlasMain")
    httpd, base = _start_server()
    try:
        status, payload, _ = _request("GET", f"{base}/api/admin/status")
        assert status == 401

        cookie = _login(base)
        status, payload, _ = _request("GET", f"{base}/api/admin/status", cookie=cookie)

        assert status == 200
        assert payload["status"]["data"]["matchCount"] == 1
        assert payload["status"]["data"]["walletCount"] == 1
        assert payload["status"]["data"]["statusCounts"]["betting_open"] == 1
        assert payload["status"]["bot"]["guildCount"] >= 0
    finally:
        _stop_server(httpd)


def test_manual_ledger_sync_is_protected_and_schedules_refresh(monkeypatch, tmp_ledger, tmp_wallets):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    calls = []
    monkeypatch.setattr(web_server, "_schedule_ledger_embed_refresh", lambda: calls.append("refresh") or True)
    httpd, base = _start_server()
    try:
        status, payload, _ = _request("POST", f"{base}/api/admin/sync/ledger", {})
        assert status == 401

        cookie = _login(base)
        status, payload, _ = _request("POST", f"{base}/api/admin/sync/ledger", {}, cookie)

        assert status == 200
        assert payload["discord_embed_update"] is True
        assert calls == ["refresh"]
    finally:
        _stop_server(httpd)


def test_settings_read_write_requires_auth_and_persists(monkeypatch, tmp_ledger, tmp_wallets, tmp_settings):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    httpd, base = _start_server()
    try:
        status, payload, _ = _request("GET", f"{base}/api/settings?guild_id=global")
        assert status == 401

        cookie = _login(base)
        update = {
            "guild_id": "global",
            "updated_by": "test-admin",
            "features": {"botEnabled": True, "draftsEnabled": False, "unknown": False},
            "channels": {"matchChannel": "#matches", "bettingChannel": "#bets"},
            "roles": {"adminRole": "Admins", "captainRole": "Captains"},
        }
        status, saved, _ = _request("POST", f"{base}/api/settings", update, cookie)
        assert status == 200
        assert saved["settings"]["features"]["draftsEnabled"] is False
        assert saved["settings"]["channels"]["matchChannel"] == "#matches"
        assert "unknown" not in saved["settings"]["features"]

        status, loaded, _ = _request("GET", f"{base}/api/settings?guild_id=global", cookie=cookie)
        assert status == 200
        assert loaded["settings"]["roles"]["captainRole"] == "Captains"
        assert loaded["settings"]["updated_by"] == "test-admin"
    finally:
        _stop_server(httpd)


def test_settings_rejects_bad_guild_ids_and_control_characters(monkeypatch, tmp_ledger, tmp_wallets, tmp_settings):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    httpd, base = _start_server()
    try:
        cookie = _login(base)
        bad_payloads = [
            {"guild_id": "../secret", "features": {"botEnabled": True}},
            {"guild_id": "global", "channels": {"matchChannel": "#matches\nSet-Cookie: hacked=true"}},
            {"guild_id": "global", "roles": {"adminRole": "A" * 81}},
        ]

        for payload in bad_payloads:
            status, response, _ = _request("POST", f"{base}/api/settings", payload, cookie)
            assert status == 400
            assert response["ok"] is False
    finally:
        _stop_server(httpd)


def test_admin_audit_requires_auth_and_records_mutations(monkeypatch, tmp_ledger, tmp_wallets, tmp_settings):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    httpd, base = _start_server()
    try:
        status, payload, _ = _request("GET", f"{base}/api/admin/audit")
        assert status == 401

        cookie = _login(base)
        status, created, _ = _request(
            "POST",
            f"{base}/api/match/create",
            {"team1": "Solaris", "team2": "Onyx"},
            cookie,
        )
        assert status == 200

        status, audit, _ = _request("GET", f"{base}/api/admin/audit?limit=5", cookie=cookie)
        assert status == 200
        assert audit["events"][0]["action"] == "match.create"
        assert audit["events"][0]["target"] == created["match"]["match_id"]
    finally:
        _stop_server(httpd)


def test_audit_log_sanitizes_and_trims_malicious_metadata(tmp_audit):
    event = audit_utils.record_event(
        "settings.update\nSet-Cookie: hacked=true",
        "<script>alert(1)</script>",
        metadata={"x" * 60: "A" * 140, "nested": {"ignored": True}},
    )

    assert "\n" not in event["action"]
    assert event["target"] == "<script>alert(1)</script>"
    assert list(event["metadata"].keys()) == ["x" * 40]
    assert event["metadata"]["x" * 40] == "A" * 120


def test_admin_mutations_schedule_discord_ledger_refresh(monkeypatch, tmp_ledger, tmp_wallets):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    calls = []
    monkeypatch.setattr(web_server, "_schedule_ledger_embed_refresh", lambda: calls.append("refresh") or True)
    httpd, base = _start_server()
    try:
        cookie = _login(base)

        status, created, _ = _request(
            "POST",
            f"{base}/api/match/create",
            {"team1": "Solaris", "team2": "Onyx"},
            cookie,
        )
        match_id = created["match"]["match_id"]
        assert status == 200
        assert created["discord_embed_update"] is True

        mutations = [
            ("POST", "/api/bet/place", {"match_id": match_id, "username": "AtlasMain", "type": "win", "team": "Solaris", "amount": 100}),
            ("POST", "/api/match/status", {"match_id": match_id, "status": "in_progress"}),
            ("POST", "/api/match/resolve/winner", {"match_id": match_id, "winner": "Solaris"}),
            ("POST", "/api/ledger/reset", {}),
        ]

        for method, path, payload in mutations:
            status, response, _ = _request(method, f"{base}{path}", payload, cookie)
            assert status == 200
            assert response["discord_embed_update"] is True

        assert len(calls) == 5
    finally:
        _stop_server(httpd)


def test_reset_preserves_embed_pointer_for_in_place_discord_update(monkeypatch, tmp_ledger, tmp_wallets):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    ledger_utils.create_match("@TeamA", "@TeamB")
    ledger_utils.update_embed_info(12345, 67890)
    httpd, base = _start_server()
    try:
        cookie = _login(base)
        status, payload, _ = _request("POST", f"{base}/api/ledger/reset", {}, cookie)

        data = ledger_utils.load_ledger()
        assert status == 200
        assert payload["cleared"] == 1
        assert data["matches"] == []
        assert data["embed_message_id"] == 12345
        assert data["embed_channel_id"] == 67890
    finally:
        _stop_server(httpd)


def test_malicious_bet_payloads_do_not_debit_wallet_or_write_bets(monkeypatch, tmp_ledger, tmp_wallets):
    monkeypatch.setenv("GODFORGE_ADMIN_PASSWORD", "secret-test")
    match = ledger_utils.create_match("Solaris", "Onyx")
    wallet_utils.seed_wallet(111, "AtlasMain")
    httpd, base = _start_server()
    try:
        cookie = _login(base)

        bad_payloads = [
            {"match_id": match["match_id"], "user_id": 111, "username": "AtlasMain", "type": "win", "team": "Solaris", "amount": -50},
            {"match_id": match["match_id"], "user_id": 111, "username": "AtlasMain", "type": "win", "team": "Intruder", "amount": 50},
            {"match_id": match["match_id"], "user_id": 111, "username": "AtlasMain", "type": "prop", "player": "ADC", "stat": "kills", "direction": "sideways", "threshold": 7.5, "amount": 50},
        ]

        for payload in bad_payloads:
            status, response, _ = _request("POST", f"{base}/api/bet/place", payload, cookie)
            assert status == 400
            assert response["ok"] is False

        assert wallet_utils.get_wallet(111)["balance"] == 500
        assert ledger_utils.get_match(match["match_id"])["bets"] == []
    finally:
        _stop_server(httpd)
