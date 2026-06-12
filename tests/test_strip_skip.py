"""Tests for orchestrator-side STRIP skip.

Design source: FABLES_DECISIONS.md Suggestion 2 — orchestrator-side STRIP skip.

Covers:
- _load_strip_list() pure-function behavior (absent file, round-trip parsing)
- Orchestrator.convert_common_events() strip branch: stub emission, name mismatch,
  missing stub_message, compile-gate failure, ledger idempotence, no queue entries
- Orchestrator.convert_map() map-event skip
- Mixed pass (strip CE + normal CE in one convert_common_events run)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import orchestrator as orch
from rpg2gba.conversion_agent import poryscript
from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REPO_ROOT / "reference"

TANDOR_STUB_MSG = "The Tandor Network is currently unavailable."


# ---------------------------------------------------------------------------
# Harness helpers (mirror test_label_uniquing.py idioms)
# ---------------------------------------------------------------------------


class MockBackend(ConversionBackend):
    def __init__(self, results: list[ConversionResult], system_prompt: str = "") -> None:
        self.results = results
        self.system_prompt = system_prompt  # drives memo fingerprint (dedup C)
        self.calls = 0

    def convert_event(self, event_json, registry_state, prompt) -> ConversionResult:
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return r


def _fake_compile(script: str) -> poryscript.CompileResult:
    """Accept scripts containing 'GOOD'; reject everything else."""
    return poryscript.CompileResult(ok=("GOOD" in script), stdout="", stderr="syntax error")


def _compile_stub_ok(script: str) -> poryscript.CompileResult:
    """Accept 'GOOD' (normal events) or 'STRIPPED' (stubs); reject otherwise."""
    ok = ("GOOD" in script) or ("STRIPPED" in script)
    return poryscript.CompileResult(ok=ok, stdout="", stderr="syntax error")


def _compile_reject_all(script: str) -> poryscript.CompileResult:
    """Always reject — drives the compile-gate RuntimeError in test_compile_gate_failure."""
    return poryscript.CompileResult(ok=False, stdout="", stderr="compile failed")


def _write_common_events(out_dir: Path, ces: list[dict]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "common_events.json"
    path.write_text(json.dumps(ces), encoding="utf-8")
    return path


def _write_map(maps_dir: Path, map_id: int, events: list[dict]) -> Path:
    maps_dir.mkdir(parents=True, exist_ok=True)
    m = {
        "map_id": map_id,
        "tileset_id": 1,
        "width": 1,
        "height": 1,
        "tiles": {"xsize": 1, "ysize": 1, "zsize": 1, "data": [0]},
        "events": events,
    }
    path = maps_dir / f"Map{map_id:03d}.json"
    path.write_text(json.dumps(m), encoding="utf-8")
    return path


def _make_ce(ce_id: int, name: str) -> dict:
    """Minimal common-event fixture with one real command (code 101 != 0)."""
    return {
        "id": ce_id,
        "name": name,
        "trigger": 0,
        "switch_id": 1,
        "list": [{"code": 101, "parameters": ["hi"]}],
    }


def _orchestrator(
    tmp_path: Path,
    backend: ConversionBackend,
    compile_fn=_fake_compile,
) -> orch.Orchestrator:
    return orch.Orchestrator(
        backend,
        FlagRegistry(),
        tmp_path / "out",
        reference_dir=REFERENCE,
        compile_fn=compile_fn,
    )


# ---------------------------------------------------------------------------
# Test 1: Stub emission — backend not called; .pory, ledger, and .done correct
# ---------------------------------------------------------------------------


def test_stub_emission(tmp_path: Path) -> None:
    """CE 4 (GTS/WT) from the real strip list: stub emitted, no backend spawn."""
    backend = MockBackend([])
    o = _orchestrator(tmp_path, backend, compile_fn=_compile_stub_ok)
    ce_path = _write_common_events(tmp_path, [_make_ce(4, "GTS/WT")])

    o.convert_common_events(ce_path)

    assert backend.calls == 0

    pory = (tmp_path / "out" / "scripts" / "CommonEvents.pory").read_text(encoding="utf-8")
    assert "script CommonEvent_004 {" in pory
    assert "# STRIPPED:" in pory
    assert TANDOR_STUB_MSG in pory

    ledger_path = tmp_path / "out" / "checkpoints" / "CommonEvents.blocks.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert "4" in ledger
    assert "CommonEvent_004" in (ledger["4"] or "")

    done_path = tmp_path / "out" / "checkpoints" / "CommonEvents.done"
    assert done_path.exists()


# ---------------------------------------------------------------------------
# Test 2: Name mismatch aborts
# ---------------------------------------------------------------------------


def test_name_mismatch_aborts(tmp_path: Path) -> None:
    """CE 4 given wrong name raises RuntimeError mentioning 'expects name'."""
    backend = MockBackend([])
    o = _orchestrator(tmp_path, backend, compile_fn=_compile_stub_ok)
    ce_path = _write_common_events(tmp_path, [_make_ce(4, "Something Else")])

    with pytest.raises(RuntimeError, match="expects name"):
        o.convert_common_events(ce_path)


# ---------------------------------------------------------------------------
# Test 3: Missing stub_message aborts
# ---------------------------------------------------------------------------


def test_missing_stub_message_aborts(tmp_path: Path) -> None:
    """Strip entry with no stub_message raises RuntimeError."""
    backend = MockBackend([])
    o = _orchestrator(tmp_path, backend, compile_fn=_compile_stub_ok)
    # CE 9 is not in the real strip list; inject a minimal entry without stub_message
    o._strip_ces = {9: {"id": 9, "expect_name": "X"}}
    ce_path = _write_common_events(tmp_path, [_make_ce(9, "X")])

    with pytest.raises(RuntimeError):
        o.convert_common_events(ce_path)


# ---------------------------------------------------------------------------
# Test 4: Compile-gate failure aborts; nothing queued
# ---------------------------------------------------------------------------


def test_compile_gate_failure_aborts(tmp_path: Path) -> None:
    """Stub that fails the compile gate raises RuntimeError; unhandled.jsonl stays empty."""
    backend = MockBackend([])
    o = _orchestrator(tmp_path, backend, compile_fn=_compile_reject_all)
    ce_path = _write_common_events(tmp_path, [_make_ce(4, "GTS/WT")])

    with pytest.raises(RuntimeError):
        o.convert_common_events(ce_path)

    unhandled = tmp_path / "out" / "unhandled.jsonl"
    assert not unhandled.exists() or unhandled.read_text(encoding="utf-8").strip() == ""


# ---------------------------------------------------------------------------
# Test 5: Absent file
# ---------------------------------------------------------------------------


def test_load_strip_list_absent_file(tmp_path: Path) -> None:
    """_load_strip_list on a directory with no strip_list.json returns empty structures."""
    ces, map_events = orch._load_strip_list(tmp_path)
    assert ces == {}
    assert map_events == set()


# ---------------------------------------------------------------------------
# Test 6: Loader parsing
# ---------------------------------------------------------------------------


def test_load_strip_list_parsing(tmp_path: Path) -> None:
    """_load_strip_list parses CEs keyed by int and map_events as a set of int tuples."""
    data = {
        "common_events": [
            {"id": 7, "expect_name": "TestCE", "stub_message": "Unavailable."}
        ],
        "map_events": [[3, 5]],
    }
    (tmp_path / "strip_list.json").write_text(json.dumps(data), encoding="utf-8")

    ces, map_events = orch._load_strip_list(tmp_path)

    assert 7 in ces
    assert ces[7]["expect_name"] == "TestCE"
    assert (3, 5) in map_events


# ---------------------------------------------------------------------------
# Test 7: Ledger idempotence
# ---------------------------------------------------------------------------


def test_ledger_idempotence(tmp_path: Path) -> None:
    """Second convert_common_events call is skipped by checkpoint; .pory byte-identical."""
    backend = MockBackend([])
    o = _orchestrator(tmp_path, backend, compile_fn=_compile_stub_ok)
    ce_path = _write_common_events(tmp_path, [_make_ce(4, "GTS/WT")])

    o.convert_common_events(ce_path)
    pory_first = (tmp_path / "out" / "scripts" / "CommonEvents.pory").read_text(encoding="utf-8")
    calls_after_first = backend.calls

    o.convert_common_events(ce_path)  # second run — .done checkpoint present
    pory_second = (tmp_path / "out" / "scripts" / "CommonEvents.pory").read_text(encoding="utf-8")

    assert backend.calls == calls_after_first  # no additional backend calls
    assert pory_second == pory_first  # byte-identical


# ---------------------------------------------------------------------------
# Test 8: Map-event skip
# ---------------------------------------------------------------------------


def test_map_event_skip(tmp_path: Path) -> None:
    """(map_id, event_id) in _strip_map_events is skipped; the other event converts normally."""
    ev1 = {
        "id": 1, "name": "online_event", "x": 0, "y": 0,
        "pages": [{"list": [{"code": 101, "parameters": ["hi"]}]}],
    }
    ev2 = {
        "id": 2, "name": "normal_event", "x": 1, "y": 0,
        "pages": [{"list": [{"code": 101, "parameters": ["hello"]}]}],
    }
    backend = MockBackend([
        ConversionResult(script="script Map003_normal_event_Page1 { GOOD }")
    ])
    o = _orchestrator(tmp_path, backend, compile_fn=_fake_compile)
    o._strip_map_events = {(3, 1)}

    o.convert_map(_write_map(tmp_path / "out" / "maps", 3, [ev1, ev2]))

    assert backend.calls == 1  # only event 2 spawned

    pory = (tmp_path / "out" / "scripts" / "Map003.pory").read_text(encoding="utf-8")
    assert "EV002" in pory  # event 2 block present (label qualified with EV002)

    unhandled = tmp_path / "out" / "unhandled.jsonl"
    if unhandled.exists():
        lines = [
            json.loads(ln)
            for ln in unhandled.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        # No queue entry for the skipped event 1 on map 3
        assert all(not (e.get("map_id") == 3 and e.get("event_id") == 1) for e in lines)


# ---------------------------------------------------------------------------
# Test 9: No queue entries from stubs
# ---------------------------------------------------------------------------


def test_no_queue_entry_from_stub(tmp_path: Path) -> None:
    """Stub emission for CE 4 must not generate any unhandled.jsonl entry."""
    backend = MockBackend([])
    o = _orchestrator(tmp_path, backend, compile_fn=_compile_stub_ok)
    ce_path = _write_common_events(tmp_path, [_make_ce(4, "GTS/WT")])

    o.convert_common_events(ce_path)

    unhandled = tmp_path / "out" / "unhandled.jsonl"
    if unhandled.exists():
        lines = [
            json.loads(ln)
            for ln in unhandled.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        assert all(e.get("common_event_id") != 4 for e in lines)


# ---------------------------------------------------------------------------
# Test 10: Mixed pass — strip CE and normal CE in one run
# ---------------------------------------------------------------------------


def test_mixed_pass_strip_and_normal(tmp_path: Path) -> None:
    """CE 4 (strip) and CE 104 (normal) in one pass: one backend call, both blocks in .pory."""
    backend = MockBackend([
        ConversionResult(script="script CommonEvent_104 { GOOD }")
    ])
    o = _orchestrator(tmp_path, backend, compile_fn=_compile_stub_ok)
    ces = [
        _make_ce(4, "GTS/WT"),   # strip-listed (id avoids 5/6 which are also real)
        _make_ce(104, "Other"),  # normal CE — id safely outside 4/5/6
    ]
    ce_path = _write_common_events(tmp_path, ces)

    o.convert_common_events(ce_path)

    assert backend.calls == 1  # only CE 104 spawned; CE 4 is a zero-spawn stub

    pory = (tmp_path / "out" / "scripts" / "CommonEvents.pory").read_text(encoding="utf-8")
    assert "CommonEvent_004" in pory  # stub block present
    assert "# STRIPPED:" in pory
    assert "CommonEvent_104" in pory  # normal CE block present
