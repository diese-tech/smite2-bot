# Godforge Website

Static landing page and admin portal for the Godforge Discord bot.

This folder is intentionally separate from the Python bot runtime. It does not change `bot.py`, `requirements.txt`, `Procfile`, environment variables, or deployment settings.

The dashboard now runs locally or through the combined Railway launcher. Public randomizer/build tools stay open, while admin actions use a temporary password session or staged Discord OAuth session. Dashboard settings, audit events, and custom command configs persist to JSON by default, or to SQLite when `GODFORGE_STORAGE=sqlite` is enabled. Future guild-scoped authorization, bot-side custom command execution, and production asset work are tracked in `TODO.md`.

Product-level release milestones are tracked in `../VERSION_HISTORY.md`. The ledger system is v2.0; dashboard bridge work is staged as v2.1.0 candidate work, to be tagged after OAuth and DB-backed dashboard basics are working.

Release process details live in `../RELEASE_PROCESS.md`. The bot-visible version is controlled by `GODFORGE_VERSION` in `../utils/formatter.py` and appears at the bottom of `.help`.

The optional local API in `../web_api` exposes a development-only bridge to the existing Godforge parser, loader, picker, draft, ledger, and wallet modules. When that API is not running, the website stays previewable with demo fallback data for god rolls, Roll Team, builds, matches, bets, and wallets.

## Preview Locally

From the repo root:

```powershell
cd web
npm run dev
```

Then open:

```text
http://localhost:5173
```

You can also open `web/index.html` directly in a browser.

## Optional Shared-Logic API

In a second terminal, from the repo root:

```powershell
python web_api/server.py
```

The local API runs at:

```text
http://localhost:8787
```

With the API running, the dashboard random god, Roll Team (`.roll5`), build generator, command runner, draft room, match lifecycle, bet placement, prop resolution, and wallet panels use the same local Python modules as the Discord bot where implemented.

Admin-only dashboard actions require `GODFORGE_ADMIN_PASSWORD` when using `web_api/server.py` or the combined Railway launcher. Public randomizer and build endpoints remain available without login.

After login, the Overview panel includes a MEE6-style operations monitor with bot status, guild count, ledger state, wallet count, active draft rooms, a managed-server selector grid, module health, recent admin activity, and a manual Discord ledger embed sync action. The sync control only queues a real Discord refresh when the API and bot are running together through `railway_app.py`.

The Settings module now saves temporary guild defaults to `data/guild_settings.json`: feature toggles, channel names, and admin/captain role labels. This is the staging surface for the future Discord OAuth server picker and database-backed guild settings.

The Command Config module saves temporary custom command configs to `data/custom_commands.json`. These configs are not executed by the bot yet; they stage the schema for future guild-scoped custom command execution.

Dashboard settings, audit, and custom command configs can use SQLite instead of JSON by setting:

```text
GODFORGE_STORAGE=sqlite
GODFORGE_DB_PATH=/app/data/godforge_dashboard.db
```

JSON remains the default until the storage switch is explicitly enabled.

## Combined Railway Launcher

The fast live deployment path uses the repo-root launcher:

```powershell
python railway_app.py
```

It starts the web/API server on Railway's `$PORT` and runs the Discord bot in the same service so both use the mounted `/app/data` volume.

Current Railway public URL:

```text
https://godforge-hub.up.railway.app
```

Discord OAuth callback:

```text
https://godforge-hub.up.railway.app/api/auth/discord/callback
```

Discord OAuth client id:

```text
1493371999031136318
```

Do not commit the Discord client secret. Add it directly to Railway as `DISCORD_CLIENT_SECRET`.

OAuth Railway variables:

```text
DISCORD_CLIENT_ID=1493371999031136318
DISCORD_CLIENT_SECRET=<set in Railway>
DISCORD_OAUTH_REDIRECT_URI=https://godforge-hub.up.railway.app/api/auth/discord/callback
```

## Build

There is no compiled build step. This is plain HTML, CSS, and JavaScript.

```powershell
npm run build
```

Security helper coverage for dashboard HTML escaping:

```powershell
npm run test:security
```

Static dashboard coverage for tab/panel wiring and required admin surfaces:

```powershell
npm run test:dashboard
```

## Edit Points

- Replace the placeholder `Add to Discord` links in `index.html` with the bot's Discord OAuth invite URL.
- Replace placeholder dashboard copy as the product direction becomes clearer.
- The randomizer currently uses SmiteFire CDN god portraits for visual context.
- Dashboard data shapes are documented in `DATA_CONTRACT.md`.
- Production asset slots and naming guidance are documented in `ASSET_MANIFEST.md`.
- The temporary password login should be removed once Discord OAuth plus guild permission checks fully gate admin actions.
- Settings, audit, and custom commands use JSON by default or SQLite when enabled; multi-guild production should keep SQLite/Postgres-style durable storage enabled.
- Temporary custom command configs persist through the dashboard but need bot-side resolver work before Discord execution.
- Production graphics can be mapped into the named asset slots: `god-card`, `item-card`, `role-icon`, `dashboard-hero`, `background-texture`, and future in-game map surfaces.
