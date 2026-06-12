"""Tests for `run_bulk --skip-lane` — the human/Opus spend partition.

Synthetic maps + fake compiler + MockBackend, no live binaries (mirrors
test_strip_skip.py). Guards: the skip fires only for genuine-spawn lane events (not
deterministic-claimable ones), leaves the map .partial, and a later no-skip pass
promotes it to .done.
"""
from __future__ import annotations

import json
from pathlib import Path

from rpg2gba.conversion_agent import orchestrator as orch
from rpg2gba.conversion_agent import poryscript
from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

REFERENCE = Path(__file__).resolve().parents[1] / "reference"


class MockBackend(ConversionBackend):
    def __init__(self, results: list[ConversionResult], system_prompt: str = "") -> None:
        self.results = results
        self.system_prompt = system_prompt  # drives the memo fingerprint
        self.calls = 0

    def convert_event(self, event_json, registry_state, prompt) -> ConversionResult:
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return r


def _compile_good(script: str) -> poryscript.CompileResult:
    return poryscript.CompileResult(ok=("GOOD" in script), stdout="", stderr="err")


def _compile_ok(script: str) -> poryscript.CompileResult:
    return poryscript.CompileResult(ok=True, stdout="", stderr="")


def _orch(tmp_path: Path, backend, *, skip_lane: bool, compile_fn=_compile_good):
    return orch.Orchestrator(
        backend,
        FlagRegistry(),
        tmp_path / "out",
        reference_dir=REFERENCE,
        compile_fn=compile_fn,
        skip_lane=skip_lane,
    )


def _page(codes: list[int]) -> dict:
    def params(c: int):
        if c == 123:
            return ["A", 0]
        if c in (101, 401):
            return ["hi"]
        if c == 355:
            return ["pbFoo"]
        return []
    cmds = [{"code": c, "indent": 0, "parameters": params(c)} for c in codes]
    return {"condition": {}, "trigger": 0, "list": cmds}


def _event(eid: int, codes: list[int]) -> dict:
    return {"id": eid, "name": f"EV{eid:03d}", "x": 0, "y": 0, "pages": [_page(codes)]}


def _write_map(maps_dir: Path, map_id: int, events: list[dict]) -> Path:
    maps_dir.mkdir(parents=True, exist_ok=True)
    tiles = {"xsize": 1, "ysize": 1, "zsize": 1, "data": [0]}
    m = {"map_id": map_id, "tiles": tiles, "events": events}
    path = maps_dir / f"Map{map_id:03d}.json"
    path.write_text(json.dumps(m), encoding="utf-8")
    return path


# Codes: [101,111,411,412] = in-lane branch, NOT deterministic -> reaches the skip.
# [355] = non-lane (script call) -> Opus converts. [101,123] = in-lane AND deterministic.
_LANE_BRANCH = [101, 111, 411, 412]
_NONLANE = [355]


def test_skip_leaves_hole_and_partial(tmp_path):
    maps = tmp_path / "out" / "maps"
    map_path = _write_map(maps, 1, [_event(1, _LANE_BRANCH), _event(2, _NONLANE)])
    backend = MockBackend([ConversionResult(script="script EV2 { GOOD }")])
    o = _orch(tmp_path, backend, skip_lane=True)

    o.convert_map(map_path)

    assert backend.calls == 1  # only the non-lane event spawned
    assert o._partial("Map001").exists()
    assert not o._checkpoint("Map001").exists()
    pory = (o.scripts_dir / "Map001.pory").read_text()
    assert "EV2" in pory and "EV1" not in pory  # lane event omitted


def test_deterministic_lane_event_not_skipped(tmp_path):
    # A pure-dialogue+self-switch event is in-lane AND deterministic — it must be converted
    # for free, never skipped (the skip sits after the deterministic check).
    maps = tmp_path / "out" / "maps"
    map_path = _write_map(maps, 1, [_event(1, [101, 123])])
    backend = MockBackend([])  # must never be called
    o = _orch(tmp_path, backend, skip_lane=True, compile_fn=_compile_ok)

    o.convert_map(map_path)

    assert backend.calls == 0  # deterministic claimed it, no spawn
    assert o._checkpoint("Map001").exists()  # fully done, not partial
    assert not o._partial("Map001").exists()


def test_partial_promotes_to_done_on_noskip_pass(tmp_path):
    maps = tmp_path / "out" / "maps"
    map_path = _write_map(maps, 1, [_event(1, _LANE_BRANCH), _event(2, _NONLANE)])

    # Pass 1: --skip-lane → ev2 converted, ev1 held, map .partial.
    b1 = MockBackend([ConversionResult(script="script EV2 { GOOD }")])
    o1 = _orch(tmp_path, b1, skip_lane=True)
    o1.convert_map(map_path)
    assert o1._partial("Map001").exists()

    # Pass 2: plain run (no skip) → ev2 is a free memo hit, ev1 spawns; map completes.
    b2 = MockBackend([ConversionResult(script="script EV1 { GOOD }")])
    o2 = _orch(tmp_path, b2, skip_lane=False)
    o2.convert_map(map_path)

    assert b2.calls == 1  # only ev1; ev2 reused from memo
    assert o2._checkpoint("Map001").exists()
    assert not o2._partial("Map001").exists()  # marker removed on promotion
    pory = (o2.scripts_dir / "Map001.pory").read_text()
    assert "EV1" in pory and "EV2" in pory  # both assembled


def test_nonlane_only_map_completes_under_skip_lane(tmp_path):
    maps = tmp_path / "out" / "maps"
    map_path = _write_map(maps, 1, [_event(1, _NONLANE)])
    backend = MockBackend([ConversionResult(script="script EV1 { GOOD }")])
    o = _orch(tmp_path, backend, skip_lane=True)

    o.convert_map(map_path)

    assert backend.calls == 1
    assert o._checkpoint("Map001").exists()
    assert not o._partial("Map001").exists()


def test_run_human_offers_lane_events_from_partial_map(tmp_path):
    from scripts.run_human import _build_queue

    maps = tmp_path / "out" / "maps"
    map_path = _write_map(maps, 1, [_event(1, _LANE_BRANCH), _event(2, _NONLANE)])
    backend = MockBackend([ConversionResult(script="script EV2 { GOOD }")])
    o = _orch(tmp_path, backend, skip_lane=True)
    o.convert_map(map_path)
    assert o._partial("Map001").exists()

    queue = _build_queue(o, maps, only_map=None)
    offered = {(m, ev["id"]) for _score, m, ev in queue}
    assert (1, 1) in offered  # the held lane event is offered to the operator
    assert (1, 2) not in offered  # the non-lane event is not (Opus did it)
    _ = map_path  # silence unused
