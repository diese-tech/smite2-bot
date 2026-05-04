"""
Unit tests for _find_matching_team and _extract_team_names.

Verifies that plain-text team names work alongside @mention references
so neither old nor new syntax breaks.
"""
import pytest
from unittest.mock import MagicMock

import bot


def _msg(content, *, role_mentions=None, mentions=None):
    msg = MagicMock()
    msg.content = content
    msg.role_mentions = role_mentions or []
    msg.mentions = mentions or []
    return msg


def _role(name):
    r = MagicMock()
    r.name = name
    return r


def _user(display_name):
    u = MagicMock()
    u.display_name = display_name
    return u


TEAMS = ["@Whiskey Whales", "@Shadow Council"]


# ---------------------------------------------------------------------------
# _find_matching_team — plain text (new behaviour)
# ---------------------------------------------------------------------------

def test_plain_text_no_at_sign():
    """.bet … Whiskey Whales win  →  matches stored '@Whiskey Whales'."""
    msg = _msg(".bet GF-0001 100 Whiskey Whales win")
    assert bot._find_matching_team(msg, TEAMS) == "@Whiskey Whales"


def test_plain_text_other_team():
    """.bet … Shadow Council win  →  matches '@Shadow Council'."""
    msg = _msg(".bet GF-0001 100 Shadow Council win")
    assert bot._find_matching_team(msg, TEAMS) == "@Shadow Council"


def test_plain_text_case_insensitive():
    """Team name match is case-insensitive."""
    msg = _msg(".bet GF-0001 100 whiskey whales win")
    assert bot._find_matching_team(msg, TEAMS) == "@Whiskey Whales"


# ---------------------------------------------------------------------------
# _find_matching_team — @mention (legacy behaviour preserved)
# ---------------------------------------------------------------------------

def test_role_mention_still_works():
    """Discord role mention resolves correctly."""
    role = _role("Whiskey Whales")
    msg = _msg(".bet GF-0001 100 <@&123> win", role_mentions=[role])
    assert bot._find_matching_team(msg, TEAMS) == "@Whiskey Whales"


def test_user_mention_still_works():
    """Discord user mention resolves correctly."""
    user = _user("Shadow Council")
    msg = _msg(".bet GF-0001 100 <@456> win", mentions=[user])
    assert bot._find_matching_team(msg, TEAMS) == "@Shadow Council"


def test_at_prefix_in_text_still_works():
    """Plain '@TeamName' text (no Discord mention) still matches."""
    msg = _msg(".bet GF-0001 100 @Whiskey Whales win")
    assert bot._find_matching_team(msg, TEAMS) == "@Whiskey Whales"


# ---------------------------------------------------------------------------
# _find_matching_team — partial match safety
# ---------------------------------------------------------------------------

def test_longer_name_wins_over_substring():
    """'Whiskey Whales' is preferred over 'Whales' when both are stored."""
    teams = ["@Whales", "@Whiskey Whales"]
    msg = _msg(".bet GF-0001 100 Whiskey Whales win")
    assert bot._find_matching_team(msg, teams) == "@Whiskey Whales"


def test_no_match_returns_none():
    """Content with no recognisable team name returns None."""
    msg = _msg(".bet GF-0001 100 RandomSquad win")
    assert bot._find_matching_team(msg, TEAMS) is None


# ---------------------------------------------------------------------------
# _extract_team_names — quoted strings (new behaviour)
# ---------------------------------------------------------------------------

def test_quoted_team_names():
    """.match create "Whiskey Whales" "Shadow Council"  →  two teams extracted."""
    msg = _msg('.match create "Whiskey Whales" "Shadow Council"')
    teams = bot._extract_team_names(msg)
    assert teams == ["@Whiskey Whales", "@Shadow Council"]


def test_quoted_single_team():
    """Single quoted name is extracted; second slot left empty."""
    msg = _msg('.match create "Whiskey Whales"')
    teams = bot._extract_team_names(msg)
    assert "@Whiskey Whales" in teams
    assert len(teams) == 1


# ---------------------------------------------------------------------------
# _extract_team_names — @mention (legacy behaviour preserved)
# ---------------------------------------------------------------------------

def test_role_mention_extraction():
    """Role mentions are still the highest-priority extraction method."""
    role_a = _role("Whiskey Whales")
    role_b = _role("Shadow Council")
    msg = _msg(".match create <@&1> <@&2>", role_mentions=[role_a, role_b])
    teams = bot._extract_team_names(msg)
    assert teams == ["@Whiskey Whales", "@Shadow Council"]


def test_legacy_at_word_extraction():
    """Single-word @Name still works as a fallback."""
    msg = _msg(".match create @TeamA @TeamB")
    teams = bot._extract_team_names(msg)
    assert "@TeamA" in teams
    assert "@TeamB" in teams


def test_role_mention_takes_priority_over_quotes():
    """If both role mentions and quoted strings are present, mentions win."""
    role_a = _role("Alpha")
    msg = _msg('.match create <@&1> "Beta Team"', role_mentions=[role_a])
    teams = bot._extract_team_names(msg)
    assert teams[0] == "@Alpha"
    assert "@Beta Team" in teams
