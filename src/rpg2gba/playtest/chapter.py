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

**`at=` is now enforced (PLAYTEST_AUTHORING_IMPROVEMENT_V2.md Q13 slice 1).**
A declared `BeatLocation` is no longer decorative: `verify_chapter_locations`
below is the static, offline half of that enforcement (reachability against
`rpg2gba.traversal.graph.MapGraph`); `runner.py` owns the runtime half
(continuity -- does the declared position match where the previous beat
actually left the player). See `verify_chapter_locations`'s docstring for the
reachability rule and how a multi-point beat is interpreted.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..tileset_converter.map_constants import MapConstantRegistry

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from .emulator import Emulator

logger = logging.getLogger(__name__)

BeatFn = Callable[["Emulator"], None]


@dataclass(frozen=True)
class BeatLocation:
    """Where a beat is supposed to be triggered, for a debug map viewer to
    draw a marker against, and -- since Q13 slice 1 -- a claim this chapter
    makes about the world that gets checked, not merely displayed: see
    `verify_chapter_locations` (offline reachability) and `runner.py`'s
    per-beat continuity check (does this beat's *first* location match where
    the previous beat actually left the player). The beat's own `run` body
    still never reads this -- it is asserted around the body, not consulted
    inside it."""

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

        **`at=` records where the beat triggers, and does NOT move the
        player** -- a beat still runs from wherever the PREVIOUS beat left
        off; declaring `at=`/`locations=` never teleports anyone. But as of
        Q13 slice 1 the declaration is a checked claim, not decoration: it
        must name a cell the offline traversable graph says is reachable
        (`verify_chapter_locations`, static, checked before the ROM runs) and
        it must match where the previous beat actually left the player
        (`runner.py`'s per-beat continuity check, checked at run time). A
        beat whose declared `at=` disagrees with the inherited position now
        fails loud, at the point of disagreement, naming both positions --
        it no longer silently starts somewhere else and fails later as a
        misleading pathfinding "stuck" error near the target.

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


# -- at= reachability (Q13 slice 1, check 1: static, offline) ----------------
#
# The runtime half (continuity: does a beat's first declared location match
# where the previous beat actually left the player) lives in `runner.py`,
# which observes a live playthrough. This half needs no ROM at all: it asks
# `rpg2gba.traversal.graph.MapGraph` -- the offline traversable graph, built
# from decoded RMXP data -- whether a declared cell is a place the player
# could ever stand. `runner.py` calls `assert_chapter_locations_reachable`
# once, up front, before spending any emulator time on a chapter.

DEFAULT_MAP_CONSTANTS_STATE_PATH_PARTS = ("uranium-build", "porymap", "map_constants.json")


def default_map_constants_state_path() -> Path:
    """`output/uranium-build/porymap/map_constants.json`, honoring
    `RPG2GBA_OUTPUT` exactly the way the rest of the pipeline does (read
    only -- this module never sets the variable, per CLAUDE.md §3/§12)."""
    root = Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
    return root.joinpath(*DEFAULT_MAP_CONSTANTS_STATE_PATH_PARTS)


def _load_map_const_to_uranium_id(state_path: Path) -> dict[str, int]:
    """`MAP_*` constant string -> Uranium map id.

    Delegates to `MapConstantRegistry.map_const_to_uranium_id`, which is the
    one source of truth for map names (CLAUDE.md 4.3). This used to hand-parse
    the persisted JSON, and the emulator's map-id bridge separately reached
    into the registry's private `_by_id`: two forks of one table, promoted to
    a public registry method per Q6's promote-on-second-use rule.

    Fails loud if the state file is absent -- never returns a guessed id.
    """
    if not state_path.exists():
        raise FileNotFoundError(
            f"map constants state not found at {state_path} -- run the "
            "Phase 5 map-constant minting step (tileset_converter."
            "map_constants.build_map_constants) before checking at= "
            "reachability")
    registry = MapConstantRegistry(state_path=state_path)
    registry.load()
    return registry.map_const_to_uranium_id()


@dataclass(frozen=True)
class LocationCheck:
    """The result of checking one declared `BeatLocation` for reachability."""

    beat: str
    location: BeatLocation
    ok: bool
    reason: str | None = None  # populated iff not ok


def _reachable(graph, cell: tuple[int, int]) -> bool:
    """The reachability rule this task applies to `MapGraph`.

    A cell is reachable if `MapGraph.is_walkable` says so, OR it is a warp
    trigger cell (`MapGraph.warp_exits`). The warp exception is required, not
    cosmetic: `graph.py`'s own module docstring documents that a warp
    trigger's walkability is decided by *plain collision*, deliberately not
    force-stamped passable the way the Phase 5 layout converter's
    `warp_overrides` do at build time -- doors are routinely drawn as a
    "solid" tile in the source tileset and only become steppable via that
    build-time override. Treating every door/warp `at=` declaration (a very
    common beat-authoring pattern -- "at the mart door", "at the old rod
    house door") as unreachable would not surface a real bug; it would
    manufacture ~7 false positives across the four gate-passed chapters where
    the coordinate is only ever the door tile a beat crosses via `enter_door`
    or `cross_threshold`. Checking `warp_exits` is exactly the escape hatch
    `graph.py` exposes for a consumer that needs to know this without
    patching the graph itself (which this task must not touch).

    A "must be in the map's largest connected component" rule was tried and
    rejected: Map073 (Kevlar) has two same-size (79-cell) components plus
    several smaller ones that are each a legitimate separate room reached by
    its own door, not a sealed-off pocket -- picking "the largest" is
    arbitrary there and flags real, working beats. Distinguishing "genuinely
    sealed off" from "a separate room, entered another way" needs the seam/
    warp topology this per-map graph does not model (`graph.py`'s own
    docstring: seams are outside its scope). `is_walkable` (blocked-vs-open)
    plus the warp exception is the reachability claim this task can make
    correctly without over-reaching into slice 2/3 territory; it is exactly
    what catches an in-wall or out-of-bounds hardcoded coordinate (v1
    finding E's B8 shape) without flagging legitimate multi-room maps.
    """
    return graph.is_walkable(cell) or bool(graph.warp_exits.get(cell))


def check_location_reachable(
    location: BeatLocation, *, beat_name: str,
    map_const_to_uranium_id: dict[str, int],
    graph_cache: dict[int, object],
) -> LocationCheck:
    """Check one `BeatLocation` against the offline graph for its map,
    building (and caching in `graph_cache`) that map's `MapGraph` on first
    use. Never raises for an ordinary check failure (unresolved map, a graph
    that fails to build, an unreachable cell) -- those are reported in the
    returned `LocationCheck`, so a caller can collect every failure across a
    whole chapter in one pass rather than stopping at the first."""
    from ..traversal.graph import build_map_graph

    uranium_id = map_const_to_uranium_id.get(location.map_constant)
    if uranium_id is None:
        return LocationCheck(
            beat_name, location, ok=False,
            reason=(f"map_constant {location.map_constant!r} does not "
                     "resolve to any minted Uranium map id (map_constants "
                     "state has no record with this map_const -- not "
                     "guessing an id)"))

    graph = graph_cache.get(uranium_id)
    if graph is None:
        try:
            graph = build_map_graph(uranium_id)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            return LocationCheck(
                beat_name, location, ok=False,
                reason=(f"offline graph for map {uranium_id} "
                         f"({location.map_constant}) failed to build: "
                         f"{exc}"))
        graph_cache[uranium_id] = graph

    cell = (location.x, location.y)
    if not _reachable(graph, cell):
        label = f" ({location.label})" if location.label else ""
        return LocationCheck(
            beat_name, location, ok=False,
            reason=(f"cell {cell} on map {uranium_id} "
                     f"({location.map_constant}){label} is not reachable: "
                     "not walkable and not a warp trigger cell"))

    return LocationCheck(beat_name, location, ok=True)


def verify_chapter_locations(
    chapter: Chapter, *, state_path: Path | None = None,
) -> list[LocationCheck]:
    """Check every declared `BeatLocation` across `chapter.beats` (including
    replayed predecessor beats -- a chapter that replays them re-plays their
    beat bodies too, so their declared positions are live claims for this
    run as well) against the offline traversable graph.

    **Multi-point interpretation:** a beat's `locations` tuple is checked
    point by point, independently -- each declared point is its own claim
    ("the door is here", "Flood is here", "Lynette is here") and must be
    independently reachable; there is no single "the" location for a
    multi-point beat to satisfy. (Contrast `runner.py`'s continuity check,
    which -- documented there -- uses only `locations[0]`, the point the
    beat expects to already be standing at when it starts.)

    Returns every check performed (pass and fail); callers that want fail-
    loud behaviour should use `assert_chapter_locations_reachable`. A beat
    with no declared location contributes nothing to the result, per this
    module's standing rule that `at=`/`locations=` stay optional -- and a
    chapter that declares NO locations at all (every synthetic/test chapter
    that exercises unrelated machinery) never touches the map-constants
    state file or the traversal package, so it stays checkable in an
    environment with no staged pipeline output."""
    if not any(beat.locations for beat in chapter.beats):
        return []
    map_const_to_uranium_id = _load_map_const_to_uranium_id(
        state_path or default_map_constants_state_path())
    graph_cache: dict[int, object] = {}
    results: list[LocationCheck] = []
    for beat in chapter.beats:
        for location in beat.locations:
            results.append(check_location_reachable(
                location, beat_name=beat.name,
                map_const_to_uranium_id=map_const_to_uranium_id,
                graph_cache=graph_cache))
    return results


def assert_chapter_locations_reachable(
    chapter: Chapter, *, state_path: Path | None = None,
) -> None:
    """Run `verify_chapter_locations` and raise loud, listing every failure,
    if any declared location is unreachable. Intended to run once per
    chapter attempt, before any emulator time is spent (`runner.py`)."""
    failures = [c for c in verify_chapter_locations(chapter, state_path=state_path)
                if not c.ok]
    if not failures:
        return
    lines = [f"  beat {c.beat!r}: {c.reason}" for c in failures]
    raise ValueError(
        f"chapter {chapter.name!r}: {len(failures)} declared at=/locations= "
        f"failed the offline reachability check (Q13 slice 1):\n"
        + "\n".join(lines))
