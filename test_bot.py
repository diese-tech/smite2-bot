"""
Quick sanity tests for the parser and picker. Run with: python test_bot.py
Weight simulation: python test_bot.py --sim
Not a formal test suite — just verifies the core logic before deploying.
"""

import sys
sys.path.insert(0, '.')

from utils import parser, picker, loader, formatter


def test_parser():
    cases = [
        # God commands
        (".rg",     {"kind": "god", "role": None, "source": "website"}),
        (".rgj",    {"kind": "god", "role": "jungle", "source": "website"}),
        (".rgm",    {"kind": "god", "role": "mid", "source": "website"}),
        (".rga",    {"kind": "god", "role": "adc", "source": "website"}),
        (".rgs",    {"kind": "god", "role": "support", "source": "website"}),
        (".rgo",    {"kind": "god", "role": "solo", "source": "website"}),
        (".rgjw",   {"kind": "god", "role": "jungle", "source": "website"}),
        (".rgjt",   {"kind": "god", "role": "jungle", "source": "tab"}),
        (".rgmt",   {"kind": "god", "role": "mid", "source": "tab"}),
        # Roll5 commands
        (".roll5",     {"kind": "roll5", "role": None, "source": "website"}),
        (".roll5j",    {"kind": "roll5", "role": "jungle", "source": "website"}),
        (".roll5m",    {"kind": "roll5", "role": "mid", "source": "website"}),
        (".roll5jw",   {"kind": "roll5", "role": "jungle", "source": "website"}),
        (".roll5jt",   {"kind": "roll5", "role": "jungle", "source": "tab"}),
        (".roll5ot",   {"kind": "roll5", "role": "solo", "source": "tab"}),
        (".roll5x",    None),  # bad role
        (".roll5jx",   None),  # bad source
        # Chaos build
        (".rc",      {"kind": "build", "role": "chaos", "type": None, "count": 6}),
        (".rc 1",    {"kind": "build", "role": "chaos", "type": None, "count": 1}),
        (".rc 5",    {"kind": "build", "role": "chaos", "type": None, "count": 5}),
        # Build commands (default count 6)
        (".midint",  {"kind": "build", "role": "mid", "type": "int", "count": 6}),
        (".midstr",  {"kind": "build", "role": "mid", "type": "str", "count": 6}),
        (".jungint", {"kind": "build", "role": "jungle", "type": "int", "count": 6}),
        (".jungstr", {"kind": "build", "role": "jungle", "type": "str", "count": 6}),
        (".soloint", {"kind": "build", "role": "solo", "type": "int", "count": 6}),
        (".solostr", {"kind": "build", "role": "solo", "type": "str", "count": 6}),
        (".solohyb", {"kind": "build", "role": "solo", "type": "hyb", "count": 6}),
        (".adc",     {"kind": "build", "role": "adc", "type": "standard", "count": 6}),
        (".adcstr",  {"kind": "build", "role": "adc", "type": "str", "count": 6}),
        (".adchyb",  {"kind": "build", "role": "adc", "type": "hyb", "count": 6}),
        (".sup",     {"kind": "build", "role": "support", "type": None, "count": 6}),
        # Build commands with explicit count
        (".midint 3",  {"kind": "build", "role": "mid", "type": "int", "count": 3}),
        (".adcstr 4",  {"kind": "build", "role": "adc", "type": "str", "count": 4}),
        (".sup 2",     {"kind": "build", "role": "support", "type": None, "count": 2}),
        (".solohyb 1", {"kind": "build", "role": "solo", "type": "hyb", "count": 1}),
        # Invalid counts (silent ignore)
        (".adcstr 0",   None),
        (".adcstr 6",   None),
        (".adcstr 99",  None),
        (".adcstr abc", None),
        (".adcstr -1",  None),
        # Utility
        (".help",      {"kind": "help"}),
        # Session commands
        (".session start", {"kind": "session", "action": "start"}),
        (".session end",   {"kind": "session", "action": "end"}),
        (".session show",  {"kind": "session", "action": "show"}),
        (".session reset", {"kind": "session", "action": "reset"}),
        (".session",       None),  # no action
        (".session foo",   None),  # bad action
        # Case insensitivity / whitespace
        (".RGJ",     {"kind": "god", "role": "jungle", "source": "website"}),
        (".rgj  ",   {"kind": "god", "role": "jungle", "source": "website"}),
        # Non-commands and removed commands
        ("hello",    None),
        (".",        None),
        (".rgx",     None),  # bad role
        (".rgjx",    None),  # bad source
        (".midxxx",  None),  # bad type
        (".midhyb",  None),  # mid has no hybrid pool
        (".junghyb", None),  # jungle has no hybrid pool
        (".adcxxx",  None),  # bad ADC variant
        (".sups",    None),  # support doesn't take type
    ]
    fails = 0
    for cmd, expected in cases:
        actual = parser.parse(cmd)
        status = "OK" if actual == expected else "FAIL"
        if actual != expected:
            fails += 1
            print(f"  [{status}] {cmd!r}  expected={expected}  actual={actual}")
        else:
            print(f"  [{status}] {cmd!r}")
    print(f"\nParser: {len(cases) - fails}/{len(cases)} passed\n")
    return fails == 0


