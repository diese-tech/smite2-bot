"""
Tests for god-rights (owner bypass) in _is_admin.
"""
import pytest
from unittest.mock import MagicMock, patch

import bot


def _message(user_id, *, is_admin_perm=False):
    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = user_id
    perms = MagicMock()
    perms.administrator = is_admin_perm
    msg.author.guild_permissions = perms
    return msg


def test_god_user_passes_without_server_perms():
    """Owner ID bypasses the check even with no server admin permission."""
    msg = _message(bot._GOD_USER_ID, is_admin_perm=False)
    assert bot._is_admin(msg) is True


def test_god_user_passes_in_dm_context():
    """Owner ID bypasses even when guild_permissions is absent (DM context)."""
    msg = MagicMock()
    msg.author = MagicMock()
    msg.author.id = bot._GOD_USER_ID
    del msg.author.guild_permissions
    assert bot._is_admin(msg) is True


def test_regular_admin_still_passes():
    """Normal Discord server admins continue to work."""
    msg = _message(99999, is_admin_perm=True)
    assert bot._is_admin(msg) is True


def test_regular_user_still_blocked():
    """Non-admin, non-owner users are still blocked."""
    msg = _message(99999, is_admin_perm=False)
    assert bot._is_admin(msg) is False


def test_different_user_id_not_granted():
    """An ID one digit off from the owner's is not granted god rights."""
    msg = _message(bot._GOD_USER_ID + 1, is_admin_perm=False)
    assert bot._is_admin(msg) is False
