"""
GodForge — Smite 2 Discord Bot

Session system: when a session is active in a channel, .rg and .roll5
produce interactive embeds with reactions for tracking random god picks.

Draft system: fearless competitive drafting with enforced turn order,
unlimited undo, semi-fearless carry-over, and JSON export.

Sessions and drafts are mutually exclusive per channel.

Run with: python bot.py
"""

import os
import io
import json
import re
import logging
import discord
from discord.ext import tasks
from datetime import datetime, timezone
from dotenv import load_dotenv

from utils import parser, picker, loader, formatter
from utils.formatter import NUMBER_EMOJIS
from utils.session import SessionManager
from utils.draft import DraftManager
from utils.resolver import resolve_god_name
from utils import ledger as ledger_utils
from utils import wallet as wallet_utils

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Channel IDs for the betting system.
# Set these in .env (or leave 0 to disable that feature).
BETTING_LEDGER_CHANNEL_ID = int(os.getenv("BETTING_LEDGER_CHANNEL_ID", "0"))
PLACE_BETS_CHANNEL_ID = int(os.getenv("PLACE_BETS_CHANNEL_ID", "0"))

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

# Per-channel tracking (in-memory, resets on restart).
sessions = SessionManager()
drafts = DraftManager()

# Track metadata for reaction-enabled messages (sessions only).
_tracked_messages = {}

# Server-specific reports channel. When a draft ends in a server listed here,
# the JSON export is also posted to this channel. Other servers are unaffected.
# Format: guild_id: reports_channel_id
REPORTS_CHANNELS = {
    1129404279808073758: 1496553890181550110,  # GodForge server -> #godforge-reports
}


def _channel_has_active(channel_id: int) -> str | None:
    """Check if a channel has an active session or draft. Returns type string or None."""
    if sessions.get(channel_id):
        return "session"
    if drafts.get(channel_id):
        return "draft"
    return None


@client.event
async def on_ready():
    log.info(f"Logged in as {client.user} (id: {client.user.id})")
    log.info(f"Connected to {len(client.guilds)} guild(s)")
    if not cleanup_task.is_running():
        cleanup_task.start()
    # Re-register the persistent betting embed view so buttons survive restarts.
    client.add_view(BettingLedgerView())
    try:
        await update_betting_embed()
    except Exception as exc:
        log.warning(f"Could not refresh betting embed on startup: {exc}")


@tasks.loop(minutes=5)
async def cleanup_task():
    """Periodically remove expired sessions and drafts."""
    expired_sessions = sessions.cleanup_expired()
    if expired_sessions:
        to_remove = [mid for mid, info in _tracked_messages.items()
                     if info.get("channel_id") in expired_sessions]
        for mid in to_remove:
            del _tracked_messages[mid]
        log.info(f"Cleaned up {len(expired_sessions)} expired session(s)")

    expired_drafts = drafts.cleanup_expired()
    if expired_drafts:
        log.info(f"Cleaned up {len(expired_drafts)} expired draft(s)")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user or message.author.bot:
        return
    if not message.content.startswith("."):
        return

    # ---- Betting system commands (bypass parser — not handled there) ----
    _first = message.content[1:].split()[0].lower() if message.content[1:].split() else ""
    if _first == "match":
        await _handle_match_command(message)
        return
    if _first == "bet":
        await _handle_bet_command(message)
        return
    if _first == "wallet":
        await _handle_wallet_command(message)
        return
    if _first == "ledger":
        await _handle_ledger_command(message)
        return
    # ---- End betting routing ----

    intent = parser.parse(message.content)
    if intent is None:
        return

    channel_id = message.channel.id

    try:
        # ---- Help ----
        if intent["kind"] == "help":
            response = formatter.format_help()

        # ---- Session management ----
        elif intent["kind"] == "session":
            async with sessions.get_lock(channel_id):
                response = await _handle_session(intent, channel_id)

        # ---- Draft management ----
        elif intent["kind"] == "draft":
            async with drafts.get_lock(channel_id):
                response = await _handle_draft(intent, message)
                if response is None:
                    return  # already handled (e.g., board posted directly)

        # ---- Ban / Pick (draft) ----
        elif intent["kind"] == "draft_action":
            async with drafts.get_lock(channel_id):
                response = await _handle_draft_action(intent, message)
                if response is None:
                    return

        # ---- God pick ----
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
                    log.info(f"Session rg: {message.author.display_name} rolled {god} "
                             f"in channel {channel_id}")
                    return
                else:
                    response = formatter.format_god(god, intent["role"], intent["source"])

        # ---- Roll5 ----
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
                    log.info(f"Session roll5: {message.author.display_name} rolled "
                             f"{gods} in channel {channel_id}")
                    return
                else:
                    response = formatter.format_team(gods, intent["role"], intent["source"])

        # ---- Build ----
        elif intent["kind"] == "build":
            items = picker.pick_build(
                loader.builds(), intent["role"], intent["type"], intent["count"]
            )
            response = formatter.format_build(items, intent["role"], intent["type"])

        else:
            return  # unknown intent kind, ignore

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


# ---------------------------------------------------------------------------
# Session handlers
# ---------------------------------------------------------------------------

