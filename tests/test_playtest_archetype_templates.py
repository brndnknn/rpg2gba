"""Structural tests for the archetype beat templates
(`src/rpg2gba/playtest/archetypes/`).

**mgba is not installed in this environment**, so `playtest.emulator`
cannot be imported and no beat BODY can actually be executed against a ROM.
These tests are therefore purely structural: they check what beats get
REGISTERED (names, order, `archetype`, `rows`, resolved non-literal
locations), and that the manifest-vs-stated-parameter validation and the
`ChapterArchetypeModel` conflict check fire correctly at registration time.
They do not, and cannot, prove a beat's runtime assertions are correct
against a live emulator -- that is what a real chapter's boot-walk gate
(CLAUDE.md sec 9) is for.

Fixtures: `reference/manifests/CH04.manifest.json` (committed, real,
current schema) supplies `trainer`/`item_ball` instances; CH05 does not
have a committed manifest yet, so its rows are generated in memory via
`generate_chapter_manifest` (never written to disk) to supply `warp`/
`arrival_nudge` instances -- CH04's own warp/nudge instance targets
Map036, which is not yet staged into `output/uranium-build`, so it cannot
resolve real coordinates through `cells.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.chapter_manifest.generator import generate_chapter_manifest
from rpg2gba.chapter_manifest.schema import ManifestRow, row_to_dict
from rpg2gba.playtest.archetypes import ChapterArchetypeModel, find_match
from rpg2gba.playtest.archetypes.arrival_nudge import arrival_nudge_beat
from rpg2gba.playtest.archetypes.item_ball import item_ball_beats
from rpg2gba.playtest.archetypes.trainer import trainer_beats
from rpg2gba.playtest.archetypes.warp import warp_beat
from rpg2gba.playtest.chapter import ChapterBuilder

pytestmark = pytest.mark.skipif(
    not Path("output/uranium-build/porymap/map_constants.json").exists(),
    reason="requires staged pipeline output (output/uranium-build/) to "
           "resolve coordinates via playtest.cells",
)

_BUILD_DIR = Path("output/uranium-build")
_CHAPTERS_PATH = Path("reference/chapters.json")

# CH04's real, committed, current-schema manifest -- used directly, never
# regenerated, per the module docstring.
_CH04_MANIFEST_PATH = Path("reference/manifests/CH04.manifest.json")

# CH04 fixture instances (verified against reference/manifests/CH04.manifest.json
# and ch04.py's own hand-derived constants):
#   trainer  map035 event 12 (Timothy): trigger=event_touch, phone=False,
#            double=False, retalk_pages=1, rider=False
#   item_ball map035 event 9 (Potion ball)


@pytest.fixture(scope="module")
def ch05_rows() -> tuple[ManifestRow, ...]:
    """CH05's manifest, generated in memory -- never written to disk (task
    constraint). Supplies real `warp`/`arrival_nudge` instances on Map036,
    which CH04's own manifest cannot (its one warp/nudge pair targets the
    unstaged Map036 from the OTHER side)."""
    return tuple(generate_chapter_manifest(
        "CH05", build_dir=_BUILD_DIR, chapters_path=_CHAPTERS_PATH))


def _builder(name: str = "CHZZ_TEST") -> ChapterBuilder:
    return ChapterBuilder(name, doc="test-only, not a real chapter doc")


# -- trainer -------------------------------------------------------------


def test_trainer_beats_registers_battle_and_retalk_in_order() -> None:
    b = _builder()
    trainer_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=12, trainer_const="TRAINER_TIMOTHY_247",
        defeat_flag="TRAINER_FLAGS_START + TRAINER_TIMOTHY_247",
        beat_prefix="T1", trigger="event_touch", phone=False, double=False,
        retalk_pages=1, rider=False,
    )
    chapter = b.build()
    names = [beat.name for beat in chapter.beats]
    assert names == ["T1", "T1_retalk1"]

    battle, retalk = chapter.beats
    assert battle.archetype == "trainer"
    assert battle.rows == ("map035/ev012/p0",)
    assert retalk.archetype == "trainer"
    assert retalk.rows == ("map035/ev012/p1",)

    # group=None defaults to beat_prefix, and reaches every beat the
    # template registers -- the whole point of problem 1's fix.
    assert battle.group == "T1"
    assert retalk.group == "T1"

    for beat in chapter.beats:
        assert beat.locations, f"{beat.name}: no location declared"
        loc = beat.locations[0]
        assert loc.map_constant == "MAP_ROUTE_02"
        # A resolved (derived) location, not a hand-typed literal: the
        # coordinate must be a plausible on-map cell, not (0, 0)/sentinel.
        assert isinstance(loc.x, int) and isinstance(loc.y, int)
        assert (loc.x, loc.y) != (0, 0)


def test_trainer_beats_two_retalk_pages() -> None:
    """map035 event 3 (Larrie): phone=True, retalk_pages=2 -- exercises the
    multi-retalk path and phone=True agreement."""
    b = _builder()
    trainer_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=3, trainer_const="TRAINER_LARRIE_4",
        defeat_flag="FLAG_MAP035_EVENT003_SSA",
        beat_prefix="T2", trigger="event_touch", phone=True, double=False,
        retalk_pages=2, rider=False,
    )
    chapter = b.build()
    names = [beat.name for beat in chapter.beats]
    assert names == ["T2", "T2_retalk1", "T2_retalk2"]
    rows = [beat.rows for beat in chapter.beats]
    assert rows == [
        ("map035/ev003/p0",), ("map035/ev003/p1",), ("map035/ev003/p2",),
    ]
    assert all(beat.group == "T2" for beat in chapter.beats)


def test_trainer_beats_explicit_group_overrides_default_and_reaches_every_beat() -> None:
    b = _builder()
    trainer_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=3, trainer_const="TRAINER_LARRIE_4",
        defeat_flag="FLAG_MAP035_EVENT003_SSA",
        beat_prefix="T2", trigger="event_touch", phone=True, double=False,
        retalk_pages=2, rider=False, group="STOP_LARRIE",
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == [
        "T2", "T2_retalk1", "T2_retalk2",
    ]
    assert all(beat.group == "STOP_LARRIE" for beat in chapter.beats)


def test_trainer_beats_param_disagreement_fails_loud() -> None:
    b = _builder()
    with pytest.raises(ValueError, match="disagrees with classify_manifest"):
        trainer_beats(
            b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
            event_id=12, trainer_const="TRAINER_TIMOTHY_247",
            defeat_flag="TRAINER_FLAGS_START + TRAINER_TIMOTHY_247",
            beat_prefix="T1", trigger="action",  # wrong: real trigger is event_touch
            phone=False, double=False, retalk_pages=1, rider=False,
        )


def test_trainer_beats_wrong_retalk_count_fails_loud() -> None:
    b = _builder()
    with pytest.raises(ValueError, match="disagrees with classify_manifest"):
        trainer_beats(
            b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
            event_id=12, trainer_const="TRAINER_TIMOTHY_247",
            defeat_flag="TRAINER_FLAGS_START + TRAINER_TIMOTHY_247",
            beat_prefix="T1", trigger="event_touch", phone=False,
            double=False, retalk_pages=2,  # wrong: real count is 1
            rider=False,
        )


def test_trainer_beats_unknown_event_fails_loud() -> None:
    b = _builder()
    with pytest.raises(ValueError, match="no 'trainer' archetype match"):
        trainer_beats(
            b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
            event_id=999, trainer_const="TRAINER_NOBODY",
            defeat_flag="FLAG_NOBODY", beat_prefix="TX", trigger="event_touch",
            phone=False, double=False, retalk_pages=0, rider=False,
        )


# -- item_ball -------------------------------------------------------------


def test_item_ball_beats_grant_only_by_default() -> None:
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=9, item="ITEM_POTION", beat_prefix="IB1",
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["IB1"]
    assert chapter.beats[0].archetype == "item_ball"
    assert chapter.beats[0].rows == ("map035/ev009/p0",)
    assert chapter.beats[0].group == "IB1"


def test_item_ball_beats_negative_beat_adds_spent_beat() -> None:
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=9, item="ITEM_POTION", beat_prefix="IB1", negative_beat=True,
    )
    chapter = b.build()
    names = [beat.name for beat in chapter.beats]
    assert names == ["IB1", "IB1_spent"]
    grant, spent = chapter.beats
    assert grant.rows == ("map035/ev009/p0",)
    assert spent.rows == ("map035/ev009/p1",)
    assert grant.archetype == spent.archetype == "item_ball"
    # group=None defaults to beat_prefix and reaches the satellite beat too.
    assert grant.group == spent.group == "IB1"


def test_item_ball_beats_explicit_group_overrides_default_and_reaches_every_beat() -> None:
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=9, item="ITEM_POTION", beat_prefix="IB1", negative_beat=True,
        group="STOP_POTION",
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["IB1", "IB1_spent"]
    assert all(beat.group == "STOP_POTION" for beat in chapter.beats)


def test_item_ball_beats_single_page_item_ball_registers_grant_only() -> None:
    """Loosened 2026-09-10 (REDERIVATION_PLAN.md sec 13.3 T1): CH03's
    map068/ev018 is a single-page `pbItemBall` with no page-1 remainder --
    `item_ball_beats` must still register the grant beat, claiming only the
    one row."""
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH03", map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER",
        map_id=68, event_id=18, item="ITEM_ANTIDOTE", beat_prefix="IBX",
        self_switch_letter="A",
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["IBX"]
    assert chapter.beats[0].archetype == "item_ball"
    assert chapter.beats[0].rows == ("map068/ev018/p0",)


def test_item_ball_beats_single_page_without_stated_letter_fails_loud() -> None:
    """The letter a page WRITES is not in the manifest -- `Condition` carries
    only the letter a page reads to gate itself -- so a single-page ball has
    nothing to derive it from. Demanding it beats defaulting to "A"
    (CLAUDE.md 4.5): a ball that writes B would otherwise have its grant beat
    assert the wrong flag and pass or fail for the wrong reason."""
    b = _builder()
    with pytest.raises(ValueError, match="self_switch_letter= explicitly"):
        item_ball_beats(
            b, chapter_id="CH03", map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER",
            map_id=68, event_id=18, item="ITEM_ANTIDOTE", beat_prefix="IBX",
        )


def test_item_ball_beats_stated_letter_contradicting_spent_row_fails_loud(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    """When a spent page DOES exist the manifest is the source of truth, so a
    stated letter that disagrees with it is a contradiction, not an override
    -- the same fail-loud-on-disagreement discipline the other templates apply
    to author-stated params."""
    b = _builder()
    with pytest.raises(ValueError, match="disagrees with the spent row"):
        item_ball_beats(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=3, item="ITEM_ESCAPE_ROPE", beat_prefix="IBX",
            self_switch_letter="Z", manifest_rows=ch05_rows,
        )


def test_item_ball_beats_negative_beat_on_single_page_ball_fails_loud() -> None:
    """A single-page item ball has no spent row to assert a negative beat
    against -- `negative_beat=True` must fail loud rather than silently
    skip the beat or crash on a missing row lookup."""
    b = _builder()
    with pytest.raises(ValueError, match="requires a 'spent' page"):
        item_ball_beats(
            b, chapter_id="CH03", map_constant="MAP_KEVLAR_TOWN_POKEMON_CENTER",
            map_id=68, event_id=18, item="ITEM_ANTIDOTE", beat_prefix="IBX",
            negative_beat=True,
        )


def test_item_ball_beats_unknown_event_fails_loud() -> None:
    b = _builder()
    with pytest.raises(ValueError, match="no 'item_ball' archetype match"):
        item_ball_beats(
            b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
            event_id=998, item="ITEM_POTION", beat_prefix="IBX",
        )


# -- warp --------------------------------------------------------------


def test_warp_beat_registers_one_beat_with_resolved_location(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["W1"]
    beat = chapter.beats[0]
    assert beat.archetype == "warp"
    assert beat.rows == ("map036/ev001/p0",)
    assert beat.locations[0].map_constant == "MAP_PASSAGE_CAVE_1F"
    assert (beat.locations[0].x, beat.locations[0].y) != (0, 0)
    # group=None defaults to beat_name, consistent with the other templates.
    assert beat.group == "W1"


def test_warp_beat_explicit_group_overrides_default(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
        group="STOP_CAVE_EXIT",
    )
    chapter = b.build()
    assert chapter.beats[0].group == "STOP_CAVE_EXIT"


def test_warp_beat_threshold_requires_direction(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    with pytest.raises(ValueError, match="requires direction="):
        warp_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=1, dest_map_constant="MAP_ROUTE_02",
            mechanism="threshold", beat_name="W1", manifest_rows=ch05_rows,
        )


def test_warp_beat_unknown_mechanism_fails_loud(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    with pytest.raises(ValueError, match="is not one of"):
        warp_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=1, dest_map_constant="MAP_ROUTE_02",
            mechanism="teleporter",  # not a real mechanism
            beat_name="W1", manifest_rows=ch05_rows,
        )


def test_warp_beat_round_trip_still_registers_one_beat_with_one_row(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    """`round_trip=True` is still ONE beat claiming ONE row (task brief) --
    the extra crossings it performs at runtime don't change registration."""
    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
        round_trip=True, return_direction="UP",
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["W1"]
    beat = chapter.beats[0]
    assert beat.archetype == "warp"
    assert beat.rows == ("map036/ev001/p0",)
    assert beat.group == "W1"


