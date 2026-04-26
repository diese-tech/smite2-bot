"""
GodForge — Smite 2 Discord Bot

Session system: when a session is active in a channel, .rg and .roll5
produce interactive embeds with reactions for tracking random god picks.

Draft system: integrates with an Activity backend to facilitate competitive
drafting. Captains participate in a Discord Activity while the bot mirrors
draft state as a live, updating embed in the channel.

Sessions and drafts are mutually exclusive per channel.

Run with: python bot.py
"""

import asyncio
import io
import json
import logging
import os

import aiohttp
import discord
from discord.ext import tasks
from dotenv import load_dotenv

from utils import formatter, loader, parser, picker
from utils.formatter import NUMBER_EMOJIS
from utils.resolver import resolve_god_name
from utils.session import SessionManager

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
ACTIVITY_BACKEND_URL = os.getenv("ACTIVITY_BACKEND_URL", "").rstrip("/")
ACTIVITY_API_KEY = os.getenv("ACTIVITY_API_KEY", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("godforge")

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
client = discord.Client(intents=intents)

sessions = SessionManager()

# Track metadata for reaction-enabled messages (sessions only).
_tracked_messages = {}

# Activity backend draft tracking (in-memory, resets on restart).
_match_ids: dict[int, str] = {}           # channel_id -> match_id
_match_channels: dict[str, int] = {}      # match_id -> channel_id
_snapshots: dict[int, dict] = {}          # channel_id -> latest state snapshot
_board_message_ids: dict[int, int] = {}   # channel_id -> embed message id
_ws_tasks: dict[int, asyncio.Task] = {}   # channel_id -> listener task

# Server-specific reports channel.
REPORTS_CHANNELS = {
    1129404279808073758: 1496553890181550110,  # GodForge server -> #godforge-reports
}


def _channel_has_active(channel_id: int) -> str | None:
    if sessions.get(channel_id):
        return "session"
    if channel_id in _match_ids:
        return "draft"
    return None


def _cleanup_draft(channel_id: int) -> None:
    match_id = _match_ids.pop(channel_id, None)
    if match_id:
        _match_channels.pop(match_id, None)
    _snapshots.pop(channel_id, None)
    _board_message_ids.pop(channel_id, None)
    task = _ws_tasks.pop(channel_id, None)
    if task:
        task.cancel()


# ── Activity backend helpers ──────────────────────────────────────────────────

def _activity_headers() -> dict:
    return {"X-Api-Key": ACTIVITY_API_KEY, "Content-Type": "application/json"}


async def _activity_post(path: str, data: dict | None = None) -> dict | None:
    url = ACTIVITY_BACKEND_URL + path
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data or {}, headers=_activity_headers()) as resp:
                return await resp.json()
    except Exception as e:
        log.error(f"Activity backend POST {path} failed: {e}")
        return None


async def _activity_get(path: str) -> dict | None:
    url = ACTIVITY_BACKEND_URL + path
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=_activity_headers()) as resp:
                return await resp.json()
    except Exception as e:
        log.error(f"Activity backend GET {path} failed: {e}")
        return None


async def _update_embed_from_snapshot(snapshot: dict, channel) -> None:
    channel_id = channel.id
    embed = formatter.format_board_from_snapshot(snapshot)
    msg_id = _board_message_ids.get(channel_id)
    if msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed)
            return
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
    sent = await channel.send(embed=embed)
    _board_message_ids[channel_id] = sent.id


async def _post_export(export: dict, channel) -> None:
    draft_id = export.get("draftId", "unknown")
    embed = formatter.format_draft_end_from_export(export)
    await channel.send(embed=embed)

    filename = f"draft_{draft_id}.json"
    json_bytes = json.dumps(export, indent=2).encode("utf-8")
    file = discord.File(io.BytesIO(json_bytes), filename=filename)
    await channel.send(f"📎 Draft record: `{filename}`", file=file)

    guild_id = channel.guild.id if channel.guild else None
    if guild_id and guild_id in REPORTS_CHANNELS:
        reports_ch = client.get_channel(REPORTS_CHANNELS[guild_id])
        if reports_ch:
            try:
                await reports_ch.send(embed=embed)
                report_file = discord.File(io.BytesIO(json_bytes), filename=filename)
                await reports_ch.send(f"📎 Draft record: `{filename}`", file=report_file)
            except (discord.Forbidden, discord.HTTPException) as e:
                log.warning(f"Failed to post to reports channel: {e}")


