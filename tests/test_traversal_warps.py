"""`traversal.warps.extract_warp_exits`: one exit per distinct transfer.

Pins the C6 Task 9 duplicate-exit fix. Map040 event 19 carries the same
code-201 on more than one page, and before the fix `cells.warp_cell` read
that as "2 distinct warp exits" at one cell.
"""
from rpg2gba.traversal.warps import WarpExit, extract_warp_exits


def _transfer(dest_map: int, x: int, y: int, facing: int = 2) -> dict:
    return {"code": 201, "parameters": [0, dest_map, x, y, facing, 0]}


def _map(*pages: list[dict]) -> dict:
    return {
        "map_id": 40,
        "events": [None, {
            "id": 19, "x": 68, "y": 43,
            "pages": [{"list": list(cmds)} for cmds in pages],
        }],
    }


def test_identical_transfer_on_two_pages_is_one_exit():
    exits = extract_warp_exits(_map([_transfer(37, 16, 5)], [_transfer(37, 16, 5)]))
    assert exits == [WarpExit(cell=(68, 43), event_id=19, dest_map=37,
                              dest_x=16, dest_y=5, dest_facing=2)]


def test_transfers_differing_in_destination_stay_distinct():
    exits = extract_warp_exits(_map([_transfer(37, 16, 5)], [_transfer(37, 16, 6)]))
    assert len(exits) == 2


def test_transfers_differing_only_in_facing_stay_distinct():
    exits = extract_warp_exits(_map([_transfer(37, 16, 5, 2)], [_transfer(37, 16, 5, 8)]))
    assert len(exits) == 2
