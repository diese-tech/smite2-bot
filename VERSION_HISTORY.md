# GodForge Version History

This file tracks product-level milestones so dashboard and bot work does not blur together across releases.

## v2.0 - Ledger System

The ledger and wallet system brought GodForge to v2.0.

Included scope:

- Match lifecycle commands and ledger JSON persistence.
- Wallet balances and betting payouts.
- Discord ledger posting and embed update behavior.
- Tests for match creation, team matching, ledger posting, normal-user bets, and admin commands.

## v2.1 - Live Dashboard Bridge

Current local work is staged as v2.1 candidate work unless a later release decision changes the version.

Included or in-progress scope:

- Railway single-service launcher for bot plus web/API.
- Temporary password-protected admin dashboard.
- Match Ops, Betting, Wallets, Settings, and Admin Overview panels.
- Manual Discord ledger sync from the dashboard.
- Module health, managed-server selector, JSON-backed guild settings, and admin audit feed.
- Documentation and tests for the temporary web/API bridge.

## Future Version Gates

Substantial work after v2.0 should be tagged deliberately before deployment or release notes:

- `v2.1`: Live admin dashboard bridge and MEE6-style management surface.
- `v2.2`: Discord OAuth, guild picker, and guild permission checks.
- `v2.3`: Database-backed settings, wallets, ledger, and durable audit rows.
- `v3.0`: Full dual-use platform milestone with standalone web users and production-grade assets.
