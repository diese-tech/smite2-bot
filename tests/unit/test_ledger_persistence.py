import json
from pathlib import Path

import pytest

from utils import ledger as ledger_utils


def test_save_ledger_atomic(tmp_ledger, monkeypatch):
    calls = []

    def fail_replace(src, dst):
        calls.append((Path(src), Path(dst)))
        raise OSError("replace failed")

    monkeypatch.setattr(ledger_utils.os, "replace", fail_replace)

    with pytest.raises(OSError):
        ledger_utils.save_ledger({"matches": []})

    assert calls, "os.replace should be called for atomic writes"
    assert not list(tmp_ledger.parent.glob("*.tmp")), "temp file should be cleaned on failure"


def test_resolve_win_bets_idempotent(tmp_ledger):
    m = ledger_utils.create_match("A", "B")
    ledger_utils.add_bet(m["match_id"], {"type": "win", "user_id": 1, "username": "u", "team": "A", "amount": 10})

    first = ledger_utils.resolve_win_bets(m["match_id"], "A")
    second = ledger_utils.resolve_win_bets(m["match_id"], "A")

    assert len(first) == 1
    assert second == []


def test_resolve_prop_bets_idempotent(tmp_ledger):
    m = ledger_utils.create_match("A", "B")
    ledger_utils.add_bet(m["match_id"], {
        "type": "prop", "user_id": 1, "username": "u", "player": "Player1", "stat": "kills",
        "direction": "over", "threshold": 10.5, "amount": 10,
    })

    first, had_bets_first = ledger_utils.resolve_prop_bets(m["match_id"], "player1", "KILLS", 12)
    second, had_bets_second = ledger_utils.resolve_prop_bets(m["match_id"], "Player1", "kills", 12)

    assert had_bets_first is True
    assert len(first) == 1
    assert second == []
    assert had_bets_second is False


def test_reset_ledger_creates_backup(tmp_ledger):
    ledger_utils.create_match("A", "B")
    ledger_utils.reset_ledger()

    backup = tmp_ledger.parent / "weekly_ledger.bak.json"
    assert backup.exists()
    backup_data = json.loads(backup.read_text())
    assert len(backup_data["matches"]) == 1
    assert ledger_utils.load_ledger()["matches"] == []