async def _listen_draft_ws(match_id: str, channel_id: int) -> None:
    """Connect to the Activity backend WebSocket and mirror state to the embed."""
    ws_url = ACTIVITY_BACKEND_URL.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                await ws.send_json({"type": "join", "matchId": match_id})
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data["type"] == "state":
                            _snapshots[channel_id] = data["state"]
                            channel = client.get_channel(channel_id)
                            if channel:
                                await _update_embed_from_snapshot(data["state"], channel)
                        elif data["type"] == "export":
                            if channel_id in _match_ids:
                                channel = client.get_channel(channel_id)
                                if channel:
                                    await _post_export(data["export"], channel)
                                _cleanup_draft(channel_id)
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log.error(f"WS listener error for {match_id}: {e}")
    finally:
        _ws_tasks.pop(channel_id, None)


# ── Discord events ────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    log.info(f"Logged in as {client.user} (id: {client.user.id})")
    log.info(f"Connected to {len(client.guilds)} guild(s)")
    if not cleanup_task.is_running():
        cleanup_task.start()


@tasks.loop(minutes=5)
async def cleanup_task():
    expired_sessions = sessions.cleanup_expired()
    if expired_sessions:
        to_remove = [mid for mid, info in _tracked_messages.items()
                     if info.get("channel_id") in expired_sessions]
        for mid in to_remove:
            del _tracked_messages[mid]
        log.info(f"Cleaned up {len(expired_sessions)} expired session(s)")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user or message.author.bot:
        return
    if not message.content.startswith("."):
        return

    intent = parser.parse(message.content)
    if intent is None:
        return

    channel_id = message.channel.id

    try:
        if intent["kind"] == "help":
            response = formatter.format_help()

        elif intent["kind"] == "session":
            async with sessions.get_lock(channel_id):
                response = await _handle_session(intent, channel_id)

        elif intent["kind"] == "draft":
            response = await _handle_draft(intent, message)
            if response is None:
                return

        elif intent["kind"] == "draft_action":
            response = await _handle_draft_action(intent, message)
            if response is None:
                return

        elif intent["kind"] == "god":
            async with sessions.get_lock(channel_id):
                session = sessions.get(channel_id)
                exclude = session.get_excluded_gods() if session else None
                god = picker.pick_god(loader.gods(), intent["role"], intent["source"],
                                      exclude=exclude)
                if session:
                    embed = formatter.format_rg_session(god, intent["role"], intent["source"])
                    sent = await message.channel.send(embed=embed)
                    session.register_rg(sent.id, god, intent["role"], intent["source"])
                    _tracked_messages[sent.id] = {
                        "kind": "rg", "god": god, "channel_id": channel_id,
                        "role": intent["role"], "source": intent["source"],
                        "author_id": message.author.id,
                        "author_name": message.author.display_name,
                    }
                    await sent.add_reaction("✅")
                    await sent.add_reaction("❌")
                    return
                else:
                    response = formatter.format_god(god, intent["role"], intent["source"])

        elif intent["kind"] == "roll5":
            async with sessions.get_lock(channel_id):
                session = sessions.get(channel_id)
                exclude = session.get_excluded_gods() if session else None
                gods = picker.pick_team(loader.gods(), intent["role"], intent["source"],
                                        exclude=exclude)
                if session:
                    embed = formatter.format_roll5_session(gods, intent["role"], intent["source"])
                    sent = await message.channel.send(embed=embed)
                    session.register_roll5(sent.id, gods)
                    _tracked_messages[sent.id] = {
                        "kind": "roll5", "gods": gods, "channel_id": channel_id,
                        "role": intent["role"], "source": intent["source"],
                        "author_id": message.author.id,
                        "author_name": message.author.display_name,
                    }
                    for emoji in NUMBER_EMOJIS:
                        await sent.add_reaction(emoji)
                    return
                else:
                    response = formatter.format_team(gods, intent["role"], intent["source"])

        elif intent["kind"] == "build":
            items = picker.pick_build(
                loader.builds(), intent["role"], intent["type"], intent["count"]
            )
            response = formatter.format_build(items, intent["role"], intent["type"])

        else:
            return

    except ValueError as e:
        response = formatter.format_error(str(e))
    except FileNotFoundError as e:
        log.error(f"Data file missing: {e}")
        response = formatter.format_error("Data file missing. Check bot logs.")
    except Exception as e:
        log.exception(f"Unexpected error handling '{message.content}'")
        response = formatter.format_error("Something went wrong. Check bot logs.")

    if isinstance(response, discord.Embed):
        await message.channel.send(embed=response)
    else:
        await message.channel.send(response)


