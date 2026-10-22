"""W1 tests — species staging emitter (`species_converter.stage`).

Per CLAUDE.md §4.6:
  * round-trip: emit, then parse the emitted C back well enough to confirm
    the six entries carry the stats/types that came out of the parsers.
  * golden: pinned emitted `species_info` entries for ORCHYNX (plain) and
    METALYNX (the evolution-target edge).
  * edge: fork-append id math (SPECIES_EGG chaining), empty-selection no-op,
    idempotence, and a dangling evolution-target failing loud.

All tests that touch real Uranium data are gated behind the `uranium_data`
fixture (skips cleanly when `RPG2GBA_URANIUM_SRC` is unset) and the
`fork_path` fixture (skips when `RPG2GBA_POKEEMERALD`/`engine/` is unset),
matching `test_pbs_pokemon.py`'s pattern.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rpg2gba.pbs_converter import pokemon
from rpg2gba.pbs_converter._id_map import IdMap
from rpg2gba.species_converter import stage
from rpg2gba.species_converter.common import STARTER_SPECIES, SpeciesSpec

pytestmark = pytest.mark.phase2

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _make_resolver(
    *,
    move_internal: dict[int, str] | None = None,
    species_names: dict[int, str] | None = None,
    species_kinds: dict[int, str] | None = None,
    species_pokedex: dict[int, str] | None = None,
    item_internal: dict[int, str] | None = None,
    item_names: dict[int, str] | None = None,
    fork_items: set[str] | None = None,
    fork_moves: set[str] | None = None,
) -> pokemon._Resolver:
    """Minimal `_Resolver` for unit-level tests that don't need real Uranium
    data or a real fork checkout — just enough dicts for the fields exercised."""
    return pokemon._Resolver(
        id_map=IdMap(),
        species_internal={},
        species_names=species_names or {},
        species_kinds=species_kinds or {},
        species_pokedex=species_pokedex or {},
        move_internal=move_internal or {},
        move_names={},
        ability_internal={},
        ability_names={},
        item_internal=item_internal or {},
        item_names=item_names or {},
        type_internal={0: "NORMAL"},
        fork_species=set(),
        fork_moves=fork_moves if fork_moves is not None else set(),
        fork_abilities=set(),
        fork_items=fork_items if fork_items is not None else set(),
    )


def _make_species(**kwargs) -> pokemon.Species:
    defaults = dict(
        id=1,
        internal_name="TESTMON",
        color=0,
        habitat=0,
        type1=0,
        type2=0,
        base_stats=(1, 1, 1, 1, 1, 1),
        rareness=45,
        gender_rate=127,
        happiness=70,
        growth_rate=0,
        steps_to_hatch=5120,
        effort_points=(0, 0, 0, 0, 0, 0),
        abilities=(0, 0),
        compatibility=(0, 0),
        height_dm=10,
        weight_hg=100,
        base_exp=64,
        hidden_abilities=(0, 0, 0, 0),
        wild_item_common=0,
        wild_item_uncommon=0,
        wild_item_rare=0,
    )
    defaults.update(kwargs)
    return pokemon.Species(**defaults)


def _make_staged(spec: SpeciesSpec, record: pokemon.Species) -> stage.StagedSpecies:
    return stage.StagedSpecies(
        spec=spec,
        fork_id=9999,
        record=record,
        evolution_target_fork_id=None,
        evolution_level=None,
        front_pic_y_offset=stage.DEFAULT_FRONT_PIC_Y_OFFSET,
        back_pic_y_offset=stage.DEFAULT_BACK_PIC_Y_OFFSET,
        icon_pal_index=stage.DEFAULT_ICON_PAL_INDEX,
    )


@pytest.fixture()
def uranium_src(uranium_data: Path) -> Path:
    """`$RPG2GBA_URANIUM_SRC` root (one level up from the `Data` dir)."""
    return uranium_data.parent


@pytest.fixture()
def engine_dir(fork_path: Path | None) -> Path:
    if fork_path is None:
        pytest.skip("RPG2GBA_POKEEMERALD not set; species staging needs the real fork")
    return fork_path


def _entry(c_text: str, const: str) -> str:
    m = re.search(r"    \[" + re.escape(const) + r"\] =\n    \{.*?\n    \},", c_text, re.S)
    assert m, f"{const} entry not found in emitted species_info.h"
    return m.group(0)


# ===========================================================================
# Round-trip
# ===========================================================================


def test_roundtrip_stats_and_types(uranium_src: Path, engine_dir: Path, tmp_path: Path) -> None:
    """Stats/types emitted into rpg2gba_species_info.h re-read back to parsed values."""
    manifest = stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=tmp_path)
    c_text = (tmp_path / "rpg2gba_species_info.h").read_text(encoding="utf-8")

    species, _ = stage.load_all_species(uranium_src, stage._reference_dir())
    records = stage.select_starters(species, STARTER_SPECIES)

    assert len(manifest["species"]) == len(STARTER_SPECIES)
    for spec, rec in zip(STARTER_SPECIES, records):
        entry = _entry(c_text, spec.constant)
        stat_fields = ("baseHP", "baseAttack", "baseDefense", "baseSpeed", "baseSpAttack", "baseSpDefense")
        for field, expected in zip(stat_fields, rec.base_stats):
            m = re.search(rf"\.{field} = (\d+),", entry)
            assert m and int(m.group(1)) == expected, f"{spec.internal_name}.{field}"
        # types: both type1/type2 constants must appear inside MON_TYPES(...)
        types_m = re.search(r"\.types = MON_TYPES\(([^)]*)\),", entry)
        assert types_m, f"{spec.internal_name}: no .types field"


def test_roundtrip_manifest_matches_emitted_constants(
    uranium_src: Path, engine_dir: Path, tmp_path: Path
) -> None:
    """Every manifest species_constant appears as a `[SPECIES_X] =` entry and
    a `#define SPECIES_X` in the constants overlay."""
    manifest = stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=tmp_path)
    info_text = (tmp_path / "rpg2gba_species_info.h").read_text(encoding="utf-8")
    const_text = (tmp_path / "rpg2gba_species_constants.h").read_text(encoding="utf-8")
    for rec in manifest["species"]:
        const = rec["species_constant"]
        assert f"[{const}] =" in info_text
        assert f"#define {const} " in const_text


# ===========================================================================
# Golden
# ===========================================================================


def test_golden_orchynx_metalynx(uranium_src: Path, engine_dir: Path, tmp_path: Path) -> None:
    """Pinned emitted entries for ORCHYNX (plain) + METALYNX (evolution target)."""
    stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=tmp_path)
    c_text = (tmp_path / "rpg2gba_species_info.h").read_text(encoding="utf-8")
    got = _entry(c_text, "SPECIES_ORCHYNX") + "\n" + _entry(c_text, "SPECIES_METALYNX") + "\n"
    expected = (FIXTURES / "species_stage_golden.h").read_text(encoding="utf-8")
    assert got == expected


# ===========================================================================
# Edge cases
# ===========================================================================


def test_edge_fork_append_id_math(uranium_src: Path, engine_dir: Path, tmp_path: Path) -> None:
    """The first new species takes the pristine SPECIES_EGG value, ids chain
    sequentially, and RPG2GBA_SPECIES_LAST anchors to the final one.

    STARTER_SPECIES is no longer just the six starters (2026-08-05: extended
    with the seven Route-1 trainer-party species plus every intermediate/
    final evolution stage needed to avoid a dangling evolution reference —
    see `common.py`'s comment for the full chain), so this asserts against
    `len(STARTER_SPECIES)` rather than a pinned 6.
    """
    pristine_egg, anchor = stage.read_pristine_species_egg(engine_dir)
    assert pristine_egg == 1573
    assert anchor == "SPECIES_GLIMMORA_MEGA"

    n = len(STARTER_SPECIES)
    manifest = stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=tmp_path)
    assert manifest["pristine_species_egg"] == pristine_egg
    assert manifest["new_species_egg"] == pristine_egg + n

    ids = [rec["fork_species_id"] for rec in manifest["species"]]
    assert ids == list(range(pristine_egg, pristine_egg + n))

    const_text = (tmp_path / "rpg2gba_species_constants.h").read_text(encoding="utf-8")
    assert f"#define SPECIES_ORCHYNX ({anchor} + 1)" in const_text
    assert "#define SPECIES_METALYNX (SPECIES_ORCHYNX + 1)" in const_text
    assert f"#define RPG2GBA_SPECIES_LAST {STARTER_SPECIES[-1].constant}" in const_text


def test_edge_empty_selection_is_noop(engine_dir: Path, tmp_path: Path) -> None:
    """Empty selection emits every file in a no-op (empty-guarded) form and
    needs no Uranium source at all."""
    manifest = stage.write_all(
        uranium_src=Path("/nonexistent"), engine_dir=engine_dir, out_dir=tmp_path, selected=()
    )
    assert manifest["species"] == []
    assert manifest["new_species_egg"] == manifest["pristine_species_egg"]

    for name in (
        "rpg2gba_species_constants.h",
        "rpg2gba_pokedex_ids.h",
        "rpg2gba_learnsets.h",
        "rpg2gba_species_info.h",
        "rpg2gba_species_graphics.h",
        "rpg2gba_cries_enum.h",
        "rpg2gba_cry_table_forward.inc",
        "rpg2gba_cry_table_reverse.inc",
        "rpg2gba_cry_sound_data.inc",
    ):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert "SPECIES_ORCHYNX" not in text
        assert "no Uranium species selected" in text
        # Every #define/emitted symbol line must be absent — only banner/guard/note lines remain.
        assert "RPG2GBA_SPECIES_LAST" not in text


def test_edge_idempotence(uranium_src: Path, engine_dir: Path, tmp_path: Path) -> None:
    """Emitting twice with identical inputs produces byte-identical output."""
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"
    stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=out1)
    stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=out2)

    names1 = sorted(p.name for p in out1.iterdir())
    names2 = sorted(p.name for p in out2.iterdir())
    assert names1 == names2
    for name in names1:
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes(), name


def test_edge_dangling_evolution_target_fails_loud(uranium_src: Path, engine_dir: Path) -> None:
    """An evolution pointing at a species not in the selection is a fail-loud error."""
    species, _ = stage.load_all_species(uranium_src, stage._reference_dir())
    records = stage.select_starters(species, STARTER_SPECIES)
    pristine_egg, _ = stage.read_pristine_species_egg(engine_dir)

    # Drop METALYNX (index 1) — ORCHYNX (index 0) still evolves into it.
    partial_specs = (STARTER_SPECIES[0],) + STARTER_SPECIES[2:]
    partial_records = [records[0]] + records[2:]

    with pytest.raises(ValueError, match="dangling reference"):
        stage.build_staged_species(partial_specs, partial_records, pristine_egg)


def test_edge_route1_chain_dangling_evolution_target_fails_loud(
    uranium_src: Path, engine_dir: Path
) -> None:
    """Same guard, exercised on the Route-1 extension's two-stage chain:
    BIRBIE -> AVEDEN -> SPLENDIFOWL. Staging BIRBIE+AVEDEN without
    SPLENDIFOWL leaves AVEDEN's own evolution dangling."""
    species, _ = stage.load_all_species(uranium_src, stage._reference_dir())
    by_name = {spec.internal_name: spec for spec in STARTER_SPECIES}
    birbie, aveden = by_name["BIRBIE"], by_name["AVEDEN"]
    records = stage.select_starters(species, (birbie, aveden))
    pristine_egg, _ = stage.read_pristine_species_egg(engine_dir)

    with pytest.raises(ValueError, match="dangling reference"):
        stage.build_staged_species((birbie, aveden), records, pristine_egg)


def test_route1_species_present_in_manifest_and_constants(
    uranium_src: Path, engine_dir: Path, tmp_path: Path
) -> None:
    """The seven Route-1 trainer-party species (and the evolution stages
    staged alongside them to avoid a dangling reference) all reach the
    manifest and the emitted constants header."""
    manifest = stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=tmp_path)
    const_text = (tmp_path / "rpg2gba_species_constants.h").read_text(encoding="utf-8")
    manifest_constants = {rec["species_constant"] for rec in manifest["species"]}

    expected_new = {
        "SPECIES_FARTOG", "SPECIES_FOLEROG", "SPECIES_BLUBELROG",
        "SPECIES_BIRBIE", "SPECIES_AVEDEN", "SPECIES_SPLENDIFOWL",
        "SPECIES_BAREWL", "SPECIES_DEAREWL", "SPECIES_GARAREWL",
        "SPECIES_CUBBUG", "SPECIES_CUBBLFLY", "SPECIES_NIMFLORA",
        "SPECIES_CHYINMUNK", "SPECIES_KINETMUNK",
        "SPECIES_TONEMY", "SPECIES_TOFURANG",
        "SPECIES_OWTEN", "SPECIES_ESHOUTEN",
    }
    assert expected_new <= manifest_constants
    for const in expected_new:
        assert f"#define {const} " in const_text