async def _handle_session(intent: dict, channel_id: int):
    """Handle .session start/end/show/reset. Caller must hold session lock."""
    action = intent["action"]

    if action == "start":
        active = _channel_has_active(channel_id)
        if active == "draft":
            return formatter.format_error("A draft is active in this channel. Use `.draft end` first.")
        if sessions.start(channel_id):
            log.info(f"Session started in channel {channel_id}")
            return "✅ Draft session started! Rolls in this channel will now track picks. Use `.session end` when done."
        return formatter.format_error("A session is already active in this channel. Use `.session end` first.")

    elif action == "end":
        session = sessions.end(channel_id)
        if session:
            to_remove = [mid for mid, info in _tracked_messages.items()
                         if info.get("channel_id") == channel_id]
            for mid in to_remove:
                del _tracked_messages[mid]
            log.info(f"Session ended in channel {channel_id}: {len(session.picks)} pick(s)")
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
            log.info(f"Session reset in channel {channel_id}")
            return "🔄 Session picks cleared. Session is still active."
        return formatter.format_error("No active session in this channel.")


# ---------------------------------------------------------------------------
# Draft handlers
# ---------------------------------------------------------------------------

async def _handle_draft(intent: dict, message: discord.Message):
    """Handle .draft start/show/next/end/undo. Caller must hold draft lock.
    Returns response or None if already handled."""
    action = intent["action"]
    channel_id = message.channel.id

    if action == "start":
        # Check mutual exclusivity
        active = _channel_has_active(channel_id)
        if active == "session":
            return formatter.format_error("A session is active in this channel. Use `.session end` first.")
        if active == "draft":
            return formatter.format_error("A draft is already active in this channel. Use `.draft end` first.")

        # Extract two mentioned users
        mentions = message.mentions
        if len(mentions) < 2:
            return formatter.format_error("Usage: `.draft start @blue_captain @red_captain`")
        blue_user = mentions[0]
        red_user = mentions[1]
        if blue_user.id == red_user.id:
            return formatter.format_error("Blue and red captains must be different users.")

        guild = message.guild
        draft = drafts.start(
            channel_id,
            blue_captain_id=blue_user.id,
            blue_captain_name=blue_user.display_name,
            red_captain_id=red_user.id,
            red_captain_name=red_user.display_name,
            guild_id=guild.id if guild else 0,
            guild_name=guild.name if guild else "DM",
            channel_name=message.channel.name if hasattr(message.channel, 'name') else "unknown",
        )
        if not draft:
            return formatter.format_error("Failed to start draft.")

        # Post the living board embed
        embed = formatter.format_draft_board(draft)
        sent = await message.channel.send(embed=embed)
        draft.board_message_id = sent.id

        log.info(f"Draft {draft.draft_id} started in channel {channel_id}: "
                 f"🔵 {blue_user.display_name} vs 🔴 {red_user.display_name}")

        return None  # already posted

    elif action == "show":
        draft = drafts.get(channel_id)
        if not draft:
            return formatter.format_error("No active draft in this channel.")
        return formatter.format_draft_show(draft)

    elif action == "next":
        draft = drafts.get(channel_id)
        if not draft:
            return formatter.format_error("No active draft in this channel.")

        error = draft.advance_game()
        if error:
            return formatter.format_error(error)

        # Clean up claim tracked messages from the completed game
        for team in ("blue", "red"):
            mid = draft.claim_message_ids.get(team)
            if mid:
                _tracked_messages.pop(mid, None)

        # Post confirmation
        await message.channel.send(formatter.format_draft_next(draft))

        # Post new living board for the next game
        embed = formatter.format_draft_board(draft)
        sent = await message.channel.send(embed=embed)
        draft.board_message_id = sent.id

        log.info(f"Draft {draft.draft_id} advanced to Game {draft.current_game.game_number}")
        return None

    elif action == "end":
        draft = drafts.end(channel_id)
        if not draft:
            return formatter.format_error("No active draft in this channel.")

        export = draft.to_export_dict()

        # Post summary embed in the draft channel
        embed = formatter.format_draft_end(draft, export)
        await message.channel.send(embed=embed)

        # Attach JSON export as a file in the draft channel
        filename = draft.sanitized_filename()
        json_bytes = json.dumps(export, indent=2).encode("utf-8")
        file = discord.File(io.BytesIO(json_bytes), filename=filename)
        await message.channel.send(f"📎 Draft record: `{filename}`", file=file)

        # Also post to the server's reports channel if configured
        guild_id = message.guild.id if message.guild else None
        if guild_id and guild_id in REPORTS_CHANNELS:
            reports_ch = client.get_channel(REPORTS_CHANNELS[guild_id])
            if reports_ch:
                try:
                    await reports_ch.send(embed=embed)
                    report_file = discord.File(
                        io.BytesIO(json_bytes), filename=filename
                    )
                    await reports_ch.send(
                        f"📎 Draft record: `{filename}`", file=report_file
                    )
                    log.info(f"Draft {draft.draft_id} report posted to "
                             f"reports channel {REPORTS_CHANNELS[guild_id]}")
                except (discord.Forbidden, discord.HTTPException) as e:
                    log.warning(f"Failed to post to reports channel: {e}")

        log.info(f"Draft {draft.draft_id} ended: {len(export['games'])} game(s), "
                 f"fearless pool: {export['fearless_pool']}")
        return None

    elif action == "undo":
        draft = drafts.get(channel_id)
        if not draft:
            return formatter.format_error("No active draft in this channel.")
        result = draft.undo()
        if result is None:
            return formatter.format_error("Nothing to undo.")

        if result["type"] == "step":
            await message.channel.send(
                formatter.format_draft_undo(result["team"], result["action"], result["god"])
            )
        elif result["type"] == "claim":
            await message.channel.send(
                formatter.format_claim_undo(result["team"], result["god"], result["user_name"])
            )
            # Update the claim embed
            await _update_claim_embed(draft, result["team"], message.channel)
        elif result["type"] == "next_game":
            await message.channel.send(
                f"↩️ Undid game advance. Back to **Game {result['game_number']}**."
            )

        # Update the living board
        await _update_draft_board(draft, message.channel)
        return None