def test_warp_beat_round_trip_requires_return_direction_for_threshold(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    with pytest.raises(ValueError, match="requires return_direction="):
        warp_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=1, dest_map_constant="MAP_ROUTE_02",
            mechanism="threshold", direction="DOWN", beat_name="W1",
            manifest_rows=ch05_rows, round_trip=True,
        )


def test_warp_beat_return_direction_without_round_trip_fails_loud(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    with pytest.raises(ValueError, match="without round_trip=True"):
        warp_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=1, dest_map_constant="MAP_ROUTE_02",
            mechanism="threshold", direction="DOWN", beat_name="W1",
            manifest_rows=ch05_rows, return_direction="UP",
        )


def test_warp_beat_round_trip_derives_reciprocal_cells_not_a_literal(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    """The reciprocal warp/arrival cells are derived through `cells.py`'s
    own resolvers (task brief), not passed in -- there is no parameter for
    them at all. This just proves registration succeeds (i.e. the
    reciprocal derivation didn't raise) for a real corpus pair (B1's own
    Cave1F<->Route2 warp) with no coordinate ever spelled out here."""
    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
        round_trip=True, return_direction="UP",
    )
    chapter = b.build()
    assert len(chapter.beats) == 1


def test_warp_beat_round_trip_unknown_reciprocal_fails_loud(
    ch05_rows: tuple[ManifestRow, ...], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A destination map with no warp back to the origin can't be
    round-tripped -- `warp_beat` propagates `cells.warp_cell`'s own
    fail-loud error rather than silently degrading to a one-way crossing.
    Every real warp pair in the staged CH05 corpus happens to be mutually
    reciprocal, so this patches `warp_cell` to simulate the one-way case
    rather than searching the whole corpus for a coincidental example --
    the forward leg's own resolution (real data) is left untouched."""
    import rpg2gba.playtest.archetypes.warp as warp_module

    real_warp_cell = warp_module.warp_cell

    def _fake_warp_cell(map_constant: str, *, to: str, event_id: int | None = None):
        if map_constant == "MAP_ROUTE_02" and to == "MAP_PASSAGE_CAVE_1F":
            raise ValueError(
                "warp_cell: MAP_ROUTE_02 has no warp exit whose destination "
                "is MAP_PASSAGE_CAVE_1F (synthetic, for this test)"
            )
        return real_warp_cell(map_constant, to=to, event_id=event_id)

    monkeypatch.setattr(warp_module, "warp_cell", _fake_warp_cell)

    b = _builder()
    with pytest.raises(ValueError, match="no warp exit"):
        warp_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=1, dest_map_constant="MAP_ROUTE_02",
            mechanism="threshold", direction="DOWN", beat_name="W1",
            manifest_rows=ch05_rows, round_trip=True, return_direction="UP",
        )