def test_picker_gods():
    gods_data = loader.gods()
    print("God picker tests:")
    # .rg pulls from flat 'all' roster
    god = picker.pick_god(gods_data, None, "website")
    print(f"  .rg -> {god}")
    assert god in gods_data["all"], f"{god} not in 'all' roster"
    print(f"  [OK] picked from full roster of {len(gods_data['all'])} gods")
    # Each populated role pool should return a god from that pool
    for source in ["website", "tab"]:
        for role in ["jungle", "mid", "adc", "support", "solo"]:
            god = picker.pick_god(gods_data, role, source)
            pool = gods_data["pools"][source][role]
            assert god in pool, f"{god} not in {source}/{role} pool"
            print(f"  .rg{role[0]}{'' if source == 'website' else 't'} -> {god} (from {len(pool)}-god pool)")

    # pick_team — 5 unique gods
    print("\nTeam picker tests:")
    team = picker.pick_team(gods_data, None, "website")
    assert len(team) == 5 and len(set(team)) == 5, f"Expected 5 unique, got {team}"
    print(f"  .roll5 -> {team}")

    # Verify weights loaded correctly
    weights = gods_data.get("weights", {})
    assert weights.get("support") == 1.0, "Support weight should be 1.0"
    assert weights.get("solo") == 1.0, "Solo weight should be 1.0"
    assert weights.get("mid") == 0.75, "Mid weight should be 0.75"
    assert weights.get("jungle") == 0.75, "Jungle weight should be 0.75"
    assert weights.get("adc") == 0.75, "ADC weight should be 0.75"
    print(f"  [OK] weights loaded: {weights}")

    # Verify _get_god_weight returns expected values
    # Ares is support-only -> 1.0
    assert picker._get_god_weight("Ares", gods_data) == 1.0, "Ares should be 1.0 (support)"
    # Hou Yi is adc-only -> 0.75
    assert picker._get_god_weight("Hou Yi", gods_data) == 0.75, "Hou Yi should be 0.75 (adc)"
    # Apollo is in adc (0.75) + support (1.0) + solo (1.0) -> highest = 1.0
    assert picker._get_god_weight("Apollo", gods_data) == 1.0, "Apollo should be 1.0 (multi-role, highest)"
    # Charon is only in tab/support -> 1.0
    assert picker._get_god_weight("Charon", gods_data) == 1.0, "Charon should be 1.0 (support)"
    print(f"  [OK] god weight lookups correct")

    for source in ["website", "tab"]:
        for role in ["jungle", "mid", "adc", "support", "solo"]:
            team = picker.pick_team(gods_data, role, source)
            assert len(team) == 5 and len(set(team)) == 5
            pool = gods_data["pools"][source][role]
            for g in team:
                assert g in pool, f"{g} not in {source}/{role} pool"
            print(f"  .roll5{role[0]}{'' if source == 'website' else 't'} -> {team}")
    return True


