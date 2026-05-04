"""
Simulations: different server configurations.

Covers three personas:
  - "Frank's server" — fully configured (both channel IDs set)
  - Misconfigured server — one or both IDs missing / wrong
  - Self-hosted server — someone reconfigured the bot with their own channel IDs

Skipped (already covered):
  - BETTING_LEDGER_CHANNEL_ID=0 notification → test_update_embed_notifies_when_channel_id_zero
  - Channel not found notification  → test_update_embed_notifies_when_channel_not_found
  - Bot lacks send permission       → test_update_embed_forbidden_on_send_notifies
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
    return ledger_utils.create_match("@TeamA", "@TeamB")


def _user_message(content, channel, *, admin=False, user_id=100, mentions=None):
    msg = MagicMock()
    msg.content = content
    msg.channel = channel
    msg.author = MagicMock()
    msg.author.id = user_id
    msg.author.display_name = "ServerUser"
    msg.author.bot = False
    perms = MagicMock()
    perms.administrator = admin
    msg.author.guild_permissions = perms
    msg.guild = MagicMock()
    msg.role_mentions = []
    msg.mentions = mentions or []
    msg.add_reaction = AsyncMock()
    return msg


# ---------------------------------------------------------------------------
# Frank's server — both channel IDs properly configured
# ---------------------------------------------------------------------------

FRANKS_LEDGER_CHANNEL_ID  = 111000
FRANKS_BETS_CHANNEL_ID    = 222000


async def test_franks_server_bet_in_correct_channel(
    tmp_ledger, tmp_wallets, open_match
):
    """
    Frank's server: PLACE_BETS_CHANNEL_ID=222000.
    Bet placed in #place-bets (id=222000) → accepted.
    """
    bets_channel = MagicMock()
    bets_channel.id = FRANKS_BETS_CHANNEL_ID
    bets_channel.send = AsyncMock()

    user = MagicMock()
    user.id = 201
    user.display_name = "FrankUser"
    user.bot = False
    perms = MagicMock()
    perms.administrator = False
    user.guild_permissions = perms

    wallet_utils.seed_wallet(user.id, user.display_name)
    match_id = open_match["match_id"]
    msg = _user_message(
        f".bet {match_id} 50 @TeamA win", bets_channel,
        user_id=user.id,
    )
    msg.author = user

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("bot.PLACE_BETS_CHANNEL_ID", FRANKS_BETS_CHANNEL_ID))
        stack.enter_context(patch("bot.update_betting_embed", new=AsyncMock()))
        await bot._handle_bet_command(msg)

    assert len(ledger_utils.get_match(match_id)["bets"]) == 1


async def test_franks_server_bet_in_wrong_channel(
    tmp_ledger, tmp_wallets, open_match
):
    """
    Frank's server: PLACE_BETS_CHANNEL_ID=222000.
    Bet placed in #general (id=333000) → rejected with channel hint.
    """
    wrong_channel = MagicMock()
    wrong_channel.id = 333000
    wrong_channel.send = AsyncMock()

    match_id = open_match["match_id"]
    msg = _user_message(f".bet {match_id} 50 @TeamA win", wrong_channel)

    with patch("bot.PLACE_BETS_CHANNEL_ID", FRANKS_BETS_CHANNEL_ID):
        await bot._handle_bet_command(msg)

    wrong_channel.send.assert_called_once()
    assert "place-bets" in wrong_channel.send.call_args[0][0].lower()
    assert ledger_utils.get_match(match_id)["bets"] == []


async def test_franks_server_admin_creates_match(tmp_ledger, mock_notify_channel):
    """
    Frank's server: admin creates match; ledger embed updates in configured channel.
    """
    ledger_channel = MagicMock()
    ledger_channel.id = FRANKS_LEDGER_CHANNEL_ID
    ledger_channel.send = AsyncMock(return_value=MagicMock(id=9001))
    ledger_channel.fetch_message = AsyncMock(side_effect=Exception("not found"))

    role_a = MagicMock(); role_a.name = "TeamA"
    role_b = MagicMock(); role_b.name = "TeamB"

    msg = _user_message(".match create @TeamA @TeamB", mock_notify_channel, admin=True)
    msg.role_mentions = [role_a, role_b]

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("bot.BETTING_LEDGER_CHANNEL_ID", FRANKS_LEDGER_CHANNEL_ID))
        stack.enter_context(patch.object(bot.client, "get_channel", return_value=ledger_channel))
        stack.enter_context(patch("bot._build_ledger_embed", return_value=MagicMock()))
        stack.enter_context(patch("bot.BettingLedgerView", return_value=MagicMock()))
        await bot._match_create(msg)

    assert len(ledger_utils.load_ledger()["matches"]) == 1
    ledger_channel.send.assert_called_once()


# ---------------------------------------------------------------------------
# Misconfigured server — PLACE_BETS_CHANNEL_ID not set
# ---------------------------------------------------------------------------

async def test_misconfigured_no_bet_channel_allows_bets_anywhere(
    tmp_ledger, tmp_wallets, open_match, mock_notify_channel
):
    """
    Server where PLACE_BETS_CHANNEL_ID was never set (=0).
    Bets should be accepted from any channel.
    """
    user = MagicMock()
    user.id = 300
    user.display_name = "AnyoneUser"
    user.bot = False
    perms = MagicMock()
    perms.administrator = False
    user.guild_permissions = perms

    wallet_utils.seed_wallet(user.id, user.display_name)
    match_id = open_match["match_id"]
    msg = _user_message(f".bet {match_id} 50 @TeamA win", mock_notify_channel, user_id=user.id)
    msg.author = user

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("bot.PLACE_BETS_CHANNEL_ID", 0))
        stack.enter_context(patch("bot.update_betting_embed", new=AsyncMock()))
        await bot._handle_bet_command(msg)

    assert len(ledger_utils.get_match(match_id)["bets"]) == 1


async def test_misconfigured_no_ledger_channel_informs_admin(
    tmp_ledger, mock_notify_channel
):
    """
    Server where BETTING_LEDGER_CHANNEL_ID was never set.
    Admin creating a match sees an informative error; match is still saved.
    """
    role_a = MagicMock(); role_a.name = "TeamA"
    role_b = MagicMock(); role_b.name = "TeamB"
    msg = _user_message(".match create @TeamA @TeamB", mock_notify_channel, admin=True)
    msg.role_mentions = [role_a, role_b]

    with patch("bot.BETTING_LEDGER_CHANNEL_ID", 0):
        await bot._match_create(msg)

    # Match still persisted
    assert len(ledger_utils.load_ledger()["matches"]) == 1
    # Informative message sent to the command channel
    calls = [c[0][0] for c in mock_notify_channel.send.call_args_list]
    config_warning = any("configured" in t.lower() or "admin" in t.lower() for t in calls)
    assert config_warning


async def test_misconfigured_wrong_ledger_channel_id_informs_admin(
    tmp_ledger, mock_notify_channel
):
    """
    Server where BETTING_LEDGER_CHANNEL_ID points to a deleted or inaccessible channel.
    Admin sees a 'could not be found' message; match is still created.
    """
    import discord
    role_a = MagicMock(); role_a.name = "TeamA"
    role_b = MagicMock(); role_b.name = "TeamB"
    msg = _user_message(".match create @TeamA @TeamB", mock_notify_channel, admin=True)
    msg.role_mentions = [role_a, role_b]

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("bot.BETTING_LEDGER_CHANNEL_ID", 999888777))
        stack.enter_context(patch.object(bot.client, "get_channel", return_value=None))
        stack.enter_context(patch.object(
            bot.client, "fetch_channel",
            new=AsyncMock(side_effect=discord.NotFound(MagicMock(), "not found")),
        ))
        await bot._match_create(msg)

    assert len(ledger_utils.load_ledger()["matches"]) == 1
    calls = [c[0][0] for c in mock_notify_channel.send.call_args_list]
    error_sent = any("could not be found" in t.lower() or "admin" in t.lower() for t in calls)
    assert error_sent


# ---------------------------------------------------------------------------
# Self-hosted / reconfigured server
# ---------------------------------------------------------------------------

CUSTOM_LEDGER_ID = 777100
CUSTOM_BETS_ID   = 777200


async def test_custom_server_full_bet_flow(
    tmp_ledger, tmp_wallets, open_match
):
    """
    User has cloned the bot and set their own channel IDs.
    Bet placed in their configured #place-bets → accepted.
    """
    custom_bets_ch = MagicMock()
    custom_bets_ch.id = CUSTOM_BETS_ID
    custom_bets_ch.send = AsyncMock()

    user = MagicMock()
    user.id = 401
    user.display_name = "CustomServerUser"
    user.bot = False
    perms = MagicMock()
    perms.administrator = False
    user.guild_permissions = perms

    wallet_utils.seed_wallet(user.id, user.display_name)
    match_id = open_match["match_id"]

    msg = MagicMock()
    msg.content = f".bet {match_id} 50 @TeamA win"
    msg.channel = custom_bets_ch
    msg.author = user
    msg.guild = MagicMock()
    msg.role_mentions = []
    msg.mentions = []
    msg.add_reaction = AsyncMock()

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch("bot.PLACE_BETS_CHANNEL_ID", CUSTOM_BETS_ID))
        stack.enter_context(patch("bot.update_betting_embed", new=AsyncMock()))
        await bot._handle_bet_command(msg)

    assert len(ledger_utils.get_match(match_id)["bets"]) == 1


async def test_custom_server_old_bets_channel_rejected(
    tmp_ledger, open_match
):
    """
    Server owner changed PLACE_BETS_CHANNEL_ID but a user posts in the old channel.
    Bet is rejected with a redirect message.
    """
    OLD_CHANNEL_ID = 555000
    old_channel = MagicMock()
    old_channel.id = OLD_CHANNEL_ID
    old_channel.send = AsyncMock()

    match_id = open_match["match_id"]
    msg = MagicMock()
    msg.content = f".bet {match_id} 50 @TeamA win"
    msg.channel = old_channel
    msg.author = MagicMock()
    msg.author.id = 402
    msg.role_mentions = []
    msg.mentions = []

    with patch("bot.PLACE_BETS_CHANNEL_ID", CUSTOM_BETS_ID):  # new channel ID
        await bot._handle_bet_command(msg)

    old_channel.send.assert_called_once()
    assert "place-bets" in old_channel.send.call_args[0][0].lower()