def test_edge_starter_species_internal_names_verified(uranium_src: Path) -> None:
    """select_starters fails loud if a STARTER_SPECIES entry's internal_name
    doesn't match the parsed record (drift guard)."""
    species, _ = stage.load_all_species(uranium_src, stage._reference_dir())
    bad = (SpeciesSpec(1, "NOT_ORCHYNX"),)
    with pytest.raises(ValueError, match="expected internal_name"):
        stage.select_starters(species, bad)


def test_edge_ability_constants_verified_against_fork(engine_dir: Path) -> None:
    """The six starters' abilities are asserted to be real fork constants,
    not merely assumed (CLAUDE.md §4.7)."""
    stage.assert_fork_constants_exist(
        engine_dir, stage._EXPECTED_ABILITIES, "include/constants/abilities.h", "ABILITY"
    )
    with pytest.raises(ValueError, match="not defined in fork"):
        stage.assert_fork_constants_exist(
            engine_dir, {"ABILITY_TOTALLY_MADE_UP"}, "include/constants/abilities.h", "ABILITY"
        )


# ===========================================================================
# Bug 1 — learnset moves gated against the fork's real MOVE_* constants
# ===========================================================================


def test_learnset_move_absent_from_fork_dropped_and_recorded(caplog: pytest.LogCaptureFixture) -> None:
    """A level-up entry whose move isn't in the fork's moves.h is dropped,
    warned about, and the surviving entries still emit correctly."""
    resolver = _make_resolver(move_internal={1: "TACKLE", 2: "METAL_WHIP"})
    record = _make_species(level_up_moves=[(1, 1), (5, 2)])
    spec = SpeciesSpec(1, "TESTMON")
    staged = [_make_staged(spec, record)]
    fork_moves = {"MOVE_TACKLE"}  # MOVE_METAL_WHIP deliberately absent

    with caplog.at_level("WARNING"):
        text, dropped = stage.emit_learnsets(staged, resolver, fork_moves)

    assert "LEVEL_UP_MOVE(  1, MOVE_TACKLE)" in text
    assert "MOVE_METAL_WHIP" not in text
    assert dropped == [
        {
            "species": "TESTMON",
            "species_constant": "SPECIES_TESTMON",
            "level": 5,
            "move_constant": "MOVE_METAL_WHIP",
            "uranium_move_id": 2,
        }
    ]
    assert any("MOVE_METAL_WHIP" in r.message and "TESTMON" in r.message for r in caplog.records)


