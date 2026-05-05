import threading

from utils import wallet as wallet_utils


def test_concurrent_wallet_writes(tmp_wallets):
    user_id = 42
    wallet_utils.seed_wallet(user_id, "concurrent-user")
    delta = 7

    errors = []

    def worker():
        try:
            wallet_utils.update_balance(user_id, delta)
        except Exception as exc:  # test should assert none occur
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    final_balance = wallet_utils.get_balance(user_id)
    assert final_balance == wallet_utils.SEED_AMOUNT + (10 * delta)
