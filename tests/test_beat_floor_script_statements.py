"""C8 stage 5: beat_floor/script.py classifies whole parsed statements.

Each case is a statement shape the old split-and-read-the-head scheme got
wrong in one direction or the other: control flow it shredded into refused
fragments, or a chained expression it read as a harmless getter.
"""
from rpg2gba.beat_floor.assertion import ExtractContext
from rpg2gba.beat_floor.script import extract_script
from rpg2gba.ruby_subset import builtins as bi
from rpg2gba.ruby_subset import FixedOracle, evaluate_expression, parse_expression

MAP_ID = 50
ROW_ID = "map050/ev005/p0"


def _ctx() -> ExtractContext:
    return ExtractContext(
        map_id=MAP_ID, event_id=5, page_idx=0, row_id=ROW_ID,
        event={}, map_data={}, common_events_by_id={}, door_cells={},
    )


def _reasons(text: str) -> list[str]:
    _, r = extract_script(text, 0, _ctx())
    return [x.reason for x in r]


# --- silent: only modelled state and locals change -------------------------

BAMBO_TALLY = (
    "x=pbGet(151).index(pbGet(151).max)\n"
    "if x==1\nx=0\nelsif x==0\nx=1\nend\n"
    "$game_variables[151]=x\n"
    "pbStarterSelector(x,true)"
)


def test_bambo_tally_block_is_silent_except_the_selector_service():
    # Old scheme: six unknown_script_head refusals (if/elsif/end fragments).
    a, r = extract_script(BAMBO_TALLY, 0, _ctx())
    assert r == ()
    assert [x.kind for x in a] == ["service"]
    assert a[0].param("name") == "starter_select"


def test_argmax_alone_is_silent_not_a_getter_misread():
    assert _reasons("x=pbGet(151).index(pbGet(151).max)") == []


def test_state_write_loop_is_silent():
    assert _reasons('for i in 14..18\n   pbSetSelfSwitch(i,"A",true)\nend') == []


def test_nuzlocke_party_loop_is_silent():
    assert _reasons("for i in $Trainer.party\n  i.nuzlocke_heal\nend") == []


def test_postfix_conditional_state_write_is_silent():
    assert _reasons("$game_switches[61] = true if $game_variables[151]==1") == []


def test_engine_attribute_write_is_silent_here():
    # Silent in the script extractor: story_state's EngineKey write becomes
    # the row's `engine_flag_write` (walk.py), pinned in
    # test_beat_floor_engine_flag_write.py. Old scheme: the split-row `true`
    # continuation refused as a head.
    assert _reasons("$PokemonGlobal.seenStorageCreator=\ntrue") == []
    assert _reasons("$Trainer.pokedex=true") == []


def test_redraw_hint_write_is_silent():
    assert _reasons("$game_map.need_refresh=true") == []


def test_in_place_array_mutation_is_silent():
    assert _reasons("pbGet(151)[pbGet(2)]+=1") == []


def test_party_read_into_a_variable_is_left_to_story_state():
    # Silent here; story_state refuses the row party_model itself.
    assert _reasons("$game_variables[43]=$Trainer.party.length") == []


# --- refusals, by name --------------------------------------------------------

def test_asserting_effect_under_control_flow_refuses():
    assert _reasons("pbReceiveItem(PBItems::POTION) if $game_switches[1]") == [
        "conditional_script_effect",
    ]


def test_input_in_a_condition_refuses():
    text = 'if pbConfirmMessage("Sure?")\n$game_switches[1]=true\nend'
    assert _reasons(text) == ["script_input"]


def test_effect_nested_in_an_argument_refuses():
    assert _reasons("pbCallBub(pbReceiveItem(PBItems::POTION))") == ["nested_script_effect"]


def test_unknown_call_nested_in_control_flow_refuses():
    assert _reasons("if x==1\nsomeUnknownThing\nend") == ["unknown_script_head"]


def test_party_member_attribute_write_refuses():
    assert _reasons("$Trainer.party[0].nuclearFree=true") == ["unmodelled_attribute_write"]


def test_untracked_global_write_refuses():
    assert _reasons("$lobbyreset=true") == ["unmodelled_global_write"]


def test_one_bad_statement_refuses_only_itself():
    a, r = extract_script("pbCallBub(2)\n$lobbyreset=true\npbEraseThisEvent", 0, _ctx())
    assert sorted(x.kind for x in a) == ["erase_event", "visual"]
    assert [x.reason for x in r] == ["unmodelled_global_write"]


# --- the pure-read table agrees with the evaluator -------------------------

def test_every_state_read_call_evaluates_without_effect_or_unknown_call():
    # STATE_READ_CALLS mirrors code branches in evaluate._dispatch_head; pin
    # that each really is a pure read there, so the two cannot drift.
    samples = {
        "pbGet": "pbGet(1)",
        "tsOn?": 'tsOn?("A")',
        "tsOff?": 'tsOff?("A")',
        "_I": '_I("x")',
        "$game_map.map_id": "$game_map.map_id",
        "$game_player.x": "$game_player.x",
        "$game_player.y": "$game_player.y",
        "$PokemonBag.pbQuantity": "$PokemonBag.pbQuantity(PBItems::POTION)",
    }
    assert set(samples) == set(bi.STATE_READ_CALLS)
    for head, source in samples.items():
        _, result = evaluate_expression(
            parse_expression(source), oracle=FixedOracle(), event=(MAP_ID, 5),
        )
        assert result.refusal is None, (head, result.refusal)
        assert result.effects == (), head
