"""Tests for predecessor chaining (src/rpg2gba/playtest/chapter.py).

No mgba bindings or ROM needed: chapters are plain `Chapter`/`ChapterBuilder`
objects, and `load_chapter`'s real work is just `importlib.import_module` +
`getattr(module, "CHAPTER")`, so a chapter under test is "installed" by
dropping a fake module object straight into `sys.modules` under the same
`rpg2gba.playtest.chapters.<name>` path `load_chapter` looks up -- the same
sys.modules-faking style `tests/test_runner.py` uses for its `FakeEmulator`
seam, just applied to imports instead of the emulator.
"""
from __future__ import annotations

import sys
import types

import pytest

from rpg2gba.playtest.chapter import Beat, Chapter, ChapterBuilder

PKG = "rpg2gba.playtest.chapters"


def ok(emu) -> None:
    pass


def install_chapter(name: str, chapter: Chapter) -> None:
    """Register `chapter` as `rpg2gba.playtest.chapters.<name>`'s CHAPTER,
    the same shape a real `chapters/<name>.py` module provides."""
    module = types.ModuleType(f"{PKG}.{name}")
    module.CHAPTER = chapter
    sys.modules[f"{PKG}.{name}"] = module


def install_builder(name: str, builder: ChapterBuilder) -> Chapter:
    """Build `builder` and install the result, returning the built Chapter
    (for assertions in the test itself)."""
    chapter = builder.build()
    install_chapter(name, chapter)
    return chapter


class LazyModule:
    """A module stand-in whose `CHAPTER` attribute triggers `builder.build()`
    on first access rather than being precomputed.

    Needed for the cycle test: a *real* cyclic predecessor graph can never
    have any member fully built (building any one of them recurses into
    building the others, which recurses back) -- exactly the situation a
    real `chapters/a.py` importing `chapters/b.py` importing `chapters/a.py`
    would hit via Python's own circular-import machinery. `importlib.
    import_module` returns an already-registered `sys.modules` entry without
    re-running any module body, so pre-registering three `LazyModule`s (one
    per name) lets `load_chapter`'s `getattr(module, "CHAPTER")` re-enter
    `ChapterBuilder.build()` for the same in-progress chain, which is what
    `_building_stack` is there to catch.
    """

    def __init__(self, builder: ChapterBuilder) -> None:
        self._builder = builder

    def __getattr__(self, item):
        if item == "CHAPTER":
            return self._builder.build()
        raise AttributeError(item)


def install_lazy(name: str, builder: ChapterBuilder) -> None:
    sys.modules[f"{PKG}.{name}"] = LazyModule(builder)


@pytest.fixture(autouse=True)
def _clean_sys_modules():
    """Every test installs fake modules under rpg2gba.playtest.chapters.* --
    scrub them afterward so tests can't see each other's fixtures, and so a
    genuinely-missing chapter stays genuinely missing for the "unknown
    predecessor" test.

    Restoring, not just deleting, is the point. A test that fakes `moki`
    *overwrites* a key that may already hold the real module (anything
    importing a chapter whose predecessor chain reaches `moki` caches it on
    import). Deleting only the keys this test added would leave that fake in
    place for the rest of the session, and the next test to load the real
    chapter would silently get the fake instead.
    """
    prefix = f"{PKG}."
    before = {name: mod for name, mod in sys.modules.items()
              if name == PKG or name.startswith(prefix)}
    yield
    for name in [n for n in sys.modules if n == PKG or n.startswith(prefix)]:
        if name not in before:
            del sys.modules[name]
        elif sys.modules[name] is not before[name]:
            sys.modules[name] = before[name]


# -- no predecessor: unchanged behavior --------------------------------------

def test_no_predecessor_chapter_unchanged() -> None:
    builder = ChapterBuilder("solo", doc="reference/chapters/00-solo.md")

    @builder.beat("B1", "first")
    def b1(emu):
        pass

    @builder.beat("B2", "second")
    def b2(emu):
        pass

    chapter = builder.build()

    assert chapter.predecessor is None
    assert [b.name for b in chapter.beats] == ["B1", "B2"]
    assert chapter.beats[0].description == "first"
    assert chapter.index_of("B2") == 1


# -- composition order + prefixing -------------------------------------------

def test_predecessor_beats_come_first_and_are_prefixed() -> None:
    moki_builder = ChapterBuilder("moki", doc="reference/chapters/01-moki.md")

    @moki_builder.beat("B1", "moki first beat")
    def m1(emu):
        pass

    @moki_builder.beat("B2", "moki second beat")
    def m2(emu):
        pass

    install_builder("moki", moki_builder)

    route1_builder = ChapterBuilder(
        "route1", doc="reference/chapters/02-route-1.md", predecessor="moki")

    @route1_builder.beat("B1", "route1 first beat")
    def r1(emu):
        pass

    route1 = route1_builder.build()

    assert route1.predecessor == "moki"
    assert [b.name for b in route1.beats] == ["moki:B1", "moki:B2", "B1"]
    assert route1.beats[0].description == "[moki] moki first beat"
    assert route1.beats[1].description == "[moki] moki second beat"
    # Own beat keeps its bare name and description untouched.
    assert route1.beats[2].description == "route1 first beat"
    # run callables carry over unchanged (identity-preserved).
    assert route1.beats[0].run is m1
    assert route1.beats[2].run is r1


