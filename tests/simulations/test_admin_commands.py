"""
Simulations: privileged (admin) user running match, wallet, and ledger commands.

Skipped (already covered):
  - Admin .match create happy path  → test_full_flow_creates_match_and_posts_ledger
  - Admin .match create missing teams → test_match_create_command_missing_teams
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


@pytest.fixture()
def in_progress_match(tmp_ledger):
    m = ledger_utils.create_match("@TeamA", "@TeamB")
    ledger_utils.set_match_status(m["match_id"], "in_progress")
    return m


def _admin_message(content, channel, *, mentions=None, role_mentions=None, channel_name="general"):
    msg = MagicMock()
    msg.content = content
    msg.channel = channel
    msg.channel.name = channel_name
    msg.author = MagicMock()
    msg.author.display_name = "AdminUser"
    msg.author.bot = False
    perms = MagicMock()
    perms.administrator = True
    msg.author.guild_permissions = perms
    msg.guild = MagicMock()
    msg.mentions = mentions or []
    msg.role_mentions = role_mentions or []
    msg.add_reaction = AsyncMock()
    return msg


# ---------------------------------------------------------------------------
# .match draft
# ---------------------------------------------------------------------------

async def test_match_draft_happy_path(tmp_ledger, open_match, mock_notify_channel):
    """.match draft in a handshake channel moves status to in_progress."""
    match_id = open_match["match_id"]
    msg = _admin_message(
        f".match draft {match_id}", mock_notify_channel,
        channel_name="team-handshake",
    )

    with patch("bot.update_betting_embed", new=AsyncMock()):
        with patch("bot._post_wallets_to_reports", new=AsyncMock()):
            await bot._match_draft(msg)

    assert ledger_utils.get_match(match_id)["status"] == "in_progress"
    mock_notify_channel.send.assert_called_once()
    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "in progress" in reply




async def test_match_draft_nonexistent_match(tmp_ledger, mock_notify_channel):
    """.match draft for an unknown match ID returns a clear error."""
    msg = _admin_message(
        ".match draft GF-9999", mock_notify_channel,
        channel_name="team-handshake",
    )

    await bot._match_draft(msg)

    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "not found" in reply or "gf-9999" in reply


async def test_match_draft_wrong_status(tmp_ledger, in_progress_match, mock_notify_channel):
    """.match draft on a match already in_progress is rejected."""
    match_id = in_progress_match["match_id"]
    msg = _admin_message(
        f".match draft {match_id}", mock_notify_channel,
        channel_name="team-handshake",
    )

    await bot._match_draft(msg)

    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "not open" in reply or "status" in reply or "in_progress" in reply


# ---------------------------------------------------------------------------
# .match resolve winner
# ---------------------------------------------------------------------------

async def test_match_resolve_winner_happy_path(
    tmp_ledger, tmp_wallets, in_progress_match, mock_notify_channel
):
    """Admin resolves a winner; match moves to 'completed', payouts applied."""
    match_id = in_progress_match["match_id"]
    # Seed a bettor, deduct the bet amount (as _handle_bet_command would), then record it
    wallet_utils.seed_wallet(999, "Bettor")
    wallet_utils.update_balance(999, -100)  # deduct as if .bet command ran
    ledger_utils.add_bet(match_id, {
        "type": "win", "user_id": 999, "username": "@Bettor",
        "team": "@TeamA", "amount": 100,
    })

    msg = _admin_message(f".match resolve {match_id} winner @TeamA", mock_notify_channel)

    with patch("bot.update_betting_embed", new=AsyncMock()):
        await bot._match_resolve_winner(msg, match_id, msg.content.split())

    assert ledger_utils.get_match(match_id)["status"] == "completed"
    assert ledger_utils.get_match(match_id)["winner"] == "@TeamA"
    # Bettor had 500 - 100 = 400, then won all 100 back → 500 again
    assert wallet_utils.get_wallet(999)["balance"] == 500


async def test_match_resolve_winner_unknown_winner(
    tmp_ledger, in_progress_match, mock_notify_channel
):
    """Resolve attempt with an unrecognised team name returns a clear error."""
    match_id = in_progress_match["match_id"]
    msg = _admin_message(
        f".match resolve {match_id} winner @Nobody", mock_notify_channel
    )

    with patch("bot.update_betting_embed", new=AsyncMock()):
        await bot._match_resolve_winner(msg, match_id, msg.content.split())

    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "could not identify" in reply or "winner" in reply
    assert ledger_utils.get_match(match_id)["status"] == "in_progress"  # unchanged


async def test_match_resolve_winner_wrong_status(
    tmp_ledger, open_match, mock_notify_channel
):
    """Cannot resolve winner on a match that is still betting_open."""
    match_id = open_match["match_id"]
    msg = _admin_message(
        f".match resolve {match_id} winner @TeamA", mock_notify_channel
    )

    with patch("bot.update_betting_embed", new=AsyncMock()):
        await bot._match_resolve_winner(msg, match_id, msg.content.split())

    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "in_progress" in reply or "must be" in reply


# ---------------------------------------------------------------------------
# .wallet commands
# ---------------------------------------------------------------------------

async def test_wallet_give(tmp_wallets, mock_notify_channel):
    """Admin gives points to a user."""
    target = MagicMock()
    target.id = 555
    target.display_name = "Recipient"
    wallet_utils.seed_wallet(target.id, target.display_name)

    msg = _admin_message(".wallet give @Recipient 200", mock_notify_channel, mentions=[target])

    await bot._wallet_adjust(msg, "give", target, 200)

    assert wallet_utils.get_wallet(target.id)["balance"] == 700
    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "200" in reply and "700" in reply


async def test_wallet_take(tmp_wallets, mock_notify_channel):
    """Admin takes points from a user."""
    target = MagicMock()
    target.id = 556
    target.display_name = "Loser"
    wallet_utils.seed_wallet(target.id, target.display_name)

    msg = _admin_message(".wallet take @Loser 150", mock_notify_channel, mentions=[target])

    await bot._wallet_adjust(msg, "take", target, 150)

    assert wallet_utils.get_wallet(target.id)["balance"] == 350


async def test_wallet_set(tmp_wallets, mock_notify_channel):
    """Admin sets a user's balance to an exact amount."""
    target = MagicMock()
    target.id = 557
    target.display_name = "SetUser"
    wallet_utils.seed_wallet(target.id, target.display_name)

    msg = _admin_message(".wallet set @SetUser 1000", mock_notify_channel, mentions=[target])

    await bot._wallet_adjust(msg, "set", target, 1000)

    assert wallet_utils.get_wallet(target.id)["balance"] == 1000


