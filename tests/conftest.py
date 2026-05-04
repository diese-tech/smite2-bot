"""
Shared pytest fixtures for GodForge tests.

All Discord objects are mocked — no real Discord connection is made.
All file I/O uses tmp_path — no real data files are touched.
"""
import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Minimal discord stub so bot.py can be imported without discord installed
# (the real discord.py is expected in the test environment; this guard only
# ensures import-time safety).
# ---------------------------------------------------------------------------

def _make_discord_stub():
    """Return a minimal discord module stub used when discord.py is absent."""
    stub = types.ModuleType("discord")
    stub.Client = MagicMock
    stub.Intents = MagicMock()
    stub.Intents.default = MagicMock(return_value=MagicMock())
    stub.Message = MagicMock
    stub.Embed = MagicMock
    stub.Color = MagicMock()
    stub.NotFound = type("NotFound", (Exception,), {})
    stub.Forbidden = type("Forbidden", (Exception,), {})
    stub.HTTPException = type("HTTPException", (Exception,), {})
    abc = types.ModuleType("discord.abc")
    abc.Messageable = object
    stub.abc = abc

    ext = types.ModuleType("discord.ext")
    tasks_mod = types.ModuleType("discord.ext.tasks")
    tasks_mod.loop = lambda **kw: (lambda f: f)
    ext.tasks = tasks_mod
    stub.ext = ext
    return stub


# ---------------------------------------------------------------------------
# JSON file fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_ledger(tmp_path, monkeypatch):
    """Redirect ledger I/O to a fresh tmp file for each test."""
    import utils.ledger as ledger_mod
    ledger_file = tmp_path / "weekly_ledger.json"
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", ledger_file)
    return ledger_file


@pytest.fixture()
def tmp_wallets(tmp_path, monkeypatch):
    """Redirect wallet I/O to a fresh tmp file for each test."""
    import utils.wallet as wallet_mod
    wallet_file = tmp_path / "wallets.json"
    monkeypatch.setattr(wallet_mod, "WALLETS_PATH", wallet_file)
    return wallet_file


@pytest.fixture()
def tmp_settings(tmp_path, monkeypatch):
    """Redirect dashboard settings I/O to a fresh tmp file for each test."""
    import utils.settings as settings_mod
    settings_file = tmp_path / "guild_settings.json"
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", settings_file)
    return settings_file


# ---------------------------------------------------------------------------
# Discord mock objects
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_sent_message():
    """A Discord message object returned by channel.send()."""
    msg = MagicMock()
    msg.id = 99999
    msg.edit = AsyncMock()
    return msg


@pytest.fixture()
def mock_ledger_channel(mock_sent_message):
    """A mock Discord channel representing #betting-ledger."""
    channel = MagicMock()
    channel.id = 111222333
    channel.send = AsyncMock(return_value=mock_sent_message)
    channel.fetch_message = AsyncMock(return_value=mock_sent_message)
    return channel


@pytest.fixture()
def mock_notify_channel():
    """A mock Discord channel used for command-response notifications."""
    channel = MagicMock()
    channel.id = 444555666
    channel.send = AsyncMock()
    return channel


@pytest.fixture()
def mock_author():
    """A mock Discord member with administrator permissions."""
    author = MagicMock()
    author.id = 123456789
    author.display_name = "TestUser"
    author.bot = False
    perms = MagicMock()
    perms.administrator = True
    author.guild_permissions = perms
    return author


@pytest.fixture()
def mock_author_no_admin(mock_author):
    """A mock Discord member WITHOUT administrator permissions."""
    mock_author.guild_permissions.administrator = False
    return mock_author


@pytest.fixture()
def mock_message(mock_notify_channel, mock_author):
    """A mock Discord Message for .match create @TeamA @TeamB."""
    msg = MagicMock()
    msg.content = ".match create @TeamA @TeamB"
    msg.channel = mock_notify_channel
    msg.author = mock_author
    msg.guild = MagicMock()
    msg.role_mentions = []
    msg.mentions = []
    msg.add_reaction = AsyncMock()
    return msg
