"""
Wallet persistence for the GodForge betting system.

All read/write operations on wallets.json are encapsulated here.
Balances survive ledger resets and season transitions.
They are only wiped by an explicit .wallet wipe command.

Starting balance: 500 points (auto-seeded on first bet).
Balances CAN go negative via admin .wallet take — no floor.
"""

import json
from pathlib import Path

WALLETS_PATH = Path("data/wallets.json")
SEED_AMOUNT = 500


# ---------------------------------------------------------------------------
# Raw I/O
# ---------------------------------------------------------------------------

def load_wallets() -> dict:
    if not WALLETS_PATH.exists():
        return {}
    try:
        with open(WALLETS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_wallets(data: dict):
    WALLETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WALLETS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Wallet operations
# ---------------------------------------------------------------------------

def get_wallet(user_id: int) -> dict | None:
    """Return the wallet dict for user_id, or None if no wallet exists."""
    return load_wallets().get(str(user_id))


def seed_wallet(user_id: int, username: str) -> int:
    """
    Auto-seed wallet at SEED_AMOUNT if this user has no entry.
    Returns the current balance (whether seeded or pre-existing).
    """
    wallets = load_wallets()
    uid = str(user_id)
    if uid not in wallets:
        wallets[uid] = {"username": username, "balance": SEED_AMOUNT}
        save_wallets(wallets)
    else:
        # Keep username fresh
        wallets[uid]["username"] = username
        save_wallets(wallets)
    return wallets[uid]["balance"]


def get_balance(user_id: int) -> int | None:
    wallet = get_wallet(user_id)
    return wallet["balance"] if wallet else None


def update_balance(user_id: int, delta: int) -> int:
    """Add delta to user's balance (use negative delta to subtract). Returns new balance."""
    wallets = load_wallets()
    uid = str(user_id)
    wallets[uid]["balance"] += delta
    save_wallets(wallets)
    return wallets[uid]["balance"]


def set_balance(user_id: int, amount: int) -> int:
    """Set user's balance to an exact amount. Returns new balance."""
    wallets = load_wallets()
    uid = str(user_id)
    wallets[uid]["balance"] = amount
    save_wallets(wallets)
    return amount


def ensure_wallet(user_id: int, username: str) -> int:
    """
    Ensure a wallet entry exists for user_id (creates with 0 balance if absent,
    rather than the seed amount — for admin give/take/set on non-betters).
    Returns current balance.
    """
    wallets = load_wallets()
    uid = str(user_id)
    if uid not in wallets:
        wallets[uid] = {"username": username, "balance": 0}
        save_wallets(wallets)
    return wallets[uid]["balance"]


def apply_payouts(payouts: list[dict]):
    """Bulk-add payout amounts to wallets. Skips unknown user IDs gracefully."""
    if not payouts:
        return
    wallets = load_wallets()
    for p in payouts:
        uid = str(p["user_id"])
        if uid in wallets:
            wallets[uid]["balance"] += p["payout"]
    save_wallets(wallets)


def reset_all() -> int:
    """
    Reset every wallet balance to SEED_AMOUNT.
    Does not remove players — only resets balances.
    Returns count of wallets reset.
    """
    wallets = load_wallets()
    for uid in wallets:
        wallets[uid]["balance"] = SEED_AMOUNT
    save_wallets(wallets)
    return len(wallets)
