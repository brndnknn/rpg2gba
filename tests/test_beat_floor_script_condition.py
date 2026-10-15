"""Tests for `rpg2gba.beat_floor.script` and `rpg2gba.beat_floor.condition`
(REDERIVATION_PLAN.md §16.3 C4).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.beat_floor.assertion import ExtractContext
from rpg2gba.beat_floor.condition import CONDITION_FAMILY_EXTRACTORS, extract_condition
from rpg2gba.beat_floor.script import SCRIPT_HEAD_EXTRACTORS, _split_statements, extract_script
from rpg2gba.chapter_atlas.census import _script_head
from rpg2gba.chapter_manifest.conditions import classify_condition

MAP_ID = 1
EVENT_ID = 5
ROW_ID = "map001/ev005/p0"


def _ctx(row_id: str = ROW_ID, event_id: int = EVENT_ID) -> ExtractContext:
    return ExtractContext(
        map_id=MAP_ID, event_id=event_id, page_idx=0, row_id=row_id,
        event={"id": event_id, "pages": []}, map_data={}, common_events_by_id={},
    )


def _kinds(assertions) -> list[str]:
    return [a.kind for a in assertions]


# --- extract_script: statement splitting --------------------------------

def test_split_statements_keeps_multiline_call_together():
    text = 'pbPokemonMart([\nPBItems::POKeBALL,\nPBItems::POTION,\nPBItems::ANTIDOTE])'
    assert _split_statements(text) == [text]


def test_split_statements_keeps_wrapped_string_argument_together():
    text = (
        'pbPhoneRegisterBattle(_I("Hey, you up for a rematch?\n'
        'Hook me up on PokePod if you want to battle again!"),'
        'get_character(0),PBTrainers::FISHERMAN,"Brandon",2)'
    )
    assert _split_statements(text) == [text]


def test_split_statements_splits_sequential_calls():
    text = 'pbNoticePlayer(event)\npbTrainerIntro(:X)\nsetTempSwitchOn("A")'
    assert _split_statements(text) == [
        "pbNoticePlayer(event)", "pbTrainerIntro(:X)", 'setTempSwitchOn("A")',
    ]


def test_split_statements_drops_blank_lines():
    assert _split_statements("pbSave\n\n\npbSave") == ["pbSave", "pbSave"]


# --- extract_script: per-category behaviour ------------------------------

def test_unknown_head_refuses_row():
    a, r = extract_script("someTotallyUnknownCall(1,2)", 3, _ctx())
    assert a == ()
    assert len(r) == 1
    assert r[0].reason == "unknown_script_head"
    assert r[0].row_id == ROW_ID
    assert r[0].list_index == 3
    assert r[0].code == 355


def test_unparseable_block_refuses_row():
    # C8 stage 5: a block outside the Ruby subset refuses as a whole, by
    # name -- still refused, not silently skipped.
    a, r = extract_script("+=1", 0, _ctx())
    assert a == ()
    assert len(r) == 1
    assert r[0].reason == "ruby_parse_error"


def test_visual_head_asserts_visual_and_nothing_else():
    a, r = extract_script("pbCallBub(0,0,0)", 2, _ctx())
    assert r == ()
    assert _kinds(a) == ["visual"]
    assert a[0].param("detail") == "pbCallBub"
    assert a[0].tag == "visual"
    assert a[0].offline is True


def test_audio_head_asserts_audio():
    a, r = extract_script("pbTrainerIntro(:YOUNGSTER)", 0, _ctx())
    assert r == ()
    assert _kinds(a) == ["audio"]
    assert a[0].tag == "audio"


def test_state_write_head_asserts_nothing():
    a, r = extract_script('setTempSwitchOn("A")', 0, _ctx())
    assert a == ()
    assert r == ()
    a, r = extract_script("pbSetSelfSwitch(3, \"B\", true)", 0, _ctx())
    assert a == ()
    assert r == ()
    a, r = extract_script("pbGet(151)", 0, _ctx())
    assert a == ()
    assert r == ()


def test_erase_this_event_asserts_erase_event_with_ctx_event_id():
    a, r = extract_script("pbEraseThisEvent", 4, _ctx(event_id=42))
    assert r == ()
    assert _kinds(a) == ["erase_event"]
    assert a[0].param("event_id") == 42


def test_receive_item_literal_asserts_item_grant():
    a, r = extract_script("Kernel.pbReceiveItem(::PBItems::REVIVE)", 0, _ctx())
    assert r == ()
    assert _kinds(a) == ["item_grant"]
    assert a[0].param("item") == "REVIVE"
    assert a[0].param("quantity") == 1


def test_receive_item_with_quantity():
    a, r = extract_script("Kernel.pbReceiveItem(::PBItems::POKeBALL,10)", 0, _ctx())
    assert a[0].param("quantity") == 10


def test_receive_item_non_literal_refuses():
    a, r = extract_script("Kernel.pbReceiveItem(pbGet(1))", 0, _ctx())
    assert a == ()
    assert len(r) == 1
    assert r[0].reason == "non_literal_args"


def test_add_pokemon_literal_asserts_pokemon_grant():
    a, r = extract_script("Kernel.pbAddPokemon(::PBSpecies::RAPTORCH,5)", 0, _ctx())
    assert r == ()
    assert _kinds(a) == ["pokemon_grant"]
    assert a[0].param("species") == "RAPTORCH"
    assert a[0].param("level") == 5


def test_add_pokemon_non_literal_refuses():
    a, r = extract_script("Kernel.pbAddPokemon(pbGet(151),5)", 0, _ctx())
    assert a == ()
    assert len(r) == 1
    assert r[0].reason == "non_literal_args"


def test_pokemon_mart_literal_asserts_service_with_items():
    a, r = extract_script(
        "pbPokemonMart([\nPBItems::POKeBALL,\nPBItems::POTION])", 0, _ctx(),
    )
    assert r == ()
    assert _kinds(a) == ["service"]
    assert a[0].param("name") == "mart"
    assert a[0].param("items") == ("POKeBALL", "POTION")


def test_custom_trainer_battle_refuses_non_literal():
    # The corpus shape: the local is built earlier in the same block.
    text = (
        'trainer = createPhoneTrainer(PBTrainers::BIRDKEEPER,"Brent",0)\n'
        'result = customTrainerBattle(trainer, "Oh no!")'
    )
    a, r = extract_script(text, 0, _ctx())
    assert a == ()
    assert len(r) == 1
    assert r[0].reason == "non_literal_args"


def test_service_heads_assert_service_kind():
    for stmt, name in (
        ("pbShowMap", "region_map"),
        ("pbBerryPlant", "berry_plant"),
        ("pbPhoneRegisterBattle(nil,get_character(0),PBTrainers::X,\"N\",2)", "phone_register"),
        ("pbSave", "save"),
        ("pbPokeCenterPC", "pc"),
        ("pbTrainerPC", "pc"),
        ("pbStarterSelector(1,true)", "starter_select"),
        ("pbChooseNuclearCurePokemon(1,3)", "nuclear_cure"),
        ("GTS.open", "online_gts"),
    ):
        a, r = extract_script(stmt, 0, _ctx())
        assert r == (), (stmt, r)
        assert _kinds(a) == ["service"], stmt
        assert a[0].param("name") == name
        assert a[0].tag == "service"
        assert a[0].offline is False


def test_set_pokemon_center_asserts_nothing():
    a, r = extract_script("Kernel.pbSetPokemonCenter", 0, _ctx())
    assert a == ()
    assert r == ()


def test_system_head_refuses_unknown_script_head():
    a, r = extract_script('system("start http://showdown.pokemonuranium.org")', 0, _ctx())
    assert a == ()
    assert len(r) == 1
    assert r[0].reason == "unknown_script_head"


def test_jv_give_reward_refuses_one_of_n_grant():
    # C8 stage 7 task 1: was `non_literal_args`, a misdiagnosis -- var 22 is
    # modelled; the real obstruction is the floor's lack of a one-of-N kind.
    a, r = extract_script("jvGiveReward", 0, _ctx())
    assert a == ()
    assert len(r) == 1
    assert r[0].reason == "one_of_n_grant"


def test_transfer_player_resolves_this_map_and_literal_xy():
    a, r = extract_script("Kernel.pbTransferPlayer($game_map.map_id,5,5)", 0, _ctx())
    assert r == ()
    assert _kinds(a) == ["warp"]
    assert a[0].param("map_id") == MAP_ID
    assert a[0].param("x") == 5
    assert a[0].param("y") == 5
    assert a[0].param("direction") is None


def test_mixed_head_block_covers_every_line():
    text = 'pbNoticePlayer(get_character(0))\npbTrainerIntro(:X)\nsetTempSwitchOn("A")'
    a, r = extract_script(text, 0, _ctx())
    assert r == ()
    assert sorted(_kinds(a)) == ["audio", "visual"]


def test_mixed_head_block_one_bad_line_refuses_only_that_line():
    text = 'pbCallBub(0,0,0)\nsomeUnknownThing(1)\npbEraseThisEvent'
    a, r = extract_script(text, 0, _ctx())
    assert sorted(_kinds(a)) == ["erase_event", "visual"]
    assert len(r) == 1
    assert r[0].reason == "unknown_script_head"
    assert "someUnknownThing" in r[0].detail


def test_every_script_extractor_registered_is_callable():
    ctx = _ctx()
    for head, extractor in SCRIPT_HEAD_EXTRACTORS.items():
        # Smoke-call every extractor with a bare head-only line; extractors
        # that need real args (item/trainer/species literals) will refuse,
        # not crash -- this only proves the dict's values are all valid
        # `ScriptHeadExtractor`s.
        extractor(head, 0, ctx)


# --- extract_condition ---------------------------------------------------

def test_unclassified_condition_refuses():
    a, r = extract_condition("!$lobbyreset", 0, _ctx())
    assert a == ()
    assert len(r) == 1
    assert r[0].reason == "unclassified_condition"


def test_pure_predicate_family_asserts_nothing():
    a, r = extract_condition("get_character(0).onEvent?", 0, _ctx())
    assert a == ()
    assert r == ()
    a, r = extract_condition("$game_player.x==17", 0, _ctx())
    assert a == ()
    assert r == ()


def test_pb_item_ball_asserts_item_grant():
    a, r = extract_condition("Kernel.pbItemBall(::PBItems::REVIVE)", 0, _ctx())
    assert r == ()
    assert a[0].kind == "item_grant"
    assert a[0].param("item") == "REVIVE"


def test_pb_trainer_battle_asserts_battle_with_literal_identity():
    text = (
        'pbTrainerBattle(PBTrainers::YOUNGSTER,"Bob",'
        '_I("I guess I will try new games."),false,0)'
    )
    a, r = extract_condition(text, 0, _ctx())
    assert r == ()
    assert a[0].kind == "battle"
    assert a[0].param("kind") == "trainer"
    assert a[0].param("trainer_type") == "YOUNGSTER"
    assert a[0].param("name") == "Bob"


def test_pb_rock_smash_asserts_visual():
    a, r = extract_condition("Kernel.pbRockSmash", 0, _ctx())
    assert r == ()
    assert a[0].kind == "visual"


def test_pb_pick_berry_asserts_item_grant():
    a, r = extract_condition("pbPickBerry(PBItems::ORANBERRY,2)", 0, _ctx())
    assert r == ()
    assert a[0].kind == "item_grant"
    assert a[0].param("item") == "ORANBERRY"
    assert a[0].param("quantity") == 2


def test_jv_give_reward_family_refuses_give_but_not_next():
    # C8 stage 7 task 1: the condition tests pbReceiveItem's bag-space
    # success, not which rung fired.
    a, r = extract_condition("jvGiveReward", 0, _ctx())
    assert a == ()
    assert len(r) == 1
    assert r[0].reason == "bag_capacity_unmodelled"
    a, r = extract_condition("jvNextReward", 0, _ctx())
    assert a == ()
    assert r == ()


def test_every_family_has_an_extractor():
    from rpg2gba.chapter_manifest.conditions import FAMILIES
    names = {f.name for f in FAMILIES}
    assert names <= set(CONDITION_FAMILY_EXTRACTORS)


def test_every_condition_extractor_registered_is_callable():
    ctx = _ctx()
    samples = {
        "pb_trainer_battle": 'pbTrainerBattle(PBTrainers::YOUNGSTER,"Bob",_I("x"),false,0)',
        "pb_wild_battle": "pbWildBattle(PBSpecies::LINKITE,38)",
        "pb_item_ball": "Kernel.pbItemBall(::PBItems::REVIVE)",
        "pb_receive_item": "Kernel.pbReceiveItem(::PBItems::REVIVE)",
        "pb_rock_smash": "Kernel.pbRockSmash",
        "pb_pick_berry": "pbPickBerry(PBItems::ORANBERRY,2)",
        "uranium_jv_give_reward": "jvGiveReward",
    }
    for name, extractor in CONDITION_FAMILY_EXTRACTORS.items():
        extractor(samples.get(name, name), 0, ctx)


# --- real-corpus coverage (skipped if the staged build isn't present) ----

REPO = Path(__file__).resolve().parents[1]
MAPS_DIR = REPO / "output" / "uranium-build" / "maps"
COMMON_EVENTS_PATH = REPO / "output" / "uranium-build" / "common_events.json"
CHAPTERS_PATH = REPO / "reference" / "chapters.json"

pytestmark_corpus = pytest.mark.skipif(
    not MAPS_DIR.is_dir(), reason="output/uranium-build/maps not staged",
)


def _ch01_ch05_map_ids() -> list[int]:
    chapters = json.loads(CHAPTERS_PATH.read_text(encoding="utf-8"))
    ids: list[int] = []
    for c in chapters["chapters"]:
        if c.get("id") in ("CH01", "CH02", "CH03", "CH04", "CH05"):
            ids.extend(c.get("maps", []))
    return sorted(set(ids))


def _load_common_events_by_id() -> dict[int, dict]:
    if not COMMON_EVENTS_PATH.exists():
        return {}
    data = json.loads(COMMON_EVENTS_PATH.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {ce["id"]: ce for ce in data if ce}
    return {int(k): v for k, v in data.items()}


def _iter_script_blocks_and_conditions(commands, ce_by_id, visited_ce):
    """Yields (kind, text) for every 355/655 block and 111 type-12 condition
    in `commands`, inlining 117-called common events once each (mirrors
    `story_state.extract`'s own inlining discipline)."""
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
            yield ("script", "\n".join(parts))
            i = j
            continue
        if code == 111:
            params = cmd.get("parameters") or []
            if len(params) >= 2 and params[0] == 12:
                yield ("condition", params[1])
        if code == 117:
            params = cmd.get("parameters") or []
            if params and params[0] in ce_by_id and params[0] not in visited_ce:
                visited_ce.add(params[0])
                yield from _iter_script_blocks_and_conditions(
                    ce_by_id[params[0]].get("list") or [], ce_by_id, visited_ce)
        i += 1


# Genuine embedded Ruby control flow (`for ... end`, `if ... elsif ... end`,
# a loop variable used bare) and the seenStorageCreator split-assignment's
# bare `true` continuation (transpiler._SEEN_STORAGE_CREATOR_OPEN_RE) --
# real statement-level fragments once split by `_split_statements`, not call
# heads at all. Interpreting these is R10/C8's Ruby-subset interpreter, not
# C4's generic floor (R11); `unknown_script_head` is their correct, expected
# disposition. Measured 2026-09-16 against the staged CH01-CH05 corpus
# (`for i in 14..18 / pbSetSelfSwitch(i,"A",true) / end` and
# `for i in $Trainer.party / i.nuzlocke_heal / end`).
_KNOWN_EMBEDDED_RUBY_FRAGMENTS = frozenset({
    "elsif", "end", "for", "if", "true", "x", "i.nuzlocke_heal",
})

# `system(...)` (Kernel#system, a shell-out -- opens a URL, not presentation
# of anything in-game) is deliberately unregistered so it refuses
# `unknown_script_head` rather than being mapped to a kind that doesn't fit
# (lead review 2026-09-16).
_KNOWN_UNREGISTERED_HEADS = frozenset({"system"})


@pytestmark_corpus
def test_every_ch01_ch05_script_head_has_an_extractor():
    ce_by_id = _load_common_events_by_id()
    missing: set[str] = set()
    for map_id in _ch01_ch05_map_ids():
        path = MAPS_DIR / f"Map{map_id:03d}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data.get("events") or []:
            if event is None:
                continue
            for page in event.get("pages") or []:
                visited_ce: set[int] = set()
                for kind, text in _iter_script_blocks_and_conditions(
                    page.get("list") or [], ce_by_id, visited_ce,
                ):
                    if kind != "script":
                        continue
                    for stmt in _split_statements(text):
                        head = _script_head(stmt)
                        if head is None:
                            continue  # unknown_script_head is a real, expected refusal
                        if head not in SCRIPT_HEAD_EXTRACTORS:
                            missing.add(head)
    unexpected = missing - _KNOWN_EMBEDDED_RUBY_FRAGMENTS - _KNOWN_UNREGISTERED_HEADS
    assert not unexpected, f"script heads with no extractor: {sorted(unexpected)}"


@pytestmark_corpus
def test_every_ch01_ch05_classified_condition_family_has_an_extractor():
    ce_by_id = _load_common_events_by_id()
    missing: set[str] = set()
    for map_id in _ch01_ch05_map_ids():
        path = MAPS_DIR / f"Map{map_id:03d}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data.get("events") or []:
            if event is None:
                continue
            for page in event.get("pages") or []:
                visited_ce: set[int] = set()
                for kind, text in _iter_script_blocks_and_conditions(
                    page.get("list") or [], ce_by_id, visited_ce,
                ):
                    if kind != "condition":
                        continue
                    family = classify_condition(text)
                    if family is not None and family.name not in CONDITION_FAMILY_EXTRACTORS:
                        missing.add(family.name)
    assert not missing, f"condition families with no extractor: {sorted(missing)}"
