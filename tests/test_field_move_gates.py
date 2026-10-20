"""Pin the field-move badge-gate hooks in the vendored engine.

Uranium counts badges for HM use (``HIDDENMOVESCOUNTBADGES = true``,
``002__Settings.rb``): each HM needs at least N badges of any kind. Emerald
gates each on one specific badge flag; the CH04 boot walk hit that on Flash
and the CH06 walk found Rock Smash working only through a badge-3 boot rig.

Since I3 S4 the counts are generated (``rpg2gba.game_profile``, values pinned
in ``tests/test_game_profile.py``); this file pins that every gate reads the
generated macro before falling back to stock.
"""

import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1] / "engine"
FIELD_MOVE_C = ENGINE / "src" / "field_move.c"
NEW_GAME_C = ENGINE / "src" / "new_game.c"

GATED_MOVES = {
    "Cut": "CUT",
    "Flash": "FLASH",
    "RockSmash": "ROCK_SMASH",
    "Strength": "STRENGTH",
    "Surf": "SURF",
    "Dive": "DIVE",
    "Fly": "FLY",
    "Waterfall": "WATERFALL",
}


def _statements(name: str) -> list[str]:
    source = FIELD_MOVE_C.read_text(encoding="utf-8")
    match = re.search(rf"static bool32 {name}\(void\)\n\{{\n(.*?)\n\}}", source, re.DOTALL)
    assert match, f"{name} not found in {FIELD_MOVE_C}"
    return [line.strip() for line in match.group(1).splitlines()
            if line.strip() and not line.strip().startswith("//")]


@pytest.mark.parametrize(("move", "macro"), sorted(GATED_MOVES.items()))
def test_hm_gate_reads_the_generated_badge_count(move: str, macro: str):
    statements = _statements(f"IsFieldMoveUnlocked_{move}")
    assert statements[:3] == [
        f"#ifdef RPG2GBA_FIELD_MOVE_BADGE_{macro}",
        f"return Rpg2gbaFieldMoveBadgeGate(RPG2GBA_FIELD_MOVE_BADGE_{macro});",
        "#endif",
    ]


def test_badge_count_helper_counts_every_badge():
    source = FIELD_MOVE_C.read_text(encoding="utf-8")
    assert "flag < FLAG_BADGE01_GET + NUM_BADGES" in source
    assert "return owned >= n;" in source


def test_no_boot_badge_rig():
    # Rock Smash used to work only because every new game set badge 3.
    assert not re.search(r"FlagSet\(FLAG_BADGE0\d_GET\)", NEW_GAME_C.read_text(encoding="utf-8"))
