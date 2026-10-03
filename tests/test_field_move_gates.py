"""Pin Uranium's field-move badge gates in the vendored engine.

Uranium counts badges for HM use (``HIDDENMOVESCOUNTBADGES = true``) and sets
``BADGEFORFLASH = 0`` (``002__Settings.rb``), so Flash works outside battle with
no badge. Emerald gates it on badge 2; the CH04 boot walk hit that gate.
"""

import re
from pathlib import Path

FIELD_MOVE_C = Path(__file__).resolve().parents[1] / "engine" / "src" / "field_move.c"


def _function_body(source: str, name: str) -> str:
    match = re.search(rf"static bool32 {name}\(void\)\n\{{\n(.*?)\n\}}", source, re.DOTALL)
    assert match, f"{name} not found in {FIELD_MOVE_C}"
    return match.group(1)


def test_flash_needs_no_badge():
    body = _function_body(FIELD_MOVE_C.read_text(encoding="utf-8"), "IsFieldMoveUnlocked_Flash")
    statements = [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith("//")]
    assert statements[0] == "return TRUE;"
