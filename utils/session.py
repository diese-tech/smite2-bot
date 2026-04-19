"""
Session manager for tracking draft picks per channel.

Each channel can have one active session at a time. While a session is active:
- Picked gods are excluded from future rolls.
- Gods appearing in open (unresolved) .roll5 embeds are also excluded.
- .rg and .roll5 embeds get reactions for interactive selection.

Production hardening:
- Per-channel asyncio.Lock prevents race conditions across concurrent events.
- Reaction dedup cache prevents double-processing of reaction events.
- TTL-based cleanup removes abandoned sessions after 30 min of inactivity.
- Session state lives in memory only — it resets on bot restart.
"""

import asyncio
import time

# Sessions expire after 30 minutes of inactivity.
SESSION_TTL_SECONDS = 30 * 60

# Max size for the reaction dedup cache per session.
MAX_DEDUP_CACHE_SIZE = 200


class SessionState:
    """Draft session state for a single channel."""

    def __init__(self):
        self.active = True
        self.last_updated = time.monotonic()
        # god_name -> {"user_id": int, "user_name": str}
        self.picks = {}
        # message_id -> [list of 5 god names]
        self.open_rolls = {}
        # message_id -> {"god": str, "role": ..., "source": ...}
        self.open_rg = {}
        # Dedup cache: set of (message_id, emoji_str) already processed
        self._processed_reactions = set()

    def _touch(self):
        """Update last_updated timestamp on any mutation."""
        self.last_updated = time.monotonic()

    def is_expired(self) -> bool:
        """Check if session has been inactive beyond TTL."""
        return (time.monotonic() - self.last_updated) > SESSION_TTL_SECONDS

    def is_reaction_processed(self, message_id: int, emoji: str) -> bool:
        """Check if this reaction was already handled (dedup)."""
        return (message_id, emoji) in self._processed_reactions

    def mark_reaction_processed(self, message_id: int, emoji: str):
        """Mark a reaction as processed. Prunes cache if oversized."""
        self._processed_reactions.add((message_id, emoji))
        if len(self._processed_reactions) > MAX_DEDUP_CACHE_SIZE:
            # Drop oldest half — order isn't guaranteed in a set,
            # but for dedup purposes any pruning is fine.
            to_keep = list(self._processed_reactions)[-MAX_DEDUP_CACHE_SIZE // 2:]
            self._processed_reactions = set(to_keep)

    def get_excluded_gods(self) -> set:
        """Return all gods that should be excluded from new rolls."""
        excluded = set(self.picks.keys())
        for gods in self.open_rolls.values():
            excluded.update(gods)
        for info in self.open_rg.values():
            excluded.add(info["god"])
        return excluded

    def register_roll5(self, message_id: int, gods: list[str]):
        """Track an open .roll5 embed awaiting selection."""
        self.open_rolls[message_id] = gods
        self._touch()

    def register_rg(self, message_id: int, god: str, role, source):
        """Track an open .rg embed awaiting confirmation."""
        self.open_rg[message_id] = {"god": god, "role": role, "source": source}
        self._touch()

    def lock_roll5_pick(self, message_id: int, index: int,
                        user_id: int, user_name: str) -> str | None:
        """
        Lock a god from an open .roll5 roll.
        Returns the god name if successful, None if invalid.
        """
        if message_id not in self.open_rolls:
            return None
        gods = self.open_rolls[message_id]
        if index < 0 or index >= len(gods):
            return None
        god = gods[index]
        if god in self.picks:
            return None  # already picked
        self.picks[god] = {"user_id": user_id, "user_name": user_name}
        del self.open_rolls[message_id]
        self._touch()
        return god

    def lock_rg_pick(self, message_id: int,
                     user_id: int, user_name: str) -> str | None:
        """
        Lock a god from an open .rg roll.
        Returns the god name if successful, None if invalid.
        """
        if message_id not in self.open_rg:
            return None
        god = self.open_rg[message_id]["god"]
        if god in self.picks:
            return None
        self.picks[god] = {"user_id": user_id, "user_name": user_name}
        del self.open_rg[message_id]
        self._touch()
        return god

    def discard_rg(self, message_id: int) -> str | None:
        """
        Discard an open .rg roll (user hit ❌). Returns the god name,
        or None if the message wasn't an open rg roll.
        """
        if message_id not in self.open_rg:
            return None
        god = self.open_rg[message_id]["god"]
        del self.open_rg[message_id]
        self._touch()
        return god

    def reset(self):
        """Clear all picks and open rolls, keep session active."""
        self.picks.clear()
        self.open_rolls.clear()
        self.open_rg.clear()
        self._processed_reactions.clear()
        self._touch()


class SessionManager:
    """Manages per-channel draft sessions with async locks and TTL cleanup."""

    def __init__(self):
        # channel_id -> SessionState
        self._sessions = {}
        # channel_id -> asyncio.Lock (one lock per channel for concurrency safety)
        self._locks = {}

    def get_lock(self, channel_id: int) -> asyncio.Lock:
        """Get or create the async lock for a channel."""
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()
        return self._locks[channel_id]

    def start(self, channel_id: int) -> bool:
        """Start a session. Returns False if one is already active."""
        if channel_id in self._sessions and self._sessions[channel_id].active:
            return False
        self._sessions[channel_id] = SessionState()
        return True

    def end(self, channel_id: int) -> SessionState | None:
        """End a session. Returns the final state, or None if no session."""
        session = self._sessions.pop(channel_id, None)
        self._locks.pop(channel_id, None)
        if session:
            session.active = False
        return session

    def get(self, channel_id: int) -> SessionState | None:
        """Get the active session for a channel, or None."""
        session = self._sessions.get(channel_id)
        if session and session.active:
            return session
        return None

    def reset(self, channel_id: int) -> bool:
        """Reset picks in current session. Returns False if no session."""
        session = self.get(channel_id)
        if not session:
            return False
        session.reset()
        return True

    def cleanup_expired(self) -> list[int]:
        """
        Remove sessions that have been inactive beyond SESSION_TTL_SECONDS.
        Returns list of cleaned-up channel IDs (for logging).
        """
        expired = [
            cid for cid, s in self._sessions.items()
            if s.is_expired()
        ]
        for cid in expired:
            self._sessions.pop(cid, None)
            self._locks.pop(cid, None)
        return expired