def test_index_of_works_on_composed_chapter() -> None:
    moki_builder = ChapterBuilder("moki", doc="reference/chapters/01-moki.md")

    @moki_builder.beat("B1", "moki first")
    def m1(emu):
        pass

    install_builder("moki", moki_builder)

    route1_builder = ChapterBuilder(
        "route1", doc="reference/chapters/02-route-1.md", predecessor="moki")

    @route1_builder.beat("B1", "route1 first")
    def r1(emu):
        pass

    @route1_builder.beat("B2", "route1 second")
    def r2(emu):
        pass

    route1 = route1_builder.build()

    assert route1.index_of("moki:B1") == 0
    assert route1.index_of("B1") == 1
    assert route1.index_of("B2") == 2
    with pytest.raises(KeyError):
        route1.index_of("B99")


# -- three-chapter chain: no double-prefixing --------------------------------

def test_three_chapter_chain_does_not_double_prefix() -> None:
    moki_builder = ChapterBuilder("moki", doc="reference/chapters/01-moki.md")

    @moki_builder.beat("B3", "auntie grants running shoes")
    def m3(emu):
        pass

    install_builder("moki", moki_builder)

    route1_builder = ChapterBuilder(
        "route1", doc="reference/chapters/02-route-1.md", predecessor="moki")

    @route1_builder.beat("B1", "cross the gate")
    def r1(emu):
        pass

    install_builder("route1", route1_builder)

    kevlar_builder = ChapterBuilder(
        "kevlar", doc="reference/chapters/03-kevlar.md", predecessor="route1")

    @kevlar_builder.beat("B1", "enter kevlar city")
    def k1(emu):
        pass

    kevlar = kevlar_builder.build()

    names = [b.name for b in kevlar.beats]
    assert names == ["moki:B3", "route1:B1", "B1"]
    # The moki-owned beat is qualified once, with its TRUE origin (moki), not
    # with the immediate predecessor (route1) -- "moki:B3", never
    # "kevlar:moki:B3" or "route1:moki:B3".
    assert "moki:B3" in names
    assert "kevlar:moki:B3" not in names
    assert "route1:moki:B3" not in names
    descriptions = {b.name: b.description for b in kevlar.beats}
    assert descriptions["moki:B3"] == "[moki] auntie grants running shoes"
    assert descriptions["route1:B1"] == "[route1] cross the gate"
    assert descriptions["B1"] == "enter kevlar city"


# -- error cases --------------------------------------------------------------

def test_unknown_predecessor_raises_clear_error() -> None:
    builder = ChapterBuilder(
        "route1", doc="reference/chapters/02-route-1.md",
        predecessor="does_not_exist")

    @builder.beat("B1", "first")
    def b1(emu):
        pass

    with pytest.raises(ValueError, match="unknown predecessor"):
        builder.build()


def test_self_predecessor_raises_clear_error() -> None:
    builder = ChapterBuilder(
        "loopy", doc="reference/chapters/00-loopy.md", predecessor="loopy")

    @builder.beat("B1", "first")
    def b1(emu):
        pass

    with pytest.raises(ValueError, match="own predecessor"):
        builder.build()


def test_cycle_in_predecessor_chain_raises_clear_error() -> None:
    a_builder = ChapterBuilder("a", doc="reference/chapters/a.md", predecessor="c")

    @a_builder.beat("B1", "a beat")
    def a1(emu):
        pass

    b_builder = ChapterBuilder("b", doc="reference/chapters/b.md", predecessor="a")

    @b_builder.beat("B1", "b beat")
    def b1(emu):
        pass

    c_builder = ChapterBuilder("c", doc="reference/chapters/c.md", predecessor="b")

    @c_builder.beat("B1", "c beat")
    def c1(emu):
        pass

    # a -> c -> b -> a: a cyclic graph, so none of these can ever fully
    # build. Register all three lazily so building any one re-enters the
    # in-progress chain (see LazyModule's docstring) instead of hitting a
    # plain "module not found".
    install_lazy("a", a_builder)
    install_lazy("b", b_builder)
    install_lazy("c", c_builder)

    with pytest.raises(ValueError, match="cycle"):
        a_builder.build()


def test_build_with_no_beats_still_raises() -> None:
    builder = ChapterBuilder("empty", doc="reference/chapters/00-empty.md")
    with pytest.raises(ValueError, match="no beats"):
        builder.build()
