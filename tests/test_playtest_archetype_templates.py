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

from pathlib import Path

import pytest

from rpg2gba.chapter_manifest.generator import generate_chapter_manifest
from rpg2gba.chapter_manifest.schema import ManifestRow
from rpg2gba.playtest.archetypes import ChapterArchetypeModel
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
    assert names == ["T1_battle", "T1_retalk1"]

    battle, retalk = chapter.beats
    assert battle.archetype == "trainer"
    assert battle.rows == ("map035/ev012/p0",)
    assert retalk.archetype == "trainer"
    assert retalk.rows == ("map035/ev012/p1",)

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
    assert names == ["T2_battle", "T2_retalk1", "T2_retalk2"]
    rows = [beat.rows for beat in chapter.beats]
    assert rows == [
        ("map035/ev003/p0",), ("map035/ev003/p1",), ("map035/ev003/p2",),
    ]


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
    assert [beat.name for beat in chapter.beats] == ["IB1_grant"]
    assert chapter.beats[0].archetype == "item_ball"
    assert chapter.beats[0].rows == ("map035/ev009/p0",)


def test_item_ball_beats_negative_beat_adds_spent_beat() -> None:
    b = _builder()
    item_ball_beats(
        b, chapter_id="CH04", map_constant="MAP_ROUTE_02", map_id=35,
        event_id=9, item="ITEM_POTION", beat_prefix="IB1", negative_beat=True,
    )
    chapter = b.build()
    names = [beat.name for beat in chapter.beats]
    assert names == ["IB1_grant", "IB1_spent"]
    grant, spent = chapter.beats
    assert grant.rows == ("map035/ev009/p0",)
    assert spent.rows == ("map035/ev009/p1",)
    assert grant.archetype == spent.archetype == "item_ball"


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
    assert [beat.name for beat in chapter.beats] == ["T3_battle", "T3_retalk1"]
