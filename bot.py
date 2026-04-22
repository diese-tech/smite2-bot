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
import logging
import discord
from discord.ext import tasks
from dotenv import load_dotenv

from utils import parser, picker, loader, formatter
from utils.formatter import NUMBER_EMOJIS
from utils.session import SessionManager
from utils.draft import DraftManager
from utils.resolver import resolve_god_name

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

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
        if not draft.current_game.is_complete():
            return formatter.format_error("Current game isn't complete yet. Finish all bans and picks first.")
        if not draft.advance_game():
            return formatter.format_error("Failed to advance game.")

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

        # Post summary embed
        embed = formatter.format_draft_end(draft, export)
        await message.channel.send(embed=embed)

        # Attach JSON export as a file
        filename = draft.sanitized_filename()
        json_bytes = json.dumps(export, indent=2).encode("utf-8")
        file = discord.File(io.BytesIO(json_bytes), filename=filename)
        await message.channel.send(f"📎 Draft record: `{filename}`", file=file)

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

    # Check if game is complete
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


# ---------------------------------------------------------------------------
# Reaction handler (sessions only)
# ---------------------------------------------------------------------------

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Handle reactions on tracked roll messages."""
    if payload.user_id == client.user.id:
        return

    message_id = payload.message_id
    if message_id not in _tracked_messages:
        return

    info = _tracked_messages[message_id]
    channel_id = info["channel_id"]
    emoji = str(payload.emoji)

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


def main():
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN not set. Create a .env file with DISCORD_TOKEN=your_token"
        )
    client.run(TOKEN)


if __name__ == "__main__":
    main()
