from unittest.mock import AsyncMock, MagicMock

import pytest

import bot
from utils import custom_commands


def _message(content=".scrimrules", *, guild_id="123", channel_name="captains", admin=False, roles=None):
    channel = MagicMock()
    channel.id = 555
    channel.name = channel_name
    channel.send = AsyncMock()

    author = MagicMock()
    author.id = 999
    author.bot = False
    author.display_name = "ScrimUser"
    author.roles = roles or []
    perms = MagicMock()
    perms.administrator = admin
    author.guild_permissions = perms

    msg = MagicMock()
    msg.content = content
    msg.channel = channel
    msg.author = author
    msg.guild = MagicMock()
    msg.guild.id = guild_id
    return msg


@pytest.fixture(autouse=True)
def clear_cooldowns():
    bot._custom_command_cooldowns.clear()


@pytest.mark.asyncio
async def test_custom_command_executes_for_matching_unknown_trigger(tmp_custom_commands):
    custom_commands.upsert_command(
        "123",
        {
            "trigger": ".scrimrules",
            "response": "Post lobby code before queue.",
            "channel": "#captains",
            "role_gate": "Everyone",
            "cooldown": "0s",
            "enabled": True,
        },
    )

    msg = _message()

    handled = await bot._handle_custom_command(msg, "scrimrules")

    assert handled is True
    msg.channel.send.assert_awaited_once()
    assert msg.channel.send.await_args.args[0] == "Post lobby code before queue."


@pytest.mark.asyncio
async def test_custom_command_falls_back_to_global_config(tmp_custom_commands):
    custom_commands.upsert_command(
        "global",
        {
            "trigger": ".rules",
            "response": "Global rules.",
            "channel": "",
            "role_gate": "Everyone",
            "cooldown": "0s",
            "enabled": True,
        },
    )

    msg = _message(".rules", guild_id="456", channel_name="general")

    handled = await bot._handle_custom_command(msg, "rules")

    assert handled is True
    msg.channel.send.assert_awaited_once()
    assert msg.channel.send.await_args.args[0] == "Global rules."


@pytest.mark.asyncio
async def test_disabled_custom_command_is_handled_without_response(tmp_custom_commands):
    custom_commands.upsert_command(
        "123",
        {
            "trigger": ".closed",
            "response": "Nope.",
            "channel": "",
            "role_gate": "Everyone",
            "cooldown": "0s",
            "enabled": False,
        },
    )

    msg = _message(".closed")

    handled = await bot._handle_custom_command(msg, "closed")

    assert handled is True
    msg.channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_custom_command_enforces_channel_gate(tmp_custom_commands):
    custom_commands.upsert_command(
        "123",
        {
            "trigger": ".captains",
            "response": "Captain notes.",
            "channel": "#captains",
            "role_gate": "Everyone",
            "cooldown": "0s",
            "enabled": True,
        },
    )

    msg = _message(".captains", channel_name="general")

    handled = await bot._handle_custom_command(msg, "captains")

    assert handled is True
    assert "can only be used" in msg.channel.send.await_args.args[0]


@pytest.mark.asyncio
async def test_custom_command_enforces_role_gate(tmp_custom_commands):
    custom_commands.upsert_command(
        "123",
        {
            "trigger": ".adminnote",
            "response": "Admin notes.",
            "channel": "",
            "role_gate": "Admins",
            "cooldown": "0s",
            "enabled": True,
        },
    )

    msg = _message(".adminnote", admin=False)

    handled = await bot._handle_custom_command(msg, "adminnote")

    assert handled is True
    assert "do not have permission" in msg.channel.send.await_args.args[0]


@pytest.mark.asyncio
async def test_custom_command_allows_captain_role(tmp_custom_commands):
    custom_commands.upsert_command(
        "123",
        {
            "trigger": ".captainnote",
            "response": "Captain notes.",
            "channel": "",
            "role_gate": "Captains",
            "cooldown": "0s",
            "enabled": True,
        },
    )
    captain_role = MagicMock()
    captain_role.name = "Captains"
    msg = _message(".captainnote", roles=[captain_role])

    handled = await bot._handle_custom_command(msg, "captainnote")

    assert handled is True
    assert msg.channel.send.await_args.args[0] == "Captain notes."


@pytest.mark.asyncio
async def test_custom_command_cooldown_is_per_user(tmp_custom_commands):
    custom_commands.upsert_command(
        "123",
        {
            "trigger": ".timer",
            "response": "Tick.",
            "channel": "",
            "role_gate": "Everyone",
            "cooldown": "5s",
            "enabled": True,
        },
    )

    msg = _message(".timer")

    assert await bot._handle_custom_command(msg, "timer") is True
    assert await bot._handle_custom_command(msg, "timer") is True

    assert msg.channel.send.await_count == 2
    assert "cooldown" in msg.channel.send.await_args.args[0]


@pytest.mark.asyncio
async def test_unknown_custom_command_is_not_handled(tmp_custom_commands):
    msg = _message(".missing")

    handled = await bot._handle_custom_command(msg, "missing")

    assert handled is False
    msg.channel.send.assert_not_awaited()