# ── Session handlers ──────────────────────────────────────────────────────────

async def _handle_session(intent: dict, channel_id: int):
    action = intent["action"]

    if action == "start":
        active = _channel_has_active(channel_id)
        if active == "draft":
            return formatter.format_error("A draft is active in this channel. Use `.draft end` first.")
        if sessions.start(channel_id):
            return "✅ Draft session started! Use `.session end` when done."
        return formatter.format_error("A session is already active. Use `.session end` first.")

    elif action == "end":
        session = sessions.end(channel_id)
        if session:
            to_remove = [mid for mid, info in _tracked_messages.items()
                         if info.get("channel_id") == channel_id]
            for mid in to_remove:
                del _tracked_messages[mid]
            return formatter.format_session_end(session.picks)
        return formatter.format_error("No active session in this channel.")

    elif action == "show":
        session = sessions.get(channel_id)
        if session:
            return formatter.format_session_show(session.picks)
        return formatter.format_error("No active session in this channel.")

    elif action == "reset":
        if sessions.reset(channel_id):
            to_remove = [mid for mid, info in _tracked_messages.items()
                         if info.get("channel_id") == channel_id]
            for mid in to_remove:
                del _tracked_messages[mid]
            return "🔄 Session picks cleared. Session is still active."
        return formatter.format_error("No active session in this channel.")


# ── Draft handlers ────────────────────────────────────────────────────────────

async def _handle_draft(intent: dict, message: discord.Message):
    action = intent["action"]
    channel_id = message.channel.id

    if not ACTIVITY_BACKEND_URL:
        return formatter.format_error("Activity backend not configured. Set ACTIVITY_BACKEND_URL.")

    if action == "start":
        active = _channel_has_active(channel_id)
        if active == "session":
            return formatter.format_error("A session is active. Use `.session end` first.")
        if active == "draft":
            return formatter.format_error("A draft is already active. Use `.draft end` first.")

        mentions = message.mentions
        if len(mentions) < 2:
            return formatter.format_error("Usage: `.draft start @blue_captain @red_captain`")
        blue_user, red_user = mentions[0], mentions[1]
        if blue_user.id == red_user.id:
            return formatter.format_error("Blue and red captains must be different users.")

        result = await _activity_post("/api/draft/start", {
            "blueCaptainId": str(blue_user.id),
            "blueCaptainName": blue_user.display_name,
            "redCaptainId": str(red_user.id),
            "redCaptainName": red_user.display_name,
        })
        if not result or "error" in result:
            err = result.get("error") if result else "Activity backend unreachable."
            return formatter.format_error(err)

        match_id = result["matchId"]
        _match_ids[channel_id] = match_id
        _match_channels[match_id] = channel_id

        snapshot = result["state"]
        _snapshots[channel_id] = snapshot
        embed = formatter.format_board_from_snapshot(snapshot)
        sent = await message.channel.send(
            f"🎮 Draft `{match_id}` started — open the Activity and enter this ID to join",
            embed=embed,
        )
        _board_message_ids[channel_id] = sent.id

        task = asyncio.create_task(_listen_draft_ws(match_id, channel_id))
        _ws_tasks[channel_id] = task
        log.info(f"Draft {match_id} started: 🔵 {blue_user.display_name} vs 🔴 {red_user.display_name}")
        return None

    elif action == "show":
        match_id = _match_ids.get(channel_id)
        if not match_id:
            return formatter.format_error("No active draft in this channel.")
        snapshot = await _activity_get(f"/api/draft/{match_id}")
        if not snapshot or "error" in snapshot:
            return formatter.format_error("Could not retrieve draft state.")
        return formatter.format_board_from_snapshot(snapshot)

    elif action == "undo":
        match_id = _match_ids.get(channel_id)
        if not match_id:
            return formatter.format_error("No active draft in this channel.")
        result = await _activity_post(f"/api/draft/{match_id}/undo")
        if not result or "error" in result:
            return formatter.format_error(result.get("error", "Nothing to undo.") if result else "Backend unreachable.")
        return None  # WS listener updates the embed

    elif action == "next":
        match_id = _match_ids.get(channel_id)
        if not match_id:
            return formatter.format_error("No active draft in this channel.")
        result = await _activity_post(f"/api/draft/{match_id}/next")
        if not result or "error" in result:
            return formatter.format_error(result.get("error", "Cannot advance game.") if result else "Backend unreachable.")
        return None  # WS listener updates the embed

    elif action == "end":
        match_id = _match_ids.get(channel_id)
        if not match_id:
            return formatter.format_error("No active draft in this channel.")
        result = await _activity_post(f"/api/draft/{match_id}/end")
        if not result or "error" in result:
            return formatter.format_error(result.get("error", "Failed to end draft.") if result else "Backend unreachable.")
        _cleanup_draft(channel_id)
        await _post_export(result, message.channel)
        log.info(f"Draft {match_id} ended via text command")
        return None


