"""Tests for the map-split stage (rpg2gba.map_split; design
reference/guides/map_split_stage.md)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent.flag_registry import (
    hide_flag_name,
    self_switch_flag_name,
    temp_switch_flag_name,
)
from rpg2gba.map_split import stage
from rpg2gba.map_split.derive import (
    SplitError,
    derive_split,
    rebase_connection_row,
    rewrite_transfer,
)
from rpg2gba.map_split.engine import render_siblings_header
from rpg2gba.map_split.ids import is_piece, origin_of, piece_index, piece_uid, split_blocked_cells
from rpg2gba.map_split.spec import SplitSpec, expand_split_ids, parse_split_maps

FLOOR, WALL = 384, 385
W, H = 30, 10
ORIGIN = 1
A, B = piece_uid(ORIGIN, 0), piece_uid(ORIGIN, 1)

# Room A x1..8 y2..7, a corridor along y=4 from x9..20, room B x21..28 y2..7.
# The cut at (15,4) separates A (+ west corridor) from B (+ east corridor).
_FLOOR_CELLS = (
    {(x, y) for x in range(1, 9) for y in range(2, 8)}
    | {(x, 4) for x in range(9, 21)}
    | {(x, y) for x in range(21, 29) for y in range(2, 8)}
)


def _tiles() -> dict:
    data = [0] * (3 * W * H)
    for y in range(H):
        for x in range(W):
            data[y * W + x] = FLOOR if (x, y) in _FLOOR_CELLS else WALL
    return {"xsize": W, "ysize": H, "zsize": 3, "data": data}


def _event(eid: int, x: int, y: int, cmds: list[dict] | None = None, **page: object) -> dict:
    p = {"move_type": 0, "move_route": {"list": []}, "list": (cmds or []) + [{"code": 0, "parameters": []}]}
    p.update(page)
    return {"id": eid, "name": f"EV{eid:03d}", "x": x, "y": y, "pages": [p]}


def _map(events: list[dict] | None = None) -> dict:
    return {
        "map_id": ORIGIN, "tileset_id": 1, "width": W, "height": H,
        "bgm": {"name": "town"}, "tiles": _tiles(),
        "events": events if events is not None else [_event(1, 3, 3), _event(2, 25, 5)],
    }


def _blocked() -> dict[tuple[int, int], bool]:
    return {(x, y): (x, y) not in _FLOOR_CELLS for y in range(H) for x in range(W)}


def _spec(cuts=((15, 4),), seeds_a=((3, 3),), seeds_b=((25, 5),)) -> SplitSpec:
    return parse_split_maps({"splits": {str(ORIGIN): {
        "cuts": [list(c) for c in cuts],
        "pieces": [
            {"k": 0, "name": "Town", "seeds": [list(s) for s in seeds_a]},
            {"k": 1, "name": "Town East", "seeds": [list(s) for s in seeds_b]},
        ],
    }}})[ORIGIN]


def _derive(**kw):
    return derive_split(_map(**kw), _blocked(), {(3, 3), (25, 5)}, _spec())


# --- ids / spec ------------------------------------------------------------------

def test_piece_uid_round_trips_and_never_collides_with_uranium_ids() -> None:
    assert piece_uid(40, 0) == 14000 and piece_uid(40, 6) == 14006
    assert origin_of(14006) == 40 and piece_index(14006) == 6 and is_piece(14006)
    assert origin_of(40) == 40 and not is_piece(999)
    with pytest.raises(ValueError):
        piece_uid(40, 100)


def test_expand_split_ids_replaces_origin_in_place() -> None:
    specs = {ORIGIN: _spec()}
    assert expand_split_ids([7, ORIGIN, 8], specs) == [7, A, B, 8]


@pytest.mark.parametrize("bad, match", [
    ({"splits": {"1": {"cuts": [], "pieces": []}}}, "non-empty"),
    ({"splits": {"1": {"cuts": [[1, 1]], "pieces": [{"k": 0, "name": "X", "seeds": [[1, 1]]}]}}}, "cut"),
    ({"splits": {"1": {"cuts": [], "pieces": [{"k": 1, "name": "X", "seeds": [[1, 1]]}]}}}, "0..0"),
    ({"splits": {"1": {"cuts": [[1, 1], [1, 1]], "pieces": [{"k": 0, "name": "X", "seeds": [[2, 2]]}]}}}, "duplicate cut"),
])
def test_spec_fails_loud(bad: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        parse_split_maps(bad)


def test_self_switch_and_hide_flags_keep_the_origin_name() -> None:
    assert self_switch_flag_name(14000, 79, "a") == "FLAG_MAP040_EVENT079_SSA"
    assert hide_flag_name(14003, 5) == "FLAG_HIDE_MAP040_EV005"
    assert temp_switch_flag_name(14001, 2, "b") == "FLAG_MAP040_EVENT002_TSB"


# --- derivation ----------------------------------------------------------------------

def test_pieces_rects_and_cut_walls() -> None:
    res = _derive()
    a, b = res.pieces
    assert (a.uid, b.uid) == (A, B)
    # camera box (7 cols, 5 rows) around each side's walkable cells, clipped
    assert (a.rect.x0, a.rect.y0, a.rect.w, a.rect.h) == (0, 0, 22, 10)
    assert (b.rect.x0, b.rect.y0, b.rect.w, b.rect.h) == (9, 0, 21, 10)
    assert a.blocked_cells == [(15, 4)] and b.blocked_cells == [(6, 4)]
    assert split_blocked_cells(a.map_json) == {(15, 4)}
    assert a.map_json["split"]["origin"] == ORIGIN and a.map_json["map_id"] == A


def test_events_go_to_their_piece_rebased() -> None:
    res = _derive()
    a, b = res.pieces
    assert [(e["id"], e["x"], e["y"]) for e in a.map_json["events"]] == [(1, 3, 3)]
    assert [(e["id"], e["x"], e["y"]) for e in b.map_json["events"]] == [(2, 16, 5)]


def test_tiles_are_cropped_and_unseen_cells_empty() -> None:
    res = _derive()
    b = res.pieces[1]
    t = b.map_json["tiles"]
    assert (t["xsize"], t["ysize"]) == (b.rect.w, b.rect.h) == (b.map_json["width"], b.map_json["height"])
    # origin (25,5) -> local (16,5): floor on layer 0
    assert t["data"][5 * t["xsize"] + 16] == FLOOR
    # every in-rect cell within view of B's walkable cells keeps its art; B's
    # view reaches x>=9, so its whole rect is in view here — nothing blanked
    assert all(v != 0 for v in t["data"][: t["xsize"] * t["ysize"]])


def test_arrow_seam_pairs_cells_across_the_cut() -> None:
    (seam,) = _derive().seams
    assert (seam.map_a, seam.map_b) == (A, B)
    assert seam.cells_a == ((14, 4),) and seam.cells_b == ((7, 4),)
    assert (seam.direction_a, seam.direction_b) == ("right", "left")


def test_resolve_maps_origin_cells_and_rejects_cuts() -> None:
    res = _derive()
    assert res.resolve(25, 5) == (B, 16, 5)
    assert res.resolve(3, 3) == (A, 3, 3)
    with pytest.raises(SplitError, match="cut cell"):
        res.resolve(15, 4)


def test_unseeded_area_fails_loud() -> None:
    # a second cut at (10,4) strands corridor x11..14 between the two cuts
    with pytest.raises(SplitError, match="no piece seed"):
        derive_split(_map(), _blocked(), {(3, 3), (25, 5)}, _spec(cuts=((15, 4), (10, 4))))


def test_cut_that_does_not_separate_fails_loud() -> None:
    with pytest.raises(SplitError, match="don't separate"):
        derive_split(_map(), _blocked(), {(3, 3), (25, 5)}, _spec(cuts=((4, 7),)))


def test_seed_on_wall_fails_loud() -> None:
    with pytest.raises(SplitError, match="not walkable"):
        derive_split(_map(), _blocked(), {(3, 3), (25, 5)}, _spec(seeds_b=((0, 0),)))


def test_entry_on_cut_fails_loud() -> None:
    with pytest.raises(SplitError, match="enters the map"):
        derive_split(_map(), _blocked(), {(3, 3), (15, 4)}, _spec())


def test_event_acting_on_event_in_other_piece_fails_loud() -> None:
    mover = _event(1, 3, 3, [{"code": 209, "parameters": [2, {"list": []}]}])
    with pytest.raises(SplitError, match="acts on EV002"):
        derive_split(_map([mover, _event(2, 25, 5)]), _blocked(), {(3, 3), (25, 5)}, _spec())


def test_patrol_over_a_cut_fails_loud() -> None:
    walker = _event(1, 13, 4, move_type=3,
                    move_route={"list": [{"code": 3}, {"code": 3}, {"code": 3}, {"code": 0}]})
    with pytest.raises(SplitError, match="crosses cut"):
        derive_split(_map([walker, _event(2, 25, 5)]), _blocked(), {(3, 3), (25, 5)}, _spec())


def test_event_outside_view_grows_the_rect() -> None:
    far = _event(3, 28, 9)  # a wall cell, owned by B (nearest), in view anyway
    res = derive_split(_map([_event(1, 3, 3), _event(2, 25, 5), far]), _blocked(),
                       {(3, 3), (25, 5)}, _spec())
    b = res.pieces[1]
    assert 3 in b.event_ids and b.rect.contains(28, 9)


# --- connections / transfers / engine -------------------------------------------------

def test_connection_row_is_rebased_onto_the_owning_piece() -> None:
    res = _derive()
    # neighbour 9 (10 wide) sits below origin x 21..30: shared span is room B's
    # bottom edge, which isn't walkable in this toy map, so no piece qualifies
    with pytest.raises(SplitError, match="exactly one piece"):
        rebase_connection_row([9, "N", 0, ORIGIN, "S", 21], res, (W, H), (10, 10))
    # make B's bottom-edge cells walkable and rerun
    blocked = _blocked()
    for x in range(21, 29):
        blocked[(x, 8)] = blocked[(x, 9)] = False
    res = derive_split(_map(), blocked, {(3, 3), (25, 5), (25, 9)}, _spec())
    assert rebase_connection_row([9, "N", 0, ORIGIN, "S", 21], res, (W, H), (10, 10)) == \
        [9, "N", 0, B, "S", 21 - res.piece_by_uid(B).rect.x0]


def test_rewrite_transfer_targets_the_piece() -> None:
    res = _derive()
    assert rewrite_transfer([0, ORIGIN, 25, 5, 2, 0], {ORIGIN: res}, "t") == [0, B, 16, 5, 2, 0]
    unchanged = [0, 99, 1, 1, 2, 0]
    assert rewrite_transfer(unchanged, {ORIGIN: res}, "t") is unchanged
    with pytest.raises(SplitError):
        rewrite_transfer([0, ORIGIN, 15, 4, 2, 0], {ORIGIN: res}, "t")


def test_siblings_header() -> None:
    text = render_siblings_header([5, A, B], {A: "MAP_TOWN", B: "MAP_TOWN_EAST"})
    assert "#define RPG2GBA_SPLIT_SIBLING_COUNT 2" in text
    assert "MAP_GROUP(MAP_TOWN_EAST), .mapNum = MAP_NUM(MAP_TOWN_EAST), .origin = 1" in text
    assert "COUNT 0" in render_siblings_header([5], {})


# --- stage IO -------------------------------------------------------------------------

def _build_dir(tmp_path: Path) -> Path:
    build = tmp_path / "uranium-build"
    (build / "maps").mkdir(parents=True)
    passages = [0] * 400
    passages[WALL] = 0x0F
    (build / "tilesets.json").write_text(json.dumps(
        {"1": {"passages": passages, "priorities": [0] * 400, "terrain_tags": [0] * 400}}),
        encoding="utf-8")
    (build / "maps" / "Map001.json").write_text(json.dumps(_map()), encoding="utf-8")
    door = _event(1, 1, 1, [{"code": 201, "parameters": [0, ORIGIN, 25, 5, 2, 0]}])
    other = {"map_id": 2, "tileset_id": 1, "width": 1, "height": 1,
             "tiles": {"xsize": 1, "ysize": 1, "zsize": 3, "data": [FLOOR, 0, 0]},
             "events": [door, _event(2, 0, 0, [{"code": 201, "parameters": [0, ORIGIN, 3, 3, 2, 0]}])]}
    (build / "maps" / "Map002.json").write_text(json.dumps(other), encoding="utf-8")
    (build / "connections.json").write_text("[]", encoding="utf-8")
    return build


def _split_file(tmp_path: Path) -> Path:
    p = tmp_path / "split_maps.json"
    p.write_text(json.dumps({"splits": {str(ORIGIN): {
        "cuts": [[15, 4]],
        "pieces": [{"k": 0, "name": "Town", "seeds": [[3, 3]]},
                   {"k": 1, "name": "Town East", "seeds": [[25, 5]]}],
    }}}), encoding="utf-8")
    return p


def _snapshot(build: Path) -> dict[str, str]:
    return {str(p.relative_to(build)): p.read_text(encoding="utf-8")
            for p in sorted(build.rglob("*.json"))}


def test_stage_moves_origin_writes_pieces_and_retargets_transfers(tmp_path: Path) -> None:
    build = _build_dir(tmp_path)
    stage.run(build, split_maps=_split_file(tmp_path))
    names = sorted(p.name for p in (build / "maps").glob("Map*.json"))
    assert names == ["Map002.json", f"Map{A}.json", f"Map{B}.json"]
    assert (build / "maps_presplit" / "Map001.json").is_file()
    other = json.loads((build / "maps" / "Map002.json").read_text(encoding="utf-8"))
    params = [ev["pages"][0]["list"][0]["parameters"] for ev in other["events"]]
    assert params == [[0, B, 16, 5, 2, 0], [0, A, 3, 3, 2, 0]]
    seams = json.loads((build / "split_seam_warps.json").read_text(encoding="utf-8"))["seams"]
    assert [(s["map_a"], s["map_b"]) for s in seams] == [(A, B)]


def test_stage_is_idempotent(tmp_path: Path) -> None:
    build = _build_dir(tmp_path)
    split = _split_file(tmp_path)
    stage.run(build, split_maps=split)
    first = _snapshot(build)
    stage.run(build, split_maps=split)
    assert _snapshot(build) == first


def test_stage_undoes_a_removed_split(tmp_path: Path) -> None:
    build = _build_dir(tmp_path)
    stage.run(build, split_maps=_split_file(tmp_path))
    empty = tmp_path / "none.json"
    empty.write_text(json.dumps({"splits": {}}), encoding="utf-8")
    stage.run(build, split_maps=empty)
    assert sorted(p.name for p in (build / "maps").glob("Map*.json")) == ["Map001.json", "Map002.json"]


def test_stage_after_a_fresh_deserializer_run(tmp_path: Path) -> None:
    """phase3 re-run writes the unsplit origin and unrewritten maps back into
    maps/; the next stage run must treat them as the new sources."""
    build = _build_dir(tmp_path)
    split = _split_file(tmp_path)
    stage.run(build, split_maps=split)
    first = _snapshot(build)
    fresh = _build_dir(tmp_path / "fresh")
    for name in ("Map001.json", "Map002.json"):
        (build / "maps" / name).write_text(
            (fresh / "maps" / name).read_text(encoding="utf-8"), encoding="utf-8")
    stage.run(build, split_maps=split)
    assert _snapshot(build) == first


# --- command coordinates follow the event into its piece (2026-10-11) -------


def test_rebase_moves_player_coordinate_tests_and_direct_set_location():
    from rpg2gba.map_split.derive import Rect, _rebase_event

    event = {"id": 141, "x": 49, "y": 10, "pages": [{"list": [
        {"code": 111, "parameters": [12, "$game_player.x>=49"]},
        {"code": 355, "parameters": ["pbWait(2) if $game_player.y < 12"]},
        {"code": 202, "parameters": [0, 0, 45, 11, 0]},
        {"code": 202, "parameters": [0, 1, 7, 8, 0]},   # by variables: untouched
    ]}]}
    out = _rebase_event(event, Rect(38, 2, 30, 20))
    cmds = out["pages"][0]["list"]
    assert (out["x"], out["y"]) == (11, 8)
    assert cmds[0]["parameters"][1] == "$game_player.x>=11"
    assert cmds[1]["parameters"][0] == "pbWait(2) if $game_player.y < 10"
    assert cmds[2]["parameters"][2:4] == [7, 9]
    assert cmds[3]["parameters"][2:4] == [7, 8]
    assert event["pages"][0]["list"][0]["parameters"][1] == "$game_player.x>=49"  # input kept


def test_rebase_fails_loud_on_a_player_coordinate_it_cannot_follow():
    import pytest

    from rpg2gba.map_split.derive import Rect, SplitError, _rebase_event

    event = {"id": 1, "x": 40, "y": 5, "pages": [{"list": [
        {"code": 355, "parameters": ["pbSet(1, $game_player.x)"]}]}]}
    with pytest.raises(SplitError, match="can't rebase"):
        _rebase_event(event, Rect(38, 0, 30, 20))


def test_rebase_fails_loud_on_a_set_location_outside_the_piece():
    import pytest

    from rpg2gba.map_split.derive import Rect, SplitError, _rebase_event

    event = {"id": 1, "x": 40, "y": 5, "pages": [{"list": [
        {"code": 202, "parameters": [0, 0, 10, 5, 0]}]}]}
    with pytest.raises(SplitError, match="outside its piece"):
        _rebase_event(event, Rect(38, 0, 30, 20))