def test_warp_beat_manifest_chapter_id_reads_a_predecessors_manifest(
    tmp_path: Path,
) -> None:
    """CH05's B1_in/B1_nudge shape (REDERIVATION_PLAN.md sec 10 R2/R3): the
    row physically lives in CH04's manifest, but CH05 claims it because
    only CH05's walk can ever trigger it. `manifest_chapter_id="CH04"` must
    load CH04's file while `chapter_id="CH05"` still identifies the
    registering chapter (beat names, error messages)."""
    _write_manifest(tmp_path / "CH04.manifest.json", (_WARP_ROW,))

    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=1, dest_map_constant="MAP_PASSAGE_CAVE_1F",
        mechanism="threshold", direction="UP", beat_name="W1",
        manifest_dir=tmp_path, manifest_chapter_id="CH04",
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["W1"]
    assert chapter.beats[0].rows == ("map035/ev001/p0",)
    assert chapter.beats[0].archetype == "warp"


# -- arrival_nudge -------------------------------------------------------


def test_arrival_nudge_beat_registers_one_beat(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    arrival_nudge_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=2, from_map_constant="MAP_PASSAGE_CAVE_2F",
        beat_name="N1", manifest_rows=ch05_rows,
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["N1"]
    beat = chapter.beats[0]
    assert beat.archetype == "arrival_nudge"
    assert beat.rows == ("map036/ev002/p1",)
    assert beat.locations[0].map_constant == "MAP_PASSAGE_CAVE_1F"
    # group=None defaults to beat_name, consistent with the other templates.
    assert beat.group == "N1"


def test_arrival_nudge_beat_explicit_group_overrides_default(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    arrival_nudge_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=2, from_map_constant="MAP_PASSAGE_CAVE_2F",
        beat_name="N1", manifest_rows=ch05_rows, group="STOP_CAVE_ARRIVE",
    )
    chapter = b.build()
    assert chapter.beats[0].group == "STOP_CAVE_ARRIVE"


def test_arrival_nudge_beat_unknown_event_fails_loud(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    with pytest.raises(ValueError, match="no 'arrival_nudge' archetype match"):
        arrival_nudge_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=997, from_map_constant="MAP_PASSAGE_CAVE_2F",
            beat_name="NX", manifest_rows=ch05_rows,
        )


# -- find_match: manifest_chapter_id (cross-chapter registration) ---------


def _write_manifest(path: Path, rows: tuple[ManifestRow, ...]) -> None:
    path.write_text(
        json.dumps([row_to_dict(r) for r in rows]),
        encoding="utf-8",
    )


_WARP_ROW = ManifestRow(
    row_id="map035/ev001/p0", kind="page", map_id=35, content_hash="deadbeef",
    effects=("warp",), event_id=1, event_name="cave_entrance", page_idx=0,
    trigger="event_touch",
)


def test_find_match_manifest_chapter_id_reads_a_predecessors_manifest(
    tmp_path: Path,
) -> None:
    """The row physically lives in CH04's manifest, but a CH05 caller
    claims it -- `manifest_chapter_id="CH04"` must load CH04's file while
    `chapter_id="CH05"` still identifies the registering chapter."""
    _write_manifest(tmp_path / "CH04.manifest.json", (_WARP_ROW,))

    match = find_match(
        "CH05", 35, 1, "warp", manifest_dir=tmp_path, manifest_chapter_id="CH04",
    )
    assert match.map_id == 35
    assert match.event_id == 1
    assert "map035/ev001/p0" in match.roles


def test_find_match_manifest_chapter_id_failure_names_the_searched_manifest(
    tmp_path: Path,
) -> None:
    """When `chapter_id` and the manifest actually searched differ, a
    zero-match failure must name which manifest was searched -- otherwise
    it misleadingly reads as "CH05 has no such row" when CH04's manifest
    (which has no matching row here either) was what was actually read."""
    _write_manifest(tmp_path / "CH04.manifest.json", (_WARP_ROW,))

    with pytest.raises(ValueError, match=r"searched CH04's manifest"):
        find_match(
            "CH05", 35, 999, "warp",
            manifest_dir=tmp_path, manifest_chapter_id="CH04",
        )


def test_find_match_without_manifest_chapter_id_is_unchanged(
    tmp_path: Path,
) -> None:
    """Omitting `manifest_chapter_id` (the default) must behave exactly as
    before: `chapter_id`'s own manifest is read, and a failure names no
    searched-manifest clause at all."""
    _write_manifest(tmp_path / "CH04.manifest.json", (_WARP_ROW,))

    match = find_match("CH04", 35, 1, "warp", manifest_dir=tmp_path)
    assert "map035/ev001/p0" in match.roles

    with pytest.raises(ValueError) as excinfo:
        find_match("CH04", 35, 999, "warp", manifest_dir=tmp_path)
    assert "searched" not in str(excinfo.value)


# -- Beat.archetype validation (chapter.py) -------------------------------


def test_beat_rejects_unknown_archetype_name() -> None:
    b = _builder()
    with pytest.raises(ValueError, match="is not one of"):
        @b.beat("X", "desc", archetype="not_a_real_archetype")
        def _x(emu):  # pragma: no cover - never called, registration fails first
            pass


def test_beat_accepts_known_archetype_name() -> None:
    b = _builder()

    @b.beat("X", "desc", archetype="trainer")
    def _x(emu):  # pragma: no cover - never called
        pass

    chapter = b.build()
    assert chapter.beats[0].archetype == "trainer"


def test_beat_default_archetype_is_none() -> None:
    b = _builder()

    @b.beat("X", "desc")
    def _x(emu):  # pragma: no cover - never called
        pass

    chapter = b.build()
    assert chapter.beats[0].archetype is None


# -- ChapterArchetypeModel -------------------------------------------------


def test_chapter_archetype_model_indexes_registered_rows() -> None:
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=9, item="ITEM_POTION", beat_prefix="IB1",
    )
    trainer_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=12, trainer_const="TRAINER_TIMOTHY_247",
        defeat_flag="TRAINER_FLAGS_START + TRAINER_TIMOTHY_247",
        beat_prefix="T1", trigger="event_touch", phone=False, double=False,
        retalk_pages=1, rider=False,
    )
    chapter = b.build()
    model = ChapterArchetypeModel(chapter)

    assert model.claimed_archetype("map035/ev009/p0") == "item_ball"
    assert model.claimed_archetype("map035/ev012/p0") == "trainer"
    assert model.claimed_archetype("map035/ev012/p1") == "trainer"
    assert model.claimed_archetype("map999/ev999/p0") is None


