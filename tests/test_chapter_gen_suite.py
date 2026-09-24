"""Tests for the "gen" chapter suite (C9): `playtest.chapters_gen`, threaded
through `chapter.py`'s `suite=` parameter on `load_chapter`/
`load_chapter_module` and `ChapterBuilder.suite`.

Follows `tests/test_chapter_predecessor.py`'s sys.modules-faking style: a
chapter under test is "installed" by dropping a fake module object straight
into `sys.modules` under the real lookup path (`rpg2gba.playtest.chapters.
<name>` or `rpg2gba.playtest.chapters_gen.<name>`), so no real files are
ever written under `src/`.
"""
from __future__ import annotations

import logging
import sys
import types

import pytest

from rpg2gba.playtest.chapter import (
    Chapter,
    ChapterBuilder,
    gen_chapter_names,
    load_chapter,
    load_chapter_module,
)

HAND_PKG = "rpg2gba.playtest.chapters"
GEN_PKG = "rpg2gba.playtest.chapters_gen"


def ok(emu) -> None:
    pass


def make_chapter(name: str) -> Chapter:
    builder = ChapterBuilder(name, doc=f"reference/chapters/00-{name.lower()}.md")
    builder.beat("B1", "does a thing")(ok)
    return builder.build()


def install(pkg: str, name: str, chapter: Chapter) -> None:
    """Register `chapter` as `<pkg>.<name.lower()>`'s CHAPTER."""
    module = types.ModuleType(f"{pkg}.{name.lower()}")
    module.CHAPTER = chapter
    sys.modules[f"{pkg}.{name.lower()}"] = module


def install_builder(pkg: str, name: str, builder: ChapterBuilder) -> Chapter:
    chapter = builder.build()
    install(pkg, name, chapter)
    return chapter


@pytest.fixture(autouse=True)
def _clean_sys_modules():
    """Scrub every fake module this test file installs, restoring whatever
    (real or previously-faked) module occupied that name before -- same
    rationale as `test_chapter_predecessor.py`'s fixture of the same name."""
    prefixes = (f"{HAND_PKG}.", f"{GEN_PKG}.")
    names = {HAND_PKG, GEN_PKG}
    before = {n: m for n, m in sys.modules.items()
              if n in names or n.startswith(prefixes)}
    yield
    for n in [n for n in sys.modules if n in names or n.startswith(prefixes)]:
        if n not in before:
            del sys.modules[n]
        elif sys.modules[n] is not before[n]:
            sys.modules[n] = before[n]


# -- load_chapter(_module) suite= --------------------------------------------

def test_default_suite_is_hand_unchanged():
    chapter = make_chapter("CHZHAND")
    install(HAND_PKG, "CHZHAND", chapter)
    assert load_chapter("CHZHAND") is chapter
    assert load_chapter("CHZHAND", suite="hand") is chapter


def test_gen_suite_loads_from_chapters_gen():
    chapter = make_chapter("CHZGEN")
    install(GEN_PKG, "CHZGEN", chapter)
    assert load_chapter("CHZGEN", suite="gen") is chapter
    assert load_chapter_module("CHZGEN", suite="gen").CHAPTER is chapter


def test_gen_suite_does_not_see_a_hand_only_module():
    chapter = make_chapter("CHZHANDONLY")
    install(HAND_PKG, "CHZHANDONLY", chapter)
    with pytest.raises(KeyError):
        load_chapter("CHZHANDONLY", suite="gen")


def test_missing_gen_module_names_the_suite_and_lists_available():
    with pytest.raises(KeyError) as exc_info:
        load_chapter("CHZNOPE", suite="gen")
    message = str(exc_info.value)
    assert "'gen'" in message
    assert "gen chapters" in message


def test_gen_chapter_names_is_a_sorted_list():
    names = gen_chapter_names()
    assert names == sorted(names)


# -- predecessor resolution (ChapterBuilder.suite) ----------------------------

def test_hand_chapter_always_resolves_predecessor_from_hand():
    """A suite="hand" (the default) builder must never look at chapters_gen,
    even when a gen module of the same name exists -- unchanged behaviour
    for every existing hand chapter."""
    hand_pred = make_chapter("CHPREDBOTH")
    install(HAND_PKG, "CHPREDBOTH", hand_pred)
    gen_pred = make_chapter("CHPREDBOTH")  # a distinct Chapter object
    install(GEN_PKG, "CHPREDBOTH", gen_pred)

    child = ChapterBuilder("CHCHILDHAND", doc="d", predecessor="CHPREDBOTH")
    child.beat("B1", "x")(ok)
    built = child.build()

    assert built.beats[0].name == "CHPREDBOTH:B1"
    assert built.beats[0].description == f"[CHPREDBOTH] {hand_pred.beats[0].description}"


def test_gen_chapter_replays_predecessor_from_gen_when_it_exists():
    pred = make_chapter("CHPREDGEN")
    install(GEN_PKG, "CHPREDGEN", pred)

    child = ChapterBuilder("CHCHILDGEN", doc="d", predecessor="CHPREDGEN", suite="gen")
    child.beat("B1", "x")(ok)
    built = child.build()

    assert built.beats[0].name == "CHPREDGEN:B1"


def test_gen_chapter_falls_back_to_hand_when_no_gen_predecessor(caplog):
    pred = make_chapter("CHPREDFALLBACK")
    install(HAND_PKG, "CHPREDFALLBACK", pred)

    child = ChapterBuilder("CHCHILDFALLBACK", doc="d",
                           predecessor="CHPREDFALLBACK", suite="gen")
    child.beat("B1", "x")(ok)
    with caplog.at_level(logging.INFO):
        built = child.build()

    assert built.beats[0].name == "CHPREDFALLBACK:B1"
    assert any("'hand'" in r.message for r in caplog.records)


def test_gen_chapter_prefers_gen_predecessor_over_hand_when_both_exist():
    hand_pred = make_chapter("CHPREDPREFER")
    install(HAND_PKG, "CHPREDPREFER", hand_pred)
    gen_pred = ChapterBuilder("CHPREDPREFER", doc="d")
    gen_pred.beat("B1", "the gen version")(ok)
    gen_chapter = install_builder(GEN_PKG, "CHPREDPREFER", gen_pred)

    child = ChapterBuilder("CHCHILDPREFER", doc="d",
                           predecessor="CHPREDPREFER", suite="gen")
    child.beat("B1", "x")(ok)
    built = child.build()

    assert built.beats[0].description == f"[CHPREDPREFER] {gen_chapter.beats[0].description}"


def test_unknown_predecessor_still_fails_loud_for_gen_suite():
    child = ChapterBuilder("CHCHILDNOPRED", doc="d",
                           predecessor="CHNOSUCHTHING", suite="gen")
    child.beat("B1", "x")(ok)
    with pytest.raises(ValueError, match="unknown predecessor"):
        child.build()
