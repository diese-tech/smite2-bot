# Godforge Web Portal TODO

This file tracks work intentionally skipped in the static prototype.

## Completed in the Local Prototype

- Added a dashboard-style admin portal surface with module navigation.
- Added a web tool sidebar for Random God, Roll Team (`.roll5`), and a command runner.
- Added a draft room UI that can call a local draft API when available.
- Added a build generator UI that can call a local build API when available.
- Added Match Ops and Betting dashboard modules with local API fallback data.
- Added a development-only `web_api` bridge around existing parser, loader, picker, resolver, draft, ledger, and wallet modules.
- Added protected admin operations telemetry and a manual Discord ledger embed sync control for the combined Railway process.
- Added temporary JSON-backed guild settings for feature toggles, channel labels, and admin/captain role labels.
- Added a temporary JSON-backed admin audit feed for dashboard actions.
- Kept Discord auth, storage, deployment, secrets, bot runtime files, and production assets untouched.

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
- Replace `data/guild_settings.json` with a real database before multi-guild production use.
- Replace `data/admin_audit.json` with durable database audit rows before serious multi-admin use.
- Start an asset manifest for owned graphics, especially god cards, item cards, role icons, and in-game map surfaces for rolls, drafts, and builds.

## Discord OAuth and Guild Authorization

- Create a Discord OAuth application for the web portal.
- Add login with Discord using the `identify` and `guilds` scopes.
- Show only guilds where the user has the required manage/admin permission.
- Verify the Godforge bot is installed before allowing server settings edits.
- Add a clear install flow for guilds that do not have the bot yet.

## Per-Server Settings Storage

- Choose storage for guild settings, custom commands, dashboard preferences, and asset mappings.
- Store settings by Discord guild ID.
- Track who changed settings and when.
- Add server-level defaults for role pools, source preference, channels, match rules, and feature toggles.

## Custom Command Execution

- Define a custom command schema: trigger, response, enabled state, channel scope, role gate, cooldown, and audit metadata.
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
- Add UI tests for dashboard tab switching, command preview, randomizer controls, and responsive layouts.
- Add authorization tests for Discord guild permissions before settings can be changed.
- Add bot integration tests for custom command execution and built-in command precedence.
