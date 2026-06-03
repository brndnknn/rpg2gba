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
from rpg2gba.conversion_agent.flag_registry import (
    FlagRegistry,
    RegistryError,
    self_switch_flag_name,
    temp_switch_flag_name,
)

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


def test_mint_self_switch_deterministic_and_idempotent() -> None:
    reg = FlagRegistry()
    name = reg.mint_self_switch(31, 48, "A")
    assert name == "FLAG_MAP031_EVENT048_SSA" == self_switch_flag_name(31, 48, "a")
    assert reg.mint_self_switch(31, 48, "A") == name  # idempotent on the same key
    assert reg.mint_self_switch(31, 48, "B") != name  # distinct letter
    assert reg.mint_self_switch(31, 49, "A") != name  # distinct event


def test_mint_self_switch_collision_with_global_flag() -> None:
    reg = FlagRegistry()
    reg.mint_self_switch(31, 48, "A")
    # A global-flag proposal landing on the same deterministic name is rejected.
    with pytest.raises(RegistryError):
        reg.propose_flag(900, "FLAG_MAP031_EVENT048_SSA")


def test_self_switch_state_roundtrip(tmp_path: Path) -> None:
    reg = _seeded()
    reg.mint_self_switch(31, 48, "A")
    state_path = tmp_path / "flag_state.json"
    reg.save(state_path)
    reloaded = FlagRegistry.load(state_path)
    assert reloaded.mint_self_switch(31, 48, "A") == "FLAG_MAP031_EVENT048_SSA"
    reloaded.check_integrity()


def test_dump_header_self_switch_block_and_custom_bases(tmp_path: Path) -> None:
    reg = _seeded()
    reg.mint_self_switch(31, 48, "A")
    out = tmp_path / "rpg2gba_flags.h"
    reg.dump_header(out, flag_base=0x20, selfswitch_base=0x100)
    text = out.read_text(encoding="utf-8")
    assert "RPG2GBA_SELFSWITCH_BASE" in text
    assert "0x20" in text and "0x100" in text  # the Phase-7 base hooks
    assert "#define FLAG_MAP031_EVENT048_SSA (RPG2GBA_SELFSWITCH_BASE + 0)" in text


def test_mint_temp_switch_deterministic_and_idempotent() -> None:
    reg = FlagRegistry()
    name = reg.mint_temp_switch(2, 11, "A")
    assert name == "FLAG_MAP002_EVENT011_TSA" == temp_switch_flag_name(2, 11, "a")
    assert reg.mint_temp_switch(2, 11, "A") == name  # idempotent on the same key
    assert reg.mint_temp_switch(2, 11, "B") != name  # distinct key
    assert reg.mint_temp_switch(2, 12, "A") != name  # distinct event


def test_temp_switch_distinct_from_self_switch() -> None:
    # The TS marker keeps temp- and self-switches in separate namespaces even for
    # the same (map, event, letter) — both can coexist without collision.
    reg = FlagRegistry()
    ss = reg.mint_self_switch(2, 11, "A")
    ts = reg.mint_temp_switch(2, 11, "A")
    assert ss == "FLAG_MAP002_EVENT011_SSA"
    assert ts == "FLAG_MAP002_EVENT011_TSA"
    reg.check_integrity()


def test_temp_switch_collision_with_global_flag() -> None:
    reg = FlagRegistry()
    reg.mint_temp_switch(2, 11, "A")
    with pytest.raises(RegistryError):
        reg.propose_flag(900, "FLAG_MAP002_EVENT011_TSA")


def test_temp_switch_state_roundtrip(tmp_path: Path) -> None:
    reg = _seeded()
    reg.mint_temp_switch(2, 11, "A")
    state_path = tmp_path / "flag_state.json"
    reg.save(state_path)
    reloaded = FlagRegistry.load(state_path)
    assert reloaded.mint_temp_switch(2, 11, "A") == "FLAG_MAP002_EVENT011_TSA"
    reloaded.check_integrity()


def test_dump_header_temp_switch_block_and_custom_base(tmp_path: Path) -> None:
    reg = _seeded()
    reg.mint_temp_switch(2, 11, "A")
    out = tmp_path / "rpg2gba_flags.h"
    reg.dump_header(out, tempswitch_base=0x800)
    text = out.read_text(encoding="utf-8")
    assert "RPG2GBA_TEMPSWITCH_BASE" in text
    assert "0x800" in text  # the Phase-7 auto-reset-range hook
    assert "#define FLAG_MAP002_EVENT011_TSA (RPG2GBA_TEMPSWITCH_BASE + 0)" in text


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


