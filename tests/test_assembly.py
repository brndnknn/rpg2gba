"""S8 orphan-block pruning (`rpg2gba.tileset_converter.assembly`).

Covers the lossless block split, event-id keying (robust to the agent's
name-qualified labels vs S5's un-named labels), the prune itself + idempotence,
both fail-loud guards, and an optional smoke test against the real staged slice
output when it is present on disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from rpg2gba.tileset_converter import assembly as asm
from rpg2gba.tileset_converter.assembly import AssemblyError

# A synthetic map .pory mirroring the real shape: a wired single-page NPC, a wired
# name-qualified multi-page event, and two orphan doors (one warping out of slice).
SAMPLE_PORY = """\
script Map032_EV001_Page1 {
    lock
    msgbox("Welcome to {PLAYER}'s town!")
    release
    end
}

script Map032_EV008_Chyinmunk_Page1 {
    msgbox("A wild thing appears.")
    end
}

script Map032_EV006_Page1 {
    warp(MAP_URANIUM_64, 9, 12)
    end
}

script Map032_EV023_Page1 {
    warp(MAP_URANIUM_33, 70, 11)
    end
}
"""

# map.json wires EV001 (un-named page label) and EV008 (the page label is the
# un-named form even though the block is name-qualified). EV006/EV023 are doors
# S5 dropped (they appear only as the orphan blocks above).
SAMPLE_MAP_JSON = {
    "object_events": [
        {"script": "Map032_EV001_Page1", "x": 1, "y": 1},
        {"script": "Map032_EV008_Page1", "x": 2, "y": 2},
    ],
    "warp_events": [{"dest_map": "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F", "dest_warp_id": 0}],
}

ALLOWED = {32, 48, 49}


def test_split_blocks_is_lossless():
    preamble, blocks = asm.split_blocks(SAMPLE_PORY)
    assert preamble == ""  # file starts at the first block
    assert [b.label for b in blocks] == [
        "Map032_EV001_Page1",
        "Map032_EV008_Chyinmunk_Page1",
        "Map032_EV006_Page1",
        "Map032_EV023_Page1",
    ]
    assert preamble + "".join(b.text for b in blocks) == SAMPLE_PORY


def test_split_blocks_preserves_preamble():
    text = "// header comment\n\n" + SAMPLE_PORY
    preamble, blocks = asm.split_blocks(text)
    assert preamble == "// header comment\n\n"
    assert preamble + "".join(b.text for b in blocks) == text


def test_split_blocks_empty():
    assert asm.split_blocks("") == ("", [])
    assert asm.split_blocks("# no blocks here\n") == ("# no blocks here\n", [])


def test_block_event_id():
    assert asm.block_event_id("Map032_EV008_Chyinmunk_Page1") == 8
    assert asm.block_event_id("Map032_EV014_Dispatch") == 14
    assert asm.block_event_id("Map049_EV001_Page1") == 1
    assert asm.block_event_id("CommonEvent_005") is None
    assert asm.block_event_id("SomeOtherLabel") is None


def test_live_event_ids_reads_scripts_skips_warps():
    assert asm.live_event_ids(SAMPLE_MAP_JSON) == {1, 8}


def test_live_event_ids_dispatcher_label():
    mj = {"object_events": [{"script": "Map032_EV014_Dispatch"}]}
    assert asm.live_event_ids(mj) == {14}


def test_prune_drops_orphan_doors():
    result = asm.prune_map_pory(
        SAMPLE_PORY, SAMPLE_MAP_JSON, allowed_uranium_maps=ALLOWED
    )
    assert result.kept == ["Map032_EV001_Page1", "Map032_EV008_Chyinmunk_Page1"]
    assert sorted(result.dropped) == ["Map032_EV006_Page1", "Map032_EV023_Page1"]
    assert "MAP_URANIUM_64" not in result.text
    assert "MAP_URANIUM_33" not in result.text
    # kept blocks survive verbatim
    assert "Welcome to {PLAYER}'s town!" in result.text
    assert "A wild thing appears." in result.text


def test_prune_is_idempotent():
    once = asm.prune_map_pory(SAMPLE_PORY, SAMPLE_MAP_JSON, allowed_uranium_maps=ALLOWED)
    twice = asm.prune_map_pory(once.text, SAMPLE_MAP_JSON, allowed_uranium_maps=ALLOWED)
    assert twice.text == once.text
    assert twice.dropped == []


def test_prune_keeps_non_event_blocks():
    pory = "script CommonEvent_005 {\n    end\n}\n"
    result = asm.prune_orphan_blocks(pory, live_ids=set())
    assert result.kept == ["CommonEvent_005"]
    assert result.dropped == []


def test_guard_cross_event_reference_fails_loud():
    # EV001 (live) gotos into EV006 (orphan) — pruning EV006 would dangle the goto.
    pory = (
        "script Map032_EV001_Page1 {\n    goto(Map032_EV006_Page1)\n}\n\n"
        "script Map032_EV006_Page1 {\n    warp(MAP_URANIUM_64, 9, 12)\n    end\n}\n"
    )
    with pytest.raises(AssemblyError, match="dangling goto"):
        asm.prune_orphan_blocks(pory, live_ids={1})


def test_guard_out_of_slice_in_wired_block_fails_loud():
    # A WIRED event warping out of slice cannot be pruned away — surface it.
    pory = "script Map032_EV001_Page1 {\n    warp(MAP_URANIUM_99, 1, 1)\n    end\n}\n"
    with pytest.raises(AssemblyError, match="out-of-slice"):
        asm.prune_orphan_blocks(pory, live_ids={1}, allowed_uranium_maps=ALLOWED)


def test_out_of_slice_in_dropped_block_is_fine():
    # The same out-of-slice warp inside an ORPHAN block is exactly what we prune.
    pory = "script Map032_EV006_Page1 {\n    warp(MAP_URANIUM_99, 1, 1)\n    end\n}\n"
    result = asm.prune_orphan_blocks(pory, live_ids=set(), allowed_uranium_maps=ALLOWED)
    assert result.dropped == ["Map032_EV006_Page1"]
    assert result.text == ""


# --- Option A: label normalization -------------------------------------------

def test_normalize_strips_event_name_defs_and_refs():
    text = (
        "script Map032_EV009_Trainer6_Page1 {\n    goto(Map032_EV009_Trainer6_Page2)\n}\n\n"
        "script Map032_EV009_Trainer6_Page2 {\n    end\n}\n"
    )
    r = asm.normalize_labels(text)
    assert "Trainer6" not in r.text
    assert "script Map032_EV009_Page1 {" in r.text
    assert "goto(Map032_EV009_Page2)" in r.text  # the reference moved with the def
    assert r.renames == {
        "Map032_EV009_Trainer6_Page1": "Map032_EV009_Page1",
        "Map032_EV009_Trainer6_Page2": "Map032_EV009_Page2",
    }


def test_normalize_leaves_unnamed_unchanged():
    text = "script Map032_EV074_Page1 {\n    end\n}\n"
    r = asm.normalize_labels(text)
    assert r.text == text
    assert r.renames == {}


def test_normalize_is_idempotent():
    text = "script Map049_EV001_Auntie_Page3 {\n    end\n}\n"
    once = asm.normalize_labels(text).text
    assert asm.normalize_labels(once).text == once


def test_normalize_leaves_flags_and_dispatch_labels():
    text = (
        "script Map032_EV014_Rock_Page1 {\n"
        "    if (flag(FLAG_MAP032_EVENT014_SSA)) { goto(Map032_EV014_Dispatch) }\n}\n"
    )
    r = asm.normalize_labels(text)
    assert "FLAG_MAP032_EVENT014_SSA" in r.text  # upper-case flag token untouched
    assert "Map032_EV014_Dispatch" in r.text  # no Page suffix -> untouched
    assert "script Map032_EV014_Page1 {" in r.text


def test_option_a_makes_dispatcher_gotos_resolve():
    # The whole point: agent emits name-qualified page blocks; S5's dispatcher
    # gotos the un-named form. Normalizing the map .pory reconciles them.
    map_pory = (
        "script Map032_EV014_Rock_Page1 {\n    end\n}\n"
        "script Map032_EV014_Rock_Page2 {\n    end\n}\n"
    )
    dispatch = (
        "script Map032_EV014_Dispatch {\n"
        "    goto Map032_EV014_Page2\n    goto Map032_EV014_Page1\n}\n"
    )
    mj = {"object_events": [{"script": "Map032_EV014_Dispatch"}]}
    assert asm.find_dangling_references([map_pory, dispatch], [mj]) == {
        "Map032_EV014_Page1",
        "Map032_EV014_Page2",
    }  # before normalization: gotos dangle
    staged = asm.normalize_labels(map_pory).text
    assert asm.find_dangling_references([staged, dispatch], [mj]) == set()


# --- existence / duplicate checks --------------------------------------------

def test_dangling_reference_flags_missing_block():
    # map.json wires EV002 but no block exists (the empty-event / gap case)
    mj = {"object_events": [{"script": "Map032_EV002_Page1"}]}
    assert asm.find_dangling_references([""], [mj]) == {"Map032_EV002_Page1"}


def test_dangling_reference_common_event_resolves_with_ce_file():
    map_pory = "script Map032_EV001_Page1 {\n    call(CommonEvent_005)\n    end\n}\n"
    assert asm.find_dangling_references([map_pory]) == {"CommonEvent_005"}
    ce = "script CommonEvent_005 {\n    end\n}\n"
    assert asm.find_dangling_references([map_pory, ce]) == set()


def test_static_object_sentinel_is_not_a_reference():
    # An object_event S5 stubbed to a static object (no .pory body) carries the
    # "0x0" sentinel, not a label -> it must not register as a dangling reference.
    mj = {"object_events": [
        {"script": "0x0", "x": 1, "y": 1},
        {"script": "0", "x": 2, "y": 2},
        {"script": "Map032_EV001_Page1", "x": 3, "y": 3},
    ]}
    assert asm.map_json_script_refs(mj) == {"Map032_EV001_Page1"}
    block = "script Map032_EV001_Page1 {\n    end\n}\n"
    assert asm.find_dangling_references([block], [mj]) == set()


def test_duplicate_definition_from_collapsed_names():
    a = asm.normalize_labels("script Map032_EV009_Foo_Page1 {\n    end\n}\n").text
    b = asm.normalize_labels("script Map032_EV009_Bar_Page1 {\n    end\n}\n").text
    assert asm.find_duplicate_definitions([a, b]) == {"Map032_EV009_Page1": 2}
    assert asm.find_duplicate_definitions([a]) == {}


# --- patch_out_of_slice_warps ------------------------------------------------

def test_patch_replaces_out_of_slice_warps():
    pory = (
        "script CommonEvent_086 {\n"
        "    warp(MAP_URANIUM_70, 9, 8)\n"
        "    warp(MAP_URANIUM_32, 5, 5)\n"
        "    end\n"
        "}\n"
    )
    result = asm.patch_out_of_slice_warps(pory, {32, 48, 49})
    assert "MAP_URANIUM_70" not in result
    assert "warp(MAP_URANIUM_32, 5, 5)" in result  # in-slice warp untouched
    assert result.count("return") == 1


def test_patch_is_idempotent():
    pory = "script CommonEvent_086 {\n    warp(MAP_URANIUM_70, 9, 8)\n    end\n}\n"
    once = asm.patch_out_of_slice_warps(pory, {32, 48, 49})
    assert asm.patch_out_of_slice_warps(once, {32, 48, 49}) == once


def test_patch_leaves_text_with_no_warps_unchanged():
    pory = "script CommonEvent_005 {\n    msgbox(\"Hi\")\n    end\n}\n"
    assert asm.patch_out_of_slice_warps(pory, {32, 48, 49}) == pory


# --- normalize_pory (charmap legality + command alias) -----------------------

# A representable set sufficient for the unit strings below: letters/digits/space,
# the substitution *targets* (~ ( ) and the typographic quotes), basic punctuation.
_ALLOWED = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 '.!?,:~()“”"
)


def test_normalize_double_quotes_to_typographic_pairs():
    out = asm.normalize_pory('    msgbox("say \\"hi\\" now")\n', _ALLOWED)
    assert "“hi”" in out            # open then close, alternating
    assert '\\"' not in out          # no escaped straight quotes survive


def test_normalize_char_substitutions():
    assert "~sniffle~" in asm.normalize_pory('msgbox("*sniffle*")', _ALLOWED)
    assert "(note)" in asm.normalize_pory('msgbox("[note]")', _ALLOWED)


def test_normalize_healparty_alias():
    out = asm.normalize_pory("    healparty\n", _ALLOWED)
    assert out == "    special(HealPlayerParty)\n"


def test_normalize_ignores_placeholders_and_breaks():
    # {PLAYER} and \n must not be validated as literal characters.
    asm.normalize_pory('msgbox("Hi {PLAYER}!\\nBye")', _ALLOWED)  # no raise


def test_normalize_fails_loud_on_unrepresentable():
    with pytest.raises(ValueError, match="U\\+007C"):  # '|' has no glyph, no sub
        asm.normalize_pory('msgbox("a|b")', _ALLOWED)


def test_normalize_leaves_comments_untouched():
    line = '    # UNHANDLED: cond "$game_player.x==17" gates the sign — see unhandled[]\n'
    assert asm.normalize_pory(line, _ALLOWED) == line


def test_normalize_is_idempotent():
    src = 'msgbox("a \\"quote\\" and *star* and [brackets]")\n    healparty\n'
    once = asm.normalize_pory(src, _ALLOWED)
    assert asm.normalize_pory(once, _ALLOWED) == once


# --- undefined-symbol patches (multichoice + self/temp-switch refs) ----------

def test_patch_undefined_multichoice_stubs_unknown():
    text = "    multichoice(0, 0, MULTI_DREAM_VISUALIZER, TRUE)\n"
    out = asm.patch_undefined_multichoice(text, {"MULTI_YESNO"})
    assert "MULTI_DREAM_VISUALIZER" not in out
    assert "setvar(VAR_RESULT, 0)" in out


def test_patch_undefined_multichoice_keeps_defined():
    text = "    multichoice(0, 0, MULTI_YESNO, TRUE)\n"
    assert asm.patch_undefined_multichoice(text, {"MULTI_YESNO"}) == text


def test_load_multi_constants(tmp_path):
    hdr = tmp_path / "script_menu.h"
    hdr.write_text("#define MULTI_YESNO 0\n#define MULTI_TVNO 1\n#define NOT_MULTI 2\n")
    assert asm.load_multi_constants(hdr) == {"MULTI_YESNO", "MULTI_TVNO"}


def test_referenced_switch_keys():
    texts = [
        "    setflag(FLAG_MAP049_EVENT019_SSA)\n",
        "    if (flag(FLAG_MAP032_EVENT005_TSB)) {\n",
    ]
    self_keys, temp_keys = asm.referenced_switch_keys(texts)
    assert self_keys == {(49, 19, "A")}
    assert temp_keys == {(32, 5, "B")}


# --- optional smoke test against the real staged slice output ----------------

_OUT = Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"
_REAL_PORY = _OUT / "scripts" / "Map032.pory"
_REAL_MAP_JSON = _OUT / "porymap" / "maps" / "MokiTown" / "map.json"


@pytest.mark.skipif(
    not (_REAL_PORY.is_file() and _REAL_MAP_JSON.is_file()),
    reason="staged slice output not present",
)
def test_real_slice_map032_prunes_clean():
    pory = _REAL_PORY.read_text(encoding="utf-8")
    map_json = json.loads(_REAL_MAP_JSON.read_text(encoding="utf-8"))
    result = asm.prune_map_pory(pory, map_json, allowed_uranium_maps={32, 48, 49})
    # the out-of-slice doors surfaced by the completed S6 run
    assert {asm.block_event_id(lbl) for lbl in result.dropped} == {3, 5, 6, 7, 17, 23, 36, 37, 78}
    # and nothing undefined is left for the assembler
    import re

    survivors = {int(n) for n in re.findall(r"MAP_URANIUM_(\d+)", result.text)} - {32, 48, 49}
    assert survivors == set()


@pytest.mark.skipif(not _REAL_PORY.is_file(), reason="staged slice output not present")
def test_real_slice_normalization_yields_unnamed_labels():
    import re

    staged = asm.normalize_labels(_REAL_PORY.read_text(encoding="utf-8")).text
    labels = asm.script_definitions(staged)
    # every page block is the canonical un-named form S5 references
    assert all(re.fullmatch(r"Map\d+_EV\d+_Page\d+", lbl) for lbl in labels), [
        lbl for lbl in labels if not re.fullmatch(r"Map\d+_EV\d+_Page\d+", lbl)
    ]
