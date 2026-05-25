"""Phase 4 conversion-agent machinery tests (PHASE4_PLAN test strategy).

Most tests are pure units (registry, backend parsers, prompt assembly,
orchestrator with a MockBackend) and always run. Only the compile-gate test needs
the real `poryscript` binary; it is marked `phase4` and skips when absent. No test
spawns `claude` or hits the network (F7).
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import orchestrator as orch
from rpg2gba.conversion_agent import poryscript, prompt_builder
from rpg2gba.conversion_agent.backends import (
    ConversionBackend,
    ConversionResult,
    claude_code,
    ollama,
)
from rpg2gba.conversion_agent.flag_registry import FlagRegistry, RegistryError

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE = REPO_ROOT / "reference"
PRESEED = REFERENCE / "essentials_to_emerald_map.md"
SWITCHES = REFERENCE / "uranium_switches.json"
VARIABLES = REFERENCE / "uranium_variables.json"


def _seeded() -> FlagRegistry:
    reg = FlagRegistry()
    reg.pre_seed(PRESEED, SWITCHES, VARIABLES)
    return reg


# ----------------------------------------------------------------------------
# 1. Flag registry
# ----------------------------------------------------------------------------


def test_preseed_loads_known_mappings() -> None:
    reg = _seeded()
    assert reg.get_flag(2) == "FLAG_RECEIVED_STARTER"
    assert reg.get_flag(121) == "FLAG_DEFEATED_GYM8_LEADER"
    assert reg.get_var(87) == "VAR_GYM8_WHITE_TILES"
    assert reg.get_var(24) == "VAR_TANDOR_CHAMPIONSHIP_ROUND"


def test_script_switches_blocked() -> None:
    reg = _seeded()
    assert reg.is_script_switch(1)  # switch 1 == "s:pbIsWeekday(...)"
    with pytest.raises(RegistryError, match="script-switch"):
        reg.propose_flag(1, "FLAG_WEEKDAY")


def test_propose_and_collision() -> None:
    reg = FlagRegistry()
    assert reg.propose_flag(500, "FLAG_TEST_THING") == "FLAG_TEST_THING"
    assert reg.get_flag(500) == "FLAG_TEST_THING"
    # Same name, different id -> collision.
    with pytest.raises(RegistryError, match="collision"):
        reg.propose_flag(501, "FLAG_TEST_THING")
    # Re-proposing for the same id returns the existing name (idempotent).
    assert reg.propose_flag(500, "FLAG_SOMETHING_ELSE") == "FLAG_TEST_THING"


@pytest.mark.parametrize("bad", ["FLAG_TODO", "flag_lower", "FLAG_SWITCH_42", "FLAG_X", "VAR_FOO"])
def test_invalid_names_rejected(bad: str) -> None:
    reg = FlagRegistry()
    with pytest.raises(RegistryError):
        reg.propose_flag(600, bad)


def test_reserved_fork_constant_rejected() -> None:
    reg = FlagRegistry()
    with pytest.raises(RegistryError, match="already exists"):
        reg.propose_flag(601, "FLAG_SYS_GAME_CLEAR")


def test_state_roundtrip(tmp_path: Path) -> None:
    reg = _seeded()
    reg.propose_flag(700, "FLAG_RUNTIME_PROPOSAL")
    state_path = tmp_path / "flag_state.json"
    reg.save(state_path)

    reloaded = FlagRegistry.load(state_path)
    assert reloaded.get_flag(2) == "FLAG_RECEIVED_STARTER"
    assert reloaded.get_flag(700) == "FLAG_RUNTIME_PROPOSAL"
    assert reloaded.is_script_switch(1)
    reloaded.check_integrity()


def test_dump_header(tmp_path: Path) -> None:
    reg = _seeded()
    out = tmp_path / "rpg2gba_flags.h"
    reg.dump_header(out)
    text = out.read_text(encoding="utf-8")
    assert "#define FLAG_RECEIVED_STARTER" in text
    assert "#define VAR_GYM8_WHITE_TILES" in text


# ----------------------------------------------------------------------------
# 2. Backend response parsing (no live spawn / network)
# ----------------------------------------------------------------------------

_GOOD = {"script": "script S { end }", "new_flags": [], "new_vars": [], "unhandled": []}


def test_claude_parse_envelope_and_direct() -> None:
    envelope = json.dumps({"result": json.dumps(_GOOD), "type": "result"})
    assert claude_code._parse_response(envelope).script == "script S { end }"
    # Bare object (no CLI envelope) also works.
    assert claude_code._parse_response(json.dumps(_GOOD)).script == "script S { end }"


def test_claude_parse_malformed() -> None:
    with pytest.raises(RuntimeError):
        claude_code._parse_response("not json and no object")
    with pytest.raises(RuntimeError, match="missing 'script'"):
        claude_code._parse_response(json.dumps({"new_flags": []}))


def test_claude_convert_event_mocks_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd, **kw):
        payload = json.dumps({"result": json.dumps(_GOOD)})
        return types.SimpleNamespace(returncode=0, stdout=payload, stderr="")

    monkeypatch.setattr(claude_code.subprocess, "run", fake_run)
    backend = claude_code.ClaudeCodeBackend("SYSTEM")
    assert backend.convert_event({}, {}, "prompt").script == "script S { end }"


def test_ollama_parse() -> None:
    payload = {"message": {"content": json.dumps(_GOOD)}}
    assert ollama._parse_chat(payload).script == "script S { end }"
    with pytest.raises(RuntimeError):
        ollama._parse_chat({"message": {"content": "nope"}})


# ----------------------------------------------------------------------------
# 3. Compile-gate (needs the real binary)
# ----------------------------------------------------------------------------


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_compile_gate() -> None:
    ok = poryscript.compile_script(
        'script Test { lock\n faceplayer\n msgbox("Hi")\n release\n end\n}\n'
    )
    assert ok.ok, ok.stderr
    bad = poryscript.compile_script("script Test { this is not poryscript")
    assert not bad.ok
    assert bad.stderr


# ----------------------------------------------------------------------------
# 4. Orchestrator integration (MockBackend + fake compiler + synthetic map)
# ----------------------------------------------------------------------------


class MockBackend(ConversionBackend):
    def __init__(self, results: list[ConversionResult]) -> None:
        self.results = results
        self.calls = 0

    def convert_event(self, event_json, registry_state, prompt) -> ConversionResult:
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return r


def _fake_compile(script: str) -> poryscript.CompileResult:
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


_EVENT = {"id": 1, "name": "EV001", "x": 0, "y": 0, "pages": [{"list": []}]}


def _orchestrator(tmp_path: Path, backend: ConversionBackend) -> orch.Orchestrator:
    return orch.Orchestrator(
        backend, FlagRegistry(), tmp_path / "out", reference_dir=REFERENCE, compile_fn=_fake_compile
    )


def test_retry_once_then_succeed(tmp_path: Path) -> None:
    backend = MockBackend([ConversionResult(script="BAD"), ConversionResult(script="GOOD script")])
    o = _orchestrator(tmp_path, backend)
    map_file = _write_map(tmp_path / "out" / "maps", 1, [dict(_EVENT)])
    o.convert_map(map_file)
    assert backend.calls == 2  # first attempt + one retry
    pory = (tmp_path / "out" / "scripts" / "Map001.pory").read_text(encoding="utf-8")
    assert "GOOD" in pory


def test_double_failure_queues(tmp_path: Path) -> None:
    backend = MockBackend([ConversionResult(script="BAD always")])
    o = _orchestrator(tmp_path, backend)
    map_file = _write_map(tmp_path / "out" / "maps", 2, [dict(_EVENT)])
    o.convert_map(map_file)
    queue = tmp_path / "out" / "unhandled.jsonl"
    entries = [json.loads(line) for line in queue.read_text().splitlines()]
    assert any("compile failed twice" in e["reason"] for e in entries)
    assert (tmp_path / "out" / "scripts" / "Map002.pory").read_text() == ""


def test_proposals_committed(tmp_path: Path) -> None:
    result = ConversionResult(
        script="GOOD",
        new_flags=[{"switch_id": 800, "name": "FLAG_NEW_THING", "reason": "x"}],
    )
    backend = MockBackend([result])
    o = _orchestrator(tmp_path, backend)
    map_file = _write_map(tmp_path / "out" / "maps", 3, [dict(_EVENT)])
    o.convert_map(map_file)
    assert o.registry.get_flag(800) == "FLAG_NEW_THING"


def test_checkpoint_skip_and_idempotence(tmp_path: Path) -> None:
    backend = MockBackend([ConversionResult(script="GOOD")])
    o = _orchestrator(tmp_path, backend)
    map_file = _write_map(tmp_path / "out" / "maps", 4, [dict(_EVENT)])
    o.convert_map(map_file)
    first = (tmp_path / "out" / "scripts" / "Map004.pory").read_bytes()
    calls_after_first = backend.calls
    o.convert_map(map_file)  # checkpoint exists -> skipped
    assert backend.calls == calls_after_first
    assert (tmp_path / "out" / "scripts" / "Map004.pory").read_bytes() == first


def test_triage(tmp_path: Path) -> None:
    backend = MockBackend([ConversionResult(script="BAD")])
    o = _orchestrator(tmp_path, backend)
    map_file = _write_map(tmp_path / "out" / "maps", 5, [dict(_EVENT)])
    o.convert_map(map_file)
    summary = orch.triage(tmp_path / "out" / "unhandled.jsonl")
    assert sum(summary.values()) >= 1


# ----------------------------------------------------------------------------
# 5. Prompt assembly
# ----------------------------------------------------------------------------


def test_build_prompt_has_sections() -> None:
    state = {"flags": {"2": "FLAG_RECEIVED_STARTER"}, "vars": {}}
    prompt = prompt_builder.build_prompt(
        {"id": 1, "name": "EV001", "pages": []},
        state,
        few_shots=prompt_builder.load_few_shots(),
        cheatsheet=prompt_builder.load_cheatsheet(REFERENCE),
        command_ref=prompt_builder.load_command_reference(REFERENCE),
    )
    assert "FLAG_RECEIVED_STARTER" in prompt
    assert "Poryscript cheatsheet" in prompt
    assert "Few-shot examples" in prompt
    assert '"name": "EV001"' in prompt


def test_system_prompt_loads() -> None:
    assert "conversion agent" in prompt_builder.load_system_prompt().lower()