async def _handle_draft_action(intent: dict, message: discord.Message):
    """Handle .ban / .pick routed through the Activity backend."""
    channel_id = message.channel.id
    match_id = _match_ids.get(channel_id)

    if not match_id:
        return formatter.format_error("No active draft. Use `.draft start` first.")

    snapshot = _snapshots.get(channel_id)
    if not snapshot:
        return formatter.format_error("Draft state loading — try again in a moment.")

    if snapshot.get("isClaiming"):
        return formatter.format_error("Claiming phase active. Use `.draft undo` to go back.")

    turn = snapshot.get("currentTurn")
    if not turn:
        return formatter.format_error("Game complete. Use `.draft next` or `.draft end`.")

    action = intent["action"]
    if action != turn["action"]:
        return formatter.format_error(f"It's time to **{turn['action']}**, not {action}.")

    expected_captain_id = snapshot.get("currentCaptainId")
    if expected_captain_id and str(message.author.id) != expected_captain_id:
        team = turn["team"]
        captain_name = (snapshot["blueCaptain"]["name"] if team == "blue"
                        else snapshot["redCaptain"]["name"])
        return formatter.format_error(f"It's **{captain_name}**'s turn ({team}).")

    god, error = resolve_god_name(intent["god_input"])
    if error:
        return formatter.format_error(error)

    result = await _activity_post(f"/api/draft/{match_id}/action", {
        "god": god,
        "userId": str(message.author.id),
    })
    if not result or "error" in result:
        return formatter.format_error(result.get("error", f"{god} is unavailable.") if result else "Backend unreachable.")

    log.info(f"Draft {match_id}: {turn['team']} {turn['action']} {god} via text command")
    return None  # WS listener updates the embed


# ── Reaction handler ──────────────────────────────────────────────────────────

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == client.user.id:
        return
    message_id = payload.message_id
    if message_id not in _tracked_messages:
        return

    info = _tracked_messages[message_id]
    channel_id = info["channel_id"]
    emoji = str(payload.emoji)

    if info["kind"] in ("roll5", "rg"):
        await _handle_session_reaction(payload, info, message_id, channel_id, emoji)


async def _handle_session_reaction(payload, info, message_id, channel_id, emoji):
    async with sessions.get_lock(channel_id):
        session = sessions.get(channel_id)
        if not session:
            return
        if session.is_reaction_processed(message_id, emoji):
            return
        session.mark_reaction_processed(message_id, emoji)

        channel = client.get_channel(channel_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            _tracked_messages.pop(message_id, None)
            return

        author_id = info["author_id"]
        author_name = info["author_name"]

        if info["kind"] == "roll5" and emoji in NUMBER_EMOJIS:
            index = NUMBER_EMOJIS.index(emoji)
            god = session.lock_roll5_pick(message_id, index, author_id, author_name)
            if god:
                embed = formatter.format_roll5_locked(
                    info["gods"], index, author_name, info["role"], info["source"],
                )
                await msg.edit(embed=embed)
                try:
                    await msg.clear_reactions()
                except discord.Forbidden:
                    pass
                _tracked_messages.pop(message_id, None)

        elif info["kind"] == "rg":
            if emoji == "✅":
                god = session.lock_rg_pick(message_id, author_id, author_name)
                if god:
                    embed = formatter.format_rg_locked(god, author_name, info["role"], info["source"])
                    await msg.edit(embed=embed)
                    try:
                        await msg.clear_reactions()
                    except discord.Forbidden:
                        pass
                    _tracked_messages.pop(message_id, None)
            elif emoji == "❌":
                god = session.discard_rg(message_id)
                if god:
                    embed = formatter.format_rg_discarded(god, info["role"], info["source"])
                    await msg.edit(embed=embed)
                    try:
                        await msg.clear_reactions()
                    except discord.Forbidden:
                        pass
                    _tracked_messages.pop(message_id, None)


def main():
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN not set.")
    client.run(TOKEN)


if __name__ == "__main__":
    main()
