"""`playtest.archetypes.warp._pre_warp_texts`: which messages a warp beat reads
before its transfer, and which text shapes it refuses at registration.

First user: CH06's Maria's Key door (map14006/ev017/p0/b0), whose arm shows
"used Maria's House Key!" and then transfers -- `wait_for_map` alone would
sit on that text box until its budget ran out.
"""
from __future__ import annotations

import pytest

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor, make_params
from rpg2gba.playtest.archetypes.warp import _pre_warp_texts

PAGE, ARM = "map14006/ev017/p0", "map14006/ev017/p0/b0"


def _lookup(arm_assertions: list[FloorAssertion]):  # noqa: ANN202
    floors = {
        PAGE: RowFloor(row_id=PAGE, trigger="player_touch", assertions=frozenset(), refusals=()),
        ARM: RowFloor(row_id=ARM, trigger="player_touch",
                      assertions=frozenset(arm_assertions), refusals=()),
    }
    return floors.__getitem__


def _text(idx: int, text: str) -> FloorAssertion:
    return FloorAssertion(row_id=ARM, kind="text", list_index=idx, code=101,
                          params=make_params(index=0, text=text), tag="text")


_WARP = FloorAssertion(row_id=ARM, kind="warp", list_index=33, code=201,
                       params=make_params(map_id=47, x=5, y=9))


def test_pre_transfer_text_is_read_in_order():
    lookup = _lookup([_text(9, "second"), _text(3, "first"), _WARP])
    texts = _pre_warp_texts("b", (PAGE, ARM), lookup, mechanism="threshold", boundary=False)
    assert [t.param("text") for t in texts] == ["first", "second"]


def test_no_text_is_empty():
    assert _pre_warp_texts("b", (PAGE, ARM), _lookup([_WARP]),
                           mechanism="door", boundary=False) == ()


def test_boundary_beat_reads_nothing():
    assert _pre_warp_texts("b", (PAGE, ARM), _lookup([_text(3, "x"), _WARP]),
                           mechanism="threshold", boundary=True) == ()


def test_text_after_transfer_refuses():
    with pytest.raises(ValueError, match="after the transfer"):
        _pre_warp_texts("b", (PAGE, ARM), _lookup([_WARP, _text(40, "late")]),
                        mechanism="threshold", boundary=False)


@pytest.mark.parametrize("mechanism", ["door", "arrow"])
def test_non_threshold_text_refuses(mechanism):
    with pytest.raises(ValueError, match=mechanism):
        _pre_warp_texts("b", (PAGE, ARM), _lookup([_text(3, "x"), _WARP]),
                        mechanism=mechanism, boundary=False)
