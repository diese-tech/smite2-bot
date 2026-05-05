# Godforge Web Portal TODO

This file tracks work intentionally skipped in the static prototype.

Version note: the ledger system is the v2.0 milestone. Dashboard bridge work is staged for `v2.1.0`, to be tagged after OAuth and DB-backed dashboard basics are working.

Release/version update locations are documented in `../RELEASE_PROCESS.md`. The `.help` footer version comes from `../utils/formatter.py`.

## Completed in the Local Prototype

- Added a dashboard-style admin portal surface with module navigation.
- Added a web tool sidebar for Random God, Roll Team (`.roll5`), and a command runner.
- Added a draft room UI that can call a local draft API when available.
- Added a build generator UI that can call a local build API when available.
- Added Match Ops and Betting dashboard modules with local API fallback data.
- Added a development-only `web_api` bridge around existing parser, loader, picker, resolver, draft, ledger, and wallet modules.
- Added protected admin operations telemetry and a manual Discord ledger embed sync control for the combined Railway process.
- Added temporary dashboard-backed guild settings for feature toggles, channel labels, and admin/captain role labels.
- Added a temporary dashboard-backed admin audit feed for dashboard actions.
- Added a MEE6-inspired managed-server selector grid fed by live bot guild telemetry.
- Grouped the dashboard sidebar into MEE6-style module categories with live/staged status markers.
- Added local selected-server state in the sidebar as a placeholder for future Discord OAuth guild scoping.
- Added a production readiness panel for auth, guild permissions, and database gates.
- Added Bot Masters permission staging for role labels and future monetization access levels.
- Added temporary dashboard-backed custom command configuration staging.
- Staged Discord OAuth, combined Railway hosting, and optional SQLite dashboard storage while keeping secrets and production assets out of git.

## Bot Command Surface Parity

| Bot Command | Dashboard Module | API Endpoint | Status |
|---|---|---|---|
| `.rg` | Randomizer | `GET /api/gods/roll` | Wired |
| `.roll5` / Roll Team | Randomizer | `GET /api/gods/roll5` | Wired |
| `.build` | Builds | `GET /api/builds/roll` | Wired |
| `.draft start` | Drafts | `POST /api/draft/start` | Demo only - intentional local draft state |
| `.match create` | Match Ops | `POST /api/match/create` | Wired |
| `.match draft` | Match Ops | `POST /api/match/status` | Wired as status transition |
| `.match resolve` | Match Ops | `POST /api/match/resolve/winner`, `POST /api/match/resolve/prop` | Wired for winner and prop resolution |
| `.bet` | Betting Panel | `POST /api/bet/place` | Wired for local win and prop bets |
| `.wallet give/take/set` | Betting Panel | `POST /api/wallet/adjust` | Wired |
| `.wallet check` | Betting Panel | `GET /api/wallets` | Wired |
| `.ledger reset` | Betting Panel | `POST /api/ledger/reset` | Wired |
| `.ledger post` | Betting Panel | - | Not yet scoped; Discord embed only |

## Morning Priority

- Watch GitHub/Railway after each pushed batch and verify the live dashboard still serves public tools plus protected admin modules.
- Continue the MEE6-style dashboard pass: server selector states, module cards, audit activity, permission placeholders, and guild-scoped settings scaffolding.
- Run the local Python API and verify every web endpoint against real bot data after each admin surface expansion.
- Keep SQLite dashboard document storage enabled in Railway with `GODFORGE_STORAGE=sqlite` and `GODFORGE_DB_PATH=/app/data/godforge_dashboard.db`.
- Replace local JSON fallback storage with durable SQLite/Postgres storage before serious multi-admin use.
- Add migration/export tooling before changing storage formats again.
- Use `ASSET_MANIFEST.md` when owned graphics are available, especially god cards, item cards, role icons, and in-game map surfaces for rolls, drafts, and builds.

## Discord OAuth and Guild Authorization

- Discord OAuth application is configured for the web portal.
- Railway public URL: `https://godforge-hub.up.railway.app`.
- Discord client id: `1493371999031136318`.
- OAuth callback: `https://godforge-hub.up.railway.app/api/auth/discord/callback`.
- Keep `DISCORD_CLIENT_SECRET` in Railway only; do not commit it.
- Login with Discord is staged using the `identify` and `guilds` scopes.
- OAuth endpoints are staged: `GET /api/auth/discord/start` and `GET /api/auth/discord/callback`.
- Show only guilds where the user has the required manage/admin permission.
- Verify the Godforge bot is installed before allowing server settings edits.
- Add a clear install flow for guilds that do not have the bot yet.

## Per-Server Settings Storage

- Keep settings, custom commands, dashboard preferences, and future asset mappings in the dashboard storage layer.
- Store settings by Discord guild ID.
- Track who changed settings and when.
- Add server-level defaults for role pools, source preference, channels, match rules, and feature toggles.

## Custom Command Execution

- Define a custom command schema: trigger, response, enabled state, channel scope, role gate, cooldown, and audit metadata.
- Custom command schema is staged in `data/custom_commands.json`.
- Add a bot-side resolver before unknown commands are silently ignored.
- Enforce guild/channel/role/cooldown checks in the bot before responding.
- Add conflict handling for built-in commands and duplicate custom triggers.
- Add tests for create, update, disable, delete, conflict, and permission behavior.

## Shared Web API for Bot Logic

- Harden the local `web_api` prototype into a real service after auth and hosting decisions are made.
- Return web-friendly JSON for all Discord command families that should exist on the website.
- Keep Discord formatting separate from web formatting.
- Add tests proving Discord and web results use the same data and selection rules.
- Decide later whether the API is a standalone service or part of an existing Activity backend.

## Production Graphics Ingestion

- Prepare an asset manifest for:
  - `god-card`
  - `item-card`
  - `role-icon`
  - `dashboard-hero`
  - `background-texture`
  - `conquest-map`
  - `draft-map`
  - `roll-map`
- Asset manifest exists at `ASSET_MANIFEST.md`.
- Ingest graphics from the future Google Drive or zip source.
- Normalize filenames and dimensions.
- Replace temporary public god portraits and CSS placeholder surfaces with owned assets.
- Add fallback handling for missing god/item art.
- Design map-aware roll and draft states once the official in-game map graphics are available.

## Deployment and Domain

- Keep the bot deployment separate from the website deployment.
- Configure Vercel project root to `web` if deploying this static site directly.
- Attach a custom domain instead of relying on the public `.vercel.app` URL.
- Add production metadata: favicon, Open Graph image, `robots.txt`, `sitemap.xml`, and canonical URL.

## Testing Before Real Admin Features

- Add unit tests for any future API wrapper around bot logic.
- Static dashboard tab/panel coverage exists via `npm run test:dashboard`.
- Add deeper UI tests for command preview, randomizer controls, and responsive layouts.
- Add authorization tests for Discord guild permissions before settings can be changed.
- Add bot integration tests for custom command execution and built-in command precedence.
