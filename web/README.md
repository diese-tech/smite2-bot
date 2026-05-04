# Godforge Website

Static local landing page and admin portal prototype for the Godforge Discord bot.

This folder is intentionally separate from the Python bot runtime. It does not change `bot.py`, `requirements.txt`, `Procfile`, environment variables, or deployment settings.

The dashboard, custom-command builder, Discord connection controls, and portal controls do not authenticate with Discord, persist data, deploy anywhere, or register bot commands. Future production work is tracked in `TODO.md`.

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

## Combined Railway Launcher

The fast live deployment path uses the repo-root launcher:

```powershell
python railway_app.py
```

It starts the web/API server on Railway's `$PORT` and runs the Discord bot in the same service so both use the mounted `/app/data` volume.

## Build

There is no compiled build step. This is plain HTML, CSS, and JavaScript.

```powershell
npm run build
```

## Edit Points

- Replace the placeholder `Add to Discord` links in `index.html` with the bot's Discord OAuth invite URL.
- Replace placeholder dashboard copy as the product direction becomes clearer.
- The randomizer currently uses SmiteFire CDN god portraits for visual context.
- Dashboard data shapes are documented in `DATA_CONTRACT.md`.
- Production graphics can be mapped into the named asset slots: `god-card`, `item-card`, `role-icon`, `dashboard-hero`, `background-texture`, and future in-game map surfaces.