async def _handle_draft_action(intent: dict, message: discord.Message):
    """Handle .ban / .pick. Caller must hold draft lock.
    Returns response or None if already handled."""
    channel_id = message.channel.id
    draft = drafts.get(channel_id)

    if not draft:
        return formatter.format_error("No active draft in this channel. Use `.draft start` first.")

    # Check if we're in the claiming phase
    if draft.is_claiming():
        return formatter.format_error("Players are claiming gods. Use `.draft undo` if you need to fix something.")

    # Check if game is complete (and fully claimed — ready for .draft next)
    turn = draft.get_current_team_and_action()
    if turn is None:
        return formatter.format_error("Current game is complete. Use `.draft next` or `.draft end`.")

    current_team, expected_action = turn

    # Verify it's the right action type
    action = intent["action"]  # "ban" or "pick"
    if action != expected_action:
        return formatter.format_error(f"It's time to **{expected_action}**, not {action}.")

    # Verify it's the right captain's turn
    expected_captain_id = draft.get_current_captain_id()
    if message.author.id != expected_captain_id:
        captain_name = (draft.blue_captain["name"] if current_team == "blue"
                        else draft.red_captain["name"])
        return formatter.format_error(f"It's **{captain_name}**'s turn ({current_team}).")

    # Resolve god name
    god_input = intent["god_input"]
    god, error = resolve_god_name(god_input)
    if error:
        return formatter.format_error(error)

    # Check availability
    unavailable = draft.get_unavailable_gods()
    if god in unavailable:
        if god in draft.fearless_pool:
            return formatter.format_error(f"**{god}** is in the fearless pool and unavailable this set.")
        else:
            return formatter.format_error(f"**{god}** has already been {expected_action}ned this game.")

    # Execute the step
    team, action_done = draft.execute_step(god)

    # Post confirmation
    await message.channel.send(
        formatter.format_draft_action(team, action_done, god, draft.draft_id)
    )

    # Update the living board
    await _update_draft_board(draft, message.channel)

    log.info(f"Draft {draft.draft_id}: {team} {action_done} {god} "
             f"(step {draft.current_game.step}/{20})")

    # If game just completed, auto-post claim embeds
    if draft.current_game.is_complete():
        await _post_claim_embeds(draft, message.channel)

    return None


async def _update_draft_board(draft, channel):
    """Edit the living draft board embed. Falls back to posting a new one."""
    if draft.board_message_id:
        try:
            msg = await channel.fetch_message(draft.board_message_id)
            embed = formatter.format_draft_board(draft)
            await msg.edit(embed=embed)
            return
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    # Fallback: post a new board
    embed = formatter.format_draft_board(draft)
    sent = await channel.send(embed=embed)
    draft.board_message_id = sent.id


async def _post_claim_embeds(draft, channel):
    """Post claim embeds for both teams with 1️⃣-5️⃣ reactions."""
    game = draft.current_game
    for team in ("blue", "red"):
        embed = formatter.format_claim_embed(
            team, game.picks[team], game.claims[team], draft.draft_id
        )
        sent = await channel.send(embed=embed)
        draft.claim_message_ids[team] = sent.id
        # Track for reaction handling
        _tracked_messages[sent.id] = {
            "kind": "claim",
            "team": team,
            "picks": game.picks[team],
            "channel_id": channel.id,
            "draft_id": draft.draft_id,
        }
        for emoji in NUMBER_EMOJIS:
            await sent.add_reaction(emoji)
    log.info(f"Draft {draft.draft_id}: claim embeds posted for Game {game.game_number}")


async def _update_claim_embed(draft, team, channel):
    """Edit a claim embed after a player claims/unclaims."""
    msg_id = draft.claim_message_ids.get(team)
    if not msg_id:
        return
    try:
        msg = await channel.fetch_message(msg_id)
        game = draft.current_game
        embed = formatter.format_claim_embed(
            team, game.picks[team], game.claims[team], draft.draft_id
        )
        await msg.edit(embed=embed)
        # If all claimed on this team, clear reactions
        if all(god in game.claims[team] for god in game.picks[team]):
            try:
                await msg.clear_reactions()
            except discord.Forbidden:
                pass
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