def test_chapter_archetype_model_fails_loud_on_conflicting_claim() -> None:
    b = _builder()

    @b.beat("A", "desc", archetype="trainer", rows=("map035/ev012/p0",))
    def _a(emu):  # pragma: no cover
        pass

    @b.beat("B", "desc", archetype="item_ball", rows=("map035/ev012/p0",))
    def _bb(emu):  # pragma: no cover
        pass

    chapter = b.build()
    with pytest.raises(ValueError, match="claimed as both"):
        ChapterArchetypeModel(chapter)


# -- manifest-file loading path (not the manifest_rows= injection path) ----


def test_trainer_beats_loads_committed_ch04_manifest_from_disk() -> None:
    """No `manifest_rows=` override -- exercises the real
    `reference/manifests/CH04.manifest.json` load-and-cache path."""
    assert _CH04_MANIFEST_PATH.exists()
    b = _builder()
    trainer_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=24, trainer_const="TRAINER_WHOEVER_24",
        defeat_flag="TRAINER_FLAGS_START + TRAINER_WHOEVER_24",
        beat_prefix="T3", trigger="event_touch", phone=False, double=False,
        retalk_pages=1, rider=False,
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["T3", "T3_retalk1"]


# --- start_side: the beat begins where the PLAYER is --------------------


