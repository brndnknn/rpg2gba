"""Display-only party/dex writes are dropped and havoc'd, not refused
(`story_state.display_vars`, operator ruling 2026-10-15)."""
from __future__ import annotations

import json
from typing import Any

import pytest

from rpg2gba.beat_floor.lookup import default_build_dir
from rpg2gba.ruby_subset.search import search_scope
from rpg2gba.story_state.display_vars import DisplayVarPolicy, display_var_policy, scan_display_policy
from rpg2gba.story_state.state import Variable


def c(code: int, *params: Any, indent: int = 0) -> dict[str, Any]:
    return {"code": code, "indent": indent, "parameters": list(params)}


SEEN = [c(355, "pbSet(2,$Trainer.pokedexSeen)"), c(655, "pbSet(3,$Trainer.pokedexOwned)")]
TEXT = c(101, "you've seen \\r\\v[2]\\c[0] and caught \\r\\v[3]\\c[0]")
POLICY = DisplayVarPolicy(usable=True)


def run(commands, policy=POLICY, ces=None):
    return search_scope(
        commands, map_id=50, event_id=27, common_events_by_id=ces or {},
        stripped_ce_ids=frozenset(), read_domain=lambda k: None,
        display_write_ok=policy.write_ok if policy else None)


def test_display_only_write_is_havoc_not_refusal():
    r = run(SEEN + [TEXT, c(0)])
    assert r.refusal is None
    assert {Variable(2), Variable(3)} <= r.havoc


def test_without_policy_still_refuses():
    r = run(SEEN + [TEXT, c(0)], policy=None)
    assert r.refusal is not None and r.refusal.code == "party_model"


def test_unusable_policy_refuses():
    assert run(SEEN + [TEXT], policy=DisplayVarPolicy()).refusal.code == "party_model"


def test_conditional_read_after_write_refuses():
    cmds = SEEN + [TEXT, c(122, 5, 5, 0, 1, 2), c(0)]  # var5 = var2
    assert run(cmds).refusal.code == "party_model"


def test_script_read_after_write_refuses():
    cmds = SEEN + [TEXT, c(355, "x = pbGet(3)")]
    assert run(cmds).refusal.code == "party_model"


def test_text_code_in_script_string_is_a_read():
    cmds = SEEN + [c(355, "Kernel.pbMessage(\"\\\\v[2]\")")]
    assert run(cmds).refusal.code == "party_model"


def test_rewrite_ends_window():
    cmds = SEEN + [c(355, "pbSet(2,0)"), c(355, "pbSet(3,0)"), c(122, 5, 5, 0, 1, 2), c(0)]
    assert run(cmds).refusal is None


def test_ce_that_reads_var_refuses():
    ce = {7: {"id": 7, "list": [c(122, 5, 5, 0, 1, 2), c(0)]}}
    policy = scan_display_policy(list(ce.values()))
    assert run(SEEN + [c(117, 7)], policy=policy, ces=ce).refusal.code == "party_model"
    quiet = {8: {"id": 8, "list": [c(101, "hi"), c(0)]}}
    ok = scan_display_policy(list(quiet.values()))
    assert run(SEEN + [c(117, 8), TEXT], policy=ok, ces=quiet).refusal is None


def test_ruby_method_reading_var_refuses():
    policy = scan_display_policy([], ["def shopPrice\n  p = pbGet(2)\nend\n"])
    assert run(SEEN + [c(355, "shopPrice")], policy=policy).refusal.code == "party_model"


def test_loops_never_exempt():
    assert run(SEEN + [TEXT, c(118, "A")]).refusal.code == "party_model"


def test_profrewards_display_write_exempt():
    cmds = [c(355, "pbSet(1,PROFREWARDS[pbGet(22)+1][0])"),
            c(101, "When you catch \\r\\v[1]\\c[0] Pokémon"), c(0)]
    r = run(cmds)
    assert r.refusal is None and Variable(1) in r.havoc


def test_game_variables_form():
    cmds = [c(355, "$game_variables[2]=$Trainer.pokedexSeen"), TEXT, c(0)]
    assert run(cmds).refusal is None


def test_non_party_writes_unchanged():
    # no party read -> not routed through the exemption at all
    assert run([c(355, "pbSet(2,5)"), c(0)]).refusal is None


MAP050 = default_build_dir() / "maps" / "Map050.json"


@pytest.mark.skipif(not MAP050.is_file(), reason="corpus not staged")
def test_map050_ev027_and_ev005_no_longer_party_model():
    from rpg2gba.story_state.extract import extract_map

    root = default_build_dir()
    m = json.loads(MAP050.read_text(encoding="utf-8"))
    ces = [x for x in json.loads((root / "common_events.json").read_text(encoding="utf-8")) if x]
    rows = extract_map(50, m, common_events=ces, switch_labels={})
    bad = [k for k, r in rows.items()
           if k.startswith(("map050/ev027/", "map050/ev005/"))
           and any(x.code == "party_model" for x in tuple(r.refusals) + tuple(r.page_refusals))]
    assert not bad
    assert display_var_policy().usable
