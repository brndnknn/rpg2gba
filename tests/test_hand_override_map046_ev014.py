"""Map046 EV014 hand override: operator-approved fix (2026-10-09) of a Uranium
source bug where the "no Fortog" line also played after a successful trade."""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent import hand_overrides, poryscript

_LINE = "You don't have a Fortog, I guess..."


def _text() -> str:
    override = hand_overrides.load_hand_overrides()[(46, 14)]
    return override.text


def test_override_loads_and_carries_provenance() -> None:
    text = _text()
    first = text.splitlines()[0]
    assert first.startswith("# hand conversion (2026-10-09)")
    assert "script Map046_EV014_Page1 {" in text
    assert "script Map046_EV014_Page2 {" in text


def test_no_fortog_line_is_else_arm_of_successful_trade_branch() -> None:
    text = "\n".join(
        ln for ln in _text().splitlines() if not ln.startswith("#"))
    assert text.count(_LINE) == 1
    after_trade = text.split("setflag(FLAG_MAP046_EVENT014_SSA)", 1)[1]
    # The very next thing after the trade's last statement is the else arm
    # holding the line -- it is not reachable after a successful trade.
    assert after_trade.lstrip().startswith("} else {")
    assert after_trade.index(_LINE) < after_trade.index("Don't come back")


@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_override_compiles_through_real_poryscript() -> None:
    result = poryscript.compile_script(_text())
    assert result.ok, result.stderr
