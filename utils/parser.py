"""
Command parser for the Smite 2 bot.

Recognized command shapes:
    .rg                     -> random god (any role, website pool)
    .rg{role}               -> random god of role (website pool)
    .rg{role}{src}          -> random god of role from explicit source (w or t)
    .roll5                  -> 5 random gods from full roster
    .roll5{role}            -> 5 random gods of role (website pool)
    .roll5{role}{src}       -> 5 random gods of role from explicit source
    .rc [N]                 -> chaos build (6 random items, or N items if 1-5 given)
    .midint/.midstr [N]     -> mid build, optional count 1-5
    .jungint/.jungstr [N]   -> jungle build, optional count 1-5
    .soloint/.solostr/.solohyb [N] -> solo build, optional count 1-5
    .adc/.adcstr/.adchyb [N]-> ADC build, optional count 1-5
    .sup [N]                -> support build, optional count 1-5
    .help                   -> show command reference

Returns a dict describing the parsed intent, or None if not a recognized command.
"""

import re

ROLE_CODES = {
    "j": "jungle",
    "m": "mid",
    "a": "adc",
    "s": "support",
    "o": "solo",
}

SOURCE_CODES = {"w": "website", "t": "tab"}

# Build types that exist for each lane role.
# Mid and jungle have no hybrid pool; solo has all three.
ROLE_BUILD_TYPES = {
    "mid": {"int", "str"},
    "jungle": {"int", "str"},
    "solo": {"int", "str", "hyb"},
}
ADC_VARIANTS = {"": "standard", "str": "str", "hyb": "hyb"}

# Default build size when no count is specified.
DEFAULT_BUILD_COUNT = 6
# Valid range for explicit count argument.
MIN_BUILD_COUNT = 1
MAX_BUILD_COUNT = 5


def _split_count(cmd: str) -> tuple[str, int | None]:
    """
    Split a command like 'adcstr 4' into ('adcstr', 4).
    Returns (cmd_without_count, count) where count is None if not present.
    Returns (cmd, "INVALID") sentinel if a count is present but out of range
    or non-numeric, so caller can reject.
    """
    parts = cmd.rsplit(" ", 1)
    if len(parts) == 1:
        return parts[0], None
    base, tail = parts[0].strip(), parts[1].strip()
    if not tail.isdigit():
        return cmd, "INVALID"  # type: ignore
    n = int(tail)
    if n < MIN_BUILD_COUNT or n > MAX_BUILD_COUNT:
        return cmd, "INVALID"  # type: ignore
    return base, n


def parse(message: str):
    """
    Parse a raw user message. Returns dict or None.

    Returned dict shapes:
      God:     {"kind": "god",     "role": <role|None>, "source": "website"|"tab"}
      Roll5:   {"kind": "roll5",   "role": <role|None>, "source": "website"|"tab"}
      Build:   {"kind": "build",   "role": <role>, "type": <type|None>, "count": int}
      Help:    {"kind": "help"}
      Session: {"kind": "session", "action": "start"|"end"|"show"|"reset"}
    """
    if not message or not message.startswith("."):
        return None

    cmd = message[1:].strip().lower()
    if not cmd:
        return None

    # ---- Help: .help ----
    if cmd == "help":
        return {"kind": "help"}

    # ---- Session commands: .session start/end/show/reset ----
    if cmd.startswith("session"):
        rest = cmd[7:].strip()
        if rest in ("start", "end", "show", "reset"):
            return {"kind": "session", "action": rest}
        return None

    # ---- Roll5 commands: .roll5[role][source] ----
    # Check before generic 'r' commands since it has its own prefix.
    if cmd.startswith("roll5"):
        rest = cmd[5:]
        if rest == "":
            return {"kind": "roll5", "role": None, "source": "website"}

        role_char = rest[0]
        if role_char not in ROLE_CODES:
            return None
        role = ROLE_CODES[role_char]
        rest = rest[1:]

        if rest == "":
            return {"kind": "roll5", "role": role, "source": "website"}
        if rest in SOURCE_CODES:
            return {"kind": "roll5", "role": role, "source": SOURCE_CODES[rest]}
        return None

    # ---- God commands: .rg[role][source] ----
    if cmd.startswith("rg"):
        rest = cmd[2:]
        if rest == "":
            return {"kind": "god", "role": None, "source": "website"}

        role_char = rest[0]
        if role_char not in ROLE_CODES:
            return None
        role = ROLE_CODES[role_char]
        rest = rest[1:]

        if rest == "":
            return {"kind": "god", "role": role, "source": "website"}
        if rest in SOURCE_CODES:
            return {"kind": "god", "role": role, "source": SOURCE_CODES[rest]}
        return None

    # ---- Build commands: extract optional trailing count ----
    base_cmd, count = _split_count(cmd)
    if count == "INVALID":
        return None
    final_count = count if count is not None else DEFAULT_BUILD_COUNT

    # Chaos build: .rc [N]
    if base_cmd == "rc":
        return {"kind": "build", "role": "chaos", "type": None, "count": final_count}

    # Support build: .sup [N]
    if base_cmd == "sup":
        return {"kind": "build", "role": "support", "type": None, "count": final_count}

    # ADC builds: .adc, .adcstr, .adchyb [N]
    if base_cmd.startswith("adc"):
        variant = base_cmd[3:]
        if variant in ADC_VARIANTS:
            return {"kind": "build", "role": "adc", "type": ADC_VARIANTS[variant], "count": final_count}
        return None

    # Standard builds: .{role}{type} [N] for mid/jungle/solo
    for prefix, role in (("mid", "mid"), ("jung", "jungle"), ("solo", "solo")):
        if base_cmd.startswith(prefix):
            build_type = base_cmd[len(prefix):]
            if build_type in ROLE_BUILD_TYPES[role]:
                return {"kind": "build", "role": role, "type": build_type, "count": final_count}
            return None

    return None