def test_learnset_entirely_dropped_still_emits_valid_array() -> None:
    """A species whose whole learnset drops still emits a compiling
    (empty, LEVEL_UP_END-terminated) array — same shape as the no-op path."""
    resolver = _make_resolver(move_internal={2: "METAL_WHIP"})
    record = _make_species(level_up_moves=[(5, 2)])
    spec = SpeciesSpec(1, "TESTMON")
    staged = [_make_staged(spec, record)]
    fork_moves: set[str] = {"MOVE_TACKLE"}

    text, dropped = stage.emit_learnsets(staged, resolver, fork_moves)

    assert len(dropped) == 1
    assert (
        "static const struct LevelUpMove sUraniumLevelUpLearnset_TESTMON[] = {\n"
        "    LEVEL_UP_END\n};" in text
    )


def test_manifest_carries_dropped_move_record() -> None:
    """`build_manifest` threads dropped-move records into
    `dropped_learnset_moves`, discoverable downstream (species_manifest.json)."""
    dropped = [
        {
            "species": "TESTMON",
            "species_constant": "SPECIES_TESTMON",
            "level": 5,
            "move_constant": "MOVE_METAL_WHIP",
            "uranium_move_id": 2,
        }
    ]
    manifest = stage.build_manifest([], pristine_species_egg=1574, dropped_learnset_moves=dropped)
    assert manifest["dropped_learnset_moves"] == dropped

    manifest_empty = stage.build_manifest([], pristine_species_egg=1574)
    assert manifest_empty["dropped_learnset_moves"] == []


