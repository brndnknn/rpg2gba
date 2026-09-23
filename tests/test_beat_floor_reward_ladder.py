"""Tests for `rpg2gba.beat_floor.reward_ladder` and the `jvGiveReward`
extractor it feeds (REDERIVATION_PLAN.md §16.3 "C8 shape" ruling (e);
`assignments/C8/01_jvgivereward.md`).

These tests were checked against a throwaway reference implementation kept
OUTSIDE this repo (CLAUDE.md §4.1/§4.5 style: fail loud, one source of
truth) -- a failure here means the student's code, not the test.

STATUS: implemented, skipped. DELETE the pytestmark line when you start Task 1.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.beat_floor.assertion import ExtractContext
from rpg2gba.beat_floor.coverage import contradicts
from rpg2gba.beat_floor.reward_ladder import Rung, load_profrewards, rungs_for_variable
from rpg2gba.beat_floor.script import SCRIPT_HEAD_EXTRACTORS, _split_statements, extract_script
from rpg2gba.chapter_atlas.census import _script_head
from rpg2gba.ruby_subset import FixedOracle, evaluate_expression, parse_expression

pytestmark = pytest.mark.skip(reason="assignments/C8/01_jvgivereward.md not started")

REPO = Path(__file__).resolve().parents[1]
SCRIPTS_DUMP_DIR = REPO / "reference" / "scripts_dump"

MAP_ID = 50
EVENT_ID = 5
ROW_ID = "map050/ev005/p0"


def _ctx(row_id: str = ROW_ID, event_id: int = EVENT_ID) -> ExtractContext:
    return ExtractContext(
        map_id=MAP_ID, event_id=event_id, page_idx=0, row_id=row_id,
        event={"id": event_id, "pages": []}, map_data={}, common_events_by_id={},
    )


def _kinds(assertions) -> list[str]:
    return [a.kind for a in assertions]


# --- load_profrewards: table parsing --------------------------------------

def test_load_profrewards_parses_all_twelve_rungs():
    # R1: PROFREWARDS has 12 entries, indices 0-11.
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    assert len(rungs) == 12
    assert [r.index for r in rungs] == list(range(12))


def test_rung_five_is_the_two_item_rung():
    # R1: `[75,SHINYSTONE,DUSKSTONE]` is ONE rung paying TWO items -- not
    # two rungs (the hint's "eight items, seven rungs" warning).
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    rung = rungs[5]
    assert rung.threshold == 75
    assert rung.items == ("SHINYSTONE", "DUSKSTONE")
    assert rung.species is None
    assert rung.is_egg is False


def test_egg_rungs_are_exactly_indices_four_six_eight():
    # R1: the three egg-paying rungs, no more, no fewer.
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    egg_indices = [r.index for r in rungs if r.is_egg]
    assert egg_indices == [4, 6, 8]


def test_rung_eight_species_is_the_literal_starter_sentinel():
    # R1: rung 8's species resolves from switches 59/60/61 at RUNTIME;
    # statically all this module can know is the literal "starter" string.
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    rung = rungs[8]
    assert rung.is_egg is True
    assert rung.species == "starter"
    assert rung.items == ()


def test_rung_zero_pays_nothing():
    # R1: `[0]` -- no reward, not egg, no items.
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    rung = rungs[0]
    assert rung.threshold == 0
    assert rung.items == ()
    assert rung.species is None
    assert rung.is_egg is False


def test_rung_eleven_is_represented_not_dropped():
    # R1: `[999]` is the author's own crash workaround, unreachable in play,
    # but the table has 12 entries and this module must not silently drop
    # one of them (CLAUDE.md §4.5 -- a silently empty/short ladder would
    # misrepresent every index above it too).
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    assert len(rungs) == 12
    rung = rungs[11]
    assert rung.index == 11
    assert rung.threshold == 999
    assert rung.items == ()
    assert rung.species is None
    assert rung.is_egg is False


def test_thresholds_match_source():
    # R1: every threshold, read straight off `213_Bambo_Reward.rb`.
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    assert [r.threshold for r in rungs] == [
        0, 10, 20, 30, 50, 75, 100, 125, 150, 175, 194, 999,
    ]


def test_missing_source_file_raises(tmp_path: Path):
    # R1 docstring: "Raises `FileNotFoundError` if the source is missing."
    with pytest.raises(FileNotFoundError):
        load_profrewards(tmp_path)


def test_unparseable_literal_raises(tmp_path: Path):
    # R1 docstring: "Raises ... `ValueError` if the array literal cannot be
    # parsed -- a silently empty ladder would turn every rung into a no-op."
    bad = tmp_path / "213_Bambo_Reward.rb"
    bad.write_text("PROFREWARDS=[1,,2]\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_profrewards(tmp_path)


# --- rungs_for_variable: narrowing -----------------------------------------

def test_rungs_for_variable_none_is_unconstrained():
    # R2: `values is None` means every reachable rung is possible -- the
    # extractor must not silently narrow to one rung with no evidence.
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    unconstrained = rungs_for_variable(rungs, None)
    assert {r.index for r in unconstrained} == {r.index for r in rungs}


def test_rungs_for_variable_explicit_set_narrows():
    # R2: an explicit frozenset narrows the candidate set to those indices.
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    narrowed = rungs_for_variable(rungs, frozenset({4, 6, 8}))
    assert {r.index for r in narrowed} == {4, 6, 8}
    assert all(r.is_egg for r in narrowed)


def test_rungs_for_variable_single_index_narrows_to_one_rung():
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    narrowed = rungs_for_variable(rungs, frozenset({5}))
    assert [r.index for r in narrowed] == [5]


def test_rungs_for_variable_never_returns_fewer_than_the_constraint_implies():
    # R2 hint: "the safe direction here is to return more rungs, never
    # fewer." Every index named by the constraint must appear in the
    # result; widening the constraint must never shrink the result set.
    rungs = load_profrewards(SCRIPTS_DUMP_DIR)
    narrow = rungs_for_variable(rungs, frozenset({5}))
    wider = rungs_for_variable(rungs, frozenset({4, 5, 6}))
    narrow_indices = {r.index for r in narrow}
    wider_indices = {r.index for r in wider}
    assert narrow_indices <= wider_indices
    for constraint in (frozenset({0}), frozenset({4, 6, 8}), frozenset({11})):
        result_indices = {r.index for r in rungs_for_variable(rungs, constraint)}
        assert constraint <= result_indices


# --- the jvGiveReward extractor (script.py) --------------------------------

def test_jv_give_reward_is_registered():
    assert "jvGiveReward" in SCRIPT_HEAD_EXTRACTORS


# R2 was rewritten (2026-09-23): emitting one assertion per possible rung
# at a single call site is semantically wrong -- `coverage.uncovered()`
# treats a row's floor assertions as a CONJUNCTION ("all of these hold"),
# not a disjunction, and every item-rung assertion here would share the
# same `(row_id, kind, list_index, code)` key, making them pairwise
# `coverage.contradicts()` -- a self-contradicting floor, not merely a weak
# one. R2 now offers three defensible options (refuse precisely / narrow to
# one rung via an extended `ExtractContext` / emit a single disjunctive
# assertion) and the student picks one in Q2. These tests pin only what
# every correct option must share -- they do NOT require any one of the
# three, and do not assert a specific assertion count or a specific set of
# items/species for the bare call.

def test_bare_jv_give_reward_never_self_contradicts():
    # The load-bearing test: whatever the extractor emits for one call
    # site, no two of its own assertions may contradict each other
    # (coverage.contradicts). This is the property that rules out the
    # original "one assertion per rung" design and admits all three of
    # R2's options.
    a, r = extract_script("jvGiveReward", 0, _ctx())
    for i, x in enumerate(a):
        for j, y in enumerate(a):
            if i == j:
                continue
            assert not contradicts(x, y), (x, y)


def test_bare_jv_give_reward_refusal_reason_is_not_the_old_wrong_one():
    # If the chosen design refuses the bare call outright (option: "refuse
    # precisely"), the reason must not be the pre-task misdiagnosis
    # ("...not literal" -- the call IS bare/literal; the problem is which
    # rung fires is ambiguous, a different claim entirely). If the design
    # instead resolves (narrows or emits a disjunctive assertion), there is
    # no refusal at all and this is vacuously true.
    a, r = extract_script("jvGiveReward", 0, _ctx())
    if r:
        assert "not literal" not in r[0].detail


def test_non_bare_jv_give_reward_refuses_non_literal_args():
    # R2: anything other than the bare call still refuses -- this is the
    # one shape the ladder read does NOT cover (arguments would mean a
    # different call entirely; Uranium's own source never passes any).
    # Unchanged by the R2 rewrite -- only the bare-call behaviour was
    # ambiguous.
    a, r = extract_script("jvGiveReward(1)", 0, _ctx())
    assert a == ()
    assert len(r) == 1
    assert r[0].reason == "non_literal_args"
    assert "jvGiveReward" in r[0].detail


def test_jv_give_reward_via_kernel_prefix_matches_bare_call():
    # `Kernel.` normalization applies to this head like every other one in
    # script.py's registry (see the module's own docstring) -- both spellings
    # must dispatch to the same extractor and produce the same shape of
    # result, whichever of R2's three options that extractor implements.
    a1, r1 = extract_script("jvGiveReward", 0, _ctx())
    a2, r2 = extract_script("Kernel.jvGiveReward", 0, _ctx())
    assert len(a1) == len(a2)
    assert [x.reason for x in r1] == [x.reason for x in r2]


# --- guard: jvNextReward still refuses, still names the dex read (R4) -----

def test_jv_next_reward_dex_read_still_refuses_party_model():
    # R4: `jvNextReward` reads `$Trainer.pokedexOwned` -- ruling (b)'s
    # party-model refusal must not regress. This must not become resolvable
    # by accident: if it does, the dex has been modelled, which is out of
    # scope for this task (and for ruling (b) generally).
    node = parse_expression(
        "$Trainer.pokedexOwned >= PROFREWARDS[$game_variables[22]+1][0]"
    )
    value, result = evaluate_expression(node, oracle=FixedOracle(), event=(MAP_ID, EVENT_ID))
    assert value is None
    assert result.refusal is not None
    assert result.refusal.code == "party_model"
    assert "pokedexOwned" in str(result.refusal)


# --- real-corpus coverage (skipped if the staged build isn't present) -----

MAPS_DIR = REPO / "output" / "uranium-build" / "maps"
MAP050_PATH = MAPS_DIR / "Map050.json"

pytestmark_corpus = pytest.mark.skipif(
    not MAP050_PATH.is_file(), reason="output/uranium-build/maps/Map050.json not staged",
)


def _iter_script_and_condition_jv_give_reward_sites(commands):
    """Yields (code, text) for every bare `jvGiveReward` call site in
    `commands` -- both the 355/655 script-block form and the 111 type-12
    condition form."""
    i, n = 0, len(commands)
    while i < n:
        cmd = commands[i]
        code = cmd.get("code")
        if code == 355:
            parts = [str((cmd.get("parameters") or [""])[0])]
            j = i + 1
            while j < n and commands[j].get("code") == 655:
                p = commands[j].get("parameters") or [""]
                parts.append(str(p[0]))
                j += 1
            text = "\n".join(parts)
            for stmt in _split_statements(text):
                if _script_head(stmt) == "jvGiveReward":
                    yield (355, stmt)
            i = j
            continue
        if code == 111:
            params = cmd.get("parameters") or []
            if len(params) >= 2 and params[0] == 12 and str(params[1]).strip() == "jvGiveReward":
                yield (111, params[1])
        i += 1


@pytestmark_corpus
def test_map050_has_eleven_jv_give_reward_call_sites():
    # Measured fact (assignments/C8/README.md): "`jvGiveReward` call sites |
    # 11, all on `Map050`". Measured directly against the staged corpus:
    # of those 11, 7 are bare code-355 script calls (R2's extractor target)
    # and 4 are bare code-111 type-12 conditions (R3's, testing the RETURN
    # VALUE, a different question -- see the task file's R3 note). Both
    # forms are counted here because both are real `jvGiveReward` call
    # sites in the source, even though only the 355 form is this task's
    # R2 extractor.
    data = json.loads(MAP050_PATH.read_text(encoding="utf-8"))
    script_sites: list[str] = []
    condition_sites: list[str] = []
    for event in data.get("events") or []:
        if event is None:
            continue
        for page in event.get("pages") or []:
            for code, text in _iter_script_and_condition_jv_give_reward_sites(
                page.get("list") or []
            ):
                if code == 355:
                    script_sites.append(text)
                else:
                    condition_sites.append(text)
    assert len(script_sites) + len(condition_sites) == 11
    assert len(script_sites) == 7
    assert len(condition_sites) == 4
    for text in script_sites:
        assert text.strip() == "jvGiveReward"


@pytestmark_corpus
def test_map050_script_form_sites_never_self_contradict():
    # Every one of the 7 bare code-355 `jvGiveReward` sites on Map050 must
    # produce an internally consistent result through the real extractor
    # registry -- no two of the assertions emitted for ANY ONE call site
    # may satisfy `coverage.contradicts` (see the extractor tests above for
    # why). This holds regardless of which of R2's three options was
    # implemented, and does not assume the call resolves without refusal.
    data = json.loads(MAP050_PATH.read_text(encoding="utf-8"))
    checked = 0
    for event in data.get("events") or []:
        if event is None:
            continue
        for page in event.get("pages") or []:
            for code, text in _iter_script_and_condition_jv_give_reward_sites(
                page.get("list") or []
            ):
                if code != 355:
                    continue
                a, r = extract_script(text, 0, _ctx())
                for i, x in enumerate(a):
                    for j, y in enumerate(a):
                        if i != j:
                            assert not contradicts(x, y), (text, x, y)
                checked += 1
    assert checked == 7
