import json
from pathlib import Path

import pytest

from utils import wallet as wallet_utils


def test_save_wallets_atomic(tmp_wallets, monkeypatch):
    calls = []

    def fail_replace(src, dst):
        calls.append((Path(src), Path(dst)))
        raise OSError("replace failed")

    monkeypatch.setattr(wallet_utils.os, "replace", fail_replace)

    with pytest.raises(OSError):
        wallet_utils.save_wallets({"1": {"username": "u", "balance": 10}})

    assert calls, "os.replace should be called for atomic writes"
    assert not list(tmp_wallets.parent.glob("*.tmp")), "temp file should be cleaned on failure"


def test_update_balance_missing_user(tmp_wallets):
    with pytest.raises(KeyError, match="No wallet for user_id 999"):
        wallet_utils.update_balance(999, 5)


def test_reset_all_creates_backup(tmp_wallets):
    wallet_utils.save_wallets({"1": {"username": "u", "balance": 123}})
    count = wallet_utils.reset_all()

    backup = tmp_wallets.parent / "wallets.bak.json"
    assert count == 1
    assert backup.exists()
    backup_data = json.loads(backup.read_text())
    assert backup_data["1"]["balance"] == 123
    current = wallet_utils.load_wallets()
    assert current["1"]["balance"] == wallet_utils.SEED_AMOUNT