# ===========================================================================
# Bug 2 — non-ASCII engine text (charmap.txt), not \xNN escapes
# ===========================================================================


def test_non_ascii_description_emits_literal_charmap_char(engine_dir: Path) -> None:
    """A description containing a charmap-representable non-ASCII character
    (accented é, as in Uranium's real "Pokémon" descriptions) is emitted
    literally, not as a `\\xE9` escape gcc rejects."""
    charmap_chars = stage.load_charmap_chars(engine_dir)
    assert "é" in charmap_chars

    out = stage.emit_engine_text("Pokémon are great.", charmap_chars, species="TESTMON", field="description")
    assert out == "Pokémon are great."
    assert "\\x" not in out


def test_species_info_emits_literal_accented_char_not_hex_escape(engine_dir: Path) -> None:
    """End-to-end through emit_species_info: a description with 'é' compiles
    to a raw UTF-8 char in the .h, matching the vanilla fork's own convention
    (engine/src/data/pokemon/species_info/gen_3_families.h embeds Pokémon
    literally, not \\xE9)."""
    charmap_chars = stage.load_charmap_chars(engine_dir)
    charmap = stage.load_charmap(engine_dir / "charmap.txt")
    resolver = _make_resolver(species_pokedex={1: "A wild Pokémon appears."})
    record = _make_species()
    spec = SpeciesSpec(1, "TESTMON")
    staged = [_make_staged(spec, record)]

    text = stage.emit_species_info(staged, resolver, charmap_chars, charmap)

    assert '"A wild Pokémon appears."),' in text
    assert "\\xE9" not in text
    assert "\\x" not in text


def test_unrepresentable_char_fails_loud(engine_dir: Path) -> None:
    """A character with no charmap.txt entry fails loud, naming the species
    and the character, rather than silently emitting garbage."""
    charmap_chars = stage.load_charmap_chars(engine_dir)
    with pytest.raises(ValueError, match=r"TESTMON.*description.*U\+2603"):
        stage.emit_engine_text("A snowman: ☃", charmap_chars, species="TESTMON", field="description")


