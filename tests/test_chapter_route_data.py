"""Tests for scripts/chapter_route_data.py (pure join + layout)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import chapter_route_data as crd  # noqa: E402
from rpg2gba.routing.plan import (  # noqa: E402
    ChosenApproach,
    RouteLeg,
    RoutePlan,
    RouteSegment,
    RouteNode,
    RouteWarp,
    TriggerCrossing,
)

REPO = Path(__file__).resolve().parents[1]


def _plan() -> RoutePlan:
    nodes = (
        RouteNode(0, "entry", 1, (0, 0)),
        RouteNode(1, "group", 1, (2, 0), group="g1", beats=("a",), rows=("r1",),
                  chosen_approach=ChosenApproach("UP", "x")),
        RouteNode(2, "group", 2, (5, 5), group="solo", beats=("solo",)),
        RouteNode(3, "exit", 2, (6, 5)),
    )
    segs = (
        RouteSegment(0, 1, (RouteLeg(1, ((0, 0), (1, 0), (2, 0))),), 2),
        RouteSegment(1, 2, (
            RouteLeg(1, ((2, 0), (3, 0)), RouteWarp(7, 2, (4, 4))),
            RouteLeg(2, ((4, 4), (5, 5))),
        ), 3, (TriggerCrossing(2, (4, 5), "S", "certain"),)),
        RouteSegment(2, 3, (RouteLeg(2, ((5, 5), (6, 5))),), 1),
    )
    return RoutePlan("CHXX", "m", nodes, segs, (), 6, "t")


def _beats():
    return [
        crd.BeatInfo("a", "g1", ("r1",)),
        crd.BeatInfo("b", "g1", ("r2",)),   # non-primary beat of g1
        crd.BeatInfo("solo", None, ()),
    ]


def _comp(mid: int) -> dict:
    return {"members": [{"id": mid, "name": f"M{mid}", "ox": 0, "oy": 0, "w": 10, "h": 8}]}


def _payload(sidecar=None, observed=None, beats=None):
    return crd.build_payload("CHXX", _plan(), beats or _beats(), sidecar, observed, component=_comp)


def test_numbering_skips_entry_exit():
    p = _payload()
    assert [g["number"] for g in p["groups"]] == [1, 2]
    assert [g["node_index"] for g in p["groups"]] == [1, 2]
    assert p["groups"][0]["side"] == "UP" and p["groups"][1]["side"] is None


def test_step_lettering_and_beat_to_group():
    g1, g2 = _payload()["groups"]
    assert [b["step"] for b in g1["beats"]] == ["1a", "1b"]
    assert [b["name"] for b in g1["beats"]] == ["a", "b"]  # 'b' not in node.beats
    assert [b["step"] for b in g2["beats"]] == ["2"]
    assert crd.step_label(3, 27, 30) == "3.28"


def test_to_from_segments():
    g1, g2 = _payload()["groups"]
    assert g1["to"] == [{"map_id": 1, "tiles": [[0, 0], [1, 0], [2, 0]]}]  # from entry
    assert [leg["map_id"] for leg in g1["from"]] == [1, 2]
    assert g2["to"] == g1["from"]
    assert g2["from"] == [{"map_id": 2, "tiles": [[5, 5], [6, 5]]}]  # to exit
    assert g1["from_crossings"][0]["script"] == "S" and g1["to_crossings"] == []


def test_connectors_and_route():
    p = _payload()
    assert p["connectors"] == [{"from": {"map_id": 1, "cell": [3, 0]}, "to": {"map_id": 2, "cell": [4, 4]}}]
    assert len(p["route"]) == 4
    assert {m["id"] for m in p["maps"]} == {1, 2}


def test_sidecar_card_odw_refusals():
    sc = {
        "schema": 1,
        "beats": [{"name": "a", "group": "g1", "rows": ["r1"]}],
        "order_dependent_writes": [{"rows": ["r1", "r9"], "text": "w"}, {"rows": ["r5"], "text": "x"}],
        "refusals": [{"row": "r2", "text": "no"}],
    }
    g1 = _payload(sidecar=sc)["groups"][0]
    a, b = g1["beats"]
    assert a["card"]["name"] == "a" and b["card"] is None
    assert [e["text"] for e in a["order_dependent_writes"]] == ["w"]
    assert b["order_dependent_writes"] == [] and [e["text"] for e in b["refusals"]] == ["no"]
    assert any("sidecar" in n for n in _payload()["notes"])


def test_inherited_beats_excluded_from_sidecar_fallback_and_loader():
    # fallback list comes verbatim; ':' filtering is the loader's job (_load_gen_beats)
    sc = {"beats": [{"name": "a", "group": "g1", "rows": []}, {"name": "solo"}]}
    got = crd._beats_from_sidecar(sc)
    assert [b.name for b in got] == ["a", "solo"] and got[1].group_key == "solo"


def test_borrowed_crops_pad_clamp_and_skip():
    sizes = {32: (72, 64), 33: (79, 53), 7: (10, 10)}
    pts = [(32, 8, 43), (32, 9, 45), (33, 1, 1), (7, 1, 1), (7, 8, 8)]
    got = crd.borrowed_crops({32, 7, 99}, pts, sizes, pad=4)
    assert got[32] == (4, 39, 10, 11)        # bbox (8..9, 43..45) padded by 4
    assert 33 not in got                      # own map: never cropped
    assert 7 not in got                       # padded bbox covers the whole map: left whole
    assert 99 not in got                      # no points / no size


def test_apply_crop_moves_drawn_rect():
    m = crd._apply_crop({"id": 32, "ox": 100, "oy": 0, "w": 72, "h": 64}, {32: (4, 39, 10, 11)})
    assert (m["ox"], m["oy"], m["w"], m["h"], m["crop"]) == (104, 39, 10, 11, [4, 39])
    assert crd._apply_crop({"id": 1, "ox": 0, "oy": 0, "w": 5, "h": 5}, {})["crop"] == [0, 0]


def test_load_observed_prefers_playtest_gen_dir(tmp_path):
    import json as _json

    def put(sub, data):
        d = tmp_path / sub / "observed_beats"
        d.mkdir(parents=True, exist_ok=True)
        (d / "CH09.json").write_text(_json.dumps(data), encoding="utf-8")

    put("playtest", {"version": 2, "suite": "hand", "beats": []})
    assert crd._load_observed(tmp_path, "CH09")["suite"] == "hand"  # shared dir: tag kept, gated later
    put("playtest-gen", {"version": 2, "beats": [], "tag": "gen-dir"})  # untagged legacy gen record
    got = crd._load_observed(tmp_path, "CH09")
    assert got["suite"] == "gen" and got["tag"] == "gen-dir"
    put("playtest-gen", {"version": 2, "suite": "hand", "beats": []})  # explicitly hand -> not trusted
    assert crd._load_observed(tmp_path, "CH09")["suite"] == "hand"
    assert crd._load_observed(tmp_path, "CH10") is None


def test_match_card_falls_back_to_group_row_then_stem():
    # Plan names (sidecar) can differ from runtime names for one template call.
    cards = {
        "m1_item_ball": {"name": "m1_item_ball", "group": "m1_item_ball", "rows": ["map001/ev001/p0"], "description": None},
        "m1_item_ball_arms": {"name": "m1_item_ball_arms", "group": "m1_item_ball", "rows": ["map001/ev001/p1"], "description": None},
    }
    by_row = crd.BeatInfo("m1_item_ball_spent", "m1_item_ball", ("map001/ev001/p1",), "picked up")
    assert crd._match_card(by_row, cards)["name"] == "m1_item_ball_arms"
    assert crd._match_card(by_row, cards)["description"] == "picked up"
    by_stem = crd.BeatInfo("m1_item_ball_spent", "m1_item_ball", ())
    assert crd._match_card(by_stem, cards)["name"] == "m1_item_ball_arms"
    assert cards["m1_item_ball_arms"]["description"] is None  # sidecar dict not mutated
    assert crd._match_card(crd.BeatInfo("zz", "other"), cards) is None


def test_load_gen_beats_filters_colon(monkeypatch):
    import rpg2gba.playtest.chapter as chmod

    class B:
        def __init__(self, n, g=None):
            self.name, self.group, self.rows, self.description = n, g, (), ""

    class C:
        beats = (B("CH01:x"), B("own"), B("y", "G"))

    seen = {}

    def fake(name, *, suite="hand"):
        seen["suite"] = suite
        return C()

    monkeypatch.setattr(chmod, "load_chapter", fake)
    got = crd._load_gen_beats("CHXX")
    assert [b.name for b in got] == ["own", "y"] and seen["suite"] == "gen"


def _obs(**kw):
    base = {
        "version": 2,
        "beats": [
            {"beat": "a", "status": "pass",
             "path": [{"map_id": 1, "x": 1, "y": 0}, {"map_id": 1, "x": 2, "y": 0}],
             "divergence": {"off_plan": [{"map_id": 1, "cell": [9, 9], "step": 1}],
                            "trigger_violations": [{"map_id": 1, "cell": [8, 8]}]}},
            {"beat": "b", "status": "fail", "path": [{"map_id": 1, "x": 2, "y": 0}], "divergence": {}},
            {"beat": "solo", "status": "pass",
             "path": [{"map_id": 1, "x": 3, "y": 0}, {"map_id": 2, "x": 4, "y": 4},
                      {"map_id": 2, "x": 5, "y": 5}]},
        ],
    }
    base.update(kw)
    return base


@pytest.mark.parametrize("extra,ok", [
    ({"suite": "hand"}, False),
    ({}, False),
    ({"suite": "gen"}, True),
    ({"suite": "gen", "version": 1}, False),
])
def test_walked_gating(extra, ok):
    p = _payload(observed=_obs(**extra))
    assert p["walked_available"] is ok
    if ok:
        assert p["groups"][0]["walked"] is not None
    else:
        assert all(g["walked"] is None for g in p["groups"])
        assert crd.NOTE_NO_WALK in p["notes"]


def test_walked_content():
    p = _payload(observed=_obs(suite="gen"))
    g1, g2 = p["groups"]
    assert g1["beats"][0]["status"] == "pass" and g1["beats"][1]["status"] == "fail"
    w1 = g1["walked"]
    assert w1["to"] == [{"map_id": 1, "tiles": [[1, 0], [2, 0]]}]  # a + b, dup dropped
    assert w1["off_plan"] == [{"map_id": 1, "cell": [9, 9]}]
    assert w1["violations"] == [{"map_id": 1, "cell": [8, 8]}]
    assert w1["from"] == [{"map_id": 1, "tiles": [[3, 0]]}, {"map_id": 2, "tiles": [[4, 4], [5, 5]]}]
    assert g2["walked"]["from"] == []  # no next group


def test_no_plan_degrades():
    p = crd.build_payload("CH99", None, [], None, None, notes=["n"])
    assert p["groups"] == [] and p["maps"] == [] and p["notes"] == ["n"]


def test_chapter_payload_unknown_chapter(tmp_path):
    p = crd.chapter_payload("CH99", out_dir=tmp_path)
    assert p["groups"] == [] and p["notes"]
    assert crd.list_chapters(tmp_path) == []


# --- layout -----------------------------------------------------------------

_DIMS = {1: (20, 10), 2: (20, 10), 3: (6, 6), 4: (6, 6), 5: (8, 8), 6: (5, 5)}


def _lcomp(mid: int) -> dict:
    # 1 and 2 are seam-joined side by side; the rest are lone.
    if mid in (1, 2):
        return {"members": [
            {"id": 1, "name": "A", "ox": 0, "oy": 0, "w": 20, "h": 10},
            {"id": 2, "name": "B", "ox": 20, "oy": 0, "w": 20, "h": 10},
        ]}
    w, h = _DIMS[mid]
    return {"members": [{"id": mid, "name": f"M{mid}", "ox": 0, "oy": 0, "w": w, "h": h}]}


def _overlap(a, b):
    return not (a["ox"] + a["w"] <= b["ox"] or b["ox"] + b["w"] <= a["ox"]
                or a["oy"] + a["h"] <= b["oy"] or b["oy"] + b["h"] <= a["oy"])


def _route(*ids):
    return [{"map_id": i, "tiles": [[0, 0]]} for i in ids]


def test_layout_deterministic_nonoverlap_and_order():
    route = _route(1, 4, 3, 2, 5)
    a = crd.chapter_layout([1, 2, 3, 4, 5, 6], route, component=_lcomp)
    b = crd.chapter_layout([6, 5, 4, 3, 2, 1], route, component=_lcomp)
    assert a == b
    maps, w, h = a
    assert len(maps) == 6
    for i, m in enumerate(maps):
        for o in maps[i + 1:]:
            assert not _overlap(m, o), (m, o)
        assert m["ox"] + m["w"] <= w and m["oy"] + m["h"] <= h
    by = {m["id"]: m for m in maps}
    # interiors hosted under cluster {1,2}, ordered by first visit: 4 then 3 then 5
    assert by[4]["oy"] >= 10 + crd.GAP
    assert by[4]["ox"] < by[3]["ox"] < by[5]["ox"]
    # unvisited lone map 6 is standalone, placed to the right of the cluster
    assert by[6]["ox"] >= 40 + crd.GAP


def test_layout_restricts_to_chapter_maps():
    def comp(mid):
        return {"members": [
            {"id": 1, "name": "A", "ox": 0, "oy": 0, "w": 10, "h": 10},
            {"id": 2, "name": "B", "ox": 10, "oy": 0, "w": 10, "h": 10},
            {"id": 99, "name": "X", "ox": 20, "oy": 0, "w": 10, "h": 10},
        ]}
    maps, w, _ = crd.chapter_layout([1, 2], _route(1, 2), component=comp)
    assert {m["id"] for m in maps} == {1, 2} and w == 20


# --- real data ---------------------------------------------------------------


def test_real_ch02_smoke():
    if not (crd._beats_dir(None) / "CH02.route.json").is_file():
        pytest.skip("no output/beats/CH02.route.json")
    p = crd.chapter_payload("CH02")
    assert p["chapter"] == "CH02" and "CH02" in crd.list_chapters()
    assert p["groups"] and p["maps"] and p["route"]
    assert [g["number"] for g in p["groups"]] == list(range(1, len(p["groups"]) + 1))
    ids = {m["id"] for m in p["maps"]}
    assert {leg["map_id"] for leg in p["route"]} <= ids
    maps = p["maps"]
    for i, m in enumerate(maps):
        for o in maps[i + 1:]:
            assert not _overlap(m, o)
