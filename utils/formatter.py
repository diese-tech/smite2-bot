"""
Format picker results as Discord messages.

`format_god` returns a discord.Embed (rich card with thumbnail + color).
`format_build` and `format_error` return plaintext strings.
The bot.py handler checks the return type and sends accordingly.
"""

import re
import discord


# Buff-themed role colors (Smite 2 has no green buff; support takes green).
ROLE_COLORS = {
    "jungle": 0xF1C40F,   # yellow
    "mid": 0xE74C3C,      # red
    "adc": 0x9B59B6,      # purple
    "support": 0x2ECC71,  # green
    "solo": 0x3498DB,     # blue
}
RANDOM_COLOR = 0xFFFFFF   # white - no specific role

# SmiteFire CDN base for god portrait icons.
ICON_BASE = "https://www.smitefire.com/images/v2/god/icon"


def god_slug(name: str) -> str:
    """
    Convert a god name to its SmiteFire CDN slug.
    'Loki' -> 'loki', 'Da Ji' -> 'da-ji', 'Morgan Le Fay' -> 'morgan-le-fay'
    Apostrophes are stripped defensively (current Smite 2 roster has none).
    """
    s = name.lower().replace("'", "").replace("'", "")
    s = re.sub(r"\s+", "-", s.strip())
    return s


def _command_string(role: str | None, source: str, prefix: str = "rg") -> str:
    """Reconstruct the command the user (most likely) typed, for footer display."""
    if role is None:
        return f".{prefix}"
    role_char = {"jungle": "j", "mid": "m", "adc": "a", "support": "s", "solo": "o"}[role]
    source_char = "w" if source == "website" else "t"
    return f".{prefix}{role_char}{source_char}"


def format_god(god: str, role: str | None, source: str) -> discord.Embed:
    """Return a discord.Embed for a god pick."""
    if role is None:
        color = RANDOM_COLOR
        role_label = "Random"
    else:
        color = ROLE_COLORS[role]
        role_label = role.capitalize()

    embed = discord.Embed(title=god, color=color)
    embed.set_thumbnail(url=f"{ICON_BASE}/{god_slug(god)}.png")
    embed.set_footer(text=f"{role_label} • {_command_string(role, source)}")
    return embed


def format_team(gods: list[str], role: str | None, source: str) -> discord.Embed:
    """Return a discord.Embed showing 5 gods in one card (non-session)."""
    if role is None:
        color = RANDOM_COLOR
        role_label = "Random"
    else:
        color = ROLE_COLORS[role]
        role_label = role.capitalize()

    description = "\n".join(f"{i}. **{g}**" for i, g in enumerate(gods, 1))
    embed = discord.Embed(title=f"🎲 {role_label} Roll5", description=description, color=color)
    embed.set_footer(text=f"{role_label} • {_command_string(role, source, prefix='roll5')}")
    return embed


# Number emoji constants for roll5 reactions.
NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]


def format_roll5_session(gods: list[str], role: str | None, source: str) -> discord.Embed:
    """Roll5 embed for active session — numbered list, awaiting reaction pick."""
    if role is None:
        color = RANDOM_COLOR
        role_label = "Random"
    else:
        color = ROLE_COLORS[role]
        role_label = role.capitalize()

    lines = [f"{NUMBER_EMOJIS[i]} **{g}**" for i, g in enumerate(gods)]
    description = "\n".join(lines)
    embed = discord.Embed(
        title=f"🎲 {role_label} Roll5 — Pick one!",
        description=description,
        color=color,
    )
    embed.set_footer(text=f"{role_label} • {_command_string(role, source, prefix='roll5')} • React to select")
    return embed


def format_roll5_locked(gods: list[str], selected_index: int,
                        user_name: str, role: str | None, source: str) -> discord.Embed:
    """Edited roll5 embed showing which god was picked and by whom."""
    if role is None:
        color = RANDOM_COLOR
        role_label = "Random"
    else:
        color = ROLE_COLORS[role]
        role_label = role.capitalize()

    lines = []
    for i, g in enumerate(gods):
        if i == selected_index:
            lines.append(f"🔒 **{g}** ← {user_name}")
        else:
            lines.append(f"~~{g}~~")
    description = "\n".join(lines)
    embed = discord.Embed(
        title=f"🔒 {role_label} Roll5 — Locked",
        description=description,
        color=color,
    )
    embed.set_footer(text=f"{role_label} • {_command_string(role, source, prefix='roll5')}")
    return embed


def format_rg_session(god: str, role: str | None, source: str) -> discord.Embed:
    """Single god embed for active session — awaiting ✅/❌ confirmation."""
    if role is None:
        color = RANDOM_COLOR
        role_label = "Random"
    else:
        color = ROLE_COLORS[role]
        role_label = role.capitalize()

    embed = discord.Embed(title=god, color=color)
    embed.set_thumbnail(url=f"{ICON_BASE}/{god_slug(god)}.png")
    embed.set_footer(text=f"{role_label} • {_command_string(role, source)} • ✅ to lock, ❌ to discard")
    return embed


