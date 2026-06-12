"""Tests for F1 label-qualification (orchestrator._qualify_labels + convert_map duplicate guard).

F1 fix: script-block labels derived from the event name (Map{NNN}_{name}_Page{n}) collide
when RMXP reuses the same name across events on one map (e.g. ten events all named
"NuclearBoat").  The fix qualifies every ``Map{NNN}_`` token with the event id
(``Map{NNN}_EV{eee}_…``) before acceptance, making duplicates impossible by construction.
A per-map ``seen_labels`` guard in ``convert_map`` raises RuntimeError as a belt-and-
suspenders check — Poryscript's per-event compile gate can't see cross-event duplicates,
but the linker would fail.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import orchestrator as orch
from rpg2gba.conversion_agent import poryscript
from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_conversion_agent.py style)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REPO_ROOT / "reference"


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
    """Accept any script containing the sentinel 'GOOD'; reject everything else."""
    return poryscript.CompileResult(ok=("GOOD" in script), stdout="", stderr="syntax error")


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


def _orchestrator(tmp_path: Path, backend: ConversionBackend) -> orch.Orchestrator:
    return orch.Orchestrator(
        backend,
        FlagRegistry(),
        tmp_path / "out",
        reference_dir=REFERENCE,
        compile_fn=_fake_compile,
    )


# ---------------------------------------------------------------------------
# Test 1: same-named events get distinct labels
# ---------------------------------------------------------------------------


def test_same_name_events_get_distinct_labels(tmp_path: Path) -> None:
    # Two events with the same RMXP name ("Receptionist TRADE") but different ids and
    # different dialogue — the latter keeps memo keys distinct so both spawn the backend.
    # The backend (like the real agent) returns name-derived labels, so without F1 both
    # scripts would define Map001_Receptionist_TRADE_Page1 and collide at link time.
    ev1 = {
        "id": 3, "name": "Receptionist TRADE", "x": 1, "y": 2,
        "pages": [{"list": [{"code": 101, "parameters": ["Welcome!"]}]}],
    }
    ev2 = {
        "id": 5, "name": "Receptionist TRADE", "x": 3, "y": 4,
        "pages": [{"list": [{"code": 101, "parameters": ["Goodbye!"]}]}],
    }
    backend = MockBackend([
        ConversionResult(
            script='script Map001_Receptionist_TRADE_Page1 { msgbox("Welcome!") GOOD }'
        ),
        ConversionResult(
            script='script Map001_Receptionist_TRADE_Page1 { msgbox("Goodbye!") GOOD }'
        ),
    ])
    o = _orchestrator(tmp_path, backend)
    o.convert_map(_write_map(tmp_path / "out" / "maps", 1, [ev1, ev2]))

    pory = (tmp_path / "out" / "scripts" / "Map001.pory").read_text(encoding="utf-8")
    # Each event's block carries its own EV tag.
    assert "Map001_EV003_Receptionist_TRADE_Page1" in pory
    assert "Map001_EV005_Receptionist_TRADE_Page1" in pory
    # The bare name-derived label must be absent — the EV-qualified forms do NOT
    # contain it as a substring (EV003_ is inserted between Map001_ and Receptionist),
    # so a plain "not in" is an exact check here.
    assert "Map001_Receptionist_TRADE_Page1" not in pory


# ---------------------------------------------------------------------------
# Test 2: goto references rewrite together with definitions
# ---------------------------------------------------------------------------


def test_goto_references_rewrite_with_definitions(tmp_path: Path) -> None:
    # F1 is a plain string replace over the whole script text, so a goto(Map{NNN}_…)
    # target rewrites alongside its script { } definition. If only the definition moved
    # the goto would dangle at assembly.
    ev = {
        "id": 7, "name": "npc", "x": 0, "y": 0,
        "pages": [{"list": [{"code": 101, "parameters": ["hi"]}]}],
    }
    backend = MockBackend([ConversionResult(
        script=(
            "script Map001_npc_Page1 { goto(Map001_npc_Extra) GOOD }\n"
            "script Map001_npc_Extra { GOOD }"
        )
    )])
    o = _orchestrator(tmp_path, backend)
    o.convert_map(_write_map(tmp_path / "out" / "maps", 1, [ev]))

    pory = (tmp_path / "out" / "scripts" / "Map001.pory").read_text(encoding="utf-8")
    assert "script Map001_EV007_npc_Page1 {" in pory          # definition qualified
    assert "goto(Map001_EV007_npc_Extra)" in pory              # goto target qualified
    assert "script Map001_EV007_npc_Extra {" in pory           # extra block qualified
    assert "Map001_npc_Page1" not in pory                      # bare form gone
    assert "Map001_npc_Extra" not in pory                      # bare form gone


# ---------------------------------------------------------------------------
# Test 3: idempotence
# ---------------------------------------------------------------------------


def test_qualify_labels_idempotent() -> None:
    # Applying qualification twice must equal applying it once. A second pass over an
    # already-qualified label must not double-insert the EV tag thanks to the negative
    # lookahead in the regex.
    script = (
        "script Map042_npc_Page1 { GOOD }\n"
        "script Map042_npc_OtherPage { goto(Map042_npc_OtherPage) GOOD }"
    )
    once = orch._qualify_labels(script, 42, 13)
    twice = orch._qualify_labels(once, 42, 13)
    assert twice == once, f"not idempotent:\nonce={once!r}\ntwice={twice!r}"


# ---------------------------------------------------------------------------
# Test 4: default-named events not double-qualified
# ---------------------------------------------------------------------------


def test_default_named_event_not_double_qualified() -> None:
    # Event id 11 on map 2 whose RMXP name IS "EV011" produces the natural label
    # Map002_EV011_Page1 (already EV-tagged). The negative lookahead must leave it
    # untouched — not Map002_EV011_EV011_Page1.
    script = "script Map002_EV011_Page1 { GOOD }"
    result = orch._qualify_labels(script, 2, 11)
    assert result == script, f"got: {result!r}"


# ---------------------------------------------------------------------------
# Test 5: FLAG names untouched
# ---------------------------------------------------------------------------


def test_flag_names_untouched_by_qualification() -> None:
    # FLAG_MAP002_… uses upper-case MAP; the label prefix Map002_ is mixed-case.
    # The regex is case-sensitive, so flag identifiers must survive unchanged while
    # the label gains the EV tag.
    script = "script Map002_MyLabel_Page1 { setflag(FLAG_MAP002_EVENT011_SSA) GOOD }"
    result = orch._qualify_labels(script, 2, 11)
    # Flag name byte-identical — not transformed by the Map002_ pattern.
    assert "setflag(FLAG_MAP002_EVENT011_SSA)" in result
    # Label qualified.
    assert "script Map002_EV011_MyLabel_Page1 {" in result


# ---------------------------------------------------------------------------
# Test 6: same-map memo reuse (the copy-paste / NuclearBoat×10 case)
# ---------------------------------------------------------------------------


def test_same_map_memo_reuse_produces_distinct_labels(tmp_path: Path) -> None:
    # Two structurally identical events (same name, same commands, same position — a
    # literal copy-paste stack) on one map. The second must be a memo hit (no second
    # spawn) AND the emitted .pory must carry two blocks with distinct EV-qualified
    # labels. Without F1, both would emit Map010_NuclearBoat_Page1 and collide.
    template: dict = {
        "name": "NuclearBoat", "x": 5, "y": 3,
        "pages": [{"list": [{"code": 101, "parameters": ["Board the boat?"]}]}],
    }
    ev1 = {"id": 3, **template}
    ev2 = {"id": 7, **template}

    backend = MockBackend([
        ConversionResult(script="script Map010_NuclearBoat_Page1 { GOOD }")
    ])
    o = _orchestrator(tmp_path, backend)
    o.convert_map(_write_map(tmp_path / "out" / "maps", 10, [ev1, ev2]))

    assert backend.calls == 1  # ev2 is a memo hit — no second spawn
    pory = (tmp_path / "out" / "scripts" / "Map010.pory").read_text(encoding="utf-8")
    assert "Map010_EV003_NuclearBoat_Page1" in pory
    assert "Map010_EV007_NuclearBoat_Page1" in pory
    # Bare form absent (EV-qualified forms don't contain it as a substring).
    assert "Map010_NuclearBoat_Page1" not in pory


# ---------------------------------------------------------------------------
# Test 7: pre-F1 memo entry replays correctly
# ---------------------------------------------------------------------------


def test_pre_f1_memo_entry_replays_with_ev_tag(tmp_path: Path) -> None:
    # A MemoEntry stored before F1 has a name-only label (Map010_npc_Page1, no EV
    # tag). On replay, _reinstantiate leaves it unchanged (same map/event), and
    # _qualify_labels adds the EV tag — so old memo manifests gain F1 behaviour
    # without a re-spawn (backward compat).
    event = {
        "id": 7, "name": "npc", "x": 0, "y": 0,
        "pages": [{"list": [{"code": 101, "parameters": ["hi"]}]}],
    }
    backend = MockBackend([ConversionResult(script="SHOULD NOT BE CALLED")])
    o = _orchestrator(tmp_path, backend)

    # Inject a pre-F1 (unqualified) memo entry directly into the in-memory dict,
    # keyed by the event's content hash (the same lookup _convert_event uses).
    key = orch._memo_key({"map_id": 10, **event})
    o._memo[key] = orch.MemoEntry(
        script="script Map010_npc_Page1 { GOOD }",
        src_map=10,
        src_event=7,
    )

    o.convert_map(_write_map(tmp_path / "out" / "maps", 10, [event]))

    assert backend.calls == 0  # served entirely from memo — no spawn
    pory = (tmp_path / "out" / "scripts" / "Map010.pory").read_text(encoding="utf-8")
    assert "Map010_EV007_npc_Page1" in pory   # legacy entry gained the EV tag on replay
    assert "Map010_npc_Page1" not in pory     # bare name-only form absent


# ---------------------------------------------------------------------------
# Test 8: duplicate-label assertion fires
# ---------------------------------------------------------------------------


def test_duplicate_label_assertion_fires(tmp_path: Path) -> None:
    # Two events with different content (different memo keys → both spawn) whose
    # backend scripts use a bare label with no Map{NNN}_ prefix. _qualify_labels
    # cannot touch it, so both blocks define "script npc { … }" and the seen_labels
    # guard must raise RuntimeError before the duplicate symbol escapes to the file.
    ev1 = {
        "id": 1, "name": "ev1", "x": 0, "y": 0,
        "pages": [{"list": [{"code": 101, "parameters": ["hello"]}]}],
    }
    ev2 = {
        "id": 2, "name": "ev2", "x": 1, "y": 0,
        "pages": [{"list": [{"code": 101, "parameters": ["world"]}]}],
    }
    # Both calls return the same bare label — impossible to qualify without the
    # Map{NNN}_ prefix, so qualification can't rescue this case.
    backend = MockBackend([ConversionResult(script="script npc { GOOD }")])
    o = _orchestrator(tmp_path, backend)

    with pytest.raises(RuntimeError, match="duplicate"):
        o.convert_map(_write_map(tmp_path / "out" / "maps", 3, [ev1, ev2]))
