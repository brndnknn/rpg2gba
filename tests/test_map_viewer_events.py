"""Coverage for scripts/map_viewer_events.py — the EVENTS-mode data layer
(trainer/item/warp identity, event-kind classification, playtest beat
markers) that sits behind map_viewer_common.build_map_data's "events" key.

Exercises the real output/ corpus (Map033 has trainer events; Map068 —
Kevlar Town's Pokémon Center — has warps, an item ball, and declared Kevlar
playtest beats) rather than synthetic fixtures, since the whole point of
this module is joining several real generated artifacts together. Skips
cleanly when those artifacts aren't present (CI / a fresh checkout), mirroring
the existing `pytest.skip("... not generated yet")` idiom used elsewhere in
this test suite (see tests/test_trainer_battles.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_viewer_common as mvc  # noqa: E402
import map_viewer_events as mve  # noqa: E402

from rpg2gba.routing.plan import (  # noqa: E402
    RouteLeg,
    RouteNode,
    RoutePlan,
    RouteSegment,
    TriggerCrossing,
    write_plan,
)

MAPS_DIR = mvc._maps_dir()
TRAINER_MAP_ID = 33  # has trainer/rematch events (see deterministic.py smoke checks)
KEVLAR_CENTER_MAP_ID = 68  # MAP_KEVLAR_TOWN_POKEMON_CENTER: warps + item ball


def _require_map(map_id: int) -> dict:
    path = MAPS_DIR / f"Map{map_id:03d}.json"
    if not path.is_file():
        pytest.skip(f"{path} not generated yet")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    """Module-level mtime-fingerprinted caches (mirrors the
    _png_paths_cache-clearing fixture in test_map_viewer_fingerprint.py) —
    clear around every test so no test can be served a stale value left by
    another."""
    for name in (
        "_ctx_cache", "_item_names_cache", "_trainer_join_cache",
        "_map_registry_cache", "_map_groups_cache", "_switch_names_cache",
        "_variable_names_cache", "_route_plans_cache",
    ):
        setattr(mve, name, None)
    yield
    for name in (
        "_ctx_cache", "_item_names_cache", "_trainer_join_cache",
        "_map_registry_cache", "_map_groups_cache", "_switch_names_cache",
        "_variable_names_cache", "_route_plans_cache",
    ):
        setattr(mve, name, None)


# ---------------------------------------------------------------------------
# enrich_events
# ---------------------------------------------------------------------------


def test_enrich_events_preserves_legacy_keys_and_resolves_trainer() -> None:
    doc = _require_map(TRAINER_MAP_ID)
    events = mve.enrich_events(TRAINER_MAP_ID, doc["events"])
    by_id = {e["id"]: e for e in events}

    assert 9 in by_id, "Map033 event 9 (Marko the Fisherman) missing from fixture map"
    evt = by_id[9]

    # The seven pre-existing keys stay byte-compatible for the graphics frontend.
    for key in ("id", "name", "x", "y", "npages", "is_warp", "character_name"):
        assert key in evt

    assert evt["kind"] == "trainer"
    assert evt["is_warp"] is False
    assert evt["trainer"] is not None
    assert evt["trainer"]["trainer_constant"] == "TRAINER_MARKO_19"
    assert evt["trainer"]["display_name"] == "Marko"
    assert evt["trainer"]["kind"] == "sight"
    assert evt["label"] == "Marko"


def test_enrich_events_warp_and_item_ball_on_kevlar_center() -> None:
    doc = _require_map(KEVLAR_CENTER_MAP_ID)
    events = mve.enrich_events(KEVLAR_CENTER_MAP_ID, doc["events"])
    by_id = {e["id"]: e for e in events}

    warps = [e for e in by_id.values() if e["is_warp"]]
    assert warps, "expected at least one warp event on the Kevlar Center map"
    for w in warps:
        assert w["kind"] == "warp"

    items = [e for e in by_id.values() if e["kind"] == "item"]
    assert items, "expected an item-ball event on the Kevlar Center map"


def test_enrich_events_empty_list_is_empty() -> None:
    assert mve.enrich_events(TRAINER_MAP_ID, []) == []


# ---------------------------------------------------------------------------
# event_detail
# ---------------------------------------------------------------------------


def test_event_detail_full_trainer_record() -> None:
    _require_map(TRAINER_MAP_ID)
    detail = mve.event_detail(TRAINER_MAP_ID, 9)

    assert detail["trainer"]["trainer_constant"] == "TRAINER_MARKO_19"
    assert detail["trainer"]["party"], "expected a resolved party from trainers.json"
    assert detail["pages"], "expected per-page detail"
    assert detail["pages"][0]["dialogue"], "expected joined dialogue text on page 1"
    assert detail["warp"] is None


def test_event_detail_bad_event_id_raises_keyerror() -> None:
    _require_map(TRAINER_MAP_ID)
    with pytest.raises(KeyError):
        mve.event_detail(TRAINER_MAP_ID, 999999)


def test_event_detail_warp_resolves_destination() -> None:
    doc = _require_map(KEVLAR_CENTER_MAP_ID)
    warp_id = next(
        e["id"] for e in mve.enrich_events(KEVLAR_CENTER_MAP_ID, doc["events"]) if e["is_warp"]
    )
    detail = mve.event_detail(KEVLAR_CENTER_MAP_ID, warp_id)
    assert detail["warp"] is not None
    assert "map_id" in detail["warp"] or "raw_parameters" in detail["warp"]


# ---------------------------------------------------------------------------
# beat_markers
# ---------------------------------------------------------------------------


def test_beat_markers_declared_for_kevlar_center(monkeypatch: pytest.MonkeyPatch) -> None:
    registry_state = mvc._output_base() / "uranium-build" / "porymap" / "map_constants.json"
    if not registry_state.is_file():
        pytest.skip(f"{registry_state} not generated yet")

    # Force the "no observed-beats directory" branch regardless of real repo
    # state, so this assertion is stable: point _output_base at a location
    # with the porymap registry present but no playtest/observed_beats dir.
    result = mve.beat_markers(KEVLAR_CENTER_MAP_ID)

    assert result["map_id"] == KEVLAR_CENTER_MAP_ID
    assert isinstance(result["declared"], list)
    assert isinstance(result["observed"], list)
    assert isinstance(result["notes"], list)
    kevlar_beats = [b for b in result["declared"] if b["chapter"] == "kevlar"]
    assert kevlar_beats, "expected at least one declared Kevlar beat on this map"
    for b in kevlar_beats:
        assert b["map_constant"] == "MAP_KEVLAR_TOWN_POKEMON_CENTER"


def test_beat_markers_missing_observed_dir_degrades_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry_state = mvc._output_base() / "uranium-build" / "porymap" / "map_constants.json"
    if not registry_state.is_file():
        pytest.skip(f"{registry_state} not generated yet")

    # Point _output_base() at an empty tmp dir that mirrors the real porymap
    # registry state but has no playtest/observed_beats/ directory at all.
    fake_output = tmp_path / "output"
    porymap_dir = fake_output / "uranium-build" / "porymap"
    porymap_dir.mkdir(parents=True)
    (porymap_dir / "map_constants.json").write_text(
        registry_state.read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setattr(mvc, "_output_base", lambda: fake_output)

    result = mve.beat_markers(KEVLAR_CENTER_MAP_ID)

    assert result["observed"] == []
    assert any("observed-beats directory" in n for n in result["notes"])
    # No exception, and declared beats still resolve since the registry copy is intact.
    assert isinstance(result["declared"], list)


def test_beat_markers_missing_registry_state_degrades_gracefully(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mvc, "_output_base", lambda: tmp_path / "nonexistent_output")

    result = mve.beat_markers(KEVLAR_CENTER_MAP_ID)

    assert result["declared"] == []
    assert isinstance(result["notes"], list) and result["notes"]


# ---------------------------------------------------------------------------
# beat_markers — planned (slice 3)
# ---------------------------------------------------------------------------

_ROUTE_MAP_A = 501
_ROUTE_MAP_B = 502


def _two_map_plan(chapter_id: str = "CH99") -> RoutePlan:
    """A synthetic 3-node route plan whose one segment crosses two maps
    (entry on map A, group+exit on map B), with a foreign-trigger crossing
    on map B, followed by a single-map segment map-B -> exit."""
    nodes = (
        RouteNode(index=0, kind="entry", map_id=_ROUTE_MAP_A, cell=(0, 0)),
        RouteNode(
            index=1, kind="group", map_id=_ROUTE_MAP_B, cell=(1, 1),
            group="mawuli", beats=("beat1",),
        ),
        RouteNode(index=2, kind="exit", map_id=_ROUTE_MAP_B, cell=(2, 2)),
    )
    seg0 = RouteSegment(
        from_index=0,
        to_index=1,
        legs=(
            RouteLeg(map_id=_ROUTE_MAP_A, tiles=((0, 0), (1, 0))),
            RouteLeg(map_id=_ROUTE_MAP_B, tiles=((0, 1), (1, 1))),
        ),
        tile_count=4,
        crossed_foreign_triggers=(
            TriggerCrossing(
                map_id=_ROUTE_MAP_B, cell=(1, 1), script="EventScript_Foo",
                certainty="certain", declared=False,
            ),
        ),
    )
    seg1 = RouteSegment(
        from_index=1,
        to_index=2,
        legs=(RouteLeg(map_id=_ROUTE_MAP_B, tiles=((1, 1), (2, 2))),),
        tile_count=2,
    )
    return RoutePlan(
        chapter_id=chapter_id,
        chapter_module="passage_test",
        nodes=nodes,
        segments=(seg0, seg1),
        precedence=(),
        tile_cost=6,
        solver_method="test-solver",
    )


def test_beat_markers_planned_key_present_no_routes_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mvc, "_repo_root", lambda: tmp_path)

    result = mve.beat_markers(_ROUTE_MAP_A)

    assert result["planned"] == []
    assert any("planned tiles unavailable" in n for n in result["notes"])
    # declared/observed still work (unaffected by the repo-root override).
    assert isinstance(result["declared"], list)
    assert isinstance(result["observed"], list)


def test_beat_markers_planned_from_valid_route_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mvc, "_repo_root", lambda: tmp_path)
    routes_dir = tmp_path / "reference" / "routes"
    write_plan(_two_map_plan(), routes_dir / "CH99.route.json")

    result_a = mve.beat_markers(_ROUTE_MAP_A)
    result_b = mve.beat_markers(_ROUTE_MAP_B)

    # Map A only appears in segment 0 (the entry -> group leg).
    assert len(result_a["planned"]) == 1
    item_a = result_a["planned"][0]
    assert item_a["chapter"] == "CH99"
    assert item_a["segment"] == 0
    assert item_a["from_node"] == "entry"
    assert item_a["to_node"] == "mawuli"
    assert item_a["tiles"] == [[0, 0], [1, 0]]
    assert item_a["crossings"] == []

    # Map B appears in both segments: one item per segment it's touched by.
    assert len(result_b["planned"]) == 2
    seg0_b = next(i for i in result_b["planned"] if i["segment"] == 0)
    seg1_b = next(i for i in result_b["planned"] if i["segment"] == 1)
    assert seg0_b["from_node"] == "entry"
    assert seg0_b["to_node"] == "mawuli"
    assert seg0_b["tiles"] == [[0, 1], [1, 1]]
    assert seg0_b["crossings"] == [
        {"x": 1, "y": 1, "script": "EventScript_Foo", "certainty": "certain", "declared": False}
    ]
    assert seg1_b["from_node"] == "mawuli"
    assert seg1_b["to_node"] == "exit"
    assert seg1_b["tiles"] == [[1, 1], [2, 2]]
    assert seg1_b["crossings"] == []


def test_beat_markers_planned_skips_malformed_route_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mvc, "_repo_root", lambda: tmp_path)
    routes_dir = tmp_path / "reference" / "routes"
    write_plan(_two_map_plan("CH99"), routes_dir / "CH99.route.json")
    (routes_dir / "CH98.route.json").write_text("{ not valid json", encoding="utf-8")

    result = mve.beat_markers(_ROUTE_MAP_A)

    assert len(result["planned"]) == 1
    assert result["planned"][0]["chapter"] == "CH99"
    assert any(
        "CH98.route.json" in n and "skipped" in n for n in result["notes"]
    )


# ---------------------------------------------------------------------------
# beat_markers — walked / contradictions / conformance (Q13 slice 4, schema v2)
# ---------------------------------------------------------------------------

# Arbitrary ids, disjoint from any real minted map: only need to round-trip
# through the fake registry/group-table these tests install.
_TARGET_MAP_ID = 9001
_OTHER_MAP_ID = 9002


def _write_observed_beats(tmp_path: Path, chapter: str, payload: dict) -> None:
    path = tmp_path / "output" / "playtest" / "observed_beats" / f"{chapter}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _patch_registry(monkeypatch: pytest.MonkeyPatch, by_const: dict[str, int]) -> None:
    """Bypass the real MapConstantRegistry state file: beat_markers only
    ever consumes the (by_id, by_const) tuple `_get_map_registry` returns."""
    monkeypatch.setattr(mve, "_get_map_registry", lambda: ({}, by_const))


def _patch_group_table(
    monkeypatch: pytest.MonkeyPatch, table: dict[tuple[int, int], str] | None = None
) -> None:
    monkeypatch.setattr(mve, "_get_map_group_table", lambda: (table or {}, []))


def _setup_output_and_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mvc, "_output_base", lambda: tmp_path / "output")
    monkeypatch.setattr(mvc, "_repo_root", lambda: tmp_path)


def test_beat_markers_walked_filters_tiles_and_carries_divergence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_output_and_repo(tmp_path, monkeypatch)
    _patch_registry(monkeypatch, {"MAP_TARGET": _TARGET_MAP_ID})
    _patch_group_table(monkeypatch)

    payload = {
        "version": 2,
        "chapter": "ch_test",
        "beats": [
            {
                "beat": "b1", "status": "pass", "enter": None, "exit": None,
                "path": [
                    {"map_id": _TARGET_MAP_ID, "map_group": 1, "map_num": 1, "x": 1, "y": 2},
                    {"map_id": _TARGET_MAP_ID, "map_group": 1, "map_num": 1, "x": 2, "y": 2},
                    {"map_id": _OTHER_MAP_ID, "map_group": 1, "map_num": 1, "x": 9, "y": 9},
                ],
                "divergence": {
                    "beat": "b1", "compared": True, "steps": 3, "unresolved": 0,
                    "off_plan": [
                        {"map_id": _TARGET_MAP_ID, "cell": [2, 2], "step": 1,
                         "kind": "off_plan", "triggers": []},
                        {"map_id": _OTHER_MAP_ID, "cell": [9, 9], "step": 2,
                         "kind": "off_plan", "triggers": []},
                    ],
                    "trigger_violations": [
                        {"map_id": _TARGET_MAP_ID, "cell": [1, 2], "step": 0, "kind": "trigger",
                         "triggers": [{"script": "EventScript_Foo", "kind": "warp",
                                       "certainty": "certain", "detail": "d"}]},
                    ],
                    "note": "", "failed": True,
                },
                "frame_rule": None, "refused_claim": None,
            },
            {
                # empty path -- must not appear in the walked layer at all
                "beat": "b2", "status": "skipped", "enter": None, "exit": None,
                "path": [], "divergence": None, "frame_rule": None, "refused_claim": None,
            },
        ],
        "contradictions": [
            {"kind": "graph_vs_live_collision", "beat": "b1", "detail": "d1",
             "model": "m", "measurement": "meas", "assumption": "a",
             "map_id": _TARGET_MAP_ID, "cell": [1, 2], "count": 2, "status": "carried"},
            {"kind": "walk_off_plan", "beat": "b1", "detail": "d2",
             "model": "m", "measurement": "meas", "assumption": "a",
             "map_id": _OTHER_MAP_ID, "cell": [9, 9], "count": 1, "status": "carried"},
            {"kind": "unresolved_map", "beat": "b1", "detail": "d3",
             "model": "m", "measurement": "meas", "assumption": "a",
             "map_id": None, "cell": None, "count": 1, "status": "carried"},
        ],
        "conformance": {"oracle": "offline_graph", "walkability_disagreements": 2,
                         "distinct_cells": 1, "by_map": {str(_TARGET_MAP_ID): 2}},
    }
    _write_observed_beats(tmp_path, "ch_test", payload)

    result = mve.beat_markers(_TARGET_MAP_ID)

    assert len(result["walked"]) == 1
    w = result["walked"][0]
    assert w["chapter"] == "ch_test"
    assert w["beat"] == "b1"
    assert w["status"] == "pass"
    assert w["tiles"] == [[1, 2], [2, 2]]
    assert w["off_plan"] == [[2, 2]]
    assert w["violations"] == [{"x": 1, "y": 2, "scripts": ["EventScript_Foo"]}]
    assert w["compared"] is True

    kinds = {c["kind"] for c in result["contradictions"]}
    assert kinds == {"graph_vs_live_collision", "unresolved_map"}, (
        "the OTHER_MAP_ID-scoped contradiction must be filtered out, but the "
        "map_id=null one must survive"
    )
    scope_by_kind = {c["kind"]: c["scope"] for c in result["contradictions"]}
    assert scope_by_kind["graph_vs_live_collision"] == "map"
    assert scope_by_kind["unresolved_map"] == "unscoped"
    for c in result["contradictions"]:
        assert c["chapter"] == "ch_test"

    assert result["conformance"] == {"ch_test": payload["conformance"]}


def test_beat_markers_v1_artifact_degrades_walked_and_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_output_and_repo(tmp_path, monkeypatch)
    _patch_registry(monkeypatch, {"MAP_TARGET": _TARGET_MAP_ID})
    _patch_group_table(monkeypatch)

    payload = {
        # no "version" key at all -- the actual shape old runs left on disk
        "chapter": "ch_old",
        "beats": [{"beat": "b1", "status": "pass", "enter": None, "exit": None}],
    }
    _write_observed_beats(tmp_path, "ch_old", payload)

    result = mve.beat_markers(_TARGET_MAP_ID)

    assert result["walked"] == []
    assert result["contradictions"] == []
    assert result["conformance"] == {}
    assert any("predates schema v2" in n for n in result["notes"])


def test_beat_markers_walked_null_map_id_falls_back_to_group_num(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_output_and_repo(tmp_path, monkeypatch)
    _patch_registry(monkeypatch, {"MAP_TARGET": _TARGET_MAP_ID})
    _patch_group_table(monkeypatch, {(3, 4): "MAP_TARGET"})

    payload = {
        "version": 2,
        "beats": [{
            "beat": "b1", "status": "pass", "enter": None, "exit": None,
            "path": [{"map_id": None, "map_group": 3, "map_num": 4, "x": 5, "y": 6}],
            "divergence": None,
        }],
        "contradictions": [], "conformance": {},
    }
    _write_observed_beats(tmp_path, "ch_fallback", payload)

    result = mve.beat_markers(_TARGET_MAP_ID)

    assert len(result["walked"]) == 1
    assert result["walked"][0]["tiles"] == [[5, 6]]


def test_beat_markers_walked_unresolved_tile_dropped_with_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_output_and_repo(tmp_path, monkeypatch)
    _patch_registry(monkeypatch, {"MAP_TARGET": _TARGET_MAP_ID})
    _patch_group_table(monkeypatch)  # empty table -> the fallback lookup fails

    payload = {
        "version": 2,
        "beats": [{
            "beat": "b1", "status": "pass", "enter": None, "exit": None,
            "path": [{"map_id": None, "map_group": 3, "map_num": 4, "x": 5, "y": 6}],
            "divergence": None,
        }],
        "contradictions": [], "conformance": {},
    }
    _write_observed_beats(tmp_path, "ch_unresolved", payload)

    result = mve.beat_markers(_TARGET_MAP_ID)

    assert result["walked"] == []
    assert any("unresolved map identity" in n for n in result["notes"])


def test_beat_markers_corrupt_observed_file_degrades_to_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_output_and_repo(tmp_path, monkeypatch)
    _patch_registry(monkeypatch, {"MAP_TARGET": _TARGET_MAP_ID})
    _patch_group_table(monkeypatch)

    bad_path = tmp_path / "output" / "playtest" / "observed_beats" / "ch_bad.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("{ not valid json", encoding="utf-8")

    result = mve.beat_markers(_TARGET_MAP_ID)

    assert result["walked"] == []
    assert result["contradictions"] == []
    assert result["conformance"] == {}
    assert any("unreadable" in n for n in result["notes"])