def test_straight_double_quotes_become_charmap_curly_quotes(engine_dir: Path) -> None:
    """preproc has no glyph for a straight double quote (Brainoar's dex text,
    CH09); paired straight quotes become the charmap's “ ” glyphs."""
    charmap_chars = stage.load_charmap_chars(engine_dir)
    out = stage.emit_engine_text('Called "The sage", it is', charmap_chars, species="T", field="description")
    assert out == "Called “The sage”, it is"
    with pytest.raises(ValueError, match="unpaired double quote"):
        stage.emit_engine_text('One " only', charmap_chars, species="T", field="description")


# ===========================================================================
# Luxi family (2026-08-19) — Happiness (method 1) and Item (method 7)
# evolutions, previously unsupported by build_staged_species.
# ===========================================================================


def test_happiness_evolution_emits_min_friendship_condition() -> None:
    """Uranium evolution method 1 (Happiness) is staged as EVO_LEVEL with
    param 0 plus CONDITIONS({IF_MIN_FRIENDSHIP, FRIENDSHIP_EVO_THRESHOLD}),
    matching every vanilla friendship evolution in the fork's
    species_info/*.h (e.g. Golbat -> Crobat) — there is no separate
    EVO_FRIENDSHIP method in this expansion version."""
    pre = SpeciesSpec(1, "PREMON")
    post = SpeciesSpec(2, "POSTMON")
    pre_rec = _make_species(id=1, internal_name="PREMON", evolutions=[(1, 0, 2)])
    post_rec = _make_species(id=2, internal_name="POSTMON")

    staged = stage.build_staged_species((pre, post), [pre_rec, post_rec], pristine_species_egg=100)

    assert staged[0].evolution_kind == "EVO_LEVEL"
    assert staged[0].evolution_level == 0
    assert staged[0].evolution_condition == "CONDITIONS({IF_MIN_FRIENDSHIP, FRIENDSHIP_EVO_THRESHOLD})"
    assert staged[0].evolution_target_fork_id == staged[1].fork_id
    assert staged[0].evolution_item_constant is None


def test_item_evolution_emits_evo_item_with_resolved_constant(engine_dir: Path) -> None:
    """Uranium evolution method 7 (Item) is staged as EVO_ITEM with the item
    resolved through the same `_Resolver.item_constant` path pbs_converter
    uses (never a hand-rolled mapping), matching the vanilla EVO_ITEM shape
    (e.g. Togetic -> Togekiss via ITEM_SHINY_STONE)."""
    pre = SpeciesSpec(1, "PREMON")
    post = SpeciesSpec(2, "POSTMON")
    pre_rec = _make_species(id=1, internal_name="PREMON", evolutions=[(7, 18, 2)])
    post_rec = _make_species(id=2, internal_name="POSTMON")
    resolver = _make_resolver(
        item_internal={18: "SHINYSTONE"},
        item_names={18: "Shiny Stone"},
        fork_items={"ITEM_SHINY_STONE"},
    )

    staged = stage.build_staged_species(
        (pre, post), [pre_rec, post_rec], pristine_species_egg=100, resolver=resolver
    )

    assert staged[0].evolution_kind == "EVO_ITEM"
    assert staged[0].evolution_item_constant == "ITEM_SHINY_STONE"
    assert staged[0].evolution_level is None
    assert staged[0].evolution_condition is None

    charmap_chars = stage.load_charmap_chars(engine_dir)
    charmap = stage.load_charmap(engine_dir / "charmap.txt")
    text = stage.emit_species_info(staged, resolver, charmap_chars, charmap)
    assert ".evolutions = EVOLUTION({EVO_ITEM, ITEM_SHINY_STONE, SPECIES_POSTMON})," in text


def test_item_evolution_unresolved_fork_item_fails_loud() -> None:
    """An item id that resolves to a constant absent from the fork's
    include/constants/items.h fails loud instead of being substituted
    (CLAUDE.md §4.7 forward-direction gate)."""
    pre = SpeciesSpec(1, "PREMON")
    post = SpeciesSpec(2, "POSTMON")
    pre_rec = _make_species(id=1, internal_name="PREMON", evolutions=[(7, 99, 2)])
    post_rec = _make_species(id=2, internal_name="POSTMON")
    resolver = _make_resolver(
        item_internal={99: "MADEUPSTONE"},
        item_names={99: "Made Up Stone"},
        fork_items={"ITEM_SHINY_STONE"},  # deliberately missing ITEM_MADE_UP_STONE
    )

    with pytest.raises(ValueError, match="not defined in the fork"):
        stage.build_staged_species(
            (pre, post), [pre_rec, post_rec], pristine_species_egg=100, resolver=resolver
        )


