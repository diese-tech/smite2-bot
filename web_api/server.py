"""
Local development API for the Godforge website prototype.

This server intentionally uses only the Python standard library plus the
existing repo modules so it does not add production dependencies or deployment
settings. It is local-only until auth, storage, and deployment decisions are
made.
"""

from __future__ import annotations

import json
import base64
import hashlib
import hmac
import mimetypes
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import ledger as ledger_utils, loader, parser, picker, wallet as wallet_utils  # noqa: E402
from utils.draft import DraftState, get_phase_label  # noqa: E402
from utils.resolver import resolve_god_name  # noqa: E402

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8787"))
WEB_ROOT = ROOT / "web"
SESSION_COOKIE = "godforge_admin"
SESSION_MAX_AGE = 60 * 60 * 12

ROLE_CODES = {
    "jungle": "j",
    "mid": "m",
    "adc": "a",
    "support": "s",
    "solo": "o",
}

MATCH_STATUSES = {"betting_open", "in_progress", "completed", "settled"}
PROTECTED_GET_PATHS = {"/api/ledger", "/api/wallets"}
PROTECTED_POST_PATHS = {
    "/api/command",
    "/api/draft/start",
    "/api/draft/action",
    "/api/draft/undo",
    "/api/draft/next",
    "/api/draft/end",
    "/api/match/create",
    "/api/match/status",
    "/api/match/resolve/winner",
    "/api/match/resolve/prop",
    "/api/bet/place",
    "/api/wallet/adjust",
    "/api/ledger/reset",
}

draft_rooms: dict[str, DraftState] = {}


def _role_or_none(value: str | None) -> str | None:
    if value in ("", "all", "random", "none", None):
        return None
    return value


def _source(value: str | None) -> str:
    return value if value in ("website", "tab") else "website"


def _command_for(prefix: str, role: str | None, source: str) -> str:
    if role is None:
        return f".{prefix}"
    return f".{prefix}{ROLE_CODES[role]}{'t' if source == 'tab' else 'w'}"


def god_slug(name: str) -> str:
    slug = name.lower().replace("'", "").replace("'", "")
    return re.sub(r"\s+", "-", slug.strip())


def _god_payload(name: str, role: str | None, source: str, prefix: str = "rg") -> dict:
    return {
        "name": name,
        "role": role,
        "source": source,
        "command": _command_for(prefix, role, source),
        "imageUrl": f"https://www.smitefire.com/images/v2/god/icon/{god_slug(name)}.png",
    }


def _build_payload(items: list[str], role: str, build_type: str | None, count: int) -> dict:
    return {
        "role": role,
        "type": build_type,
        "count": count,
        "items": items,
        "command": _build_command(role, build_type, count),
    }


def _build_command(role: str, build_type: str | None, count: int) -> str:
    suffix = "" if count == 6 else f" {count}"
    if role == "chaos":
        return f".rc{suffix}"
    if role == "support":
        return f".sup{suffix}"
    if role == "adc":
        variant = {"standard": "", "str": "str", "hyb": "hyb"}.get(build_type, "")
        return f".adc{variant}{suffix}"
    prefix = {"mid": "mid", "jungle": "jung", "solo": "solo"}[role]
    return f".{prefix}{build_type or ''}{suffix}"


def _draft_payload(draft: DraftState) -> dict:
    game = draft.current_game
    turn = game.current_turn()
    return {
        "draftId": draft.draft_id,
        "gameNumber": game.game_number,
        "phase": get_phase_label(game.step),
        "step": game.step,
        "complete": game.is_complete(),
        "currentTurn": None if turn is None else {"team": turn[0], "action": turn[1]},
        "blueCaptain": draft.blue_captain,
        "redCaptain": draft.red_captain,
        "bans": {"blue": list(game.bans["blue"]), "red": list(game.bans["red"])},
        "picks": {"blue": list(game.picks["blue"]), "red": list(game.picks["red"])},
        "fearlessPool": sorted(draft.fearless_pool),
        "unavailableGods": sorted(draft.get_unavailable_gods()),
    }


def _execute_intent(message: str) -> dict:
    intent = parser.parse(message)
    if intent is None:
        return {"kind": "unknown", "message": "Command not recognized."}

    if intent["kind"] == "god":
        role = intent["role"]
        source = intent["source"]
        god = picker.pick_god(loader.gods(), role, source)
        return {"kind": "god", "god": _god_payload(god, role, source)}

    if intent["kind"] == "roll5":
        role = intent["role"]
        source = intent["source"]
        gods = picker.pick_team(loader.gods(), role, source)
        return {"kind": "roll5", "gods": [_god_payload(g, role, source, "roll5") for g in gods]}

    if intent["kind"] == "build":
        items = picker.pick_build(loader.builds(), intent["role"], intent["type"], intent["count"])
        return {"kind": "build", "build": _build_payload(items, intent["role"], intent["type"], intent["count"])}

    return {"kind": intent["kind"], "message": "This command exists in Discord but is not implemented in the web API yet."}


