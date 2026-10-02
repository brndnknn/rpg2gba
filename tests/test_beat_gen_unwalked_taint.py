"""`beat_gen.__main__._unwalked_taint`: live rows the walk never fires taint
their writes -- unless the generator has placed them elsewhere as rows that
cannot fire in this chapter (ROM run 64: Grott-Hole's Richboy, blocked behind
Strength in CH03, made Maury's switch-100 page on map 73 look undecided)."""
from __future__ import annotations

from types import SimpleNamespace

from rpg2gba.beat_gen.__main__ import _unwalked_taint
from rpg2gba.beat_gen.plan import Elsewhere

_ROW = "map019/ev006/p0/b4"


def _states(map_id: int) -> dict:
    del map_id
    return {
        "map019/ev006/p0": SimpleNamespace(writes=(), havoc_keys=(), trigger="touch"),
        _ROW: SimpleNamespace(writes=("switch100",), havoc_keys=(), trigger="touch"),
    }


def _verdicts() -> list:
    return [SimpleNamespace(row_id=_ROW, status="live")]


def test_an_unwalked_live_row_taints_its_writes():
    assert _unwalked_taint((), _verdicts(), _states) == ["switch100"]


def test_a_row_placed_elsewhere_as_blocked_taints_nothing():
    elsewhere = (Elsewhere(_ROW, "blocked", None, ("strength",)),)
    assert _unwalked_taint((), _verdicts(), _states, elsewhere) == []


def test_a_row_placed_elsewhere_as_never_fires_still_taints():
    # Only blocked / unreachable / later say "cannot fire in this chapter".
    elsewhere = (Elsewhere(_ROW, "never_fires", None, detail="proof"),)
    assert _unwalked_taint((), _verdicts(), _states, elsewhere) == ["switch100"]