def test_warp_beat_start_side_dest_needs_a_return_direction(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    """Mirroring always crosses the reciprocal, round trip or not, so its
    press direction is load-bearing even without `round_trip=True`."""
    b = _builder()
    with pytest.raises(ValueError, match="requires return_direction="):
        warp_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=1, dest_map_constant="MAP_ROUTE_02",
            mechanism="threshold", direction="DOWN", beat_name="W1",
            manifest_rows=ch05_rows, start_side="dest",
        )


def test_warp_beat_return_direction_without_either_mode_fails_loud(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    """A lone forward crossing never touches the reciprocal, so naming its
    press direction is a claim the beat cannot honour."""
    b = _builder()
    with pytest.raises(ValueError, match="has no effect on a lone forward"):
        warp_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=1, dest_map_constant="MAP_ROUTE_02",
            mechanism="threshold", direction="DOWN", beat_name="W1",
            manifest_rows=ch05_rows, return_direction="UP",
        )


def test_warp_beat_unknown_start_side_fails_loud(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    b = _builder()
    with pytest.raises(ValueError, match="is not 'origin' or 'dest'"):
        warp_beat(
            b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F",
            map_id=36, event_id=1, dest_map_constant="MAP_ROUTE_02",
            mechanism="threshold", direction="DOWN", beat_name="W1",
            manifest_rows=ch05_rows, round_trip=True, return_direction="UP",
            start_side="far",
        )


def test_warp_beat_start_side_dest_still_claims_the_same_single_row(
    ch05_rows: tuple[ManifestRow, ...],
) -> None:
    """Which side the player starts on is a fact about the chapter's
    approach, not about the warp -- it must not change what is claimed."""
    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
        round_trip=True, return_direction="UP", start_side="dest",
    )
    chapter = b.build()
    assert [beat.name for beat in chapter.beats] == ["W1"]
    assert chapter.beats[0].rows == ("map036/ev001/p0",)
    assert chapter.beats[0].archetype == "warp"


