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

**Predecessor chaining.** A chapter that can only be reached after another
chapter's beats have run declares that chapter as its `predecessor`; the
predecessor's beats are prepended (in order), renamed `<chapter>:<beat>` so
names stay unique, rather than copy-pasted into the new module:

    route1 = ChapterBuilder("route1", doc="reference/chapters/02-route-1.md",
                             predecessor="moki")

    @route1.beat("B1", "Cross the Route 1 gate")
    def b1(emu):
        ...

    CHAPTER = route1.build()

`route1.CHAPTER.beats` is then moki's beats (`moki:B1`, `moki:B2`, ...)
followed by route1's own (`B1`, `B2`, ...). Predecessor resolution is
recursive and transitive: a predecessor that itself has a predecessor
contributes beats that are *already* prefixed with their true origin
chapter's name, and those are carried through unchanged rather than getting
a second prefix layered on.
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
class BeatLocation:
    """Where a beat is supposed to be triggered, for a debug map viewer to
    draw a marker against -- purely descriptive metadata, never consulted by
    the beat's own `run` body."""

    map_constant: str          # a MAP_* constant string, exactly as the
                                # chapter code already spells it
    x: int
    y: int
    label: str | None = None   # short human note, e.g. "mart door"


@dataclass(frozen=True)
class Beat:
    """One row of a chapter doc's beat table."""

    name: str
    description: str
    run: BeatFn
    locations: tuple[BeatLocation, ...] = ()


@dataclass(frozen=True)
class Chapter:
    """An ordered beat sequence, run from power-on as a single playthrough.

    `beats` is already fully composed: if this chapter has a `predecessor`,
    its beats (recursively resolved, renamed `<owner>:<beat>`) come first,
    followed by this chapter's own beats under their bare names. Runner.py
    and everything downstream just sees one flat `beats` tuple and doesn't
    need to know a predecessor was involved.
    """

    name: str
    doc: str
    beats: tuple[Beat, ...]
    predecessor: str | None = None

    def index_of(self, beat_name: str) -> int:
        for i, b in enumerate(self.beats):
            if b.name == beat_name:
                return i
        raise KeyError(
            f"chapter {self.name!r} has no beat {beat_name!r}; "
            f"beats are {[b.name for b in self.beats]}")


# Names currently mid-`build()`, in call order — used only to detect a cycle
# in the predecessor chain (a predecessor whose own resolution loops back to
# a chapter already being built). Nesting happens for real here: building a
# chapter with a predecessor imports that predecessor's module, which runs
# *its* `ChapterBuilder.build()` before returning, so this stack mirrors the
# live Python call stack one-for-one.
_building_stack: list[str] = []


def _prefix_beat(owner: str, beat: Beat) -> Beat:
    """Qualify `beat` with its owning chapter's name, unless it's already
    qualified (a beat that arrived via a predecessor's own predecessor keeps
    its existing `<true-owner>:<name>` — see the module docstring's note on
    not double-prefixing)."""
    if ":" in beat.name:
        return beat
    return Beat(name=f"{owner}:{beat.name}",
                description=f"[{owner}] {beat.description}", run=beat.run,
                locations=beat.locations)


@dataclass
class ChapterBuilder:
    """Collects `@beat`-decorated functions in declaration order."""

    name: str
    doc: str
    predecessor: str | None = None
    _beats: list[Beat] = field(default_factory=list)

    def beat(self, name: str, description: str, *,
             map_constant: str | None = None,
             at: tuple[int, int] | None = None,
             locations: tuple[BeatLocation, ...] | None = None,
             ) -> Callable[[BeatFn], BeatFn]:
        """Register a beat, optionally declaring where it triggers.

        Two mutually exclusive ways to declare location:

        - Shorthand, a single point: pass both `map_constant=` and `at=`.
        - Multi-point: pass `locations=` (a tuple of `BeatLocation`).

        Passing both forms, or only one half of the shorthand pair, fails
        loud -- an ambiguous or incomplete declaration is worse than none.

        **`at=` is descriptive metadata, not a command.** It records where the
        beat triggers so the debug map viewer can place it; it does NOT move
        the player. A beat runs from wherever the PREVIOUS beat left off, so
        one whose declared `at=` disagrees with that inherited position does
        not error -- it silently starts somewhere else and fails later, often
        as a misleading pathfinding "stuck" error near the target.

        **Registration order is playthrough order.** A chapter's beats are one
        continuous run, so position in this file is position in time, and beat
        *ids are labels, not ordering* (B26 deliberately runs between B4 and
        B7). Insert a new beat at the point where the state it needs already
        exists -- immediately after the beat that produces it -- rather than
        appending it to the end and navigating back. Appending is what makes a
        beat re-cross the map to reach a tile an earlier beat already stood on.

        Two consequences worth knowing before you add one (both cost a full
        red chapter run on 2026-08-19, see B27-B33):

        - `ON_WARP_INTO_MAP` dispatch compares against `getplayerxy` EXACTLY,
          with no tolerance, and falls through to the engine's `DIR_SOUTH`
          default on a miss. Landing one tile off is enough to break an
          arrival-facing assertion, and an `_assert_near` tolerance will hide
          it.
        - The LAST registered beat decides the chapter's end state, and it must
          leave field controls released. A beat that ends mid-script breaks the
          chapter-complete stamp (`stamp.dump_save_blocks` refuses a locked
          state as a seed candidate), taking the walk ROM with it.
        """
        if any(b.name == name for b in self._beats):
            raise ValueError(f"duplicate beat {name!r} in chapter {self.name!r}")

        shorthand_given = map_constant is not None or at is not None
        if shorthand_given and locations is not None:
            raise ValueError(
                f"beat {name!r}: pass either map_constant=/at= or "
                f"locations=, not both")
        if shorthand_given and (map_constant is None or at is None):
            raise ValueError(
                f"beat {name!r}: map_constant= and at= must be given "
                f"together")

        if locations is not None:
            resolved_locations = locations
        elif shorthand_given:
            x, y = at
            resolved_locations = (BeatLocation(map_constant, x, y),)
        else:
            resolved_locations = ()

        def decorate(fn: BeatFn) -> BeatFn:
            self._beats.append(Beat(name=name, description=description,
                                    run=fn, locations=resolved_locations))
            return fn

        return decorate

    def build(self) -> Chapter:
        if not self._beats:
            raise ValueError(f"chapter {self.name!r} declares no beats")
        if self.predecessor == self.name:
            raise ValueError(
                f"chapter {self.name!r} declares itself as its own predecessor")

        _building_stack.append(self.name)
        try:
            own_beats = tuple(self._beats)
            if self.predecessor is None:
                beats = own_beats
            else:
                if self.predecessor in _building_stack:
                    chain = " -> ".join(_building_stack + [self.predecessor])
                    raise ValueError(
                        f"cycle in predecessor chain: {chain}")
                try:
                    predecessor_chapter = load_chapter(self.predecessor)
                except KeyError as exc:
                    raise ValueError(
                        f"chapter {self.name!r} declares unknown predecessor "
                        f"{self.predecessor!r}") from exc
                prefixed = tuple(
                    _prefix_beat(predecessor_chapter.name, b)
                    for b in predecessor_chapter.beats)
                beats = prefixed + own_beats
        finally:
            _building_stack.pop()

        return Chapter(name=self.name, doc=self.doc, beats=beats,
                        predecessor=self.predecessor)


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