def test_claude_model_in_cmd() -> None:
    cmd = claude_code.ClaudeCodeBackend("SYSTEM", model="claude-opus-4-8")._build_cmd()
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "claude-opus-4-8"


def test_phase4_backend_threads_model() -> None:
    from rpg2gba import pipeline

    backend = pipeline._phase4_backend("claude_code", "claude-opus-4-8")
    assert backend.model == "claude-opus-4-8"
    # default is Sonnet (the calibration baseline)
    assert pipeline._phase4_backend("claude_code").model == pipeline._DEFAULT_MODEL


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


_EVENT = {
    "id": 1, "name": "EV001", "x": 0, "y": 0,
    "pages": [{"list": [{"code": 101, "parameters": ["hi"]}]}],
}


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
# 4b. Common-event conversion (Phase 4 dedup A)
# ----------------------------------------------------------------------------


class _RecordingBackend(ConversionBackend):
    """Records each payload it is asked to convert and returns a per-payload result."""

    def __init__(self, script_for) -> None:  # script_for: (payload) -> ConversionResult
        self.script_for = script_for
        self.payloads: list[dict] = []
        self.calls = 0

    def convert_event(self, event_json, registry_state, prompt) -> ConversionResult:
        self.payloads.append(event_json)
        self.calls += 1
        return self.script_for(event_json)


