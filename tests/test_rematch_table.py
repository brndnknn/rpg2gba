"""Tests for `trainer_converter.rematch` — PokePod phone-rematch table data.

The golden test is pinned to Route 1's (Map033) two real phone trainers,
FISHERMAN "Brandon" (EV039) and YOUNGSTER "Richey" (EV053), using synthetic
fixtures shaped exactly like the real deserialized map JSON so the test does
not depend on `output/` being populated.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from rpg2gba.trainer_converter import rematch as rm

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "engine"


# ---------------------------------------------------------------------------
# Fixtures — shaped exactly like output/uranium-build/maps/Map033.json
# ---------------------------------------------------------------------------

def _phone_event(event_id: int, cls: str, name: str, taunt: str) -> dict:
    """One phone-trainer event: the real 3-page shape (battle page, rematch
    page, post-registration page), including the 355/655 script split that
    puts the `PBTrainers::` reference on the continuation line.
    """
    register = [
        {"code": 355, "indent": 0, "parameters": [f'pbPhoneRegisterBattle(_I("{taunt}']},
        {
            "code": 655,
            "indent": 0,
            "parameters": [f'more text"),get_character(0),PBTrainers::{cls},"{name}",2)'],
        },
    ]
    return {
        "id": event_id,
        "name": "Trainer(5)",
        "x": 13,
        "y": 36,
        "pages": [
            {
                "list": [
                    {"code": 355, "indent": 0, "parameters": [f"pbTrainerIntro(:{cls})"]},
                    {
                        "code": 111,
                        "indent": 0,
                        "parameters": [
                            12,
                            f'pbTrainerBattle(PBTrainers::{cls},"{name}",_I("lost"),false,0,false,0)',
                        ],
                    },
                    *register,
                    {"code": 355, "indent": 0, "parameters": ["pbTrainerEnd"]},
                ]
            },
            {
                "list": [
                    {
                        "code": 111,
                        "indent": 0,
                        "parameters": [12, f'pbPhoneBattleCount(PBTrainers::{cls},"{name}")>=1'],
                    },
                    {
                        "code": 355,
                        "indent": 0,
                        "parameters": [f'trainer = createPhoneTrainer(PBTrainers::{cls},"{name}",0)'],
                    },
                    {"code": 655, "indent": 0, "parameters": ['result = customTrainerBattle(trainer, "x")']},
                ]
            },
            {"list": [*register]},
        ],
    }


def _plain_event(event_id: int) -> dict:
    return {
        "id": event_id,
        "name": "EV002",
        "x": 1,
        "y": 1,
        "pages": [
            {
                "list": [
                    {"code": 111, "indent": 0, "parameters": [12, "Kernel.pbItemBall(::PBItems::POTION)"]},
                    {"code": 123, "indent": 1, "parameters": ["A", 0]},
                ]
            }
        ],
    }


@pytest.fixture()
def map033() -> dict:
    return {
        "map_id": 33,
        "events": [
            _plain_event(2),
            _phone_event(39, "FISHERMAN", "Brandon", "I need some more water Pokemon..."),
            _plain_event(45),
            _phone_event(53, "YOUNGSTER", "Richey", "Wanna trade PokePod numbers?"),
        ],
    }


@pytest.fixture()
def trainers() -> dict[str, dict]:
    return {
        "TRAINER_BRANDON_16": {"id": 16, "trainer_class": "TRAINER_CLASS_FISHERMAN", "name": "Brandon"},
        # Same display name, different class — the real Route 1 ambiguity trap.
        "TRAINER_BRANDON_18": {
            "id": 18,
            "trainer_class": "TRAINER_CLASS_TRIATHLETE_MALERUNNER",
            "name": "Brandon",
        },
        "TRAINER_RICHEY_3": {"id": 3, "trainer_class": "TRAINER_CLASS_YOUNGSTER", "name": "Richey"},
    }


@pytest.fixture()
def staged() -> frozenset[str]:
    return frozenset({"TRAINER_BRANDON_16", "TRAINER_BRANDON_18", "TRAINER_RICHEY_3"})


@pytest.fixture()
def map_consts() -> dict[int, str]:
    return {33: "MAP_ROUTE_01"}


@pytest.fixture(scope="module")
def facts() -> rm.ForkRematchFacts:
    return rm.load_fork_facts(ENGINE_DIR)


def _entries(map033, trainers, map_consts, staged, facts) -> list[rm.RematchEntry]:
    events = rm.detect_phone_rematch_events(map033, 33)
    return rm.build_rematch_entries(events, trainers, map_consts, staged, facts)


# ---------------------------------------------------------------------------
# Fork facts (CLAUDE.md §4.7 — these assertions are the fork contract)
# ---------------------------------------------------------------------------

def test_fork_facts_match_the_pinned_engine(facts: rm.ForkRematchFacts) -> None:
    assert facts.vanilla_entries == 78
    assert facts.max_rematch_entries == 100
    assert facts.registered_flags_start == 0x15C
    assert facts.saveblock_headroom == 22
    # Only FLAG_UNUSED_0x1AA / 0x1AB sit between the vanilla registered block
    # and FLAG_DEFEATED_DEOXYS (0x1AC): the real limit is 2, not 22.
    assert facts.registered_flag_headroom == 2
    assert facts.capacity == 2
    assert rm.INSERT_BEFORE_MEMBER in facts.members
    assert rm.SENTINEL_MEMBER not in facts.members


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_detects_only_phone_events(map033) -> None:
    events = rm.detect_phone_rematch_events(map033, 33)
    assert [(e.event_id, e.trainer_class_internal, e.trainer_display_name) for e in events] == [
        (39, "FISHERMAN", "Brandon"),
        (53, "YOUNGSTER", "Richey"),
    ]


def test_detection_is_structural_not_id_based(map033) -> None:
    """Renumbering the events must not change what is detected."""
    for ev in map033["events"]:
        ev["id"] += 100
    events = rm.detect_phone_rematch_events(map033, 33)
    assert [e.event_id for e in events] == [139, 153]


def test_phone_call_without_trainer_reference_fails_loud() -> None:
    bad = {
        "events": [
            {
                "id": 7,
                "name": "EV007",
                "pages": [{"list": [{"code": 355, "parameters": ['pbPhoneRegisterBattle(_I("hi"))']}]}],
            }
        ]
    }
    with pytest.raises(ValueError, match="no `PBTrainers::"):
        rm.detect_phone_rematch_events(bad, 33)


# ---------------------------------------------------------------------------
# Golden output — Map033's two phone trainers
# ---------------------------------------------------------------------------

def test_golden_enum_and_table(map033, trainers, map_consts, staged, facts) -> None:
    entries = _entries(map033, trainers, map_consts, staged, facts)
    assert [e.trainer_key for e in entries] == ["TRAINER_BRANDON_16", "TRAINER_RICHEY_3"]

    table = rm.emit_rematch_table(entries)
    rows = [ln for ln in table.splitlines() if ln.startswith("    [")]
    assert rows == [
        "    [REMATCH_URANIUM_BRANDON_16] = REMATCH(TRAINER_BRANDON_16, TRAINER_BRANDON_16, "
        "TRAINER_BRANDON_16, TRAINER_BRANDON_16, TRAINER_BRANDON_16, MAP_ROUTE_01),",
        "    [REMATCH_URANIUM_RICHEY_3] = REMATCH(TRAINER_RICHEY_3, TRAINER_RICHEY_3, "
        "TRAINER_RICHEY_3, TRAINER_RICHEY_3, TRAINER_RICHEY_3, MAP_ROUTE_01),",
    ]

    enum_src = rm.emit_rematch_enum(entries)
    assert f"#define {rm.MEMBERS_MACRO} \\\n" in enum_src
    member_lines = [
        ln for ln in enum_src.splitlines()
        if not ln.startswith("//") and not ln.startswith("#define")
    ]
    assert [ln.split(",")[0].strip() for ln in member_lines] == [
        "REMATCH_URANIUM_BRANDON_16",
        "REMATCH_URANIUM_RICHEY_3",
    ]
    # Every member line but the last carries a line-continuation: the whole
    # definition must expand on one line inside the enum (see MEMBERS_MACRO).
    assert [ln.endswith("\\") for ln in member_lines] == [True, False]


def test_golden_flag_names_and_values(map033, trainers, map_consts, staged, facts) -> None:
    entries = _entries(map033, trainers, map_consts, staged, facts)
    wally_index = facts.members.index(rm.INSERT_BEFORE_MEMBER)
    assert [(e.registered_flag_name, e.registered_flag_value) for e in entries] == [
        ("FLAG_REGISTERED_URANIUM_BRANDON_16", 0x15C + wally_index),
        ("FLAG_REGISTERED_URANIUM_RICHEY_3", 0x15C + wally_index + 1),
    ]
    # The two entries land exactly on the fork's two free registered-flag
    # numbers once the vanilla specials shift up by 2.
    assert [0x15C + facts.vanilla_entries, 0x15C + facts.vanilla_entries + 1] == [0x1AA, 0x1AB]


def test_manifest_records(map033, trainers, map_consts, staged, facts) -> None:
    entries = _entries(map033, trainers, map_consts, staged, facts)
    recs = rm.build_rematch_manifest_records(entries)
    assert recs[0]["uranium_trainer_id"] == 16
    assert recs[0]["map_const"] == "MAP_ROUTE_01"
    assert recs[0]["trainer_ids"] == ["TRAINER_BRANDON_16"] * 5
    assert json.loads(json.dumps(recs)) == recs  # JSON-serializable


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------

def test_idempotent(map033, trainers, map_consts, staged, facts) -> None:
    first = _entries(map033, trainers, map_consts, staged, facts)
    second = _entries(map033, trainers, map_consts, staged, facts)
    assert first == second
    assert rm.emit_rematch_enum(first) == rm.emit_rematch_enum(second)
    assert rm.emit_rematch_table(first) == rm.emit_rematch_table(second)


def test_output_order_independent_of_input_order(map033, trainers, map_consts, staged, facts) -> None:
    events = rm.detect_phone_rematch_events(map033, 33)
    forward = rm.build_rematch_entries(events, trainers, map_consts, staged, facts)
    reverse = rm.build_rematch_entries(list(reversed(events)), trainers, map_consts, staged, facts)
    assert rm.emit_rematch_table(forward) == rm.emit_rematch_table(reverse)


# ---------------------------------------------------------------------------
# Fail-loud
# ---------------------------------------------------------------------------

def test_over_capacity_raises_rather_than_truncating(trainers, map_consts, staged, facts) -> None:
    """A batch bigger than the fork's free slots must raise, naming the count.

    Uses the saveblock limit (22) as the binding one by handing the builder a
    fork-facts record with the flag headroom widened, so the assertion is
    specifically about the 22 free `trainerRematches[]` slots.
    """
    saveblock_only = rm.ForkRematchFacts(
        members=facts.members,
        max_rematch_entries=facts.max_rematch_entries,
        registered_flags_start=facts.registered_flags_start,
        registered_flag_headroom=9999,
    )
    assert saveblock_only.capacity == 22

    many_trainers = dict(trainers)
    events = []
    for i in range(23):
        key = f"TRAINER_PHONEY_{i}"
        many_trainers[key] = {"id": 900 + i, "trainer_class": "TRAINER_CLASS_PHONEY", "name": f"P{i}"}
        events.append(
            rm.PhoneRematchEvent(
                uranium_map_id=33,
                event_id=200 + i,
                event_name=f"EV{200 + i}",
                trainer_class_internal="PHONEY",
                trainer_display_name=f"P{i}",
            )
        )
    all_staged = set(staged) | {f"TRAINER_PHONEY_{i}" for i in range(23)}

    with pytest.raises(ValueError, match=r"23 Uranium rematch entries requested but only 22"):
        rm.build_rematch_entries(events, many_trainers, map_consts, all_staged, saveblock_only)

    # 22 is fine; the 23rd is what breaks it — proves the boundary, not an
    # off-by-one that silently drops the tail.
    ok = rm.build_rematch_entries(events[:22], many_trainers, map_consts, all_staged, saveblock_only)
    assert len(ok) == 22


def test_real_fork_capacity_rejects_a_third_entry(map033, trainers, map_consts, staged, facts) -> None:
    events = rm.detect_phone_rematch_events(map033, 33)
    extra = dict(trainers)
    extra["TRAINER_THIRD_99"] = {"id": 99, "trainer_class": "TRAINER_CLASS_LASS", "name": "Third"}
    events.append(
        rm.PhoneRematchEvent(33, 77, "EV077", "LASS", "Third")
    )
    with pytest.raises(ValueError, match=r"3 Uranium rematch entries requested but only 2"):
        rm.build_rematch_entries(
            events, extra, map_consts, set(staged) | {"TRAINER_THIRD_99"}, facts
        )


def test_unstaged_trainer_raises(map033, trainers, map_consts, facts) -> None:
    events = rm.detect_phone_rematch_events(map033, 33)
    with pytest.raises(ValueError, match="not staged as a battle trainer"):
        rm.build_rematch_entries(events, trainers, map_consts, frozenset(), facts)


def test_missing_map_const_raises(map033, trainers, staged, facts) -> None:
    events = rm.detect_phone_rematch_events(map033, 33)
    with pytest.raises(ValueError, match="no MAP_. constant"):
        rm.build_rematch_entries(events, trainers, {}, staged, facts)


def test_unresolvable_trainer_raises(map033, staged, map_consts, facts) -> None:
    events = rm.detect_phone_rematch_events(map033, 33)
    with pytest.raises(ValueError, match="no trainers.json entry"):
        rm.build_rematch_entries(events, {}, map_consts, staged, facts)


def test_ambiguous_trainer_raises(map033, trainers, map_consts, staged, facts) -> None:
    dupes = dict(trainers)
    dupes["TRAINER_BRANDON_99"] = {
        "id": 99,
        "trainer_class": "TRAINER_CLASS_FISHERMAN",
        "name": "Brandon",
    }
    events = rm.detect_phone_rematch_events(map033, 33)
    with pytest.raises(ValueError, match="is ambiguous across"):
        rm.build_rematch_entries(
            events, dupes, map_consts, set(staged) | {"TRAINER_BRANDON_99"}, facts
        )


def test_duplicate_rematch_name_raises(map033, trainers, map_consts, staged, facts) -> None:
    """The same trainer registered on two maps is a REMATCH_* enum collision."""
    events = rm.detect_phone_rematch_events(map033, 33)
    clone = rm.PhoneRematchEvent(81, 4, "EV004", "FISHERMAN", "Brandon")
    with pytest.raises(ValueError, match="minted twice"):
        rm.build_rematch_entries(
            [*events, clone], trainers, {**map_consts, 81: "MAP_ROUTE_01_HOUSE"}, staged, facts
        )


def test_vanilla_name_collision_raises(map_consts, facts) -> None:
    vanilla_name = facts.members[0].removeprefix("REMATCH_")  # e.g. ROSE
    key = f"TRAINER_URANIUM_{vanilla_name}"
    # Force the mint to collide by naming the trainer so rematch_const_for()
    # reproduces a vanilla member exactly.
    colliding_key = "TRAINER_" + facts.members[0].removeprefix("REMATCH_")
    trainers = {colliding_key: {"id": 1, "trainer_class": "TRAINER_CLASS_LASS", "name": "X"}}
    events = [rm.PhoneRematchEvent(33, 1, "EV001", "LASS", "X")]
    monkey = rm.ForkRematchFacts(
        members=(*facts.members, rm.rematch_const_for(colliding_key)),
        max_rematch_entries=facts.max_rematch_entries,
        registered_flags_start=facts.registered_flags_start,
        registered_flag_headroom=facts.registered_flag_headroom,
    )
    assert key  # (documents the naming shape under test)
    with pytest.raises(ValueError, match="collides with a vanilla member"):
        rm.build_rematch_entries(events, trainers, map_consts, {colliding_key}, monkey)


def test_assembler_pass_runs_by_default_and_installs_into_the_fork() -> None:
    """S8b5 runs on every assembly, and installs both fragments into the fork.

    The committed `#include` hooks in `include/constants/rematches.h` and
    `src/battle_setup.c` are unconditional, so the generated headers must always
    exist -- the pass writes comment-only stubs for an empty batch rather than
    being skippable by default. `--skip-rematches` is the escape hatch.
    """
    spec = importlib.util.spec_from_file_location(
        "_asm_rematch_probe", REPO_ROOT / "scripts" / "assemble_pathfinder.py"
    )
    assert spec is not None and spec.loader is not None
    asm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(asm)
    assert hasattr(asm, "run_rematch_pass")

    src = (REPO_ROOT / "scripts" / "assemble_pathfinder.py").read_text(encoding="utf-8")
    assert '"--skip-rematches", action="store_true"' in src
    assert "if not args.skip_rematches:\n        run_rematch_pass(" in src
    assert '"include" / "constants" / "uranium_rematches.gen.h"' in src
    assert '"src" / "data" / "uranium_rematch_table.gen.h"' in src


def test_committed_engine_hooks_are_present_and_correctly_placed() -> None:
    """The enum hook must sit ABOVE `REMATCH_WALLY_VR`.

    `IsRematchForbidden` rejects every id >= `REMATCH_ELITE_FOUR_ENTRIES`, and the
    normal-trainer scans stop at `REMATCH_SPECIAL_TRAINER_START` (== WALLY_VR), so
    a hook placed after it would compile clean and never fire a rematch.
    """
    engine = REPO_ROOT / "engine"
    header = (engine / "include" / "constants" / "rematches.h").read_text(encoding="utf-8")
    include_at = header.index('#include "constants/uranium_rematches.gen.h"')
    enum_at = header.index("enum {")
    macro_at = header.index(f"    {rm.MEMBERS_MACRO}\n")
    wally_at = header.index("    REMATCH_WALLY_VR,")
    # The include sits ABOVE the enum (cpp line markers break tools/preproc's
    # in-enum parser); only the macro expansion lands inside, before WALLY.
    assert include_at < enum_at < macro_at < wally_at

    table = (engine / "src" / "battle_setup.c").read_text(encoding="utf-8")
    assert '#include "data/uranium_rematch_table.gen.h"' in table


def test_empty_batch_emits_no_op_fragments() -> None:
    empty_enum = rm.emit_rematch_enum([])
    assert "no Uranium phone-rematch trainers" in empty_enum
    # Still defines the macro -- the committed hook expands it unconditionally.
    assert f"#define {rm.MEMBERS_MACRO}\n" in empty_enum
    assert "no Uranium phone-rematch trainers" in rm.emit_rematch_table([])
