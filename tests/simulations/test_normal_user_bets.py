"""
Simulations: normal (non-admin) user placing bets.

Skipped (already covered):
  - Non-admin .match create  → test_non_admin_cannot_create_match
  - Ledger channel errors    → test_ledger_posting.py suite
"""
import contextlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import bot
from utils import ledger as ledger_utils
from utils import wallet as wallet_utils


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_wallets(tmp_path, monkeypatch):
    wallet_file = tmp_path / "wallets.json"
    monkeypatch.setattr(wallet_utils, "WALLETS_PATH", wallet_file)
    return wallet_file


@pytest.fixture()
def open_match(tmp_ledger):
    """Create a fresh betting_open match and return it."""
    return ledger_utils.create_match("@TeamA", "@TeamB")


def _bet_message(content, channel, author, *, mentions=None, role_mentions=None):
    msg = MagicMock()
    msg.content = content
    msg.channel = channel
    msg.author = author
    msg.guild = MagicMock()
    msg.mentions = mentions or []
    msg.role_mentions = role_mentions or []
    msg.add_reaction = AsyncMock()
    return msg


def _normal_user(user_id=111):
    user = MagicMock()
    user.id = user_id
    user.display_name = "NormalUser"
    user.bot = False
    perms = MagicMock()
    perms.administrator = False
    user.guild_permissions = perms
    return user


def _patch_embed(ledger_channel_id=0):
    return (
        patch("bot.BETTING_LEDGER_CHANNEL_ID", ledger_channel_id),
        patch("bot.update_betting_embed", new=AsyncMock()),
    )


# ---------------------------------------------------------------------------
# 1. First-time better — wallet is auto-seeded at 500 pts
# ---------------------------------------------------------------------------

async def test_first_time_better_is_seeded(tmp_ledger, tmp_wallets, open_match, mock_notify_channel):
    """A user with no wallet is auto-seeded at 500 pts on their first bet."""
    user = _normal_user(user_id=999)
    match_id = open_match["match_id"]
    msg = _bet_message(f".bet {match_id} 50 @TeamA win", mock_notify_channel, user)

    with contextlib.ExitStack() as stack:
        for cm in _patch_embed():
            stack.enter_context(cm)
        stack.enter_context(patch("bot.PLACE_BETS_CHANNEL_ID", 0))
        await bot._handle_bet_command(msg)

    # Wallet should now exist and be debited from 500
    wallet = wallet_utils.get_wallet(user.id)
    assert wallet is not None
    assert wallet["balance"] == 450  # 500 seeded - 50 bet


# ---------------------------------------------------------------------------
# 2. Win bet — happy path
# ---------------------------------------------------------------------------

async def test_win_bet_happy_path(tmp_ledger, tmp_wallets, open_match, mock_notify_channel):
    """Normal user places a valid win bet; balance decreases, bet recorded."""
    user = _normal_user()
    wallet_utils.seed_wallet(user.id, user.display_name)  # seed first
    match_id = open_match["match_id"]
    msg = _bet_message(f".bet {match_id} 100 @TeamA win", mock_notify_channel, user)

    with contextlib.ExitStack() as stack:
        for cm in _patch_embed():
            stack.enter_context(cm)
        stack.enter_context(patch("bot.PLACE_BETS_CHANNEL_ID", 0))
        await bot._handle_bet_command(msg)

    match = ledger_utils.get_match(match_id)
    assert len(match["bets"]) == 1
    assert match["bets"][0]["amount"] == 100
    assert wallet_utils.get_wallet(user.id)["balance"] == 400


# ---------------------------------------------------------------------------
# 3. Prop bet — happy path
# ---------------------------------------------------------------------------

async def test_prop_bet_happy_path(tmp_ledger, tmp_wallets, open_match, mock_notify_channel):
    """Normal user places a valid over/under prop bet."""
    user = _normal_user()
    wallet_utils.seed_wallet(user.id, user.display_name)
    match_id = open_match["match_id"]

    player = MagicMock()
    player.display_name = "PlayerOne"
    msg = _bet_message(
        f".bet {match_id} 75 @PlayerOne kills over 10.5",
        mock_notify_channel, user,
        mentions=[player],
    )

    with contextlib.ExitStack() as stack:
        for cm in _patch_embed():
            stack.enter_context(cm)
        stack.enter_context(patch("bot.PLACE_BETS_CHANNEL_ID", 0))
        await bot._handle_bet_command(msg)

    match = ledger_utils.get_match(match_id)
    assert len(match["bets"]) == 1
    bet = match["bets"][0]
    assert bet["type"] == "prop"
    assert bet["direction"] == "over"
    assert bet["threshold"] == 10.5
    assert wallet_utils.get_wallet(user.id)["balance"] == 425