def test_item_evolution_without_resolver_fails_loud() -> None:
    """Item evolution needs a resolver to look up the ITEM_* constant; a
    missing resolver fails loud rather than silently skipping the item
    lookup or defaulting to something."""
    pre = SpeciesSpec(1, "PREMON")
    post = SpeciesSpec(2, "POSTMON")
    pre_rec = _make_species(id=1, internal_name="PREMON", evolutions=[(7, 18, 2)])
    post_rec = _make_species(id=2, internal_name="POSTMON")

    with pytest.raises(ValueError, match="requires a resolver"):
        stage.build_staged_species((pre, post), [pre_rec, post_rec], pristine_species_egg=100)


def test_has_move_evolution_emits_knows_move_condition() -> None:
    """Uranium evolution method 20 (HasMove, Feleng line, CH06) is staged as
    EVO_LEVEL 0 + CONDITIONS({IF_KNOWS_MOVE, MOVE_*}) — the fork's own shape
    for Yanmega/Mamoswine/Tangrowth (species_info/gen_2_families.h)."""
    pre = SpeciesSpec(1, "PREMON")
    post = SpeciesSpec(2, "POSTMON")
    pre_rec = _make_species(id=1, internal_name="PREMON", evolutions=[(20, 246, 2)])
    post_rec = _make_species(id=2, internal_name="POSTMON")
    resolver = _make_resolver(
        move_internal={246: "ANCIENTPOWER"}, fork_moves={"MOVE_ANCIENTPOWER"}
    )

    staged = stage.build_staged_species(
        (pre, post), [pre_rec, post_rec], pristine_species_egg=100, resolver=resolver
    )

    assert staged[0].evolution_kind == "EVO_LEVEL"
    assert staged[0].evolution_level == 0
    assert staged[0].evolution_condition == "CONDITIONS({IF_KNOWS_MOVE, MOVE_ANCIENTPOWER})"


def test_has_move_evolution_unresolved_fork_move_fails_loud() -> None:
    """A HasMove evolution whose move resolves to a constant the fork lacks
    fails loud — including when the resolver carries no fork moves at all."""
    pre = SpeciesSpec(1, "PREMON")
    post = SpeciesSpec(2, "POSTMON")
    pre_rec = _make_species(id=1, internal_name="PREMON", evolutions=[(20, 246, 2)])
    post_rec = _make_species(id=2, internal_name="POSTMON")
    resolver = _make_resolver(move_internal={246: "ANCIENTPOWER"})

    with pytest.raises(ValueError, match="does not define"):
        stage.build_staged_species(
            (pre, post), [pre_rec, post_rec], pristine_species_egg=100, resolver=resolver
        )


def test_unsupported_evolution_method_still_fails_loud() -> None:
    """Every Uranium evolution method other than Level/Happiness/Item/HasMove still
    fails loud exactly as before — no permissive default was added."""
    pre = SpeciesSpec(1, "PREMON")
    post = SpeciesSpec(2, "POSTMON")
    # Method 5 = "Trade" in _EVONAMES; not one of the three handled methods.
    pre_rec = _make_species(id=1, internal_name="PREMON", evolutions=[(5, 0, 2)])
    post_rec = _make_species(id=2, internal_name="POSTMON")

    with pytest.raises(ValueError, match="unsupported evolution method 5"):
        stage.build_staged_species((pre, post), [pre_rec, post_rec], pristine_species_egg=100)


def test_uranium_original_ability_is_kept_and_passes_the_gate_as_generated(engine_dir: Path) -> None:
    """LAZY (Feliger) is no longer substituted (it was ABILITY_TRUANT until I3 S3,
    2026-10-19): the battle pass generates it, and the fork gate accepts it."""
    from types import SimpleNamespace

    from rpg2gba.species_converter import stage as st

    names = {1: "ABILITY_LAZY", 2: "ABILITY_NONE", 3: "ABILITY_INTIMIDATE"}
    r = SimpleNamespace(ability_constant=names.__getitem__)
    assert st._ability_constant(r, 1) == "ABILITY_LAZY"
    rec = SimpleNamespace(abilities=[1, 2], hidden_abilities=[3])
    staged = [SimpleNamespace(record=rec)]
    wanted = st.staged_ability_constants(staged, r)
    assert wanted == {"ABILITY_LAZY", "ABILITY_NONE", "ABILITY_INTIMIDATE"}
    assert "ABILITY_LAZY" in st.generated_battle_constants()
    st.assert_fork_constants_exist(engine_dir, wanted, "include/constants/abilities.h", "ABILITY",
                                   generated=st.generated_battle_constants())


def test_ability_gate_fails_loud_on_an_undefined_ability(tmp_path) -> None:
    from rpg2gba.species_converter import stage as st

    header = tmp_path / "include" / "constants" / "abilities.h"
    header.parent.mkdir(parents=True)
    header.write_text("#define ABILITY_NONE 0\n#define ABILITY_TRUANT 54\n", encoding="utf-8")
    st.assert_fork_constants_exist(tmp_path, {"ABILITY_TRUANT"},
                                   "include/constants/abilities.h", "ABILITY")
    with pytest.raises(ValueError, match="ABILITY_GEIGER_SENSE"):
        st.assert_fork_constants_exist(tmp_path, {"ABILITY_GEIGER_SENSE"},
                                       "include/constants/abilities.h", "ABILITY")