def _write_common_events(out_dir: Path, ces: list[dict]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "common_events.json"
    path.write_text(json.dumps(ces), encoding="utf-8")
    return path


def _labeled_block(payload: dict) -> ConversionResult:
    """A stand-in agent result that labels its block CommonEvent_<NNN>, like the real one."""
    label = f"CommonEvent_{payload['common_event_id']:03d}"
    return ConversionResult(script=f"script {label} {{ GOOD }}")


def test_convert_common_events(tmp_path: Path) -> None:
    ces = [
        {"id": 4, "name": "GTS", "trigger": 0, "switch_id": 1,
         "list": [{"code": 101, "parameters": ["hi"]}, {"code": 0, "parameters": []}]},
        {"id": 7, "name": "Decoration", "trigger": 0, "switch_id": 1,
         "list": [{"code": 0, "parameters": []}]},  # no real commands -> skipped
    ]
    ce_path = _write_common_events(tmp_path / "out", ces)
    backend = _RecordingBackend(_labeled_block)
    o = _orchestrator(tmp_path, backend)
    o.convert_common_events(ce_path)

    # Only CE 4 has commands -> exactly one spawn, carrying common_event_id + page-shape.
    assert backend.calls == 1
    assert backend.payloads[0]["common_event_id"] == 4
    assert "pages" in backend.payloads[0]  # adapted from the flat list for the helpers
    pory = (tmp_path / "out" / "scripts" / "CommonEvents.pory").read_text(encoding="utf-8")
    assert "CommonEvent_004" in pory
    assert (tmp_path / "out" / "checkpoints" / "CommonEvents.done").exists()


def test_convert_common_events_queues_failure(tmp_path: Path) -> None:
    ces = [{"id": 5, "name": "VT", "trigger": 0, "switch_id": 1,
            "list": [{"code": 101, "parameters": ["x"]}]}]
    ce_path = _write_common_events(tmp_path / "out", ces)
    backend = MockBackend([ConversionResult(script="BAD always")])
    o = _orchestrator(tmp_path, backend)
    o.convert_common_events(ce_path)

    entries = [
        json.loads(line)
        for line in (tmp_path / "out" / "unhandled.jsonl").read_text().splitlines()
    ]
    assert any(
        e.get("common_event_id") == 5 and "compile failed twice" in e["reason"] for e in entries
    )
    # No self/temp-switch minting happened for the common event.
    state = json.loads((tmp_path / "out" / "flag_state.json").read_text(encoding="utf-8"))
    assert state["self_switches"] == {} and state["temp_switches"] == {}


def test_convert_common_events_checkpoint_skips_rerun(tmp_path: Path) -> None:
    ces = [{"id": 4, "name": "A", "list": [{"code": 101, "parameters": ["a"]}]}]
    ce_path = _write_common_events(tmp_path / "out", ces)
    backend = _RecordingBackend(lambda p: ConversionResult(script="GOOD"))
    o = _orchestrator(tmp_path, backend)
    o.convert_common_events(ce_path)
    calls_after_first = backend.calls
    o.convert_common_events(ce_path)  # checkpoint exists -> whole pass skipped
    assert backend.calls == calls_after_first


def test_convert_common_events_only_ids_partial_no_checkpoint(tmp_path: Path) -> None:
    ces = [
        {"id": 4, "name": "A", "list": [{"code": 101, "parameters": ["a"]}]},
        {"id": 5, "name": "B", "list": [{"code": 101, "parameters": ["b"]}]},
    ]
    ce_path = _write_common_events(tmp_path / "out", ces)
    backend = _RecordingBackend(_labeled_block)
    o = _orchestrator(tmp_path, backend)
    o.convert_common_events(ce_path, only_ids={4})
    assert backend.calls == 1  # only CE 4
    assert backend.payloads[0]["common_event_id"] == 4
    assert not (tmp_path / "out" / "checkpoints" / "CommonEvents.done").exists()


# ----------------------------------------------------------------------------
# 5. Prompt assembly
# ----------------------------------------------------------------------------


def test_build_static_context_has_invariant_chunks() -> None:
    static = prompt_builder.build_static_context(
        cheatsheet=prompt_builder.load_cheatsheet(REFERENCE),
        script_call_ref=prompt_builder.load_script_call_reference(REFERENCE),
        few_shots=prompt_builder.load_few_shots(),
    )
    assert "Poryscript cheatsheet" in static
    assert "Uranium script-call reference" in static
    assert "pbCallBub" in static  # from the script-call reference
    assert "Few-shot examples" in static


def test_build_user_prompt_excludes_static_context() -> None:
    state = {"flags": {"2": "FLAG_RECEIVED_STARTER"}, "vars": {}}
    user = prompt_builder.build_user_prompt(
        {"id": 1, "name": "EV001", "pages": []},
        state,
        command_ref=prompt_builder.filter_command_reference(
            prompt_builder.load_command_reference(REFERENCE), {101}
        ),
    )
    # Per-event-variable content is present...
    assert "FLAG_RECEIVED_STARTER" in user
    assert '"name": "EV001"' in user
    assert "Command-code reference" in user
    # ...but the event-invariant static context is NOT (it lives in the system prompt).
    assert "Poryscript cheatsheet" not in user
    assert "Few-shot examples" not in user


def test_phase4_backend_system_prompt_includes_static_context() -> None:
    from rpg2gba import pipeline

    backend = pipeline._phase4_backend("claude_code")
    # system prompt = frozen system.md + the static context (dedup Phase B)
    assert "conversion agent" in backend.system_prompt.lower()  # from system.md
    assert "Poryscript cheatsheet" in backend.system_prompt  # from static context
    assert "Few-shot examples" in backend.system_prompt


def test_claude_parse_logs_cache_usage(caplog: pytest.LogCaptureFixture) -> None:
    envelope = json.dumps(
        {
            "type": "result",
            "result": json.dumps(_GOOD),
            "usage": {
                "input_tokens": 10,
                "cache_read_input_tokens": 1234,
                "cache_creation_input_tokens": 0,
                "output_tokens": 50,
            },
            "total_cost_usd": 0.012,
        }
    )
    with caplog.at_level("INFO", logger="rpg2gba.conversion_agent.backends.claude_code"):
        result = claude_code._parse_response(envelope)
    assert result.script == "script S { end }"
    assert "cache_read=1234" in caplog.text


def test_render_registry_lists_script_switches() -> None:
    out = prompt_builder._render_registry({"flags": {}, "vars": {}, "script_switches": [1, 22, 4]})
    assert "Script-switches" in out
    assert "1, 4, 22" in out  # sorted, never proposed as flags


def test_system_prompt_loads() -> None:
    assert "conversion agent" in prompt_builder.load_system_prompt().lower()


def test_filter_command_reference() -> None:
    full = prompt_builder.load_command_reference(REFERENCE)
    out = prompt_builder.filter_command_reference(full, {101, 355})
    assert "| 101 |" in out and "| 355 |" in out
    assert "| 122 |" not in out  # a real code we didn't ask for is dropped
    assert len(out) < len(full)  # the slice is smaller than the full reference


def test_event_codes() -> None:
    ev = {
        "pages": [{"list": [{"code": 101}, {"code": 355}], "move_route": {"list": [{"code": 1}]}}]
    }
    assert orch._event_codes(ev) == {1, 101, 355}


def test_event_self_switches() -> None:
    ev = {
        "pages": [
            {"condition": {"self_switch_valid": False, "self_switch_ch": "A"},
             "list": [{"code": 123, "parameters": ["A", 0]}]},
            {"condition": {"self_switch_valid": True, "self_switch_ch": "A"},
             "list": [{"code": 101, "parameters": ["hi"]}]},
        ]
    }
    assert orch._event_self_switches(ev) == {"A"}


def test_orchestrator_mints_self_switches(tmp_path: Path) -> None:
    event = {
        "id": 7, "name": "npc", "x": 0, "y": 0,
        "pages": [
            {"condition": {"self_switch_valid": False, "self_switch_ch": "A"},
             "list": [{"code": 123, "parameters": ["A", 0]}]},
            {"condition": {"self_switch_valid": True, "self_switch_ch": "A"},
             "list": [{"code": 101, "parameters": ["hi"]}]},
        ],
    }
    backend = MockBackend([ConversionResult(script="GOOD script")])
    o = _orchestrator(tmp_path, backend)
    map_file = _write_map(tmp_path / "out" / "maps", 31, [event])
    o.convert_map(map_file)
    state = json.loads((tmp_path / "out" / "flag_state.json").read_text(encoding="utf-8"))
    assert state["self_switches"] == {"31:7:A": "FLAG_MAP031_EVENT007_SSA"}


def test_event_temp_switches() -> None:
    ev = {
        "pages": [
            {"list": [
                {"code": 355, "parameters": ['setTempSwitchOn("A")']},
                {"code": 111, "parameters": [12, 'tsOff?("B")']},  # not a 355/655 — ignored
            ]},
            {"list": [{"code": 655, "parameters": ['setTempSwitchOff("a")']}]},
        ]
    }
    # Only the 355/655 script-call forms count; keys are upper-cased.
    assert orch._event_temp_switches(ev) == {"A"}


def test_event_temp_switches_read_form() -> None:
    ev = {"pages": [{"list": [{"code": 355, "parameters": ['x = tsOn?("C")']}]}]}
    assert orch._event_temp_switches(ev) == {"C"}


def test_orchestrator_mints_temp_switches(tmp_path: Path) -> None:
    # Mirrors Map002 EV011: a code-355 setTempSwitchOn the agent emits as a TS flag.
    event = {
        "id": 11, "name": "EV011", "x": 7, "y": 12,
        "pages": [
            {"condition": {"self_switch_valid": False, "self_switch_ch": "A"},
             "list": [{"code": 355, "parameters": ['setTempSwitchOn("A")']}]},
        ],
    }
    backend = MockBackend([ConversionResult(script="GOOD script")])
    o = _orchestrator(tmp_path, backend)
    map_file = _write_map(tmp_path / "out" / "maps", 2, [event])
    o.convert_map(map_file)
    state = json.loads((tmp_path / "out" / "flag_state.json").read_text(encoding="utf-8"))
    assert state["temp_switches"] == {"2:11:A": "FLAG_MAP002_EVENT011_TSA"}
    # It is a temp-switch, not a self-switch (no code 123 / self_switch_valid page).
    assert state["self_switches"] == {}


def test_event_has_commands() -> None:
    assert orch._event_has_commands({"pages": [{"list": [{"code": 101}]}]})
    assert not orch._event_has_commands({"pages": [{"list": [{"code": 0}]}, {"list": []}]})


def test_orchestrator_skips_empty_event(tmp_path: Path) -> None:
    empty = {"id": 9, "name": "decoration", "pages": [{"list": [{"code": 0}]}]}
    backend = MockBackend([ConversionResult(script="GOOD")])
    o = _orchestrator(tmp_path, backend)
    map_file = _write_map(tmp_path / "out" / "maps", 5, [empty])
    o.convert_map(map_file)
    assert backend.calls == 0  # no spawn for a command-less event
    assert (tmp_path / "out" / "scripts" / "Map005.pory").read_text() == ""