# ---------------------------------------------------------------------------
# Reaction handler (sessions only)
# ---------------------------------------------------------------------------

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Handle reactions on tracked messages (session rolls + draft claims)."""
    if payload.user_id == client.user.id:
        return

    message_id = payload.message_id
    if message_id not in _tracked_messages:
        return

    info = _tracked_messages[message_id]
    channel_id = info["channel_id"]
    emoji = str(payload.emoji)

    # Route based on message kind
    if info["kind"] in ("roll5", "rg"):
        await _handle_session_reaction(payload, info, message_id, channel_id, emoji)
    elif info["kind"] == "claim":
        await _handle_claim_reaction(payload, info, message_id, channel_id, emoji)


async def _handle_session_reaction(payload, info, message_id, channel_id, emoji):
    """Handle reactions on session roll5/rg embeds."""
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

        # ---- Roll5 reaction ----
        if info["kind"] == "roll5" and emoji in NUMBER_EMOJIS:
            index = NUMBER_EMOJIS.index(emoji)
            god = session.lock_roll5_pick(message_id, index, author_id, author_name)
            if god:
                embed = formatter.format_roll5_locked(
                    info["gods"], index, author_name,
                    info["role"], info["source"],
                )
                await msg.edit(embed=embed)
                try:
                    await msg.clear_reactions()
                except discord.Forbidden:
                    pass
                _tracked_messages.pop(message_id, None)
                log.info(f"Session pick: {author_name} assigned {god} "
                         f"in channel {channel_id}")

        # ---- RG reaction ----
        elif info["kind"] == "rg":
            if emoji == "✅":
                god = session.lock_rg_pick(message_id, author_id, author_name)
                if god:
                    embed = formatter.format_rg_locked(
                        god, author_name, info["role"], info["source"],
                    )
                    await msg.edit(embed=embed)
                    try:
                        await msg.clear_reactions()
                    except discord.Forbidden:
                        pass
                    _tracked_messages.pop(message_id, None)
                    log.info(f"Session pick: {author_name} assigned {god} "
                             f"in channel {channel_id}")
            elif emoji == "❌":
                god = session.discard_rg(message_id)
                if god:
                    embed = formatter.format_rg_discarded(
                        god, info["role"], info["source"],
                    )
                    await msg.edit(embed=embed)
                    try:
                        await msg.clear_reactions()
                    except discord.Forbidden:
                        pass
                    _tracked_messages.pop(message_id, None)
                    log.info(f"Session discard: {god} discarded "
                             f"in channel {channel_id}")


async def _handle_claim_reaction(payload, info, message_id, channel_id, emoji):
    """Handle reactions on draft claim embeds."""
    if emoji not in NUMBER_EMOJIS:
        return

    async with drafts.get_lock(channel_id):
        draft = drafts.get(channel_id)
        if not draft:
            return

        channel = client.get_channel(channel_id)
        if not channel:
            return

        try:
            msg = await channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            _tracked_messages.pop(message_id, None)
            return

        team = info["team"]
        picks = info["picks"]
        index = NUMBER_EMOJIS.index(emoji)

        if index >= len(picks):
            return

        god = picks[index]

        # Get the display name of whoever reacted (they're claiming)
        guild = client.get_guild(payload.guild_id) if payload.guild_id else None
        if guild:
            member = guild.get_member(payload.user_id)
            if not member:
                try:
                    member = await guild.fetch_member(payload.user_id)
                except (discord.NotFound, discord.Forbidden):
                    return
            user_name = member.display_name
        else:
            user = client.get_user(payload.user_id)
            if not user:
                try:
                    user = await client.fetch_user(payload.user_id)
                except (discord.NotFound, discord.Forbidden):
                    return
            user_name = user.display_name

        # Attempt to claim
        if draft.claim_god(team, god, payload.user_id, user_name):
            log.info(f"Draft {draft.draft_id}: {user_name} claimed {god} ({team})")

            # Update the claim embed
            await _update_claim_embed(draft, team, channel)

            # Check if both teams are fully claimed
            if draft.current_game.is_fully_claimed():
                log.info(f"Draft {draft.draft_id}: all claims complete for "
                         f"Game {draft.current_game.game_number}")


# ---------------------------------------------------------------------------
# Betting system — shared helpers
# ---------------------------------------------------------------------------

def _is_admin(message: discord.Message) -> bool:
    """True if the message author has server administrator permission."""
    member = message.author
    perms = getattr(member, "guild_permissions", None)
    return bool(perms and perms.administrator)


def _extract_team_names(message: discord.Message) -> list[str]:
    """Return up to 2 team name strings from a message (role > user > raw @word)."""
    teams: list[str] = []
    for r in message.role_mentions:
        if len(teams) >= 2:
            break
        teams.append(f"@{r.name}")
    for u in message.mentions:
        if len(teams) >= 2:
            break
        name = f"@{u.display_name}"
        if name not in teams:
            teams.append(name)
    if len(teams) < 2:
        for part in re.findall(r'@([^\s<>@]+)', message.content):
            if len(teams) >= 2:
                break
            name = f"@{part}"
            if name not in teams:
                teams.append(name)
    return teams[:2]


def _find_matching_team(message: discord.Message, stored_teams: list[str]) -> str | None:
    """Return which stored team name is referenced in the message, or None."""
    for r in message.role_mentions:
        name = f"@{r.name}"
        if name in stored_teams:
            return name
    for u in message.mentions:
        name = f"@{u.display_name}"
        if name in stored_teams:
            return name
    content_lower = message.content.lower()
    for team in stored_teams:
        if team.lower() in content_lower:
            return team
    return None


def _extract_player_name(message: discord.Message) -> str | None:
    """Return the first mentioned user's display name prefixed with @, or None."""
    if message.mentions:
        return f"@{message.mentions[0].display_name}"
    for part in re.findall(r'@([^\s<>@]+)', message.content):
        return f"@{part}"
    return None