# ===========================================================================
# Regional dex (#31)
# ===========================================================================


def _staged_testmon() -> stage.StagedSpecies:
    return _make_staged(SpeciesSpec(1, "TESTMON"), _make_species())


def test_regional_dex_maps_staged_stock_and_unbuilt_slots() -> None:
    staged = [_staged_testmon()]
    dex = stage.build_regional_dex(
        {"SPECIES_AMPHAROS": 1, staged[0].spec.constant: 2, "SPECIES_NOTBUILT": 3},
        staged,
        stock_species=frozenset({"SPECIES_AMPHAROS"}),
        stock_national=frozenset({"NATIONAL_DEX_AMPHAROS"}),
        name="Tandor",
    )
    assert dex.name == "TANDOR"
    assert dex.order == ("NATIONAL_DEX_AMPHAROS", staged[0].spec.dex_constant, None)


def test_regional_dex_fails_loud_on_a_staged_species_with_no_number() -> None:
    with pytest.raises(ValueError, match="invisible in the dex"):
        stage.build_regional_dex({}, [_staged_testmon()], frozenset(), frozenset(), "Tandor")


def test_regional_dex_fails_loud_on_a_missing_stock_national_constant() -> None:
    with pytest.raises(ValueError, match="no stock NATIONAL_DEX_AMPHAROS"):
        stage.build_regional_dex(
            {"SPECIES_AMPHAROS": 1}, [], frozenset({"SPECIES_AMPHAROS"}), frozenset(), "Tandor"
        )


def test_regional_dex_fails_loud_on_numbering_gaps() -> None:
    with pytest.raises(ValueError, match="without gaps"):
        stage.build_regional_dex({"SPECIES_A": 1, "SPECIES_B": 3}, [], frozenset(), frozenset(), "Tandor")


def test_regional_dex_lines_skip_empty_slots_and_carry_labels() -> None:
    dex = stage.RegionalDex(name="TANDOR", order=("NATIONAL_DEX_A", None, "NATIONAL_DEX_C"))
    text = "\n".join(stage._regional_dex_lines(dex))
    assert "#define RPG2GBA_REGIONAL_DEX_COUNT 4" in text
    assert "[0] = NATIONAL_DEX_A, \\" in text
    assert "[1] =" not in text
    assert "[2] = NATIONAL_DEX_C, \\" in text
    assert '#define RPG2GBA_REGIONAL_DEX_TITLE _("TANDOR DEX")' in text
    assert '#define RPG2GBA_REGIONAL_DEX_NAME _("TANDOR")' in text


def test_regional_dex_written_from_real_data(uranium_src: Path, engine_dir: Path, tmp_path: Path) -> None:
    """Tandor has 200 slots; Orchynx (the first starter) is number 1."""
    stage.write_all(uranium_src=uranium_src, engine_dir=engine_dir, out_dir=tmp_path)
    text = (tmp_path / "rpg2gba_pokedex_ids.h").read_text(encoding="utf-8")
    assert "#define RPG2GBA_REGIONAL_DEX_COUNT 201" in text
    assert "[0] = NATIONAL_DEX_ORCHYNX, \\" in text
    assert 'RPG2GBA_REGIONAL_DEX_TITLE _("TANDOR DEX")' in text


# --- multi-evolution + Seikamater (method 26), CH09 ---------------------------

_SEIKA_CONDITION = "CONDITIONS({IF_GENDER, MON_FEMALE}, {IF_HOLD_ITEM, ITEM_ROYAL_JELLY})"


def _multi_evo_fixture() -> tuple[tuple[SpeciesSpec, ...], list[pokemon.Species], pokemon._Resolver]:
    specs = (SpeciesSpec(1, "PREMON"), SpeciesSpec(2, "SIDEMON"), SpeciesSpec(3, "ENDMON"))
    recs = [
        _make_species(id=1, internal_name="PREMON", evolutions=[(26, 498, 3), (20, 148, 2)]),
        _make_species(id=2, internal_name="SIDEMON"),
        _make_species(id=3, internal_name="ENDMON"),
    ]
    resolver = _make_resolver(
        item_internal={498: "ROYALJELLY"},
        item_names={498: "Royal Jelly"},
        move_internal={148: "INCINERATE"},
        fork_items={"ITEM_SHINY_STONE"},  # ROYAL_JELLY only exists as a generated item
        fork_moves={"MOVE_INCINERATE"},
    )
    return specs, recs, resolver


