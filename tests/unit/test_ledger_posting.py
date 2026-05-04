"""
Unit tests for update_betting_embed().

Discord client, channels, and messages are fully mocked.
The ledger is backed by a tmp_path JSON file.
"""
import pytest
import discord
from unittest.mock import AsyncMock, MagicMock, patch

import bot
from utils import ledger as ledger_utils


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_client_channel(ledger_channel):
    """Return a context-manager that patches bot.client.get_channel."""
    return patch.object(bot.client, "get_channel", return_value=ledger_channel)


def _patch_build_embed():
    """Patch _build_ledger_embed so tests don't need real embed data."""
    return patch("bot._build_ledger_embed", return_value=MagicMock())


def _patch_betting_view():
    """Patch BettingLedgerView to avoid discord.ui dependency."""
    return patch("bot.BettingLedgerView", return_value=MagicMock())


# ---------------------------------------------------------------------------
# Test 1: posts a new message when no stored embed message ID exists
# ---------------------------------------------------------------------------

async def test_update_embed_posts_new_message(tmp_ledger, mock_ledger_channel):
    """No stored embed_message_id → channel.send() is called once."""
    with (
        patch("bot.BETTING_LEDGER_CHANNEL_ID", mock_ledger_channel.id),
        _patch_client_channel(mock_ledger_channel),
        _patch_build_embed(),
        _patch_betting_view(),
    ):
        await bot.update_betting_embed()

    mock_ledger_channel.send.assert_called_once()
    mock_ledger_channel.fetch_message.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: edits the existing message when a valid embed_message_id is stored
# ---------------------------------------------------------------------------

async def test_update_embed_edits_existing_message(tmp_ledger, mock_ledger_channel, mock_sent_message):
    """Stored embed_message_id for same channel → msg.edit() called, no new send."""
    # Pre-store the embed info so the edit branch is triggered.
    ledger_utils.update_embed_info(mock_sent_message.id, mock_ledger_channel.id)
    mock_ledger_channel.fetch_message = AsyncMock(return_value=mock_sent_message)

    with (
        patch("bot.BETTING_LEDGER_CHANNEL_ID", mock_ledger_channel.id),
        _patch_client_channel(mock_ledger_channel),
        _patch_build_embed(),
        _patch_betting_view(),
    ):
        await bot.update_betting_embed()

    mock_sent_message.edit.assert_called_once()
    mock_ledger_channel.send.assert_not_called()


def test_reset_ledger_preserves_embed_pointer(tmp_ledger, mock_ledger_channel, mock_sent_message):
    """reset_ledger clears matches but keeps the stored embed target for in-place refresh."""
    ledger_utils.create_match("@TeamA", "@TeamB")
    ledger_utils.update_embed_info(mock_sent_message.id, mock_ledger_channel.id)

    ledger_utils.reset_ledger()

    data = ledger_utils.load_ledger()
    assert data["matches"] == []
    assert data["embed_message_id"] == mock_sent_message.id
    assert data["embed_channel_id"] == mock_ledger_channel.id


# ---------------------------------------------------------------------------
# Test 3: notifies user when BETTING_LEDGER_CHANNEL_ID is 0 (not configured)
# ---------------------------------------------------------------------------

async def test_update_embed_notifies_when_channel_id_zero(tmp_ledger, mock_notify_channel):
    """BETTING_LEDGER_CHANNEL_ID=0 → notify_channel gets an informative message."""
    with patch("bot.BETTING_LEDGER_CHANNEL_ID", 0):
        await bot.update_betting_embed(notify_channel=mock_notify_channel)

    mock_notify_channel.send.assert_called_once()
    sent_text = mock_notify_channel.send.call_args[0][0]
    assert "hasn't been configured" in sent_text
    assert "admin" in sent_text.lower()


# ---------------------------------------------------------------------------
# Test 4: notifies user when the ledger channel cannot be found / accessed
# ---------------------------------------------------------------------------

async def test_update_embed_notifies_when_channel_not_found(tmp_ledger, mock_notify_channel):
    """get_channel returns None and fetch_channel raises NotFound → user notified."""
    with (
        patch("bot.BETTING_LEDGER_CHANNEL_ID", 999888777),
        patch.object(bot.client, "get_channel", return_value=None),
        patch.object(
            bot.client,
            "fetch_channel",
            new=AsyncMock(side_effect=discord.NotFound(MagicMock(), "not found")),
        ),
    ):
        await bot.update_betting_embed(notify_channel=mock_notify_channel)

    mock_notify_channel.send.assert_called_once()
    sent_text = mock_notify_channel.send.call_args[0][0]
    assert "could not be found" in sent_text
    assert "admin" in sent_text.lower()


# ---------------------------------------------------------------------------
# Test 5: falls back to posting a new message when stored message is deleted
# ---------------------------------------------------------------------------

async def test_update_embed_falls_through_on_message_not_found(
    tmp_ledger, mock_ledger_channel, mock_sent_message
):
    """fetch_message raises NotFound → falls through and sends a new message."""
    ledger_utils.update_embed_info(mock_sent_message.id, mock_ledger_channel.id)
    mock_ledger_channel.fetch_message = AsyncMock(
        side_effect=discord.NotFound(MagicMock(), "unknown message")
    )

    with (
        patch("bot.BETTING_LEDGER_CHANNEL_ID", mock_ledger_channel.id),
        _patch_client_channel(mock_ledger_channel),
        _patch_build_embed(),
        _patch_betting_view(),
    ):
        await bot.update_betting_embed()

    mock_ledger_channel.send.assert_called_once()


# ---------------------------------------------------------------------------
# Test 6: notifies user when the bot lacks send permission
# ---------------------------------------------------------------------------

async def test_update_embed_forbidden_on_send_notifies(tmp_ledger, mock_ledger_channel, mock_notify_channel):
    """channel.send raises Forbidden → notify_channel receives a permission error message."""
    mock_ledger_channel.send = AsyncMock(
        side_effect=discord.Forbidden(MagicMock(), "missing permissions")
    )

    with (
        patch("bot.BETTING_LEDGER_CHANNEL_ID", mock_ledger_channel.id),
        _patch_client_channel(mock_ledger_channel),
        _patch_build_embed(),
        _patch_betting_view(),
    ):
        await bot.update_betting_embed(notify_channel=mock_notify_channel)

    mock_notify_channel.send.assert_called_once()
    sent_text = mock_notify_channel.send.call_args[0][0]
    assert "permission" in sent_text.lower()
    assert "admin" in sent_text.lower()
