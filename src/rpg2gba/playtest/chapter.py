"""Chapter framework: the beat-structured unit the playtest runner executes.

A *chapter* mirrors one `reference/chapters/NN-*.md` document. Each numbered
beat in that doc (B1, B2, ... and the negative beats N1, N2, ...) becomes one
`Beat` here, so a failure names the doc row it violated rather than a line
number in a long scenario function (ROM_TEST_DEV §3 items 4 and 5).

Authoring is plain Python (C4a) — no DSL:

    from ..chapter import ChapterBuilder

    moki = ChapterBuilder("moki", doc="reference/chapters/01-moki.md")

    @moki.beat("B3", "Auntie grants the Running Shoes")
    def b3(emu):
        ...

    CHAPTER = moki.build()

Symbols are late-bound at run time (E3c): beats resolve `FLAG_*`/`VAR_*` by
name through `Emulator.resolve_constant`, never by hardcoded id.
"""
from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from .emulator import Emulator

BeatFn = Callable[["Emulator"], None]


@dataclass(frozen=True)
class Beat:
    """One row of a chapter doc's beat table."""

    name: str
    description: str
    run: BeatFn


@dataclass(frozen=True)
class Chapter:
    """An ordered beat sequence, run from power-on as a single playthrough."""

    name: str
    doc: str
    beats: tuple[Beat, ...]

    def index_of(self, beat_name: str) -> int:
        for i, b in enumerate(self.beats):
            if b.name == beat_name:
                return i
        raise KeyError(
            f"chapter {self.name!r} has no beat {beat_name!r}; "
            f"beats are {[b.name for b in self.beats]}")


@dataclass
class ChapterBuilder:
    """Collects `@beat`-decorated functions in declaration order."""

    name: str
    doc: str
    _beats: list[Beat] = field(default_factory=list)

    def beat(self, name: str, description: str) -> Callable[[BeatFn], BeatFn]:
        if any(b.name == name for b in self._beats):
            raise ValueError(f"duplicate beat {name!r} in chapter {self.name!r}")

        def decorate(fn: BeatFn) -> BeatFn:
            self._beats.append(Beat(name=name, description=description, run=fn))
            return fn

        return decorate

    def build(self) -> Chapter:
        if not self._beats:
            raise ValueError(f"chapter {self.name!r} declares no beats")
        return Chapter(name=self.name, doc=self.doc, beats=tuple(self._beats))


def chapter_names() -> list[str]:
    """Every module under `rpg2gba.playtest.chapters`, sorted."""
    from . import chapters

    return sorted(m.name for m in pkgutil.iter_modules(chapters.__path__))


def load_chapter(name: str) -> Chapter:
    """Import `rpg2gba.playtest.chapters.<name>` and return its `CHAPTER`."""
    try:
        module = importlib.import_module(f"{__package__}.chapters.{name}")
    except ModuleNotFoundError as exc:
        raise KeyError(
            f"no chapter {name!r}; known chapters: {chapter_names()}") from exc
    chapter = getattr(module, "CHAPTER", None)
    if not isinstance(chapter, Chapter):
        raise TypeError(
            f"{module.__name__} must define a module-level CHAPTER: Chapter")
    return chapter
