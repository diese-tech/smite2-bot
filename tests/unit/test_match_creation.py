"""
Unit tests for ledger_utils.create_match() and the _match_create() command handler.

These tests exercise the data layer and command validation in isolation,
without touching Discord embed posting.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import bot
from utils import ledger as ledger_utils


# ---------------------------------------------------------------------------
# ledger_utils.create_match() — data layer
# ---------------------------------------------------------------------------

def test_create_match_saves_to_ledger(tmp_ledger):
    """create_match persists a new match with status='betting_open'."""
    ledger_utils.create_match("@TeamA", "@TeamB")

    data = ledger_utils.load_ledger()
    assert len(data["matches"]) == 1
    match = data["matches"][0]
    assert match["teams"]["team1"] == "@TeamA"
    assert match["teams"]["team2"] == "@TeamB"
    assert match["status"] == "betting_open"


def test_create_match_returns_match_dict(tmp_ledger):
    """create_match returns a complete match dict with all expected keys."""
    match = ledger_utils.create_match("@TeamA", "@TeamB")

    assert "match_id" in match
    assert "teams" in match
    assert "status" in match
    assert "bets" in match
    assert match["bets"] == []
    assert match["result"] is None
    assert match["winner"] is None


def test_create_match_increments_id(tmp_ledger):
    """Successive create_match calls produce sequentially numbered IDs."""
    m1 = ledger_utils.create_match("@A", "@B")
    m2 = ledger_utils.create_match("@C", "@D")

    assert m1["match_id"] == "GF-0001"
    assert m2["match_id"] == "GF-0002"


def test_no_duplicate_prevention(tmp_ledger):
    """
    Creating a match with the same teams twice produces two separate records.
    There is intentionally no dedup guard — this documents current behaviour.
    """
    ledger_utils.create_match("@TeamA", "@TeamB")
    ledger_utils.create_match("@TeamA", "@TeamB")

    data = ledger_utils.load_ledger()
    assert len(data["matches"]) == 2
    assert data["matches"][0]["match_id"] != data["matches"][1]["match_id"]


# ---------------------------------------------------------------------------
# _match_create() — command handler validation
# ---------------------------------------------------------------------------

async def test_match_create_command_missing_teams(tmp_ledger, mock_message):
    """_match_create with no @mentions sends a usage warning and saves nothing."""
    mock_message.content = ".match create"
    mock_message.role_mentions = []
    mock_message.mentions = []

    with patch("bot.update_betting_embed", new=AsyncMock()):
        await bot._match_create(mock_message)

    mock_message.channel.send.assert_called_once()
    call_text = mock_message.channel.send.call_args[0][0]
    assert "Usage" in call_text or "usage" in call_text

    # No match should have been created.
    data = ledger_utils.load_ledger()
    assert data["matches"] == []