async def test_wallet_check_existing(tmp_wallets, mock_notify_channel):
    """Admin checks balance of a user who has placed bets."""
    target = MagicMock()
    target.id = 558
    target.display_name = "Checker"
    wallet_utils.seed_wallet(target.id, target.display_name)

    msg = _admin_message(".wallet check @Checker", mock_notify_channel, mentions=[target])

    await bot._wallet_check(msg, target)

    reply = mock_notify_channel.send.call_args[0][0]
    assert "500" in reply
    assert "Checker" in reply


async def test_wallet_check_no_wallet(tmp_wallets, mock_notify_channel):
    """Admin checks balance of a user who has never bet — returns informative message."""
    target = MagicMock()
    target.id = 559
    target.display_name = "NewUser"

    msg = _admin_message(".wallet check @NewUser", mock_notify_channel, mentions=[target])

    await bot._wallet_check(msg, target)

    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "no wallet" in reply or "haven't" in reply


async def test_wallet_wipe(tmp_wallets, mock_notify_channel):
    """Admin wipes all wallets; balances reset to seed amount."""
    for uid in [600, 601, 602]:
        wallet_utils.seed_wallet(uid, f"User{uid}")
        wallet_utils.set_balance(uid, 1000)

    msg = _admin_message(".wallet wipe", mock_notify_channel)

    with patch("bot._post_wallets_to_reports", new=AsyncMock()):
        await bot._wallet_wipe(msg)

    for uid in [600, 601, 602]:
        assert wallet_utils.get_wallet(uid)["balance"] == wallet_utils.SEED_AMOUNT

    reply = mock_notify_channel.send.call_args[0][0]
    assert "3" in reply  # 3 wallets reset


# ---------------------------------------------------------------------------
# .ledger reset
# ---------------------------------------------------------------------------

async def test_ledger_reset(tmp_ledger, mock_notify_channel):
    """Admin resets the ledger; all matches are cleared."""
    ledger_utils.create_match("@A", "@B")
    ledger_utils.create_match("@C", "@D")
    assert len(ledger_utils.load_ledger()["matches"]) == 2

    msg = _admin_message(".ledger reset", mock_notify_channel)

    with patch("bot._post_wallets_to_reports", new=AsyncMock()):
        with patch("bot.update_betting_embed", new=AsyncMock()):
            await bot._ledger_reset(msg)

    assert ledger_utils.load_ledger()["matches"] == []
    reply = mock_notify_channel.send.call_args[0][0].lower()
    assert "reset" in reply
