"""
God name resolution for draft commands (.ban / .pick).

Resolution order:
  1. Exact match (case-insensitive) against full roster
  2. Alias match (case-insensitive) against data/aliases.json
  3. Prefix match (case-insensitive) — must match exactly one god

Returns (resolved_name, error_message). One will always be None.
"""

from utils import loader


def resolve_god_name(input_name: str) -> tuple[str | None, str | None]:
    """
    Resolve a user-typed god name to the canonical roster name.

    Returns:
        (god_name, None) on success
        (None, error_message) on failure
    """
    gods_data = loader.gods()
    all_gods = gods_data.get("all", [])
    input_lower = input_name.lower().strip()

    if not input_lower:
        return None, "No god name provided."

    # 1. Exact match (case-insensitive)
    for god in all_gods:
        if god.lower() == input_lower:
            return god, None

    # 2. Alias match
    aliases = loader.aliases()
    if input_lower in aliases:
        alias_target = aliases[input_lower]
        # Verify the alias target actually exists in the roster
        for god in all_gods:
            if god.lower() == alias_target.lower():
                return god, None
        return None, f"Alias '{input_name}' points to '{alias_target}', which isn't in the roster."

    # 3. Prefix match
    matches = [god for god in all_gods if god.lower().startswith(input_lower)]
    if len(matches) == 1:
        return matches[0], None
    elif len(matches) > 1:
        match_list = ", ".join(sorted(matches)[:8])
        extra = f" (+{len(matches) - 8} more)" if len(matches) > 8 else ""
        return None, f"Multiple gods match '{input_name}': {match_list}{extra}. Be more specific."
    else:
        return None, f"No god found matching '{input_name}'."