# ---------------------------------------------------------------------------
# 4. Bet in wrong channel (PLACE_BETS_CHANNEL_ID configured)
# ---------------------------------------------------------------------------

async def test_bet_blocked_in_wrong_channel(tmp_ledger, tmp_wallets, open_match, mock_notify_channel):
    """Bet is rejected when placed outside the designated #place-bets channel."""
    user = _normal_user()
    match_id = open_match["match_id"]
    # mock_notify_channel.id = 444555666, PLACE_BETS_CHANNEL_ID = different ID
    msg = _bet_message(f".bet {match_id} 50 @TeamA win", mock_notify_channel, user)

    with patch("bot.PLACE_BETS_CHANNEL_ID", 999999999):  # different from channel.id
        await bot._handle_bet_command(msg)

    mock_notify_channel.send.assert_called_once()
    assert "place-bets" in mock_notify_channel.send.call_args[0][0].lower()
    # No bet recorded
    assert ledger_utils.get_match(match_id)["bets"] == []


# ---------------------------------------------------------------------------
# 5. Bet from any channel when PLACE_BETS_CHANNEL_ID = 0 (unconfigured)
# ---------------------------------------------------------------------------

async def test_bet_allowed_any_channel_when_unconfigured(
    tmp_ledger, tmp_wallets, open_match, mock_notify_channel
):
    """When PLACE_BETS_CHANNEL_ID=0 bets are accepted from any channel."""
    user = _normal_user()
    wallet_utils.seed_wallet(user.id, user.display_name)
    match_id = open_match["match_id"]
    msg = _bet_message(f".bet {match_id} 50 @TeamA win", mock_notify_channel, user)

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("bot.PLACE_BETS_CHANNEL_ID", 0))
        for cm in _patch_embed():
            stack.enter_context(cm)
        await bot._handle_bet_command(msg)

    assert len(ledger_utils.get_match(match_id)["bets"]) == 1


# ---------------------------------------------------------------------------
# 6. Bet with zero balance
# ---------------------------------------------------------------------------

async def test_bet_blocked_zero_balance(tmp_ledger, tmp_wallets, open_match, mock_notify_channel):
    """User with zero balance cannot place a bet."""
    user = _normal_user()
    wallet_utils.seed_wallet(user.id, user.display_name)
    wallet_utils.set_balance(user.id, 0)
    match_id = open_match["match_id"]
    msg = _bet_message(f".bet {match_id} 50 @TeamA win", mock_notify_channel, user)

    with patch("bot.PLACE_BETS_CHANNEL_ID", 0):
        await bot._handle_bet_command(msg)

    mock_notify_channel.send.assert_called_once()
    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "0" in reply or "cannot" in reply or "contact" in reply


# ---------------------------------------------------------------------------
# 7. Bet amount exceeds balance
# ---------------------------------------------------------------------------

async def test_bet_blocked_overdraft(tmp_ledger, tmp_wallets, open_match, mock_notify_channel):
    """Bet is rejected when amount exceeds current balance."""
    user = _normal_user()
    wallet_utils.seed_wallet(user.id, user.display_name)  # 500 pts
    match_id = open_match["match_id"]
    msg = _bet_message(f".bet {match_id} 999 @TeamA win", mock_notify_channel, user)

    with patch("bot.PLACE_BETS_CHANNEL_ID", 0):
        await bot._handle_bet_command(msg)

    mock_notify_channel.send.assert_called_once()
    assert "500" in mock_notify_channel.send.call_args[0][0]  # shows their actual balance
    assert ledger_utils.get_match(match_id)["bets"] == []


# ---------------------------------------------------------------------------
# 8. Non-numeric bet amount
# ---------------------------------------------------------------------------

async def test_bet_invalid_amount_not_a_number(tmp_ledger, tmp_wallets, open_match, mock_notify_channel):
    """Non-numeric amount triggers a clear error message."""
    user = _normal_user()
    match_id = open_match["match_id"]
    msg = _bet_message(f".bet {match_id} alot @TeamA win", mock_notify_channel, user)

    with patch("bot.PLACE_BETS_CHANNEL_ID", 0):
        await bot._handle_bet_command(msg)

    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "invalid" in reply or "amount" in reply


