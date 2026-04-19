# GodForge — Smite 2 Discord Bot

A Discord bot for randomizing Smite 2 god picks and item builds, with session tracking for competitive drafts.

God picks render as colored embed cards with the god's portrait. Build commands return plaintext numbered lists.

## Commands

### Gods

| Command   | Result                                       |
|-----------|----------------------------------------------|
| `.rg`     | Random god from the full Smite 2 roster      |
| `.rgj`    | Random jungle god (website pool)             |
| `.rgm`    | Random mid god (website pool)                |
| `.rga`    | Random ADC god (website pool)                |
| `.rgs`    | Random support god (website pool)            |
| `.rgo`    | Random solo god (website pool)               |
| `.roll5`  | 5 random gods from the full roster           |
| `.roll5j` | 5 random jungle gods (website pool)          |

Append `w` for explicit website source or `t` for the in-game tab pool. For example: `.rgjw` (jungle, website), `.rgjt` (jungle, tab), `.rgmt` (mid, tab), `.roll5jt` (5 jungle gods from tab). Default source when omitted is website. Same source/role pattern works for `.roll5{role}{source}` as for `.rg{role}{source}`.

The **website pool** mirrors the curated god list from [smitedraft.com](https://smitedraft.com), the competitive draft tool. The **tab pool** mirrors the gods currently available in the in-game god select tab.

God embeds use buff-themed colors: jungle = yellow, mid = red, ADC = purple, support = green, solo = blue, random = white.

**Weighting:** `.roll5` (no role) uses role-based weights to bias picks toward support/solo gods (weight 1.0) over mid/jungle/adc gods (weight 0.75). Gods in multiple role pools inherit their highest weight. Weights are configurable in `data/gods.json` under the `"weights"` section.

### Builds

Each build is 6 unique items pulled from the relevant pool, listed in the order players should buy them. Players choose their own starters, relics, and aspects.

| Command     | Result                                                 |
|-------------|--------------------------------------------------------|
| `.rc`       | Chaos build — 6 random items from the full master pool |
| `.midint`   | Mid intelligence build                                 |
| `.midstr`   | Mid strength build                                     |
| `.jungint`  | Jungle intelligence build                              |
| `.jungstr`  | Jungle strength build                                  |
| `.soloint`  | Solo intelligence build                                |
| `.solostr`  | Solo strength build                                    |
| `.solohyb`  | Solo hybrid build                                      |
| `.adc`      | Standard ADC build                                     |
| `.adcstr`   | Strength-leaning ADC build                             |
| `.adchyb`   | Hybrid ADC build                                       |
| `.sup`      | Support build (single pool)                            |

Mid and jungle do not have hybrid pools; `.midhyb` and `.junghyb` are silently ignored.

**Optional count:** Any build command can take a trailing number 1-5 for fewer items. For example: `.adcstr 3` returns 3 strength items, `.rc 1` returns a single chaos item, `.sup 4` returns 4 support items. Without a number, the default is 6. Numbers outside 1-5 are silently ignored.

### Sessions

Sessions enable draft tracking in a channel. When a session is active, `.rg` and `.roll5` produce interactive embeds with reaction buttons for locking picks. Picked gods are excluded from all future rolls in that channel until the session ends or resets.

| Command          | Result                                          |
|------------------|-------------------------------------------------|
| `.session start` | Start a draft session in this channel           |
| `.session show`  | Show all picks made so far                      |
| `.session reset` | Clear picks, keep session active (new game)     |
| `.session end`   | End session, show final summary                 |

**How it works during an active session:**

1. Someone runs `.roll5jw` — bot posts 5 gods with 1️⃣-5️⃣ reactions
2. Anyone taps a number — that god is locked to the person who reacted
3. The embed updates to show the locked pick; reactions are removed
4. That god will not appear in any future rolls for this session
5. `.rg` works similarly but with ✅ (lock) and ❌ (discard) reactions

Gods in open (unresolved) rolls are also excluded from new rolls, preventing the same god from appearing in two active rolls at once.

Without an active session, `.rg` and `.roll5` behave normally (no reactions, no tracking).

### Utility

| Command | Result                  |
|---------|-------------------------|
| `.help` | Show all commands       |

## Setup

1. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

2. **Create a Discord bot:**
   - Go to https://discord.com/developers/applications
   - New Application → Bot → copy the token
   - Under Bot settings, enable **Message Content Intent**
   - Use OAuth2 URL Generator with scopes `bot` and permissions `Send Messages` + `Read Message History` + `View Channels` + `Add Reactions` + `Manage Messages` to invite it to your server
   - The bot needs `Add Reactions` to post reaction buttons and `Manage Messages` to clear reactions after a pick is locked

3. **Configure the token:**

   For **local testing:**
   ```
   cp .env.example .env
   ```
   Edit `.env` and paste your bot token.

   For **Railway / production:** set `DISCORD_TOKEN` as an environment variable in the platform's settings. The `.env` file is gitignored and only used locally.

4. **Run:**
   ```
   python bot.py
   ```

## File layout

```
smite2-bot/
  bot.py              # entry point, event handlers, reaction listener
  requirements.txt
  Procfile            # tells Railway/Heroku to run as a worker
  .env.example
  .gitignore
  README.md
  test_bot.py         # local tests (run with --sim for weight simulation)
  data/
    gods.json         # roster, role pools, weights
    builds.json       # item master + role/type build pools
  utils/
    parser.py         # command string -> intent dict
    picker.py         # random selection with exclusion + weighting
    loader.py         # JSON loading + caching
    formatter.py      # intent + result -> Discord embed or string
    session.py        # per-channel draft session tracking
```

## Updating data

When new gods drop or item pools shift, edit `data/gods.json` or `data/builds.json` directly. The bot caches data on first read, so a restart (or pushing a new commit on Railway) is required to pick up changes.

God portraits are pulled from SmiteFire's CDN (`smitefire.com/images/v2/god/icon/{slug}.png`). The slug is generated from the god's name (lowercase, spaces → hyphens). If a new god's portrait doesn't load, check that SmiteFire has added them to their site.

**Tuning weights:** Edit the `"weights"` section in `data/gods.json` to adjust how heavily `.roll5` biases toward certain roles. Higher weight = more likely to appear. Run `python test_bot.py --sim` locally to see the effect of weight changes on pick distribution before deploying.

## Notes

- Unknown commands are silently ignored, by design — keeps the bot quiet in busy channels.
- Errors (empty pool, malformed JSON, etc.) are surfaced to the user with a `⚠️` prefix and logged to the console.
- Session state lives in memory only — it resets if the bot restarts or redeploys. This is fine for sessions that last ~15 minutes.
- Run `python test_bot.py` from a terminal to verify logic locally before deploying.
- Run `python test_bot.py --sim` (optionally `--sim 5000`) to simulate weighted `.roll5` distribution.

## Versioning

Version bumps happen when user-facing behavior changes — new commands, changed command behavior, or new features. Internal changes (hardening, data edits, README updates, bug fixes) do not bump the version.

The current version is displayed in the `.help` command footer. Update the version string in `utils/formatter.py` inside `format_help()` when shipping a new feature.

| Version | Changes |
|---------|---------|
| 1.0 | Initial bot — god picks, builds, all pools populated |
| 1.1 | Embed formatting with god portraits and buff-themed colors |
| 1.2 | `.roll5`, `.rc`, optional build count (1-5) |
| 1.3 | `.help` command |
| 1.4 | Role-based weighting for `.roll5` |
| 1.5 | Sessions — reaction-based picks, god exclusion tracking |

