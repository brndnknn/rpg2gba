"""Tests for scripts/map_graph.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable (map_graph uses sys.path.insert itself, but we
# need to import it first).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import map_graph  # noqa: E402


def _clear_caches() -> None:
    map_graph._load_map_infos.cache_clear()
    map_graph._load_overrides.cache_clear()
    map_graph._map_id_universe.cache_clear()


# ---------------------------------------------------------------------------
# Helper: patch loaders via monkeypatch
# ---------------------------------------------------------------------------


def _patch_loaders(
    monkeypatch: pytest.MonkeyPatch,
    *,
    universe: frozenset[int],
    infos: dict[str, dict],
    overrides: dict[str, dict],
    map_jsons: dict[int, dict] | None = None,
) -> None:
    _clear_caches()
    monkeypatch.setattr(map_graph, "_load_map_infos", lambda: infos)
    monkeypatch.setattr(map_graph, "_load_overrides", lambda: overrides)
    monkeypatch.setattr(map_graph, "_map_id_universe", lambda: universe)
    if map_jsons is not None:
        def _fake_load_json(mid: int) -> dict:
            if mid not in map_jsons:
                raise FileNotFoundError(f"No fake JSON for map {mid}")
            return map_jsons[mid]
        monkeypatch.setattr(map_graph, "_load_map_json", _fake_load_json)
    # Also clear the load_map_names cache if it was cached from real data
    # (load_map_names is not lru_cached but calls the cached helpers above)


# ---------------------------------------------------------------------------
# 1. extract_warp_targets
# ---------------------------------------------------------------------------


def _make_event(commands: list[dict]) -> dict:
    return {"id": 1, "name": "EV", "x": 0, "y": 0, "pages": [{"list": commands}]}


def _cmd(code: int, params: list) -> dict:
    return {"code": code, "indent": 0, "parameters": params}


def test_extract_warp_targets_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Literal warp included; variable-driven skipped; self-warp excluded; non-201 ignored."""
    source_map = 10

    events = [
        _make_event([
            _cmd(201, [0, 50, 5, 3, 2, 0]),   # literal to 50 → INCLUDE
            _cmd(201, [1, 99, 0, 0, 0, 0]),    # variable-driven → SKIP
            _cmd(201, [0, source_map, 0, 0, 0, 0]),  # self-warp → EXCLUDE
            _cmd(106, [20]),                   # non-201 → IGNORE
            _cmd(201, [0, 50, 2, 1, 0, 0]),   # duplicate literal 50 → deduplicated
        ]),
        _make_event([
            {"code": 201, "indent": 0},       # malformed: no 'parameters' key → SKIP
            {"code": 201, "indent": 0, "parameters": []},  # too short → SKIP
            {"code": 201, "indent": 0, "parameters": [0, "bad"]},  # non-int dest → SKIP
        ]),
    ]

    fake_doc = {"events": events}
    _patch_loaders(
        monkeypatch,
        universe=frozenset({source_map, 50}),
        infos={},
        overrides={},
        map_jsons={source_map: fake_doc},
    )

    result = map_graph.extract_warp_targets(source_map)
    assert result == [50], f"expected [50], got {result}"