class Handler(BaseHTTPRequestHandler):
    server_version = "GodforgeWebAPI/0.1"

    def do_OPTIONS(self):
        self._send_json({"ok": True})

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        try:
            if parsed.path == "/api/health":
                self._send_json({"ok": True, "service": "godforge-web-api"})
            elif parsed.path == "/api/auth/status":
                self._send_json({"ok": True, "authenticated": self._is_authenticated(), "configured": _auth_configured()})
            elif parsed.path == "/api/gods/roll":
                role = _role_or_none(_first(query, "role"))
                source = _source(_first(query, "source"))
                god = picker.pick_god(loader.gods(), role, source)
                self._send_json({"ok": True, "god": _god_payload(god, role, source)})
            elif parsed.path == "/api/gods/roll5":
                role = _role_or_none(_first(query, "role"))
                source = _source(_first(query, "source"))
                gods = picker.pick_team(loader.gods(), role, source)
                self._send_json({"ok": True, "gods": [_god_payload(g, role, source, "roll5") for g in gods]})
            elif parsed.path == "/api/builds/roll":
                role = _first(query, "role") or "adc"
                build_type = _first(query, "type") or ("standard" if role == "adc" else None)
                count = int(_first(query, "count") or "6")
                items = picker.pick_build(loader.builds(), role, build_type, count)
                self._send_json({"ok": True, "build": _build_payload(items, role, build_type, count)})
            elif parsed.path == "/api/ledger":
                if not self._require_auth():
                    return
                self._send_json(ledger_utils.load_ledger())
            elif parsed.path == "/api/wallets":
                if not self._require_auth():
                    return
                self._send_json(wallet_utils.load_wallets())
            elif parsed.path.startswith("/api/"):
                self._send_error(404, "Not found")
            else:
                self._send_static(parsed.path)
        except Exception as exc:
            self._send_error(400, str(exc))

    def do_POST(self):
        parsed = urlparse(self.path)

        try:
            body = self._read_body()
            if parsed.path == "/api/auth/login":
                self._login(body)
            elif parsed.path == "/api/auth/logout":
                self._logout()
            elif parsed.path in PROTECTED_POST_PATHS and not self._require_auth():
                return
            elif parsed.path == "/api/command":
                self._send_json({"ok": True, "result": _execute_intent(body.get("message", ""))})
            elif parsed.path == "/api/draft/start":
                draft = DraftState(
                    blue_captain_id=1,
                    blue_captain_name=body.get("blueCaptainName") or "Blue Captain",
                    red_captain_id=2,
                    red_captain_name=body.get("redCaptainName") or "Red Captain",
                    guild_id=0,
                    guild_name="Web Draft",
                    channel_id=0,
                    channel_name="web",
                )
                draft_rooms[draft.draft_id] = draft
                self._send_json({"ok": True, "draft": _draft_payload(draft)})
            elif parsed.path == "/api/draft/action":
                draft = _get_draft(body)
                god_input = body.get("god", "")
                resolved, resolve_error = resolve_god_name(god_input)
                if resolve_error or not resolved:
                    raise ValueError(resolve_error or f"Could not match god: {god_input}")
                turn = draft.get_current_team_and_action()
                if turn is None:
                    raise ValueError("Draft game is complete.")
                requested = body.get("action")
                if requested and requested != turn[1]:
                    raise ValueError(f"Current turn is {turn[0]} {turn[1]}, not {requested}.")
                if resolved in draft.get_unavailable_gods():
                    raise ValueError(f"{resolved} is already unavailable in this draft.")
                team, action = draft.execute_step(resolved)
                self._send_json({"ok": True, "action": {"team": team, "type": action, "god": resolved}, "draft": _draft_payload(draft)})
            elif parsed.path == "/api/draft/undo":
                draft = _get_draft(body)
                undone = draft.undo()
                self._send_json({"ok": True, "undone": undone, "draft": _draft_payload(draft)})
            elif parsed.path == "/api/draft/next":
                draft = _get_draft(body)
                error = draft.advance_game()
                if error:
                    raise ValueError(error)
                self._send_json({"ok": True, "draft": _draft_payload(draft)})
            elif parsed.path == "/api/draft/end":
                draft = _get_draft(body)
                export = draft.end()
                draft_rooms.pop(draft.draft_id, None)
                self._send_json({"ok": True, "export": export})
            elif parsed.path == "/api/match/create":
                team1 = _required_str(body, "team1")
                team2 = _required_str(body, "team2")
                match = ledger_utils.create_match(team1, team2)
                self._send_json({"ok": True, "match": match})
            elif parsed.path == "/api/match/status":
                match_id = _match_id(body)
                status = _required_str(body, "status")
                if status not in MATCH_STATUSES:
                    raise ValueError(f"Invalid match status: {status}")
                if ledger_utils.get_match(match_id) is None:
                    self._send_error(404, f"Match not found: {match_id}")
                    return
                ledger_utils.set_match_status(match_id, status)
                self._send_json({"ok": True, "match": ledger_utils.get_match(match_id)})
            elif parsed.path == "/api/match/resolve/winner":
                match_id = _match_id(body)
                winner = _required_str(body, "winner")
                if ledger_utils.get_match(match_id) is None:
                    self._send_error(404, f"Match not found: {match_id}")
                    return
                payouts = ledger_utils.resolve_win_bets(match_id, winner)
                wallet_utils.apply_payouts(payouts)
                self._send_json({"ok": True, "match": ledger_utils.get_match(match_id), "payouts": payouts})
            elif parsed.path == "/api/match/resolve/prop":
                match_id = _match_id(body)
                player = _required_str(body, "player")
                stat = _required_str(body, "stat").lower()
                actual_value = float(body.get("actual_value", body.get("actualValue", "")))
                if ledger_utils.get_match(match_id) is None:
                    self._send_error(404, f"Match not found: {match_id}")
                    return
                payouts, had_bets = ledger_utils.resolve_prop_bets(match_id, player, stat, actual_value)
                wallet_utils.apply_payouts(payouts)
                self._send_json({"ok": True, "match": ledger_utils.get_match(match_id), "payouts": payouts, "had_bets": had_bets})
            elif parsed.path == "/api/bet/place":
                result = _place_bet(body)
                self._send_json({"ok": True, **result})
            elif parsed.path == "/api/wallet/adjust":
                wallet = _adjust_wallet(body)
                self._send_json({"ok": True, "wallet": wallet})
            elif parsed.path == "/api/ledger/reset":
                ledger = ledger_utils.load_ledger()
                cleared = len(ledger.get("matches", []))
                ledger_utils.reset_ledger()
                self._send_json({"ok": True, "cleared": cleared})
            else:
                self._send_error(404, "Not found")
        except Exception as exc:
            self._send_error(400, str(exc))

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def _send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, message: str):
        self._send_json({"ok": False, "error": message}, status)

    def _send_static(self, request_path: str):
        file_path = _static_path(request_path)
        if file_path is None:
            self._send_error(404, "Not found")
            return

        data = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if file_path.suffix in (".html", ".css", ".js", ".json"):
            content_type += "; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _login(self, body: dict):
        configured = _auth_configured()
        password = str(body.get("password", ""))
        expected = _admin_password()

        if not configured:
            self._send_error(503, "Admin password is not configured.")
            return

        if not hmac.compare_digest(password, expected):
            self._send_error(401, "Invalid admin password.")
            return

        token = _sign_session(int(time.time()) + SESSION_MAX_AGE)
        payload = {"ok": True, "authenticated": True}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Set-Cookie", _cookie_header(token))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _logout(self):
        data = json.dumps({"ok": True, "authenticated": False}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _is_authenticated(self) -> bool:
        return _verify_session(_cookies(self.headers.get("Cookie", "")).get(SESSION_COOKIE, ""))

    def _require_auth(self) -> bool:
        if self._is_authenticated():
            return True
        self._send_error(401, "Admin login required.")
        return False

    def log_message(self, format, *args):  # noqa: A002
        print(f"{self.address_string()} - {format % args}")


def _first(query: dict, key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def _get_draft(body: dict) -> DraftState:
    draft_id = body.get("draftId")
    draft = draft_rooms.get(draft_id)
    if not draft or not draft.active:
        raise ValueError("Draft not found. Start a new web draft.")
    return draft


def _required_str(body: dict, key: str) -> str:
    value = str(body.get(key, "")).strip()
    if not value:
        raise ValueError(f"Missing required field: {key}")
    return value


def _match_id(body: dict) -> str:
    return _required_str(body, "match_id" if "match_id" in body else "matchId")


def _wallet_user(body: dict) -> tuple[int, str]:
    username = str(body.get("username") or body.get("target") or body.get("player") or "").strip()
    raw_id = body.get("user_id") or body.get("userId")

    if raw_id is None:
        raw_id = username

    if not username:
        username = str(raw_id).strip()

    if not username:
        raise ValueError("Missing required field: target")

    try:
        user_id = int(raw_id)
    except (TypeError, ValueError):
        user_id = _stable_user_id(username)

    return user_id, username


def _stable_user_id(username: str) -> int:
    total = 0
    for index, char in enumerate(username.lower(), start=1):
        total += index * ord(char)
    return total


def _adjust_wallet(body: dict) -> dict:
    user_id, username = _wallet_user(body)
    action = _required_str(body, "action").lower()
    amount = int(body.get("amount", 0))

    wallet_utils.ensure_wallet(user_id, username)

    if action in ("give", "add", "credit"):
        balance = wallet_utils.update_balance(user_id, abs(amount))
    elif action in ("take", "subtract", "debit"):
        balance = wallet_utils.update_balance(user_id, -abs(amount))
    elif action == "set":
        balance = wallet_utils.set_balance(user_id, amount)
    else:
        raise ValueError(f"Invalid wallet action: {action}")

    return {"user_id": user_id, "username": username, "balance": balance}


def _place_bet(body: dict) -> dict:
    match_id = _match_id(body)
    match = ledger_utils.get_match(match_id)
    if match is None:
        raise ValueError(f"Match not found: {match_id}")
    if match.get("status") != "betting_open":
        raise ValueError("Betting is closed for this match")

    amount = int(body.get("amount", 0))
    if amount <= 0:
        raise ValueError("Bet amount must be greater than zero")

    user_id, username = _wallet_user(body)
    balance = wallet_utils.seed_wallet(user_id, username)
    if balance <= 0:
        raise ValueError(f"{username} has {balance} points and cannot place bets")
    if amount > balance:
        raise ValueError(f"{username} only has {balance} points")

    bet_type = _required_str(body, "type").lower()
    if bet_type == "win":
        team = _match_team(_required_str(body, "team"), match)
        if team is None:
            teams = match["teams"]
            raise ValueError(f"Unknown team. Match {match_id} has {teams['team1']} vs {teams['team2']}")
        bet = {
            "type": "win",
            "user_id": user_id,
            "username": username,
            "team": team,
            "amount": amount,
        }
    elif bet_type == "prop":
        direction = _required_str(body, "direction").lower()
        if direction not in ("over", "under"):
            raise ValueError("Direction must be over or under")
        bet = {
            "type": "prop",
            "user_id": user_id,
            "username": username,
            "player": _required_str(body, "player"),
            "stat": _required_str(body, "stat").lower(),
            "direction": direction,
            "threshold": float(body.get("threshold", "")),
            "amount": amount,
        }
    else:
        raise ValueError(f"Invalid bet type: {bet_type}")

    wallet_utils.update_balance(user_id, -amount)
    ledger_utils.add_bet(match_id, bet)
    return {
        "bet": bet,
        "match": ledger_utils.get_match(match_id),
        "wallet": {"user_id": user_id, "username": username, "balance": wallet_utils.get_balance(user_id)},
    }


def _match_team(team_input: str, match: dict) -> str | None:
    needle = _normalize_team(team_input)
    teams = [match["teams"]["team1"], match["teams"]["team2"]]
    for team in sorted(teams, key=len, reverse=True):
        if needle == _normalize_team(team):
            return team
    for team in sorted(teams, key=len, reverse=True):
        normalized = _normalize_team(team)
        if needle in normalized or normalized in needle:
            return team
    return None


def _normalize_team(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lstrip("@").lower())


def _admin_password() -> str:
    return os.getenv("GODFORGE_ADMIN_PASSWORD", "")


def _auth_configured() -> bool:
    return bool(_admin_password())


def _auth_secret() -> bytes:
    seed = _admin_password() or os.getenv("DISCORD_TOKEN", "godforge-local-dev")
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _sign_session(expires_at: int) -> str:
    raw = str(expires_at).encode("utf-8")
    signature = hmac.new(_auth_secret(), raw, hashlib.sha256).hexdigest()
    token = f"{expires_at}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(token).decode("ascii")


def _verify_session(token: str) -> bool:
    if not token or not _auth_configured():
        return False
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        expires_raw, signature = decoded.split(":", 1)
        expires_at = int(expires_raw)
    except (ValueError, UnicodeDecodeError):
        return False
    if expires_at < int(time.time()):
        return False
    expected = hmac.new(_auth_secret(), expires_raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _cookie_header(token: str) -> str:
    return f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_MAX_AGE}; HttpOnly; SameSite=Lax"


def _cookies(raw_cookie: str) -> dict[str, str]:
    cookies = {}
    for part in raw_cookie.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def _static_path(request_path: str) -> Path | None:
    path = request_path.strip("/") or "index.html"
    candidate = (WEB_ROOT / path).resolve()
    root = WEB_ROOT.resolve()

    if not str(candidate).startswith(str(root)):
        return None
    if candidate.is_dir():
        candidate = candidate / "index.html"
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def create_server(host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host or HOST, port or PORT), Handler)


def main():
    server = create_server()
    print(f"Godforge web API running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