def test_picker_builds():
    builds_data = loader.builds()
    print("\nBuild picker tests:")
    # All populated build pools — should return 6 unique items by default
    cases = [
        ("mid", "int"), ("mid", "str"),
        ("jungle", "int"), ("jungle", "str"),
        ("solo", "int"), ("solo", "str"), ("solo", "hyb"),
        ("adc", "standard"), ("adc", "str"), ("adc", "hyb"),
        ("support", None),
        ("chaos", None),
    ]
    for role, btype in cases:
        items = picker.pick_build(builds_data, role, btype)
        assert len(items) == 6, f"Expected 6 items, got {len(items)}"
        assert len(set(items)) == 6, f"Got duplicates: {items}"
        master = set(builds_data["all"])
        unknown = [i for i in items if i not in master]
        assert not unknown, f"Items not in master list: {unknown}"
        print(f"  {role}/{btype}: {items}")

    # Variable count
    print("\nVariable-count build tests:")
    for count in [1, 2, 3, 4, 5]:
        items = picker.pick_build(builds_data, "adc", "standard", count=count)
        assert len(items) == count and len(set(items)) == count
        print(f"  .adcstr {count}: {items}")
    items = picker.pick_build(builds_data, "chaos", None, count=1)
    assert len(items) == 1
    print(f"  .rc 1: {items}")
    items = picker.pick_build(builds_data, "support", None, count=2)
    assert len(items) == 2
    print(f"  .sup 2: {items}")
    return True


def test_formatter():
    import discord
    print("\nFormatter tests:")

    # Slug helper
    slug_cases = [
        ("Loki", "loki"),
        ("Da Ji", "da-ji"),
        ("Hua Mulan", "hua-mulan"),
        ("Baron Samedi", "baron-samedi"),
        ("Morgan Le Fay", "morgan-le-fay"),
        ("The Morrigan", "the-morrigan"),
        ("Ne Zha", "ne-zha"),
        ("Princess Bari", "princess-bari"),
        ("Eset", "eset"),
    ]
    for name, expected in slug_cases:
        actual = formatter.god_slug(name)
        status = "OK" if actual == expected else "FAIL"
        print(f"  [{status}] slug({name!r}) -> {actual!r}")
        assert actual == expected, f"slug({name}) expected {expected}, got {actual}"

    # God embed
    e = formatter.format_god("Loki", "jungle", "website")
    assert isinstance(e, discord.Embed), "format_god should return discord.Embed"
    assert e.title == "Loki"
    assert e.color.value == 0xF1C40F  # yellow for jungle
    assert e.thumbnail.url.endswith("/loki.png")
    assert e.footer.text == "Jungle • .rgjw"
    print(f"  [OK] jungle embed: title={e.title} color=#{e.color.value:06X} footer={e.footer.text!r}")

    e = formatter.format_god("Zeus", None, "website")
    assert e.color.value == 0xFFFFFF  # white for random
    assert e.footer.text == "Random • .rg"
    print(f"  [OK] random embed: title={e.title} color=#{e.color.value:06X} footer={e.footer.text!r}")

    e = formatter.format_god("Da Ji", "jungle", "tab")
    assert e.thumbnail.url.endswith("/da-ji.png")
    assert e.footer.text == "Jungle • .rgjt"
    print(f"  [OK] tab source: footer={e.footer.text!r} thumb={e.thumbnail.url}")

    # Team embed
    team = ["Loki", "Da Ji", "Thor", "Susano", "Kali"]
    e = formatter.format_team(team, "jungle", "website")
    assert isinstance(e, discord.Embed)
    assert e.color.value == 0xF1C40F
    assert e.footer.text == "Jungle • .roll5jw"
    for g in team:
        assert g in e.description
    print(f"  [OK] team embed: title={e.title!r} footer={e.footer.text!r}")

    e = formatter.format_team(team, None, "website")
    assert e.color.value == 0xFFFFFF
    assert e.footer.text == "Random • .roll5"
    print(f"  [OK] random team embed: footer={e.footer.text!r}")

    # Help
    h = formatter.format_help()
    assert isinstance(h, str)
    assert "GodForge" in h
    assert ".rg" in h and ".roll5" in h and ".adcstr" in h and ".sup" in h
    assert h.startswith("```") and h.endswith("```")
    print(f"  [OK] help text rendered ({len(h)} chars)")

    # Build/error formatters still plaintext
    print("  " + formatter.format_build(["A", "B", "C", "D", "E", "F"], "mid", "int"))
    print("  " + formatter.format_build(["A", "B", "C", "D", "E", "F"], "adc", "standard"))
    print("  " + formatter.format_build(["A", "B", "C", "D", "E", "F"], "support", None))
    print("  " + formatter.format_build(["A", "B", "C", "D", "E", "F"], "chaos", None))
    print("  " + formatter.format_error("Test error"))
    return True