async def _post_wallets_to_reports(guild: discord.Guild | None):
    """Post a wallets.json snapshot to #godforge-reports."""
    if not guild or guild.id not in REPORTS_CHANNELS:
        return
    reports_ch = client.get_channel(REPORTS_CHANNELS[guild.id])
    if not reports_ch:
        return
    data = wallet_utils.load_wallets()
    json_bytes = json.dumps(data, indent=2).encode("utf-8")
    file = discord.File(io.BytesIO(json_bytes), filename="wallets_snapshot.json")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        await reports_ch.send(f"📊 **Wallet snapshot** ({ts}):", file=file)
        log.info(f"Wallets posted to reports channel {REPORTS_CHANNELS[guild.id]}")
    except (discord.Forbidden, discord.HTTPException) as exc:
        log.warning(f"Could not post wallets to reports: {exc}")


# ---------------------------------------------------------------------------
# Persistent betting embed
# ---------------------------------------------------------------------------

# In-memory page cursor — resets to 0 on restart (acceptable).
_ledger_page: int = 0


class BettingLedgerView(discord.ui.View):
    """Persistent pagination view for the #betting-ledger embed."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(emoji="⬅️", custom_id="gf_ledger_prev",
                       style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction,
                   button: discord.ui.Button):
        global _ledger_page
        data = ledger_utils.load_ledger()
        total = len(data["matches"])
        if total > 0:
            _ledger_page = max(0, _ledger_page - 1)
        embed = _build_ledger_embed(data, _ledger_page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="➡️", custom_id="gf_ledger_next",
                       style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction,
                   button: discord.ui.Button):
        global _ledger_page
        data = ledger_utils.load_ledger()
        total = len(data["matches"])
        if total > 0:
            _ledger_page = min(total - 1, _ledger_page + 1)
        embed = _build_ledger_embed(data, _ledger_page)
        await interaction.response.edit_message(embed=embed, view=self)


def _build_ledger_embed(data: dict, page: int) -> discord.Embed:
    """Build the Discord embed for one match page of the betting ledger."""
    matches = data.get("matches", [])
    if not matches:
        embed = discord.Embed(
            title="🎰 GodForge Betting Ledger",
            description="No matches scheduled this week. Check back soon!",
            color=0x2C2F33,
        )
        embed.set_footer(text="GodForge Betting • No matches yet")
        return embed

    total = len(matches)
    page = max(0, min(page, total - 1))
    m = matches[page]

    status_labels = {
        "betting_open": "🟢 Betting Open",
        "in_progress":  "🟡 In Progress",
        "completed":    "🔴 Completed",
        "settled":      "✅ Settled",
    }
    status_colors = {
        "betting_open": 0x2ECC71,
        "in_progress":  0xF1C40F,
        "completed":    0xE74C3C,
        "settled":      0x9B59B6,
    }

    t1 = m["teams"]["team1"]
    t2 = m["teams"]["team2"]
    status = status_labels.get(m["status"], m["status"])
    color = status_colors.get(m["status"], 0x2C2F33)

    embed = discord.Embed(
        title=f"🎰 {m['match_id']} — {t1} vs {t2}",
        color=color,
    )
    embed.add_field(name="Status", value=status, inline=True)
    if m.get("winner"):
        embed.add_field(name="Winner", value=m["winner"], inline=True)

    bets = m.get("bets", [])
    win_bets = [b for b in bets if b["type"] == "win"]
    t1_pool = sum(b["amount"] for b in win_bets if b["team"] == t1)
    t2_pool = sum(b["amount"] for b in win_bets if b["team"] == t2)
    embed.add_field(
        name="Win Pools",
        value=f"{t1}: **{t1_pool}** pts\n{t2}: **{t2_pool}** pts\nTotal: **{t1_pool + t2_pool}** pts",
        inline=False,
    )

    prop_bets = [b for b in bets if b["type"] == "prop"]
    if prop_bets:
        groups: dict[str, dict] = {}
        for b in prop_bets:
            key = f"{b['player']}|{b['stat']}|{b['threshold']}"
            if key not in groups:
                groups[key] = {"player": b["player"], "stat": b["stat"],
                               "threshold": b["threshold"], "over": 0, "under": 0}
            groups[key][b["direction"]] += b["amount"]
        lines = [
            f"**{p['player']}** {p['stat']} {p['threshold']} — "
            f"Over: **{p['over']}** | Under: **{p['under']}**"
            for p in groups.values()
        ]
        embed.add_field(name="Props", value="\n".join(lines), inline=False)

    embed.set_footer(text=f"Page {page + 1}/{total} • ⬅️ ➡️ to navigate • GodForge Betting")
    return embed


async def _handle_wallet_command(message: discord.Message):
    if not _is_admin(message):
        await message.channel.send("⚠️ This command requires admin permissions.")
        return
    parts = message.content.split()
    sub = parts[1].lower() if len(parts) > 1 else ""

    if sub == "wipe":
        await _wallet_wipe(message)
    elif sub in ("give", "take", "set"):
        if len(parts) < 4 or not message.mentions:
            await message.channel.send(f"⚠️ Usage: `.wallet {sub} @player amount`")
            return
        target = message.mentions[0]
        try:
            amount = int(parts[-1])
        except ValueError:
            await message.channel.send(f"⚠️ Invalid amount `{parts[-1]}`.")
            return
        await _wallet_adjust(message, sub, target, amount)
    elif sub == "check":
        if not message.mentions:
            await message.channel.send("⚠️ Usage: `.wallet check @player`")
            return
        await _wallet_check(message, message.mentions[0])
    else:
        await message.channel.send(
            "⚠️ Usage: `.wallet give|take|set @player amount`  or  "
            "`.wallet check @player`  or  `.wallet wipe`"
        )


async def _wallet_adjust(message: discord.Message, action: str,
                         target: discord.Member, amount: int):
    uid = target.id
    wallet_utils.ensure_wallet(uid, target.display_name)
    if action == "give":
        new_bal = wallet_utils.update_balance(uid, amount)
        await message.channel.send(
            f"✅ Gave **{amount}** pts to **{target.display_name}**. Balance: **{new_bal}** pts"
        )
    elif action == "take":
        new_bal = wallet_utils.update_balance(uid, -amount)
        await message.channel.send(
            f"✅ Took **{amount}** pts from **{target.display_name}**. Balance: **{new_bal}** pts"
        )
    elif action == "set":
        new_bal = wallet_utils.set_balance(uid, amount)
        await message.channel.send(
            f"✅ Set **{target.display_name}**'s balance to **{new_bal}** pts"
        )
    log.info(f"Wallet {action}: {target.display_name} ({uid}), amount={amount}")


async def _wallet_check(message: discord.Message, target: discord.Member):
    wallet = wallet_utils.get_wallet(target.id)
    if wallet is None:
        await message.channel.send(
            f"No wallet found for **{target.display_name}** — they haven't placed any bets yet."
        )
        return
    await message.channel.send(
        f"**{target.display_name}** has **{wallet['balance']}** pts"
    )


async def _wallet_wipe(message: discord.Message):
    # Safety backup to #godforge-reports before wiping.
    await _post_wallets_to_reports(message.guild)
    count = wallet_utils.reset_all()
    await message.channel.send(
        f"✅ Reset **{count}** wallet(s) to **{wallet_utils.SEED_AMOUNT}** pts each."
    )
    log.info(f"Wallet wipe by {message.author.display_name}: {count} wallets reset")


async def _handle_ledger_command(message: discord.Message):
    if not _is_admin(message):
        await message.channel.send("⚠️ This command requires admin permissions.")
        return
    parts = message.content.split()
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "reset":
        await _ledger_reset(message)
    else:
        await message.channel.send("⚠️ Usage: `.ledger reset`")


async def _ledger_reset(message: discord.Message):
    # Post wallet snapshot to reports before wiping match history.
    await _post_wallets_to_reports(message.guild)
    ledger_utils.reset_ledger()
    await update_betting_embed()
    await message.channel.send(
        "✅ Weekly ledger reset. All matches cleared. Wallet balances untouched."
    )
    log.info(f"Ledger reset by {message.author.display_name}")


async def _handle_match_command(message: discord.Message):
    if not _is_admin(message):
        await message.channel.send("⚠️ This command requires admin permissions.")
        return
    parts = message.content.split()
    if len(parts) < 2:
        await message.channel.send("⚠️ Usage: `.match create|draft|resolve ...`")
        return
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "create":
        await _match_create(message)
    elif sub == "draft":
        await _match_draft(message)
    elif sub == "resolve":
        await _match_resolve(message)
    else:
        await message.channel.send(f"⚠️ Unknown subcommand `{sub}`. Use `create`, `draft`, or `resolve`.")


async def _match_create(message: discord.Message):
    teams = _extract_team_names(message)
    if len(teams) < 2:
        await message.channel.send("⚠️ Usage: `.match create @TeamA @TeamB`")
        return
    match = ledger_utils.create_match(teams[0], teams[1])
    await message.channel.send(
        f"✅ Match **{match['match_id']}** created: **{teams[0]}** vs **{teams[1]}**\n"
        f"🟢 Betting is now open!"
    )
    await update_betting_embed()
    log.info(f"Match {match['match_id']} created: {teams[0]} vs {teams[1]}")


async def _match_draft(message: discord.Message):
    parts = message.content.split()
    if len(parts) < 3:
        await message.channel.send("⚠️ Usage: `.match draft GF-XXXX`")
        return
    match_id = parts[2].upper()

    channel_name = getattr(message.channel, "name", "")
    if "handshake" not in channel_name.lower():
        await message.channel.send("⚠️ `.match draft` must be run in the team handshake channel.")
        return

    match = ledger_utils.get_match(match_id)
    if not match:
        await message.channel.send(f"⚠️ Match {match_id} not found.")
        return
    if match["status"] != "betting_open":
        await message.channel.send(
            f"⚠️ Match {match_id} is not open for betting (status: `{match['status']}`)."
        )
        return

    ledger_utils.set_match_status(match_id, "in_progress")
    t1, t2 = match["teams"]["team1"], match["teams"]["team2"]

    # Loosely trigger the existing draft system if two captains are mentioned.
    draft_note = ""
    if len(message.mentions) >= 2:
        blue_user, red_user = message.mentions[0], message.mentions[1]
        async with drafts.get_lock(message.channel.id):
            draft = drafts.start(
                message.channel.id,
                blue_captain_id=blue_user.id,
                blue_captain_name=blue_user.display_name,
                red_captain_id=red_user.id,
                red_captain_name=red_user.display_name,
                guild_id=message.guild.id if message.guild else 0,
                guild_name=message.guild.name if message.guild else "DM",
                channel_name=channel_name,
            )
        if draft:
            from utils.formatter import format_draft_board
            embed = format_draft_board(draft)
            sent = await message.channel.send(embed=embed)
            draft.board_message_id = sent.id
            draft_note = f"\n🔵 {blue_user.display_name} vs 🔴 {red_user.display_name} — draft started!"
        else:
            draft_note = "\n⚠️ A draft is already active in this channel."
    else:
        draft_note = f"\nUse `.draft start @blue_captain @red_captain` to begin the draft."

    # If every match is now in_progress or beyond, post wallet snapshot to reports.
    data = ledger_utils.load_ledger()
    if ledger_utils.all_matches_in_progress(data):
        await _post_wallets_to_reports(message.guild)

    await message.channel.send(
        f"🟡 **{match_id}** is now **in progress** — betting locked.\n"
        f"Teams: **{t1}** vs **{t2}**{draft_note}"
    )
    await update_betting_embed()
    log.info(f"Match {match_id} set to in_progress in channel {message.channel.id}")


async def _match_resolve(message: discord.Message):
    parts = message.content.split()
    if len(parts) < 4:
        await message.channel.send(
            "⚠️ Usage: `.match resolve GF-XXXX winner @Team`  or  "
            "`.match resolve GF-XXXX prop @player stat actual_value`"
        )
        return
    match_id = parts[2].upper()
    resolve_type = parts[3].lower()
    if resolve_type == "winner":
        await _match_resolve_winner(message, match_id, parts)
    elif resolve_type == "prop":
        await _match_resolve_prop(message, match_id, parts)
    else:
        await message.channel.send(f"⚠️ Unknown resolve type `{resolve_type}`. Use `winner` or `prop`.")


async def _match_resolve_winner(message: discord.Message, match_id: str, parts: list):
    match = ledger_utils.get_match(match_id)
    if not match:
        await message.channel.send(f"⚠️ Match {match_id} not found.")
        return
    if match["status"] not in ("in_progress", "completed"):
        await message.channel.send(
            f"⚠️ Match {match_id} must be `in_progress` or `completed` to resolve a winner "
            f"(current: `{match['status']}`)."
        )
        return
    t1, t2 = match["teams"]["team1"], match["teams"]["team2"]
    winner = _find_matching_team(message, [t1, t2])
    if not winner:
        await message.channel.send(
            f"⚠️ Could not identify the winner. Teams are **{t1}** and **{t2}**."
        )
        return

    payouts = ledger_utils.resolve_win_bets(match_id, winner)
    wallet_utils.apply_payouts(payouts)

    lines = [f"✅ **{match_id}** — **{winner}** wins!"]
    if payouts:
        lines.append(f"💰 Win payouts ({len(payouts)} winner(s)):")
        for p in payouts:
            lines.append(f"  • {p['username']}: +**{p['payout']}** pts")
    else:
        lines.append("No winning win-bets to pay out.")
    await message.channel.send("\n".join(lines))
    await update_betting_embed()
    log.info(f"Match {match_id} resolved: winner={winner}, {len(payouts)} payout(s)")


async def _match_resolve_prop(message: discord.Message, match_id: str, parts: list):
    # .match resolve GF-XXXX prop @player stat actual_value  → 7 tokens
    if len(parts) < 7:
        await message.channel.send(
            "⚠️ Usage: `.match resolve GF-XXXX prop @player stat actual_value`"
        )
        return
    match = ledger_utils.get_match(match_id)
    if not match:
        await message.channel.send(f"⚠️ Match {match_id} not found.")
        return

    player = _extract_player_name(message)
    if not player:
        await message.channel.send("⚠️ Could not identify the player. Use an @mention.")
        return

    stat = parts[5].lower()
    try:
        actual_value = float(parts[6])
    except ValueError:
        await message.channel.send(f"⚠️ Invalid value `{parts[6]}` — must be a number.")
        return

    payouts, had_bets = ledger_utils.resolve_prop_bets(match_id, player, stat, actual_value)
    if not had_bets:
        await message.channel.send(f"No bets found for that prop ({player} {stat})")
        return

    wallet_utils.apply_payouts(payouts)

    updated = ledger_utils.get_match(match_id)
    settled_note = " — match is now **settled** ✅" if updated and updated["status"] == "settled" else ""
    lines = [f"✅ **{match_id}** prop resolved: **{player}** {stat} = **{actual_value}**{settled_note}"]
    if payouts:
        lines.append(f"💰 Prop payouts ({len(payouts)} winner(s)):")
        for p in payouts:
            lines.append(f"  • {p['username']}: +**{p['payout']}** pts")
    else:
        lines.append("No winning bets on this side.")
    await message.channel.send("\n".join(lines))
    await update_betting_embed()
    log.info(f"Match {match_id} prop resolved: {player} {stat}={actual_value}, {len(payouts)} payout(s)")


async def _handle_bet_command(message: discord.Message):
    if PLACE_BETS_CHANNEL_ID and message.channel.id != PLACE_BETS_CHANNEL_ID:
        await message.channel.send("⚠️ Bets can only be placed in the #place-bets channel.")
        return

    parts = message.content.split()
    # Minimum: .bet GF-XXXX amount @Team win  (5 tokens)
    if len(parts) < 5:
        await message.channel.send(
            "⚠️ Usage:\n"
            "  `.bet GF-XXXX amount @Team win`\n"
            "  `.bet GF-XXXX amount @player stat over|under threshold`"
        )
        return

    match_id = parts[1].upper()
    try:
        amount = int(parts[2])
    except ValueError:
        await message.channel.send(f"⚠️ Invalid amount `{parts[2]}` — must be a whole number.")
        return
    if amount <= 0:
        await message.channel.send("⚠️ Bet amount must be greater than zero.")
        return

    match = ledger_utils.get_match(match_id)
    if not match:
        await message.channel.send(f"Match {match_id} not found.")
        return
    if match["status"] != "betting_open":
        await message.channel.send("Betting is closed for this match")
        return

    user_id = message.author.id
    username = message.author.display_name
    balance = wallet_utils.seed_wallet(user_id, username)

    if balance <= 0:
        await message.channel.send(
            f"You have {balance} points and cannot place bets. Contact an admin."
        )
        return
    if amount > balance:
        await message.channel.send(
            f"⚠️ You only have **{balance}** pts but tried to bet **{amount}**."
        )
        return

    # Route by bet shape
    if parts[4].lower() == "win":
        # .bet GF-XXXX amount @Team win
        await _place_win_bet(message, match, match_id, amount)
    elif len(parts) >= 7 and parts[5].lower() in ("over", "under"):
        # .bet GF-XXXX amount @player stat over|under threshold
        await _place_prop_bet(message, match, match_id, amount, parts)
    else:
        await message.channel.send(
            "⚠️ Unrecognised bet format.\n"
            "Win:  `.bet GF-XXXX amount @Team win`\n"
            "Prop: `.bet GF-XXXX amount @player stat over|under threshold`"
        )


async def _place_win_bet(message: discord.Message, match: dict, match_id: str, amount: int):
    t1, t2 = match["teams"]["team1"], match["teams"]["team2"]
    team = _find_matching_team(message, [t1, t2])
    if not team:
        await message.channel.send(
            f"⚠️ Unknown team. Match {match_id} has **{t1}** vs **{t2}**."
        )
        return

    wallet_utils.update_balance(message.author.id, -amount)
    ledger_utils.add_bet(match_id, {
        "type": "win",
        "user_id": message.author.id,
        "username": message.author.display_name,
        "team": team,
        "amount": amount,
    })
    await message.add_reaction("✅")
    log.info(f"Win bet: {message.author.display_name} bet {amount} on {team} in {match_id}")
    await update_betting_embed()


async def _place_prop_bet(message: discord.Message, match: dict, match_id: str,
                          amount: int, parts: list):
    player = _extract_player_name(message)
    if not player:
        await message.channel.send("⚠️ Could not identify player — use an @mention.")
        return

    stat = parts[4].lower()
    direction = parts[5].lower()
    if direction not in ("over", "under"):
        await message.channel.send("⚠️ Direction must be `over` or `under`.")
        return
    try:
        threshold = float(parts[6])
    except ValueError:
        await message.channel.send(f"⚠️ Invalid threshold `{parts[6]}` — must be a number.")
        return

    wallet_utils.update_balance(message.author.id, -amount)
    ledger_utils.add_bet(match_id, {
        "type": "prop",
        "user_id": message.author.id,
        "username": message.author.display_name,
        "player": player,
        "stat": stat,
        "direction": direction,
        "threshold": threshold,
        "amount": amount,
    })
    await message.add_reaction("✅")
    log.info(f"Prop bet: {message.author.display_name} bet {amount} {direction} "
             f"{threshold} on {player} {stat} in {match_id}")
    await update_betting_embed()


async def update_betting_embed():
    """Post or in-place edit the persistent betting embed in #betting-ledger."""
    global _ledger_page
    if not BETTING_LEDGER_CHANNEL_ID:
        return
    channel = client.get_channel(BETTING_LEDGER_CHANNEL_ID)
    if not channel:
        return

    data = ledger_utils.load_ledger()
    total = len(data["matches"])
    _ledger_page = max(0, min(_ledger_page, total - 1)) if total > 0 else 0

    embed = _build_ledger_embed(data, _ledger_page)
    view = BettingLedgerView()

    msg_id = data.get("embed_message_id")
    chan_id = data.get("embed_channel_id")
    if msg_id and chan_id == BETTING_LEDGER_CHANNEL_ID:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=embed, view=view)
            return
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass  # fall through to post a new message

    msg = await channel.send(embed=embed, view=view)
    ledger_utils.update_embed_info(msg.id, BETTING_LEDGER_CHANNEL_ID)
    log.info(f"Betting ledger embed posted to channel {BETTING_LEDGER_CHANNEL_ID}")


def main():
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN not set. Create a .env file with DISCORD_TOKEN=your_token"
        )
    client.run(TOKEN)


if __name__ == "__main__":
    main()
