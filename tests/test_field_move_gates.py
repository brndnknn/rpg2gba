"""Pin Uranium's field-move badge gates in the vendored engine.

Uranium counts badges for HM use (``HIDDENMOVESCOUNTBADGES = true``,
``002__Settings.rb``): each HM needs at least N badges of any kind. Emerald
gates each on one specific badge flag; the CH04 boot walk hit that on Flash
and the CH06 walk found Rock Smash working only through a badge-3 boot rig.
"""

import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1] / "engine"
FIELD_MOVE_C = ENGINE / "src" / "field_move.c"
NEW_GAME_C = ENGINE / "src" / "new_game.c"

# 002__Settings.rb BADGEFOR* (Flash is 0: no gate at all).
URANIUM_BADGES_FOR = {
    "Cut": 3,
    "RockSmash": 1,
    "Strength": 4,
    "Surf": 5,
    "Dive": 7,
    "Fly": 8,
    "Waterfall": 8,
}


def _statements(name: str) -> list[str]:
    source = FIELD_MOVE_C.read_text(encoding="utf-8")
    match = re.search(rf"static bool32 {name}\(void\)\n\{{\n(.*?)\n\}}", source, re.DOTALL)
    assert match, f"{name} not found in {FIELD_MOVE_C}"
    return [line.strip() for line in match.group(1).splitlines()
            if line.strip() and not line.strip().startswith("//")]


def test_flash_needs_no_badge():
    assert _statements("IsFieldMoveUnlocked_Flash")[0] == "return TRUE;"


@pytest.mark.parametrize(("move", "count"), sorted(URANIUM_BADGES_FOR.items()))
def test_hm_gate_is_uranium_badge_count(move: str, count: int):
    assert _statements(f"IsFieldMoveUnlocked_{move}")[0] == f"return HasAtLeastBadges({count});"


def test_badge_count_helper_counts_every_badge():
    source = FIELD_MOVE_C.read_text(encoding="utf-8")
    assert "flag < FLAG_BADGE01_GET + NUM_BADGES" in source
    assert "return owned >= count;" in source


def test_no_boot_badge_rig():
    # Rock Smash used to work only because every new game set badge 3.
    assert not re.search(r"FlagSet\(FLAG_BADGE0\d_GET\)", NEW_GAME_C.read_text(encoding="utf-8"))