def test_warp_beat_start_side_dest_crosses_back_first_and_ends_on_origin(
    ch05_rows: tuple[ManifestRow, ...], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The operator's round-trip rule, mirrored.

    Starting on the far side, the legs must run dest->origin,
    origin->dest, dest->origin: it begins where the player actually is,
    crosses the claimed warp in the middle, and ENDS on the origin map so
    the next beat inherits the right position. Both directions are
    exercised, which is the whole reason the round trip exists.
    """
    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
        round_trip=True, return_direction="UP", start_side="dest",
    )
    beat = b.build().beats[0]

    legs: list[tuple[str, str]] = []

    class _RecordingEmu:
        # `_cross` drains the destination's arrival scripts after every
        # crossing; a leg-order fake only has to answer the call.
        def settle_field(self, **kwargs) -> int:
            return 0

    def _fake_cross_threshold(emu, name, approach, direction, dest_map):
        legs.append((direction, dest_map))

    def _noop(*args, **kwargs):
        return None

    from rpg2gba.playtest import assertions as real_assertions

    monkeypatch.setattr(real_assertions, "cross_threshold", _fake_cross_threshold)
    monkeypatch.setattr(real_assertions, "require_map", _noop)
    monkeypatch.setattr(real_assertions, "assert_near", _noop)

    beat.run(_RecordingEmu())

    assert legs == [
        ("UP", "MAP_PASSAGE_CAVE_1F"),    # dest -> origin, where we started
        ("DOWN", "MAP_ROUTE_02"),          # the CLAIMED crossing
        ("UP", "MAP_PASSAGE_CAVE_1F"),    # and back, ending on the origin
    ]


def test_warp_beat_start_side_origin_is_unchanged(
    ch05_rows: tuple[ManifestRow, ...], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default ordering must not have moved: forward, back, forward."""
    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
        round_trip=True, return_direction="UP",
    )
    beat = b.build().beats[0]

    legs: list[tuple[str, str]] = []

    def _fake_cross_threshold(emu, name, approach, direction, dest_map):
        legs.append((direction, dest_map))

    def _noop(*args, **kwargs):
        return None

    from rpg2gba.playtest import assertions as real_assertions

    monkeypatch.setattr(real_assertions, "cross_threshold", _fake_cross_threshold)
    monkeypatch.setattr(real_assertions, "require_map", _noop)
    monkeypatch.setattr(real_assertions, "assert_near", _noop)

    class _SettleEmu:
        def settle_field(self, **kwargs) -> int:
            return 0

    beat.run(_SettleEmu())

    assert legs == [
        ("DOWN", "MAP_ROUTE_02"),
        ("UP", "MAP_PASSAGE_CAVE_1F"),
        ("DOWN", "MAP_ROUTE_02"),
    ]