def test_multi_evolution_emits_two_entries_in_record_order(engine_dir: Path) -> None:
    specs, recs, resolver = _multi_evo_fixture()
    staged = stage.build_staged_species(specs, recs, pristine_species_egg=100, resolver=resolver)

    assert staged[0].evolution_target_fork_id == staged[2].fork_id
    assert [e.target_fork_id for e in staged[0].extra_evolutions] == [staged[1].fork_id]

    charmap_chars = stage.load_charmap_chars(engine_dir)
    charmap = stage.load_charmap(engine_dir / "charmap.txt")
    text = stage.emit_species_info(staged, resolver, charmap_chars, charmap)
    assert (
        f"        .evolutions = EVOLUTION({{EVO_LEVEL, 45, SPECIES_ENDMON, {_SEIKA_CONDITION}}},\n"
        "                                {EVO_LEVEL, 0, SPECIES_SIDEMON, CONDITIONS({IF_KNOWS_MOVE, MOVE_INCINERATE})}),\n"
    ) in text


def test_seikamater_method_26_condition_text() -> None:
    specs, recs, resolver = _multi_evo_fixture()
    staged = stage.build_staged_species(specs, recs, pristine_species_egg=100, resolver=resolver)
    assert staged[0].evolution_kind == "EVO_LEVEL"
    assert staged[0].evolution_level == 45
    assert staged[0].evolution_condition == _SEIKA_CONDITION


def test_evolution_item_accepts_item_pass_generated_constant() -> None:
    """ROYAL_JELLY is not in the fork's items.h; the item pass generates it."""
    from rpg2gba.item_converter.catalog import generated_constants

    assert "ITEM_ROYAL_JELLY" in generated_constants()
    specs = (SpeciesSpec(1, "PREMON"), SpeciesSpec(2, "POSTMON"))
    recs = [
        _make_species(id=1, internal_name="PREMON", evolutions=[(7, 498, 2)]),
        _make_species(id=2, internal_name="POSTMON"),
    ]
    resolver = _make_resolver(
        item_internal={498: "ROYALJELLY"}, item_names={498: "Royal Jelly"}, fork_items={"ITEM_SHINY_STONE"}
    )
    staged = stage.build_staged_species(specs, recs, pristine_species_egg=100, resolver=resolver)
    assert staged[0].evolution_item_constant == "ITEM_ROYAL_JELLY"


def test_seikamater_unknown_item_fails_loud() -> None:
    specs = (SpeciesSpec(1, "PREMON"), SpeciesSpec(2, "POSTMON"))
    recs = [
        _make_species(id=1, internal_name="PREMON", evolutions=[(26, 99, 2)]),
        _make_species(id=2, internal_name="POSTMON"),
    ]
    resolver = _make_resolver(
        item_internal={99: "MADEUPSTONE"}, item_names={99: "Made Up Stone"}, fork_items={"ITEM_SHINY_STONE"}
    )
    with pytest.raises(ValueError, match="not defined in the fork"):
        stage.build_staged_species(specs, recs, pristine_species_egg=100, resolver=resolver)


def test_single_evolution_text_unchanged_golden(engine_dir: Path) -> None:
    """Byte-pinned single-evolution lines (pre-multi-evolution shapes)."""
    specs = (SpeciesSpec(1, "PREMON"), SpeciesSpec(2, "POSTMON"))
    resolver = _make_resolver(move_internal={148: "INCINERATE"}, fork_moves={"MOVE_INCINERATE"})
    charmap_chars = stage.load_charmap_chars(engine_dir)
    charmap = stage.load_charmap(engine_dir / "charmap.txt")
    expected = {
        (4, 16): "        .evolutions = EVOLUTION({EVO_LEVEL, 16, SPECIES_POSTMON}),\n",
        (1, 0): "        .evolutions = EVOLUTION({EVO_LEVEL, 0, SPECIES_POSTMON, "
        "CONDITIONS({IF_MIN_FRIENDSHIP, FRIENDSHIP_EVO_THRESHOLD})}),\n",
        (20, 148): "        .evolutions = EVOLUTION({EVO_LEVEL, 0, SPECIES_POSTMON, "
        "CONDITIONS({IF_KNOWS_MOVE, MOVE_INCINERATE})}),\n",
    }
    for (method, param), line in expected.items():
        recs = [
            _make_species(id=1, internal_name="PREMON", evolutions=[(method, param, 2)]),
            _make_species(id=2, internal_name="POSTMON"),
        ]
        staged = stage.build_staged_species(specs, recs, pristine_species_egg=100, resolver=resolver)
        assert staged[0].extra_evolutions == ()
        text = stage.emit_species_info(staged, resolver, charmap_chars, charmap)
        assert line in text


def test_engine_defines_seikamater_condition_symbols(engine_dir: Path) -> None:
    header = (engine_dir / "include" / "constants" / "pokemon.h").read_text(encoding="utf-8")
    for sym in ("IF_GENDER", "IF_HOLD_ITEM", "MON_FEMALE"):
        assert re.search(rf"\b{sym}\b", header), sym