def test_extract_warp_targets_empty_events(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_doc: dict = {"events": []}
    _patch_loaders(
        monkeypatch,
        universe=frozenset({1}),
        infos={},
        overrides={},
        map_jsons={1: fake_doc},
    )
    assert map_graph.extract_warp_targets(1) == []


def test_extract_warp_targets_missing_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """Should return [] rather than raising when file is absent."""
    _patch_loaders(
        monkeypatch,
        universe=frozenset({99}),
        infos={},
        overrides={},
        map_jsons={},  # 99 absent → FileNotFoundError swallowed
    )
    assert map_graph.extract_warp_targets(99) == []


def test_extract_warp_targets_multiple_sorted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multiple distinct destinations returned sorted ascending."""
    events = [
        _make_event([
            _cmd(201, [0, 30, 0, 0, 0, 0]),
            _cmd(201, [0, 10, 0, 0, 0, 0]),
            _cmd(201, [0, 20, 0, 0, 0, 0]),
            _cmd(201, [0, 10, 0, 0, 0, 0]),  # duplicate
        ]),
    ]
    _patch_loaders(
        monkeypatch,
        universe=frozenset({5}),
        infos={},
        overrides={},
        map_jsons={5: {"events": events}},
    )
    assert map_graph.extract_warp_targets(5) == [10, 20, 30]


# ---------------------------------------------------------------------------
# 2. Name precedence
# ---------------------------------------------------------------------------


def test_name_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loaders(
        monkeypatch,
        universe=frozenset({32}),
        infos={"32": {"name": "InfoName"}},
        overrides={"32": {"display_name": "OverrideName", "evidence": "test"}},
    )
    names = map_graph.load_map_names()
    assert names[32] == "OverrideName"


def test_name_infos_used_when_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loaders(
        monkeypatch,
        universe=frozenset({7}),
        infos={"7": {"name": "Comet Cave"}},
        overrides={},
    )
    names = map_graph.load_map_names()
    assert names[7] == "Comet Cave"


def test_name_fallback_when_neither(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loaders(
        monkeypatch,
        universe=frozenset({42}),
        infos={},
        overrides={},
    )
    names = map_graph.load_map_names()
    assert names[42] == "Map042"


def test_map_display_name_unknown_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loaders(
        monkeypatch,
        universe=frozenset(),
        infos={},
        overrides={},
    )
    assert map_graph.map_display_name(999) == "Map999"


# ---------------------------------------------------------------------------
# 3. build_index forest structure
# ---------------------------------------------------------------------------


def _flat_tree_ids(nodes: list[dict]) -> list:
    """Collect ids in DFS pre-order for easy comparison."""
    result = []
    for node in nodes:
        result.append(node["id"])
        result.extend(_flat_tree_ids(node["children"]))
    return result


def test_build_index_nesting(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Topology:
      32 (root) -> children 48, 49
      7  (root) -> child 96 -> child 10
      Plus: map 5 with parent_id pointing at non-existent map 999 => root
    """
    universe = frozenset({5, 7, 10, 32, 48, 49, 96})
    infos = {
        "5":  {"name": "Map5",  "parent_id": 999},  # non-existent parent -> root
        "7":  {"name": "Map7",  "parent_id": 0},    # explicit 0 -> root
        "10": {"name": "Map10", "parent_id": 96},
        "32": {"name": "Moki Town", "parent_id": 0},
        "48": {"name": "Map48", "parent_id": 32},
        "49": {"name": "Map49", "parent_id": 32},
        "96": {"name": "Map96", "parent_id": 7},
    }
    _patch_loaders(monkeypatch, universe=universe, infos=infos, overrides={})

    idx = map_graph.build_index()

    # maps list is flat and sorted
    map_ids = [m["id"] for m in idx["maps"]]
    assert map_ids == sorted(universe)

    # tree roots: 5, 7, 32
    root_ids = [n["id"] for n in idx["tree"]]
    assert root_ids == [5, 7, 32], f"roots: {root_ids}"

    # map 32 has children 48, 49 sorted
    node32 = next(n for n in idx["tree"] if n["id"] == 32)
    assert [c["id"] for c in node32["children"]] == [48, 49]
    # 48 and 49 are leaves
    assert node32["children"][0]["children"] == []
    assert node32["children"][1]["children"] == []

    # map 7 -> 96 -> 10
    node7 = next(n for n in idx["tree"] if n["id"] == 7)
    assert [c["id"] for c in node7["children"]] == [96]
    node96 = node7["children"][0]
    assert [c["id"] for c in node96["children"]] == [10]


def test_build_index_nonexistent_parent_is_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """A map whose parent_id points to a missing JSON file becomes a root."""
    universe = frozenset({5, 32})
    infos = {
        "5":  {"name": "Map5",  "parent_id": 999},  # 999 not in universe
        "32": {"name": "Moki",  "parent_id": 0},
    }
    _patch_loaders(monkeypatch, universe=universe, infos=infos, overrides={})
    idx = map_graph.build_index()
    root_ids = [n["id"] for n in idx["tree"]]
    assert 5 in root_ids
    assert 32 in root_ids


def test_build_index_cycle_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Maps in a mutual cycle should not cause infinite recursion; both become roots."""
    universe = frozenset({10, 20})
    infos = {
        "10": {"name": "A", "parent_id": 20},
        "20": {"name": "B", "parent_id": 10},
    }
    _patch_loaders(monkeypatch, universe=universe, infos=infos, overrides={})
    # Must not raise RecursionError
    idx = map_graph.build_index()
    # Both in roots (cycle broken)
    root_ids = [n["id"] for n in idx["tree"]]
    assert set(root_ids) == {10, 20}


def test_build_index_siblings_sorted(monkeypatch: pytest.MonkeyPatch) -> None:
    universe = frozenset({1, 5, 3, 4, 2})
    infos = {
        "1": {"name": "Root", "parent_id": 0},
        "5": {"name": "E", "parent_id": 1},
        "3": {"name": "C", "parent_id": 1},
        "4": {"name": "D", "parent_id": 1},
        "2": {"name": "B", "parent_id": 1},
    }
    _patch_loaders(monkeypatch, universe=universe, infos=infos, overrides={})
    idx = map_graph.build_index()
    node1 = next(n for n in idx["tree"] if n["id"] == 1)
    child_ids = [c["id"] for c in node1["children"]]
    assert child_ids == [2, 3, 4, 5]


# ---------------------------------------------------------------------------
# 4. map_relationships
# ---------------------------------------------------------------------------


def test_map_relationships_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    universe = frozenset({32, 48, 49, 55})
    infos = {
        "32": {"name": "Moki Town", "parent_id": 55},
        "48": {"name": "Map48", "parent_id": 32},
        "49": {"name": "Map49", "parent_id": 32},
        "55": {"name": "GAME", "parent_id": 0},
    }
    _patch_loaders(
        monkeypatch,
        universe=universe,
        infos=infos,
        overrides={},
        map_jsons={
            32: {"events": [_make_event([_cmd(201, [0, 49, 0, 0, 0, 0])])]},
        },
    )
    rel = map_graph.map_relationships(32)
    assert rel["id"] == 32
    assert rel["name"] == "Moki Town"
    assert rel["parent"] == {"id": 55, "name": "GAME"}
    child_ids = [c["id"] for c in rel["children"]]
    assert child_ids == [48, 49]
    warp_ids = [w["id"] for w in rel["warps"]]
    assert warp_ids == [49]