def test_session():
    """Test SessionManager and SessionState logic."""
    from utils.session import SessionManager
    print("\nSession tests:")

    mgr = SessionManager()

    # Start a session
    assert mgr.start(123) == True
    assert mgr.start(123) == False  # already active
    print("  [OK] start / double-start")

    session = mgr.get(123)
    assert session is not None
    assert session.active

    # No excluded gods initially
    assert session.get_excluded_gods() == set()
    print("  [OK] empty exclusion set")

    # Register a roll5
    session.register_roll5(1001, ["Loki", "Thor", "Zeus", "Ra", "Ymir"])
    assert "Loki" in session.get_excluded_gods()
    assert "Thor" in session.get_excluded_gods()
    assert len(session.get_excluded_gods()) == 5
    print("  [OK] roll5 gods excluded")

    # Lock a pick from the roll
    god = session.lock_roll5_pick(1001, 0, 999, "TestUser")
    assert god == "Loki"
    assert "Loki" in session.picks
    assert session.picks["Loki"]["user_name"] == "TestUser"
    # Other gods from that roll are no longer in open_rolls
    assert "Thor" not in session.get_excluded_gods()
    # But Loki is still excluded (it's picked)
    assert "Loki" in session.get_excluded_gods()
    assert len(session.get_excluded_gods()) == 1
    print("  [OK] roll5 pick locked, others freed")

    # Duplicate pick rejected
    session.register_roll5(1002, ["Loki", "Ares", "Geb", "Athena", "Bacchus"])
    god = session.lock_roll5_pick(1002, 0, 888, "OtherUser")  # index 0 = Loki
    assert god is None  # already picked
    print("  [OK] duplicate pick rejected")

    # Register and confirm an rg
    session.register_rg(2001, "Cupid", "adc", "website")
    assert "Cupid" in session.get_excluded_gods()
    god = session.lock_rg_pick(2001, 777, "RGUser")
    assert god == "Cupid"
    assert "Cupid" in session.picks
    print("  [OK] rg lock")

    # Register and discard an rg
    session.register_rg(2002, "Anubis", "mid", "website")
    assert "Anubis" in session.get_excluded_gods()
    god = session.discard_rg(2002)
    assert god == "Anubis"
    assert "Anubis" not in session.get_excluded_gods()  # freed
    assert "Anubis" not in session.picks  # not picked
    print("  [OK] rg discard frees god")

    # Pick_god with exclusion
    gods_data = loader.gods()
    exclude = session.get_excluded_gods()
    for _ in range(50):
        g = picker.pick_god(gods_data, None, "website", exclude=exclude)
        assert g not in exclude, f"Excluded god {g} was returned"
    print("  [OK] pick_god respects exclusion")

    # Pick_team with exclusion
    exclude = session.get_excluded_gods()
    team = picker.pick_team(gods_data, None, "website", exclude=exclude)
    for g in team:
        assert g not in exclude
    print(f"  [OK] pick_team respects exclusion: {team}")

    # Reset
    mgr.reset(123)
    assert session.get_excluded_gods() == set()
    assert len(session.picks) == 0
    assert mgr.get(123) is not None  # still active
    print("  [OK] reset clears picks, session stays active")

    # End
    final = mgr.end(123)
    assert final is not None
    assert mgr.get(123) is None
    print("  [OK] end returns state and removes session")

    # No session
    assert mgr.get(123) is None
    assert mgr.end(123) is None
    assert mgr.reset(123) == False
    print("  [OK] no-session edge cases")

    return True


