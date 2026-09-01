"""Tests for beat groups (`group=`/`rows=` on `ChapterBuilder.beat`,
`Chapter.groups()`, `BeatGroup`) -- src/rpg2gba/playtest/chapter.py.

No mgba bindings or ROM needed: same style as `test_chapter_predecessor.py`
and `test_beat_locations.py` -- `Beat`/`Chapter`/`ChapterBuilder` are plain
objects, and predecessor chapters are "installed" by dropping a fake module
straight into `sys.modules` under the path `load_chapter` looks up.
"""
from __future__ import annotations

import sys
import types

import pytest

from rpg2gba.playtest.chapter import BeatGroup, Chapter, ChapterBuilder

PKG = "rpg2gba.playtest.chapters"


def ok(emu) -> None:
    pass


def install_chapter(name: str, chapter: Chapter) -> None:
    module = types.ModuleType(f"{PKG}.{name.lower()}")
    module.CHAPTER = chapter
    sys.modules[f"{PKG}.{name.lower()}"] = module


def install_builder(name: str, builder: ChapterBuilder) -> Chapter:
    chapter = builder.build()
    install_chapter(name, chapter)
    return chapter


@pytest.fixture(autouse=True)
def _clean_sys_modules():
    prefix = f"{PKG}."
    before = {name: mod for name, mod in sys.modules.items()
              if name == PKG or name.startswith(prefix)}
    yield
    for name in [n for n in sys.modules if n == PKG or n.startswith(prefix)]:
        if name not in before:
            del sys.modules[name]
        elif sys.modules[name] is not before[name]:
            sys.modules[name] = before[name]


# -- basic grouping ------------------------------------------------------------

def test_contiguous_group_produces_one_beat_group() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("B1", "battle", group="mawuli")
    def b1(emu):
        pass

    @builder.beat("B2", "re-talk", group="mawuli")
    def b2(emu):
        pass

    chapter = builder.build()
    groups = chapter.groups()

    assert len(groups) == 1
    assert groups[0] == BeatGroup(group_id="mawuli", beats=("B1", "B2"), index=0)


def test_ungrouped_beats_become_singleton_groups() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("B1", "first")
    def b1(emu):
        pass

    @builder.beat("B2", "second")
    def b2(emu):
        pass

    chapter = builder.build()
    groups = chapter.groups()

    assert groups == (
        BeatGroup(group_id="B1", beats=("B1",), index=0),
        BeatGroup(group_id="B2", beats=("B2",), index=1),
    )


def test_mixed_singleton_and_group_ordering() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("B1", "first")
    def b1(emu):
        pass

    @builder.beat("B2", "battle", group="mawuli")
    def b2(emu):
        pass

    @builder.beat("B3", "re-talk", group="mawuli")
    def b3(emu):
        pass

    @builder.beat("B4", "last")
    def b4(emu):
        pass

    chapter = builder.build()
    groups = chapter.groups()

    assert [g.group_id for g in groups] == ["B1", "mawuli", "B4"]
    assert [g.index for g in groups] == [0, 1, 2]
    assert groups[1].beats == ("B2", "B3")


# -- contiguity enforcement ----------------------------------------------------

def test_noncontiguous_group_raises_naming_group_and_intervening_beats() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("B1", "first")
    def b1(emu):
        pass

    @builder.beat("B2", "second")
    def b2(emu):
        pass

    @builder.beat("B3", "battle", group="mawuli")
    def b3(emu):
        pass

    @builder.beat("B4", "interloper")
    def b4(emu):
        pass

    @builder.beat("B5", "another interloper")
    def b5(emu):
        pass

    @builder.beat("B6", "re-talk", group="mawuli")
    def b6(emu):
        pass

    with pytest.raises(ValueError, match="mawuli") as excinfo:
        builder.build()

    message = str(excinfo.value)
    assert "B3" in message
    assert "B6" in message
    assert "B4" in message
    assert "B5" in message
    assert "not contiguous" in message


# -- registration-time validation ----------------------------------------------

def test_empty_group_id_raises() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    with pytest.raises(ValueError, match="non-empty"):
        @builder.beat("B1", "first", group="")
        def b1(emu):
            pass


def test_whitespace_only_group_id_raises() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    with pytest.raises(ValueError, match="non-empty"):
        @builder.beat("B1", "first", group="   ")
        def b1(emu):
            pass


def test_malformed_rows_entry_raises() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    with pytest.raises(ValueError, match="row-id shape"):
        @builder.beat("B1", "first", rows=("not-a-row-id",))
        def b1(emu):
            pass


def test_well_formed_page_row_id_accepted() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("B1", "first", rows=("map035/ev014/p1",))
    def b1(emu):
        pass

    chapter = builder.build()
    assert chapter.beats[0].rows == ("map035/ev014/p1",)


def test_well_formed_seam_row_id_accepted() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("B1", "first", rows=("map035/seam/NORTH/map036",))
    def b1(emu):
        pass

    chapter = builder.build()
    assert chapter.beats[0].rows == ("map035/seam/NORTH/map036",)


# -- singleton-name-vs-explicit-group-id collision ------------------------------

def test_singleton_name_colliding_with_explicit_group_raises() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("mawuli", "an ordinary ungrouped beat that happens to be "
                            "named like a group id used below")
    def b_named_mawuli(emu):
        pass

    @builder.beat("B2", "battle", group="mawuli")
    def b2(emu):
        pass

    @builder.beat("B3", "re-talk", group="mawuli")
    def b3(emu):
        pass

    with pytest.raises(ValueError, match="mawuli"):
        builder.build()


# -- predecessor-boundary group namespacing ------------------------------------

def test_inherited_groups_are_namespaced_and_do_not_collide() -> None:
    moki_builder = ChapterBuilder("CH01", doc="reference/chapters/01-moki.md")

    @moki_builder.beat("B1", "battle", group="mawuli")
    def m1(emu):
        pass

    @moki_builder.beat("B2", "re-talk", group="mawuli")
    def m2(emu):
        pass

    install_builder("CH01", moki_builder)

    route1_builder = ChapterBuilder(
        "CH02", doc="reference/chapters/02-route-1.md", predecessor="CH01")

    @route1_builder.beat("B1", "own battle", group="mawuli")
    def r1(emu):
        pass

    @route1_builder.beat("B2", "own re-talk", group="mawuli")
    def r2(emu):
        pass

    route1 = route1_builder.build()
    groups = route1.groups()

    # Inherited group id is namespaced to "CH01:mawuli", distinct from the
    # local "mawuli" group -- no collision, and both stay contiguous.
    group_ids = [g.group_id for g in groups]
    assert group_ids == ["CH01:mawuli", "mawuli"]
    assert groups[0].beats == ("CH01:B1", "CH01:B2")
    assert groups[1].beats == ("B1", "B2")
