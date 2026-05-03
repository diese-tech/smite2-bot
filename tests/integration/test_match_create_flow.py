"""
Integration tests for the full .match create → ledger post flow.

These tests run _match_create() end-to-end, mocking only the Discord
client/channel objects (no real network calls).
"""
import contextlib
import pytest
import discord
from unittest.mock import AsyncMock, MagicMock, patch

import bot
from utils import ledger as ledger_utils


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _embed_infra_stack(stack, ledger_channel):
    """Push patches for embed-building helpers and Discord channel into an ExitStack."""
    stack.enter_context(patch("bot._build_ledger_embed", return_value=MagicMock()))
    stack.enter_context(patch("bot.BettingLedgerView", return_value=MagicMock()))
    stack.enter_context(patch("bot.BETTING_LEDGER_CHANNEL_ID", ledger_channel.id))
    stack.enter_context(patch.object(bot.client, "get_channel", return_value=ledger_channel))


def _apply_team_mentions(mock_message):
    """Configure the mock message so _extract_team_names finds two teams."""
    role_a = MagicMock()
    role_a.name = "TeamA"
    role_b = MagicMock()
    role_b.name = "TeamB"
    mock_message.role_mentions = [role_a, role_b]
    mock_message.mentions = []
    return mock_message


# ---------------------------------------------------------------------------
# Test 1: happy path — match saved AND ledger embed sent
# ---------------------------------------------------------------------------

async def test_full_flow_creates_match_and_posts_ledger(
    tmp_ledger, mock_message, mock_ledger_channel
):
    """_match_create saves the match to the ledger AND calls channel.send for the embed."""
    _apply_team_mentions(mock_message)

    with contextlib.ExitStack() as stack:
        _embed_infra_stack(stack, mock_ledger_channel)
        await bot._match_create(mock_message)

    # Match saved to disk.
    data = ledger_utils.load_ledger()
    assert len(data["matches"]) == 1
    assert data["matches"][0]["teams"]["team1"] == "@TeamA"

    # Ledger embed posted.
    mock_ledger_channel.send.assert_called_once()


# ---------------------------------------------------------------------------
# Test 2: match record is saved BEFORE the ledger embed is posted
# ---------------------------------------------------------------------------

async def test_db_saved_before_ledger_posts(tmp_ledger, mock_message, mock_ledger_channel):
    """
    The JSON file must be written before channel.send() is called so that the
    embed reflects the new match.
    """
    _apply_team_mentions(mock_message)
    call_order = []

    original_save = ledger_utils.save_ledger

    def tracked_save(data):
        call_order.append("save_ledger")
        original_save(data)

    async def tracked_send(*args, **kwargs):
        call_order.append("channel.send")
        sent = MagicMock()
        sent.id = 88888
        return sent

    mock_ledger_channel.send = tracked_send

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("bot._build_ledger_embed", return_value=MagicMock()))
        stack.enter_context(patch("bot.BettingLedgerView", return_value=MagicMock()))
        stack.enter_context(patch("bot.BETTING_LEDGER_CHANNEL_ID", mock_ledger_channel.id))
        stack.enter_context(patch.object(bot.client, "get_channel", return_value=mock_ledger_channel))
        stack.enter_context(patch.object(ledger_utils, "save_ledger", side_effect=tracked_save))
        await bot._match_create(mock_message)

    assert "save_ledger" in call_order
    assert "channel.send" in call_order
    assert call_order.index("save_ledger") < call_order.index("channel.send")


# ---------------------------------------------------------------------------
# Test 3: ledger post failure does NOT prevent match creation (graceful degradation)
# ---------------------------------------------------------------------------

async def test_ledger_post_failure_does_not_prevent_match_creation(
    tmp_ledger, mock_message, mock_ledger_channel
):
    """
    If channel.send raises Forbidden, the match must still be persisted to JSON.
    This verifies the try/except wrapper around update_betting_embed() in _match_create().
    """
    _apply_team_mentions(mock_message)
    mock_ledger_channel.send = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(), "missing permissions")
    )

    with contextlib.ExitStack() as stack:
        _embed_infra_stack(stack, mock_ledger_channel)
        await bot._match_create(mock_message)

    # Match must still be in the ledger despite the embed failure.
    data = ledger_utils.load_ledger()
    assert len(data["matches"]) == 1


# ---------------------------------------------------------------------------
# Test 4: confirmation message is sent to the command channel
# ---------------------------------------------------------------------------

async def test_match_create_sends_confirmation_message(
    tmp_ledger, mock_message, mock_ledger_channel
):
    """_match_create sends a '✅ Match created' confirmation in the command channel."""
    _apply_team_mentions(mock_message)

    with contextlib.ExitStack() as stack:
        _embed_infra_stack(stack, mock_ledger_channel)
        await bot._match_create(mock_message)

    # The command channel (mock_message.channel) should receive the confirmation.
    mock_message.channel.send.assert_called()
    confirmation_text = mock_message.channel.send.call_args_list[0][0][0]
    assert "✅" in confirmation_text
    assert "GF-" in confirmation_text


# ---------------------------------------------------------------------------
# Test 5: non-admin users cannot create matches
# ---------------------------------------------------------------------------

async def test_non_admin_cannot_create_match(
    tmp_ledger, mock_message, mock_author_no_admin, mock_ledger_channel
):
    """A user without administrator permission receives an error and no match is saved."""
    mock_message.author = mock_author_no_admin
    _apply_team_mentions(mock_message)

    with contextlib.ExitStack() as stack:
        _embed_infra_stack(stack, mock_ledger_channel)
        await bot._handle_match_command(mock_message)

    mock_message.channel.send.assert_called_once()
    error_text = mock_message.channel.send.call_args[0][0]
    assert "admin" in error_text.lower() or "permission" in error_text.lower()

    data = ledger_utils.load_ledger()
    assert data["matches"] == []