def run_simulation(runs=1000):
    """Run .roll5 (no role) N times and print god frequency + role breakdown."""
    from collections import Counter

    gods_data = loader.gods()

    # Build role lookup for labeling
    role_lookup = {}
    for source_name, source_pools in gods_data.get("pools", {}).items():
        if isinstance(source_pools, dict):
            for role, role_gods in source_pools.items():
                if role.startswith("_"):
                    continue
                for g in role_gods:
                    if g not in role_lookup:
                        role_lookup[g] = set()
                    role_lookup[g].add(role)

    counts = Counter()
    for _ in range(runs):
        team = picker.pick_team(gods_data, None, "website")
        for g in team:
            counts[g] += 1

    total_picks = runs * 5
    print(f"\n.roll5 weight simulation ({runs} runs, {total_picks} picks):")
    print(f"{'God':<22} {'Roles':<30} {'Picks':>6} {'Rate':>7}")
    print("-" * 67)
    for god, count in counts.most_common():
        roles = ", ".join(sorted(role_lookup.get(god, {"none"})))
        rate = f"{count / runs * 100:.1f}%"
        print(f"  {god:<20} {roles:<30} {count:>5}  {rate:>6}")

    # Role category summary
    print(f"\nRole category averages ({runs} runs):")
    role_totals = {"support": 0, "solo": 0, "mid": 0, "jungle": 0, "adc": 0, "none": 0}
    role_god_counts = {"support": 0, "solo": 0, "mid": 0, "jungle": 0, "adc": 0, "none": 0}
    for god, count in counts.items():
        roles = role_lookup.get(god, {"none"})
        for r in roles:
            role_totals[r] = role_totals.get(r, 0) + count
            role_god_counts[r] = role_god_counts.get(r, 0) + 1

    for role in ["support", "solo", "jungle", "mid", "adc"]:
        if role_god_counts[role] > 0:
            avg = role_totals[role] / role_god_counts[role]
            weight = gods_data.get("weights", {}).get(role, 1.0)
            print(f"  {role:<10} weight={weight}  avg picks/god={avg:.1f}")


if __name__ == "__main__":
    if "--sim" in sys.argv:
        runs = 1000
        # Allow custom run count: --sim 5000
        idx = sys.argv.index("--sim")
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1].isdigit():
            runs = int(sys.argv[idx + 1])
        run_simulation(runs)
        sys.exit(0)

    print("=" * 60)
    print("PARSER TESTS")
    print("=" * 60)
    p_ok = test_parser()

    print("=" * 60)
    print("PICKER TESTS")
    print("=" * 60)
    g_ok = test_picker_gods()
    b_ok = test_picker_builds()

    print("=" * 60)
    print("SESSION TESTS")
    print("=" * 60)
    s_ok = test_session()

    print("=" * 60)
    print("FORMATTER TESTS")
    print("=" * 60)
    f_ok = test_formatter()

    print("\n" + "=" * 60)
    if p_ok and g_ok and b_ok and s_ok and f_ok:
        print("ALL TESTS PASSED ✓")
    else:
        print("SOME TESTS FAILED ✗")
        sys.exit(1)
