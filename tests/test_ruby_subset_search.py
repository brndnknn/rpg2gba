"""Tests for `rpg2gba.ruby_subset.search` (REDERIVATION_PLAN.md C8 stage 3).

Section 1 is the Bambo real-corpus gate (starter-pick tally +
argmax-remap). Section 2 is `map050/ev019` (switch writes gated on the
var-151 result -- the row that actually owns them turned out to be the
PAGE TRUNK, not `/b1`; see that test's own docstring). Section 3 is
synthetic scope tests (random write, cap, unknown-read refusal,
strip-listed 117 no-op). Section 4 is the real-corpus measurement gate
across CH01-CH05. Section 5 is determinism.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.chapter_manifest.generator import iter_page_scopes
from rpg2gba.ruby_subset.search import (
    Choice,
    load_stripped_ce_ids,
    search_scope,
)
from rpg2gba.story_state.state import EngineKey, SelfSwitch, Switch, Variable

REPO = Path(__file__).resolve().parents[1]
MAPS_DIR = REPO / "output" / "uranium-build" / "maps"
COMMON_EVENTS_PATH = REPO / "output" / "uranium-build" / "common_events.json"
CHAPTERS_PATH = REPO / "reference" / "chapters.json"

pytestmark_corpus = pytest.mark.skipif(
    not MAPS_DIR.is_dir(), reason="output/uranium-build/maps not staged",
)


def _load_common_events_by_id() -> dict[int, dict]:
    if not COMMON_EVENTS_PATH.exists():
        return {}
    data = json.loads(COMMON_EVENTS_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {ce["id"]: ce for ce in data if ce}
    return {int(k): v for k, v in data.items()}


def _map050_event(event_id: int):
    path = MAPS_DIR / "Map050.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data, next(e for e in data["events"] if e["id"] == event_id)


def _scope_by_suffix(map_id: int, event: dict, page_idx: int, page: dict, suffix: str):
    scopes = iter_page_scopes(map_id, event, page_idx, page)
    return next(s for s in scopes if s.row_id.endswith(suffix))


# --- section 1: Bambo (starter-pick tally + argmax remap) ----------------


@pytestmark_corpus
def test_bambo_starter_tally_search():
    map_data, event = _map050_event(5)
    page = event["pages"][0]
    scope = _scope_by_suffix(50, event, 0, page, "/b2")

    def read_domain(key):
        # `evaluate.py`'s `_Interp.set_key` always `_touch`es (= reads) a
        # key before overwriting it, even for a plain `Assign` -- bookkeeping
        # for its own diff-based `writes()`, not a real Ruby read; the
        # touched value is provably discarded (the write is unconditional
        # and happens immediately after -- see the build agent's C8 stage-3
        # report). Var 151's very first touch, in the tally-init block
        # (`$game_variables[151]=[0,0,0]`), is exactly this case, so it gets
        # a harmless one-element domain here; every OTHER key in this row
        # (var 2, the self switch) is genuinely never read out-of-scope, so
        # anything else still refuses loudly if this test's understanding of
        # the scope is wrong.
        if key == Variable(151):
            return frozenset({0})
        return None

    result = search_scope(
        scope.commands,
        map_id=50, event_id=5,
        common_events_by_id=_load_common_events_by_id(),
        stripped_ce_ids=load_stripped_ce_ids(REPO / "reference"),
        read_domain=read_domain,
    )
    assert result.refusal is None, result.refusal
    # 4 independent \ch choices, 3 options each, no cancel (ifCancel=0).
    assert result.runs == 81
    assert result.values[Variable(151)] == frozenset({1, 2, 3})
    assert Variable(151) in result.always_written

    # By hand: tally[i] = # of the four \ch answers == i (0-based option
    # index, matching pbShowCommands' 0-based return -- inline_choice.py's
    # docstring). x = tally.index(tally.max) (first index at the max,
    # scanning tally left to right); remap {1->0, 0->1} (2 stays 2); then
    # code-122 @list[127 in the PAGE's own list, list-local 77 in this
    # scope] does var151 += 1. So:
    #   argmax_index 1 -> remap 0 -> +1 -> var151 = 1
    #   argmax_index 0 -> remap 1 -> +1 -> var151 = 2  (the all-first-option
    #     main path: tally=[4,0,0], argmax_index=0)
    #   argmax_index 2 -> remap 2 -> +1 -> var151 = 3
    for value in (1, 2, 3):
        witness = result.witnesses[(Variable(151), value)]
        ch_choices = [c for c in witness if c.point.startswith("\\ch var 2 @list[")]
        assert len(ch_choices) == 4, (value, witness)

    main_path = result.witnesses[(Variable(151), 2)]
    ch_only = [c.value for c in main_path if c.point.startswith("\\ch var 2 @list[")]
    assert ch_only == [0, 0, 0, 0]

    # A self-switch flip (code 123 'C') is unconditional in this scope too.
    assert result.values[SelfSwitch(50, 5, "C")] == frozenset({True})
    assert SelfSwitch(50, 5, "C") in result.always_written


# --- section 2: map050/ev019 -- switch 59/60/61, gated on var 151 --------


@pytestmark_corpus
def test_ev019_switch_writes_depend_on_var151():
    """REDERIVATION_PLAN.md's own C8 brief names this row `ev019/b1`, but
    reading the real scope (Map050 event 19 page 0) shows the three
    `$game_switches[59/60/61] = true if $game_variables[151]==N` lines sit
    in the PAGE TRUNK (`map050/ev019/p0`), immediately after the
    `$PokemonGlobal.randomizer` branch's opener command -- not inside
    either of that branch's own arms (`/b0` then, `/b1` else). `/b1`
    instead owns the three `pbAddPokemon(...) if $game_variables[151]==N`
    lines (the starter Pokémon grant) -- a SEPARATE row. Both are searched
    here, each against its own row scope."""
    map_data, event = _map050_event(19)
    page = event["pages"][0]
    trunk = iter_page_scopes(50, event, 0, page)[0]
    assert trunk.row_id == "map050/ev019/p0"

    def read_domain(key):
        # The trunk row is the WHOLE page's top-level content (move routes,
        # the starter-battle rematch dialogue, ...), not just the three
        # switch-write lines -- so this needs a permissive fallback (same
        # shape as the real-corpus gate's `_gate4_read_domain`, section 4
        # below) rather than a strict per-key allowlist. Var 151 is pinned
        # to the value under test; everything else defaults harmlessly.
        if key == Variable(151):
            return frozenset({1, 2, 3})
        if isinstance(key, Variable):
            return frozenset({0})
        if isinstance(key, (Switch, SelfSwitch)):
            # Single-valued (not {False, True}): this trunk row is the
            # WHOLE page's top-level content, and this test only cares
            # about the three switches under test -- a fixed default keeps
            # `result.runs` exactly 3 (one per var-151 value) instead of
            # multiplying by every OTHER switch this row happens to touch.
            return frozenset({False})
        return None

    trunk_result = search_scope(
        trunk.commands,
        map_id=50, event_id=19,
        common_events_by_id=_load_common_events_by_id(),
        stripped_ce_ids=load_stripped_ce_ids(REPO / "reference"),
        read_domain=read_domain,
    )
    assert trunk_result.refusal is None, trunk_result.refusal
    assert trunk_result.runs == 3
    for switch_id in (59, 60, 61):
        key = Switch(switch_id)
        assert trunk_result.values[key] == frozenset({True}), switch_id
        # True in exactly one of the three runs -- not always_written.
        assert key not in trunk_result.always_written

    b1 = _scope_by_suffix(50, event, 0, page, "/b1")
    b1_result = search_scope(
        b1.commands,
        map_id=50, event_id=19,
        common_events_by_id=_load_common_events_by_id(),
        stripped_ce_ids=load_stripped_ce_ids(REPO / "reference"),
        read_domain=read_domain,
    )
    assert b1_result.refusal is None, b1_result.refusal
    assert b1_result.runs == 3
    assert len(b1_result.effects) == 3
    names_and_args = {(e[0].name, e[0].args) for e in b1_result.effects if e}
    assert len(names_and_args) == 3
    assert all(name == "pbAddPokemon" for name, _ in names_and_args)


# --- section 3: synthetic scopes ------------------------------------------


def _cmd(code, params, indent=0):
    return {"code": code, "indent": indent, "parameters": params}


def test_random_write_then_script_read():
    commands = [
        _cmd(122, [5, 5, 0, 2, 1, 3]),  # var5 = random(1..3)
        _cmd(355, ["$game_variables[6]=pbGet(5)+10"]),
    ]
    # Variable(6) is plain-assigned (never genuinely read first) -- the
    # `_Interp.set_key`-always-touches quirk explained on the Bambo test.
    result = search_scope(
        commands, map_id=1, event_id=1, common_events_by_id={},
        stripped_ce_ids=frozenset(),
        read_domain=lambda k: frozenset({0}) if k == Variable(6) else None,
    )
    assert result.refusal is None
    assert result.runs == 3
    assert result.values[Variable(5)] == frozenset({1, 2, 3})
    assert result.values[Variable(6)] == frozenset({11, 12, 13})
    for v, expected in ((1, 11), (2, 12), (3, 13)):
        witness = result.witnesses[(Variable(6), expected)]
        assert any(c.point.startswith("random var") and c.value == v for c in witness)


def test_cap_exceeded_with_thirteen_three_way_choices():
    commands = []
    for i in range(13):
        commands.append(_cmd(101, [f"q{i}"]))
        commands.append(_cmd(401, [f"\\ch[{100+i},0,A,B,C]"]))
    result = search_scope(
        commands, map_id=1, event_id=1, common_events_by_id={},
        stripped_ce_ids=frozenset(), read_domain=lambda k: None, cap=4096,
    )
    assert result.refusal is not None
    assert result.refusal.code == "search_cap"


def test_unknown_read_domain_refuses():
    commands = [_cmd(355, ["$game_variables[9]=pbGet(8)"])]
    result = search_scope(
        commands, map_id=1, event_id=1, common_events_by_id={},
        stripped_ce_ids=frozenset(), read_domain=lambda k: None,
    )
    assert result.refusal is not None
    assert result.refusal.code == "search_unknown_read"


def test_engine_key_read_refuses():
    commands = [_cmd(355, ["$game_variables[9]=1 if $PokemonGlobal.surfing"])]

    def read_domain(key):
        if isinstance(key, EngineKey):
            return None
        return frozenset({True, False})

    result = search_scope(
        commands, map_id=1, event_id=1, common_events_by_id={},
        stripped_ce_ids=frozenset(), read_domain=read_domain,
    )
    assert result.refusal is not None
    assert result.refusal.code == "search_unknown_read"


def test_strip_listed_common_event_call_is_a_noop():
    commands = [_cmd(117, [999]), _cmd(121, [1, 1, 0])]
    result = search_scope(
        commands, map_id=1, event_id=1,
        common_events_by_id={999: {"list": [_cmd(122, [1, 1, 0, 0, 5])]}},
        stripped_ce_ids=frozenset({999}), read_domain=lambda k: None,
    )
    assert result.refusal is None
    assert result.runs == 1
    assert result.values[Switch(1)] == frozenset({True})
    # the CE's own var-1 write never happened (it was stripped -- a no-op).
    assert Variable(1) not in result.values


def test_non_stripped_common_event_inlines_when_branch_free():
    commands = [_cmd(117, [5])]
    result = search_scope(
        commands, map_id=1, event_id=1,
        common_events_by_id={5: {"list": [_cmd(121, [2, 2, 0])]}},
        stripped_ce_ids=frozenset(), read_domain=lambda k: None,
    )
    assert result.refusal is None
    assert result.values[Switch(2)] == frozenset({True})


def test_branching_common_event_refuses():
    commands = [_cmd(117, [7])]
    ce_commands = [_cmd(111, [0, 1, 0], indent=0), _cmd(121, [1, 1, 0], indent=1)]
    result = search_scope(
        commands, map_id=1, event_id=1,
        common_events_by_id={7: {"list": ce_commands}},
        stripped_ce_ids=frozenset(), read_domain=lambda k: None,
    )
    assert result.refusal is not None
    assert result.refusal.code == "search_ce_branches"


def test_loop_with_no_state_writing_body_is_ignored():
    # Any code-355 in a loop body is treated as suspect regardless of its
    # own content (simpler and more conservative than dry-running it to see
    # whether it actually writes) -- so "no state-writing body" here means
    # no 121/122/123/355/117 at all, e.g. a cosmetic move-route/wait command.
    commands = [
        _cmd(112, [], indent=0),
        _cmd(106, [4], indent=1),  # Wait -- no state effect
        _cmd(121, [1, 1, 0]),  # after the loop -- unconditional
    ]
    result = search_scope(
        commands, map_id=1, event_id=1, common_events_by_id={},
        stripped_ce_ids=frozenset(), read_domain=lambda k: None,
    )
    assert result.refusal is None
    assert result.values[Switch(1)] == frozenset({True})


def test_loop_with_state_writing_body_refuses():
    commands = [
        _cmd(112, [], indent=0),
        _cmd(121, [1, 1, 0], indent=1),
    ]
    result = search_scope(
        commands, map_id=1, event_id=1, common_events_by_id={},
        stripped_ce_ids=frozenset(), read_domain=lambda k: None,
    )
    assert result.refusal is not None
    assert result.refusal.code == "search_loop"


def test_branch_opener_in_scope_is_a_noop_not_an_assertion():
    """A row's own scope legitimately contains a nested branch's OPENER
    command (its arm bodies are separate rows) -- e.g. the real
    `map050/ev019/p0` row. Must not be treated as mis-flattened input."""
    commands = [
        _cmd(111, [0, 1, 0], indent=0),  # opener only -- no arm bodies here
        _cmd(121, [1, 1, 0], indent=0),
    ]
    result = search_scope(
        commands, map_id=1, event_id=1, common_events_by_id={},
        stripped_ce_ids=frozenset(), read_domain=lambda k: None,
    )
    assert result.refusal is None
    assert result.values[Switch(1)] == frozenset({True})


def test_closer_code_in_scope_is_an_assertion_failure():
    commands = [_cmd(412, [])]  # BRANCH_END should never appear -- mis-flattened
    with pytest.raises(AssertionError):
        search_scope(
            commands, map_id=1, event_id=1, common_events_by_id={},
            stripped_ce_ids=frozenset(), read_domain=lambda k: None,
        )


# --- section 4: real-corpus measurement gate ------------------------------


def _ch01_ch05_map_ids() -> list[int]:
    chapters = json.loads(CHAPTERS_PATH.read_text(encoding="utf-8"))
    ids: list[int] = []
    for c in chapters["chapters"]:
        if c.get("id") in ("CH01", "CH02", "CH03", "CH04", "CH05"):
            ids.extend(c.get("maps", []))
    return sorted(set(ids))


def _scope_has_script_or_ch(scope) -> bool:
    for cmd in scope.commands:
        code = cmd.get("code")
        if code == 355:
            return True
        if code in (101, 401):
            params = cmd.get("parameters") or [""]
            text = str(params[0]) if params else ""
            if "\\ch[" in text:
                return True
    return False


def _gate4_read_domain(key):
    if isinstance(key, Variable):
        return frozenset({0})
    if isinstance(key, (Switch, SelfSwitch)):
        return frozenset({False, True})
    from rpg2gba.story_state.state import TempSwitch

    if isinstance(key, TempSwitch):
        return frozenset({False, True})
    return None  # EngineKey and anything else -> refuse


# (row_id, refusal_code) -- measured 2026-09-23 against the staged
# CH01-CH05 corpus, every row scope (page trunk or branch arm) that
# directly contains a code-355 script block or a `\ch[...]` text. Pinned so
# a regression shows up as a diff, not a silent count drift (CLAUDE.md §4.2).
# Only party_model remains. The six former `search_unknown_read` rows were
# engine-key WRITES the evaluator used to read before assigning (fixed
# 2026-09-23 in `_Interp.set_key`).
EXPECTED_GATE4_REFUSALS: tuple[tuple[str, str], ...] = (
    ("map050/ev005/p5/b0", "party_model"),
    ("map050/ev005/p5/b1", "party_model"),
    ("map050/ev005/p6", "party_model"),
    ("map050/ev024/p0/b1", "party_model"),
    ("map050/ev027/p0", "party_model"),
    ("map068/ev001/p0/b0", "party_model"),
    ("map068/ev001/p1", "party_model"),
)
EXPECTED_GATE4_SCOPE_COUNT = 326


@pytestmark_corpus
def test_ch01_ch05_search_refusal_set_is_pinned():
    ce_by_id = _load_common_events_by_id()
    stripped = load_stripped_ce_ids(REPO / "reference")
    found: list[tuple[str, str]] = []
    scanned = 0

    for map_id in _ch01_ch05_map_ids():
        path = MAPS_DIR / f"Map{map_id:03d}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data.get("events") or []:
            if event is None:
                continue
            for page_idx, page in enumerate(event.get("pages") or []):
                for scope in iter_page_scopes(map_id, event, page_idx, page):
                    if not _scope_has_script_or_ch(scope):
                        continue
                    scanned += 1
                    result = search_scope(
                        scope.commands,
                        map_id=map_id, event_id=event["id"],
                        common_events_by_id=ce_by_id,
                        stripped_ce_ids=stripped,
                        read_domain=_gate4_read_domain,
                    )
                    if result.refusal is not None:
                        found.append((scope.row_id, result.refusal.code, result.refusal.detail))

    found.sort()
    print(f"\nsearch_scope real-corpus gate: {scanned} scopes scanned, "
          f"{len(found)} refused")
    for row_id, code, detail in found:
        print(f"  {row_id}: {code}: {detail}")

    assert scanned == EXPECTED_GATE4_SCOPE_COUNT
    pinned = tuple((row_id, code) for row_id, code, _detail in found)
    assert pinned == EXPECTED_GATE4_REFUSALS


# --- section 5: determinism ------------------------------------------------


@pytestmark_corpus
def test_bambo_search_is_deterministic():
    map_data, event = _map050_event(5)
    page = event["pages"][0]
    scope = _scope_by_suffix(50, event, 0, page, "/b2")
    kwargs = dict(
        map_id=50, event_id=5,
        common_events_by_id=_load_common_events_by_id(),
        stripped_ce_ids=load_stripped_ce_ids(REPO / "reference"),
        read_domain=lambda key: None,
    )
    r1 = search_scope(scope.commands, **kwargs)
    r2 = search_scope(scope.commands, **kwargs)
    assert r1.runs == r2.runs
    assert r1.values == r2.values
    assert r1.always_written == r2.always_written
    assert r1.witnesses == r2.witnesses
    assert r1.effects == r2.effects