def format_rg_locked(god: str, user_name: str, role: str | None, source: str) -> discord.Embed:
    """Edited rg embed showing the god was locked by a user."""
    if role is None:
        color = RANDOM_COLOR
        role_label = "Random"
    else:
        color = ROLE_COLORS[role]
        role_label = role.capitalize()

    embed = discord.Embed(title=f"🔒 {god}", description=f"Selected by **{user_name}**", color=color)
    embed.set_thumbnail(url=f"{ICON_BASE}/{god_slug(god)}.png")
    embed.set_footer(text=f"{role_label} • {_command_string(role, source)}")
    return embed


def format_rg_discarded(god: str, role: str | None, source: str) -> discord.Embed:
    """Edited rg embed showing the god was discarded."""
    embed = discord.Embed(title=f"❌ ~~{god}~~", description="Discarded", color=0x95A5A6)
    embed.set_footer(text=f"{_command_string(role, source)}")
    return embed


def format_session_show(picks: dict) -> discord.Embed:
    """Show all picks in the current session."""
    if not picks:
        embed = discord.Embed(
            title="📋 Session Picks",
            description="No gods picked yet.",
            color=0x95A5A6,
        )
        return embed

    lines = [f"**{god}** → {info['user_name']}" for god, info in picks.items()]
    embed = discord.Embed(
        title=f"📋 Session Picks ({len(picks)} total)",
        description="\n".join(lines),
        color=0x3498DB,
    )
    return embed


def format_session_end(picks: dict) -> discord.Embed:
    """Final locked summary when session ends."""
    if not picks:
        embed = discord.Embed(
            title="📋 Session Complete",
            description="No gods were picked this session.",
            color=0x95A5A6,
        )
        return embed

    lines = [f"🔒 **{god}** → {info['user_name']}" for god, info in picks.items()]
    embed = discord.Embed(
        title=f"📋 Session Complete — {len(picks)} picks",
        description="\n".join(lines),
        color=0x2ECC71,
    )
    return embed


def format_build(items: list[str], role: str, build_type: str | None) -> str:
    if role == "chaos":
        header = "🎲 Chaos build"
    elif role == "support":
        header = "🛡️ Support build"
    elif role == "adc":
        type_labels = {"standard": "standard", "str": "strength", "hyb": "hybrid"}
        header = f"🏹 ADC build ({type_labels.get(build_type, build_type)})"
    else:
        type_labels = {"int": "intelligence", "str": "strength", "hyb": "hybrid"}
        header = f"⚔️ {role.capitalize()} build ({type_labels.get(build_type, build_type)})"

    numbered = "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1))
    return f"{header}:\n{numbered}"


def format_error(message: str) -> str:
    return f"⚠️ {message}"


def format_help() -> str:
    """Plaintext command reference, rendered as a Discord code block for monospace alignment."""
    return (
        "```\n"
        "GodForge commands\n"
        "\n"
        "GODS\n"
        "  .rg              Random god from full roster\n"
        "  .rgj/m/a/s/o     Random god by role (jungle/mid/adc/support/solo)\n"
        "  .rgjw            Same as .rgj (explicit website source)\n"
        "  .rgjt            Random jungle god from in-game tab pool\n"
        "  .roll5           5 random gods from full roster\n"
        "  .roll5j          5 random gods of a role (same role/source rules as .rg)\n"
        "\n"
        "BUILDS  (add a number 1-5 for fewer items, e.g. .adcstr 3)\n"
        "  .midint          Mid intelligence build\n"
        "  .midstr          Mid strength build\n"
        "  .jungint         Jungle intelligence build\n"
        "  .jungstr         Jungle strength build\n"
        "  .soloint         Solo intelligence build\n"
        "  .solostr         Solo strength build\n"
        "  .solohyb         Solo hybrid build\n"
        "  .adc             Standard ADC build\n"
        "  .adcstr          Strength-leaning ADC build\n"
        "  .adchyb          Hybrid ADC build\n"
        "  .sup             Support build\n"
        "  .rc              Chaos build (6 random items, any role)\n"
        "\n"
        "SESSIONS  (track picks, prevent duplicates)\n"
        "  .session start   Start a draft session in this channel\n"
        "  .session show    Show all picks so far\n"
        "  .session reset   Clear picks, keep session active\n"
        "  .session end     End session, show final summary\n"
        "  During a session, .rg and .roll5 get reactions to lock picks.\n"
        "  Picked gods are excluded from future rolls.\n"
        "\n"
        "UTILITY\n"
        "  .help            Show this list\n"
        "```"
    )
