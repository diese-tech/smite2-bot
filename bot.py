"""
GodForge — Smite 2 Discord Bot

Loads token from .env, listens for messages starting with '.', parses them,
and responds with random god picks or builds.

Session system: when a session is active in a channel, .rg and .roll5
produce interactive embeds with reactions. Picked gods are excluded from
future rolls in that channel until the session ends or resets.

Production hardening:
- Per-channel async locks prevent race conditions on concurrent events.
- Reaction dedup prevents double-processing.
- Background task cleans up abandoned sessions (30 min TTL).

Run with: python bot.py
"""

import os
import logging
import discord
from discord.ext import tasks
from dotenv import load_dotenv

from utils import parser, picker, loader, formatter
from utils.formatter import NUMBER_EMOJIS
from utils.session import SessionManager

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
client = discord.Client(intents=intents)

# Per-channel session tracking (in-memory, resets on restart).
sessions = SessionManager()

# Track metadata for reaction-enabled messages so we can edit them later.
# message_id -> {"kind": "roll5"|"rg", "role": ..., "source": ..., "gods": [...],
#                "author_id": int, "author_name": str, "channel_id": int}
_tracked_messages = {}


@client.event
async def on_ready():
    log.info(f"Logged in as {client.user} (id: {client.user.id})")
    log.info(f"Connected to {len(client.guilds)} guild(s)")
    # Start the background cleanup task
    if not session_cleanup.is_running():
        session_cleanup.start()


@tasks.loop(minutes=5)
async def session_cleanup():
    """Periodically remove sessions that have been inactive beyond TTL."""
    expired = sessions.cleanup_expired()
    if expired:
        # Also clean up tracked messages for expired channels
        to_remove = [mid for mid, info in _tracked_messages.items()
                     if info.get("channel_id") in expired]
        for mid in to_remove:
            del _tracked_messages[mid]
        log.info(f"Cleaned up {len(expired)} expired session(s): channels {expired}")


@client.event
async def on_message(message: discord.Message):
    # Ignore self and other bots
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
        else:
            items = picker.pick_build(
                loader.builds(), intent["role"], intent["type"], intent["count"]
            )
            response = formatter.format_build(items, intent["role"], intent["type"])

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


async def _handle_session(intent: dict, channel_id: int):
    """Handle .session start/end/show/reset. Returns a response (str or Embed).
    Caller must hold the channel lock."""
    action = intent["action"]

    if action == "start":
        if sessions.start(channel_id):
            log.info(f"Session started in channel {channel_id}")
            return "✅ Draft session started! Rolls in this channel will now track picks. Use `.session end` when done."
        else:
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
        else:
            return formatter.format_error("No active session in this channel.")

    elif action == "show":
        session = sessions.get(channel_id)
        if session:
            return formatter.format_session_show(session.picks)
        else:
            return formatter.format_error("No active session in this channel.")

    elif action == "reset":
        if sessions.reset(channel_id):
            to_remove = [mid for mid, info in _tracked_messages.items()
                         if info.get("channel_id") == channel_id]
            for mid in to_remove:
                del _tracked_messages[mid]
            log.info(f"Session reset in channel {channel_id}")
            return "🔄 Session picks cleared. Session is still active."
        else:
            return formatter.format_error("No active session in this channel.")


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Handle reactions on tracked roll messages."""
    # Ignore bot's own reactions
    if payload.user_id == client.user.id:
        return

    message_id = payload.message_id
    if message_id not in _tracked_messages:
        return

    info = _tracked_messages[message_id]
    channel_id = info["channel_id"]
    emoji = str(payload.emoji)

    # Acquire per-channel lock to prevent race conditions
    async with sessions.get_lock(channel_id):
        session = sessions.get(channel_id)
        if not session:
            return

        # Dedup: skip if this reaction was already processed
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

        # The pick is assigned to whoever typed the command (author),
        # not whoever tapped the reaction. Anyone can tap to choose.
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
                    pass  # bot lacks Manage Messages — reactions stay but pick is locked
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