# ---------------------------------------------------------------------------
# 9. Zero / negative bet amount
# ---------------------------------------------------------------------------

async def test_bet_zero_amount_rejected(tmp_ledger, tmp_wallets, open_match, mock_notify_channel):
    """A bet of zero points is rejected."""
    user = _normal_user()
    match_id = open_match["match_id"]
    msg = _bet_message(f".bet {match_id} 0 @TeamA win", mock_notify_channel, user)

    with patch("bot.PLACE_BETS_CHANNEL_ID", 0):
        await bot._handle_bet_command(msg)

    mock_notify_channel.send.assert_called_once()
    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "greater than zero" in reply or "must be" in reply


# ---------------------------------------------------------------------------
# 10. Bet on non-existent match
# ---------------------------------------------------------------------------

async def test_bet_nonexistent_match(tmp_ledger, tmp_wallets, mock_notify_channel):
    """Bet on a match ID that doesn't exist returns a clear error."""
    user = _normal_user()
    msg = _bet_message(".bet GF-9999 50 @TeamA win", mock_notify_channel, user)

    with patch("bot.PLACE_BETS_CHANNEL_ID", 0):
        await bot._handle_bet_command(msg)

    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "not found" in reply or "gf-9999" in reply


# ---------------------------------------------------------------------------
# 11. Bet on a match with betting locked (in_progress)
# ---------------------------------------------------------------------------

async def test_bet_blocked_on_locked_match(tmp_ledger, tmp_wallets, open_match, mock_notify_channel):
    """Bet is rejected when the match is no longer in betting_open status."""
    ledger_utils.set_match_status(open_match["match_id"], "in_progress")
    user = _normal_user()
    match_id = open_match["match_id"]
    msg = _bet_message(f".bet {match_id} 50 @TeamA win", mock_notify_channel, user)

    with patch("bot.PLACE_BETS_CHANNEL_ID", 0):
        await bot._handle_bet_command(msg)

    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "closed" in reply or "betting" in reply


# ---------------------------------------------------------------------------
# 12. Win bet with unrecognised team name
# ---------------------------------------------------------------------------

async def test_win_bet_unknown_team(tmp_ledger, tmp_wallets, open_match, mock_notify_channel):
    """Win bet mentioning neither team name returns a clear error."""
    user = _normal_user()
    wallet_utils.seed_wallet(user.id, user.display_name)
    match_id = open_match["match_id"]
    msg = _bet_message(f".bet {match_id} 50 @RandomTeam win", mock_notify_channel, user)

    with patch("bot.PLACE_BETS_CHANNEL_ID", 0):
        await bot._handle_bet_command(msg)

    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "unknown team" in reply or "teama" in reply or "teamb" in reply


# ---------------------------------------------------------------------------
# 13. Normal user tries .wallet give (admin-only)
# ---------------------------------------------------------------------------

async def test_normal_user_blocked_from_wallet_give(mock_message):
    """Non-admin cannot use .wallet give — receives permission error."""
    mock_message.content = ".wallet give @someone 100"
    mock_message.author.guild_permissions.administrator = False

    await bot._handle_wallet_command(mock_message)

    reply = mock_message.channel.send.call_args[0][0].lower()
    assert "admin" in reply or "permission" in reply


# ---------------------------------------------------------------------------
# 14. Normal user tries .ledger reset (admin-only)
# ---------------------------------------------------------------------------

async def test_normal_user_blocked_from_ledger_reset(mock_message):
    """Non-admin cannot use .ledger reset — receives permission error."""
    mock_message.content = ".ledger reset"
    mock_message.author.guild_permissions.administrator = False

    await bot._handle_ledger_command(mock_message)

    reply = mock_message.channel.send.call_args[0][0].lower()
    assert "admin" in reply or "permission" in reply


# ---------------------------------------------------------------------------
# 15. DM context — no guild_permissions → treated as non-admin
# ---------------------------------------------------------------------------

async def test_dm_context_no_guild_permissions(mock_notify_channel):
    """User with no guild_permissions (DM context) is treated as non-admin."""
    user = MagicMock()
    user.id = 777
    user.display_name = "DMUser"
    user.bot = False
    del user.guild_permissions  # No guild_permissions attribute

    msg = MagicMock()
    msg.content = ".match create @A @B"
    msg.channel = mock_notify_channel
    msg.author = user
    msg.role_mentions = []
    msg.mentions = []

    await bot._handle_match_command(msg)

    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "admin" in reply or "permission" in reply
