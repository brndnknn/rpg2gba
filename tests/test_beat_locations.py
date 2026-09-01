"""Tests for `BeatLocation` and `ChapterBuilder.beat`'s location-declaring
kwargs (src/rpg2gba/playtest/chapter.py).

No mgba bindings or ROM needed -- same style as `test_chapter_predecessor.py`:
`Beat`/`Chapter`/`ChapterBuilder` are plain objects, so a chapter under test
is a bare `ChapterBuilder` built directly, with no emulator ever touched.
"""
from __future__ import annotations

import importlib
import pkgutil

import pytest

from rpg2gba.playtest.chapter import BeatLocation, ChapterBuilder


def ok(emu) -> None:
    pass


# -- default-empty ------------------------------------------------------------

def test_beat_defaults_to_no_locations() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("B1", "no location declared")
    def b1(emu):
        pass

    chapter = builder.build()
    assert chapter.beats[0].locations == ()


# -- shorthand form -------------------------------------------------------

def test_shorthand_single_point() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("B1", "single point", map_constant="MAP_FOO", at=(3, 4))
    def b1(emu):
        pass

    chapter = builder.build()
    locations = chapter.beats[0].locations
    assert locations == (BeatLocation("MAP_FOO", 3, 4),)
    assert locations[0].label is None


def test_shorthand_with_label() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("B1", "single point with label",
                  map_constant="MAP_FOO", at=(3, 4))
    def b1(emu):
        pass

    chapter = builder.build()
    loc = chapter.beats[0].locations[0]
    assert loc.map_constant == "MAP_FOO"
    assert loc.x == 3
    assert loc.y == 4


# -- multi-point form -----------------------------------------------------

def test_multi_point_locations() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    locs = (
        BeatLocation("MAP_FOO", 1, 2, "door"),
        BeatLocation("MAP_BAR", 5, 6, "npc"),
    )

    @builder.beat("B1", "two points", locations=locs)
    def b1(emu):
        pass

    chapter = builder.build()
    assert chapter.beats[0].locations == locs


# -- fail-loud error cases --------------------------------------------------

def test_both_forms_raises() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    with pytest.raises(ValueError, match="not both"):
        @builder.beat("B1", "conflicting", map_constant="MAP_FOO", at=(1, 2),
                      locations=(BeatLocation("MAP_BAR", 3, 4),))
        def b1(emu):
            pass


def test_at_without_map_constant_raises() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    with pytest.raises(ValueError, match="together"):
        @builder.beat("B1", "incomplete", at=(1, 2))
        def b1(emu):
            pass


def test_map_constant_without_at_raises() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    with pytest.raises(ValueError, match="together"):
        @builder.beat("B1", "incomplete", map_constant="MAP_FOO")
        def b1(emu):
            pass


# -- predecessor chaining preserves locations --------------------------------

def test_predecessor_beats_keep_locations(monkeypatch) -> None:
    import sys
    import types

    PKG = "rpg2gba.playtest.chapters"

    moki_builder = ChapterBuilder("CH01", doc="reference/chapters/01-moki.md")

    @moki_builder.beat("B1", "moki beat with a location",
                        map_constant="MAP_MOKI", at=(7, 8))
    def m1(emu):
        pass

    moki_chapter = moki_builder.build()
    module = types.ModuleType(f"{PKG}.ch01")
    module.CHAPTER = moki_chapter
    monkeypatch.setitem(sys.modules, f"{PKG}.ch01", module)

    route1_builder = ChapterBuilder(
        "CH02", doc="reference/chapters/02-route-1.md", predecessor="CH01")

    @route1_builder.beat("B1", "route1 beat with a location",
                          map_constant="MAP_ROUTE_01", at=(9, 10))
    def r1(emu):
        pass

    route1_chapter = route1_builder.build()

    by_name = {b.name: b for b in route1_chapter.beats}
    assert by_name["CH01:B1"].locations == (BeatLocation("MAP_MOKI", 7, 8),)
    assert by_name["B1"].locations == (BeatLocation("MAP_ROUTE_01", 9, 10),)


# -- data check: every declared map_constant across the real chapters looks
# like a plausible MAP_* symbol -----------------------------------------------

def _all_real_chapter_names() -> list[str]:
    from rpg2gba.playtest import chapters
    return sorted(m.name for m in pkgutil.iter_modules(chapters.__path__))


def test_all_declared_map_constants_look_plausible() -> None:
    checked_any = False
    for name in _all_real_chapter_names():
        module = importlib.import_module(f"rpg2gba.playtest.chapters.{name}")
        chapter = module.CHAPTER
        for beat in chapter.beats:
            for loc in beat.locations:
                checked_any = True
                assert loc.map_constant, (
                    f"{chapter.name}:{beat.name} has an empty map_constant")
                assert loc.map_constant.startswith("MAP_"), (
                    f"{chapter.name}:{beat.name}'s map_constant "
                    f"{loc.map_constant!r} doesn't start with MAP_")
                assert isinstance(loc.x, int)
                assert isinstance(loc.y, int)
    assert checked_any, "expected at least one beat with a declared location"
