"""Pokédex-count text (Map050 EV027 / EV005) and Bambo's PROFREWARDS ladder.

Real Map050 events are driven through the transpiler (skipped when the
deserialized map JSON is absent); the fail-loud variants are synthetic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import deterministic, poryscript
from rpg2gba.conversion_agent import transpile_driver as D
from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "reference"
BUILD = ROOT / "output" / "uranium-build"
MAP50 = BUILD / "maps" / "Map050.json"
MAP_ID = 50


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def make_ctx(*, stage_all: bool = True) -> T.TranspileContext:
    reg = FlagRegistry()
    reg.seed_labels(REF / "uranium_switches.json", REF / "uranium_variables.json")
    species = D._load_species_id_map(REF)
    ctx = T.TranspileContext(
        registry=reg,
        species=species,
        item_id_map=D._load_item_id_map(REF),
        vanilla_species=D._load_vanilla_species(REF),
    )
    ctx.items = deterministic.load_context(
        reference_dir=REF, intermediate_dir=BUILD / "intermediate").items
    ctx.starter_scene = T._load_starter_selector_scene(REF)
    if stage_all:
        ctx.staged_species = frozenset(species.values())
    return ctx


def real_event(event_id: int) -> dict:
    if not MAP50.is_file():
        pytest.skip("Map050.json not deserialized")
    events = json.loads(MAP50.read_text(encoding="utf-8"))["events"]
    events = events.values() if isinstance(events, dict) else events
    return next(e for e in events if e and e["id"] == event_id)


def run_real(event_id: int, ctx: T.TranspileContext) -> T.TranspiledEvent:
    return T.transpile_event(MAP_ID, real_event(event_id), ctx)


def run_cmds(cmds: list[dict], ctx: T.TranspileContext) -> T.TranspiledEvent:
    ev = {"id": 77, "name": "t", "x": 0, "y": 0,
          "pages": [{"trigger": 0, "list": [*cmds, cmd(0)]}]}
    return T.transpile_event(MAP_ID, ev, ctx)


def ss(text: str, code: int = 355) -> dict:
    return cmd(code, [text])


# -- the table ------------------------------------------------------------------

def test_profrewards_table_parsed_from_source():
    t = T._load_profrewards()
    assert [r.threshold for r in t.rungs] == [0, 10, 20, 30, 50, 75, 100, 125, 150, 175, 194, 999]
    assert t.rungs[4].payload == (("species", "MINICORN"),)
    assert t.rungs[5].payload == (("item", "SHINYSTONE"), ("item", "DUSKSTONE"))
    assert t.rungs[8].payload == (("starter", "starter"),)
    assert t.starter_switches == ((1, 60), (3, 61), (5, 59))


# -- EV027: lab scene -----------------------------------------------------------

def test_ev027_dex_counts_and_pokeballs():
    ctx = make_ctx()
    out = run_real(27, ctx)
    assert out.unhandled == []
    text = out.text
    assert text.count("special(ScriptGetPokedexInfo)") == 1  # consecutive rows share one call
    assert "setvar(VAR_0x8004, 1)" in text
    assert "buffernumberstring(STR_VAR_1, VAR_0x8005)" in text
    assert "buffernumberstring(STR_VAR_2, VAR_0x8006)" in text
    assert "you've seen {STR_VAR_1} Pokémon and caught {STR_VAR_2} of them" in text
    assert "giveitem(ITEM_POKE_BALL, 10)" in text
    assert "\\v[" not in text and "§" not in text


# -- EV005: Bambo ---------------------------------------------------------------

def test_ev005_ladder_emits_everything_when_resolvable():
    ctx = make_ctx()
    out = run_real(5, ctx)
    ladder_rows = [u for u in out.unhandled if u.page in (5, 6, 7)]
    assert ladder_rows == [], ladder_rows
    text = out.text
    # phone registration is a documented no-op (PROJECT_TODO #142)
    assert "pbPhoneRegisterNPC stripped" in text
    # jvNextReward unrolled over VAR_BAMBO_REWARD (var 22), 999 sentinel absent
    assert "if (var(VAR_0x8006) >= 10) {" in text
    assert "if (var(VAR_0x8006) >= 194) {" in text
    assert ">= 999" not in text
    # the threshold shown to the player (var 1) is set per rung
    assert "setvar(VAR_TEMP_POKEMON_CHOICE, 10)" in text
    assert "setvar(VAR_TEMP_POKEMON_CHOICE, 999)" in text
    # reward routine: items, eggs with a party-full guard
    for const in ("ITEM_RARE_CANDY", "ITEM_PP_UP", "ITEM_TM90", "ITEM_SHINY_STONE",
                  "ITEM_DUSK_STONE", "ITEM_TM89", "ITEM_OVAL_CHARM", "ITEM_SHINY_CHARM"):
        assert f"giveitem({const})" in text
    for const in ("SPECIES_MINICORN", "SPECIES_LUXI", "SPECIES_ORCHYNX",
                  "SPECIES_RAPTORCH", "SPECIES_ELETUX"):
        assert f"giveegg({const})" in text
    assert "if (var(VAR_RESULT) >= PARTY_SIZE) {" in text
    # starter egg: later source assignment wins (59 over 61 over 60)
    assert text.index("flag(FLAG_HAS_RAPTORCH)") < text.index("flag(FLAG_HAS_ORCHYNX)") \
        < text.index("flag(FLAG_HAS_ELETUX)")
    # page 6 (retry page): party-full arm leaves the self-switch alone, success clears it
    p6 = text[text.index("script Map050_EV005_Page7 {"):]
    assert "clearflag(FLAG_MAP050_EVENT005_SSA)" in p6
    assert "call(Map050_EV005_Page7_BamboGiveReward)" in p6


def test_ev005_unresolvable_rung_queues_not_silently_defaults():
    ctx = make_ctx(stage_all=False)  # no species staged -> egg rungs cannot resolve
    out = run_real(5, ctx)
    msgs = [u.description for u in out.unhandled if u.page in (5, 6)]
    assert any("rung 4" in m and "MINICORN" in m for m in msgs)
    assert any("rung 6" in m and "LUXI" in m or "rung 6" in m for m in msgs)
    assert "giveegg(SPECIES_MINICORN)" not in out.text


@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_map050_ev005_and_ev027_compile():
    ctx = make_ctx()
    # Only the blocks this change owns: the starter-test blocks elsewhere in
    # EV005 carry escaped quotes this poryscript build's format() rejects
    # (pre-existing, unrelated).
    keep = ("EV005_Page6", "EV005_Page7", "EV005_Page8", "EV027")
    blocks = (run_real(5, ctx).text + "\n\n" + run_real(27, ctx).text).split("\n\n")
    text = "\n\n".join(b for b in blocks if any(k in "\n".join(b.splitlines()[:2]) for k in keep))
    assert "BamboGiveReward" in text and "jvNextReward" in text and "MAP050_EVENT027" in text
    result = poryscript.compile_script(text)
    assert result.ok, result.stderr


# -- fail loud ------------------------------------------------------------------

def test_uncomputed_dex_shapes_still_queue():
    ctx = make_ctx()
    out = run_cmds([ss("pbSet(2,$Trainer.pokedexSeen+1)")], ctx)
    assert len(out.unhandled) == 1


def test_untracked_value_var_text_still_queues():
    ctx = make_ctx()
    out = run_cmds([ss("pbSet(2,$Trainer.pokedexSeen)"),
                    cmd(101, ["You have \\v[5] things"])], ctx)
    assert any(u.command_code == 101 for u in out.unhandled)


def test_stray_red_code_not_swallowed():
    ctx = make_ctx()
    out = run_cmds([ss("pbSet(2,$Trainer.pokedexSeen)"),
                    cmd(101, ["\\rDanger\\c[0] seen \\v[2]"])], ctx)
    assert any(u.command_code == 101 for u in out.unhandled)


def test_jvnextreward_bare_statement_queues():
    ctx = make_ctx()
    out = run_cmds([ss("jvNextReward")], ctx)
    assert len(out.unhandled) == 1


def test_red_code_before_count_is_dropped():
    ctx = make_ctx()
    out = run_cmds([ss("pbSet(3,$Trainer.pokedexOwned)"),
                    cmd(101, ["caught \\r\\v[3]\\c[0] of them"])], ctx)
    assert out.unhandled == []
    assert "buffernumberstring(STR_VAR_1, VAR_0x8006)" in out.text
    assert "caught {STR_VAR_1} of them" in out.text
