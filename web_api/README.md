# Godforge Local Web API

Local development API for the Godforge website prototype.

This API reuses the existing Python bot logic where practical:

- `utils.parser`
- `utils.loader`
- `utils.picker`
- `utils.draft`
- `utils.resolver`
- `utils.ledger`
- `utils.wallet`

It is intentionally local-only for now. It does not implement Discord OAuth, guild authorization, persistent settings, or production deployment.

## Run

From the repo root:

```powershell
python web_api/server.py
```

Default URL:

```text
http://localhost:8787
```

The server also serves the static dashboard from `../web`, so `http://localhost:8787/` opens the site directly.

For the combined Railway process, use:

```powershell
python railway_app.py
```

That starts the web/API server on `$PORT` and the Discord bot in the same container.

## Admin Auth

Set `GODFORGE_ADMIN_PASSWORD` to enable protected dashboard actions.

Public endpoints remain available without login:

```text
GET /api/health
GET /api/auth/status
GET /api/gods/roll
GET /api/gods/roll5
GET /api/builds/roll
```

Admin actions require a session cookie from:

```text
POST /api/auth/login
POST /api/auth/logout
```

## Endpoints

```text
GET  /api/health
GET  /api/auth/status
GET  /api/gods/roll?role=jungle&source=website
GET  /api/gods/roll5?role=jungle&source=website
GET  /api/builds/roll?role=adc&type=standard&count=6
GET  /api/ledger
GET  /api/wallets
POST /api/auth/login
POST /api/auth/logout
POST /api/command
POST /api/draft/start
POST /api/draft/action
POST /api/draft/undo
POST /api/draft/next
POST /api/draft/end
POST /api/match/create
POST /api/match/status
POST /api/match/resolve/winner
POST /api/match/resolve/prop
POST /api/bet/place
POST /api/wallet/adjust
POST /api/ledger/reset
```

## Admin Payloads

```json
POST /api/match/create
{ "team1": "Solaris", "team2": "Onyx" }

POST /api/match/status
{ "match_id": "GF-0007", "status": "in_progress" }

POST /api/match/resolve/winner
{ "match_id": "GF-0007", "winner": "Solaris" }

POST /api/match/resolve/prop
{ "match_id": "GF-0007", "player": "Solaris ADC", "stat": "kills", "actual_value": 8 }

POST /api/bet/place
{ "match_id": "GF-0007", "username": "AtlasMain", "type": "win", "team": "Solaris", "amount": 100 }

POST /api/bet/place
{ "match_id": "GF-0007", "username": "WardBoss", "type": "prop", "player": "Solaris ADC", "stat": "kills", "direction": "over", "threshold": 7.5, "amount": 50 }

POST /api/wallet/adjust
{ "target": "AtlasMain", "action": "give", "amount": 100 }
```

`/api/wallet/adjust` accepts `give`, `take`, or `set`. Wallets are stored in the existing `data/wallets.json` shape keyed by user id. For local dashboard testing without Discord ids, the API derives a stable local id from `target`.

`/api/bet/place` seeds new bettor wallets at the same 500 point starting balance as the Discord bot, debits the bet amount, and appends the bet to the target match. It only accepts bets while the match status is `betting_open`.

`POST /api/ledger/reset` clears matches and returns:

```json
{ "ok": true, "cleared": 2 }
```

## Notes

- Draft rooms are in memory and disappear when the API process stops.
- The website falls back to demo data when this API is not running.
- Ledger and wallet endpoints use the existing local JSON files in `data/`.
- Production deployment and persistent state are intentionally deferred.
