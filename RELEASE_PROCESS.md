# GodForge Release Process

Use this checklist whenever GodForge moves from a release candidate to a tagged release.

## Version Sources To Update

- `utils/formatter.py`
  - `GODFORGE_VERSION`
  - This appears at the bottom of the `.help` embeds.
- `VERSION_HISTORY.md`
  - Canonical product milestone notes.
- `README.md`
  - Public bot command/version notes.
- `web/README.md`
  - Dashboard deployment, storage, and OAuth notes.
- `web/TODO.md`
  - Move completed work out of future/staged sections.
- `web_api/README.md`
  - API/env/storage notes.

## v2.1.0 Release Gate

Tag `v2.1.0` only after:

- Discord OAuth works live at `https://godforge-hub.up.railway.app/api/auth/discord/callback`.
- Railway boots with `GODFORGE_STORAGE=sqlite`.
- Dashboard settings, audit, and custom command config persist in `/app/data/godforge_dashboard.db`.
- Bot login, match ops, betting, wallet actions, ledger reset, and Discord ledger sync still work live.
- Full local tests pass before push.
- GitHub/Railway deployment status is green after push.

## Tagging

When the release gate passes:

```powershell
git tag v2.1.0
git push origin v2.1.0
```

Do not tag a release candidate as stable until the live smoke test passes.