def test_warp_beat_start_side_dest_without_round_trip_is_two_legs(
    ch05_rows: tuple[ManifestRow, ...], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CH05's B8_return shape: reciprocal in, claimed warp out, stop.

    Mirrored and two-legged, the beat still proves the warp fires both
    ways -- that is what mirroring guarantees -- but it hands the player
    over on the map it started from instead of the far side. CH05 needs
    exactly that so `B8_nudge` can observe the arrival it lands on.
    """
    b = _builder()
    warp_beat(
        b, chapter_id="CH05", map_constant="MAP_PASSAGE_CAVE_1F", map_id=36,
        event_id=1, dest_map_constant="MAP_ROUTE_02", mechanism="threshold",
        direction="DOWN", beat_name="W1", manifest_rows=ch05_rows,
        return_direction="UP", start_side="dest",
    )
    beat = b.build().beats[0]

    legs: list[tuple[str, str]] = []

    def _fake_cross_threshold(emu, name, approach, direction, dest_map):
        legs.append((direction, dest_map))

    def _noop(*args, **kwargs):
        return None

    from rpg2gba.playtest import assertions as real_assertions

    monkeypatch.setattr(real_assertions, "cross_threshold", _fake_cross_threshold)
    monkeypatch.setattr(real_assertions, "require_map", _noop)
    monkeypatch.setattr(real_assertions, "assert_near", _noop)

    class _SettleEmu:
        def settle_field(self, **kwargs) -> int:
            return 0

    beat.run(_SettleEmu())

    assert legs == [
        ("UP", "MAP_PASSAGE_CAVE_1F"),   # the DERIVED reciprocal, crossed first
        ("DOWN", "MAP_ROUTE_02"),        # the CLAIMED crossing -- and we stop here
    ]
    assert beat.rows == ("map036/ev001/p0",)


# --- cells.local_id: the compiled object-event id, not the RMXP one ------


def test_local_id_resolves_against_the_staged_table() -> None:
    """`emu.object_event()` addresses the remapped space `local_id_remap`
    mints at staging, so the RMXP event id is the wrong number to reach
    for. Map037's table maps RMXP 4 -> 1 and 5 -> 2."""
    from rpg2gba.playtest.cells import local_id

    assert local_id("MAP_PASSAGE_CAVE_2F", 4) == 1
    assert local_id("MAP_PASSAGE_CAVE_2F", 5) == 2


def test_local_id_fails_loud_on_an_event_with_no_object(
) -> None:
    """An event with no boot page never becomes an object event. Naming the
    ids that DO exist is the difference between "which one is it" and a
    bare KeyError."""
    from rpg2gba.playtest.cells import local_id

    with pytest.raises(ValueError, match="not an emitted object event"):
        local_id("MAP_PASSAGE_CAVE_2F", 999)


def test_local_id_fails_loud_on_an_unstaged_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A map with no table has not been staged -- a different fix from an
    event that simply has no object, so a different message."""
    from rpg2gba.playtest import cells

    monkeypatch.setattr(
        cells, "_local_id_table_path", lambda uid: tmp_path / f"Map{uid:03d}.json")

    with pytest.raises(ValueError, match="has not been staged"):
        cells.local_id("MAP_PASSAGE_CAVE_2F", 5)
