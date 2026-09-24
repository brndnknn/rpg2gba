"""Chapter framework: the beat-structured unit the playtest runner executes.

A *chapter* mirrors one `reference/chapters/NN-*.md` document. Each numbered
beat in that doc (B1, B2, ... and the negative beats N1, N2, ...) becomes one
`Beat` here, so a failure names the doc row it violated rather than a line
number in a long scenario function (ROM_TEST_DEV §3 items 4 and 5).

Authoring is plain Python (C4a) — no DSL:

    from ..chapter import ChapterBuilder

    moki = ChapterBuilder("CH01", doc="reference/chapters/01-moki.md")

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

    route1 = ChapterBuilder("CH02", doc="reference/chapters/02-route-1.md",
                             predecessor="CH01")

    @route1.beat("B1", "Cross the Route 1 gate")
    def b1(emu):
        ...

    CHAPTER = route1.build()

`route1.CHAPTER.beats` is then CH01's beats (`CH01:B1`, `CH01:B2`, ...)
followed by route1's own (`B1`, `B2`, ...). Predecessor resolution is
recursive and transitive: a predecessor that itself has a predecessor
contributes beats that are *already* prefixed with their true origin
chapter's name, and those are carried through unchanged rather than getting
a second prefix layered on.

**`at=` is now enforced (PLAYTEST_AUTHORING_IMPROVEMENT_V2.md Q13 slice 1).**
A declared `BeatLocation` is no longer decorative: `verify_chapter_locations`
below is the static, offline half of that enforcement (reachability against
`rpg2gba.traversal.graph.MapGraph`). `runner.py` owns the runtime half
(continuity), but -- since 2026-09-05, after `locations[0]` turned out not to
reliably mean "inherited entry position" (measured in `ChapterBuilder.beat`'s
docstring) -- continuity is checked only against the separate, opt-in
`entry_at=` beat parameter, and is a no-op for a beat that doesn't set it. See
`verify_chapter_locations`'s docstring for the reachability rule and how a
multi-point beat is interpreted, and `ChapterBuilder.beat`'s docstring for
`entry_at=`.
"""
from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Literal

from ..chapter_manifest.archetypes import ARCHETYPE_NAMES
from ..tileset_converter.map_constants import MapConstantRegistry

if TYPE_CHECKING:  # runtime import is lazy so the registry works without bindings
    from .emulator import Emulator

logger = logging.getLogger(__name__)

BeatFn = Callable[["Emulator"], None]

#: Which chapter-module package a name resolves against: "hand" is the
#: hand-written `playtest.chapters` package (the default, unchanged
#: behaviour); "gen" is the beat-gen-written `playtest.chapters_gen`
#: sibling (C9 rulings). See `load_chapter`/`load_chapter_module` and
#: `ChapterBuilder.suite`.
Suite = Literal["hand", "gen"]

# Row-id parsing is `chapter_manifest.schema.parse_row_id` now (C1,
# REDERIVATION_PLAN.md §16.3 R5's "one implementation" rule) -- this module
# used to carry its own regex trio rather than import the chapter_manifest
# package just to validate a string shape, but that duplication is exactly
# what let a stale `(NORTH|SOUTH|EAST|WEST)` seam pattern (fixed 2026-09-11)
# silently reject every seam row the generator has ever emitted. Importing
# `schema` from here does not create a cycle: `chapter_manifest.boundary_
# model` already imports `playtest.chapter`, but `schema` itself imports
# nothing from `playtest` or `chapter_manifest`'s other modules -- it is a
# leaf. A branch row (`.../pN/bM`) is accepted here too, alongside page/
# seam/terrain, so a beat can claim one.
from ..chapter_manifest.schema import parse_row_id
from ..beat_floor.assertion import FloorAssertion


def _validate_row_id(row: str, *, beat_name: str) -> None:
    try:
        parse_row_id(row)
    except ValueError as exc:
        raise ValueError(
            f"beat {beat_name!r}: rows entry {row!r} does not match the "
            "chapter-manifest row-id shape (expected a page row like "
            "'map035/ev014/p1', a branch row like 'map035/ev014/p1/b2', a "
            "seam row like 'map035/seam/NORTH/map036', or a terrain row "
            "like 'map037/terrain/stairs/11,9' -- see page_row_id/"
            "branch_row_id/seam_row_id/terrain_row_id in "
            "src/rpg2gba/chapter_manifest/schema.py)"
        ) from exc


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
    """One row of a chapter doc's beat table.

    `entry_at`, independent of `locations` (see `ChapterBuilder.beat`'s
    docstring for why the two are separate claims), is this beat's explicit
    opt-in to runtime continuity checking: "this beat starts from here." A
    beat that doesn't set it makes no inherited-position claim at all, and
    `runner.py`'s `_check_beat_continuity` is a no-op for it."""

    name: str
    description: str
    run: BeatFn
    locations: tuple[BeatLocation, ...] = ()
    entry_at: tuple[int, int] | None = None
    group: str | None = None
    rows: tuple[str, ...] = ()
    # Which recognized RPG Maker event archetype (`chapter_manifest.
    # archetypes.ARCHETYPE_NAMES`) this beat claims to be exercising, or
    # None for a beat that isn't one of the four recognized shapes. Feeds
    # `playtest.archetypes.ChapterArchetypeModel`, the concrete adapter for
    # `chapter_manifest.checker.ArchetypeModel` -- see that Protocol's
    # docstring for why the checker itself never imports `playtest`.
    # A beat whose rows are of different archetypes (a warp crossing plus
    # the arrival nudge it lands on, say) carries `(row_id, archetype)`
    # pairs instead of one name; read it through `archetype_of`.
    archetype: str | tuple[tuple[str, str], ...] | None = None
    # The assertions this beat's body actually checks, in the generic floor's
    # vocabulary (REDERIVATION_PLAN.md §16.3 C5). `None` means undeclared (a
    # hand-written beat), which is distinct from declaring nothing. The
    # checker's ⊇-floor rule compares these against each claimed row's floor.
    assertions: frozenset[FloorAssertion] | None = None

    def archetype_of(self, row_id: str) -> str | None:
        """The archetype this beat claims for `row_id`, or None when it
        claims none for that row (including a row it doesn't list)."""
        if row_id not in self.rows or self.archetype is None:
            return None
        if isinstance(self.archetype, str):
            return self.archetype
        return dict(self.archetype).get(row_id)


def page_row_script(row_id: str) -> tuple[int, str] | None:
    """`("map037/ev004/p0")` -> `(37, "Map037_EV004_Page1")`, or `None` for a
    row id that names no page script (seam and terrain rows).

    A branch row (`"map037/ev004/p0/b2"`) resolves to the SAME script as its
    owning page: the transpiler emits one `.pory` script per PAGE, not per
    arm (`conversion_agent.transpiler.parse_tree` nests branches inside one
    page's control flow), so an arm's trigger fires as part of that same
    script -- there is no separate script for a branch row to name.

    The one place that knows this mapping. Both consumers of the
    foreign-trigger exemption go through it -- `resolved_trigger_scripts`
    below for a predecessor's dispositions, and
    `runner._WalkOracle.mark_rows_resolved` for this chapter's own beats as
    they pass -- so the two can never disagree about which script a row
    names. Note the page number is 1-based on the label and 0-based in the
    row id (`metadata_wiring.page_label`'s own convention).
    """
    from ..tileset_converter.metadata_wiring import page_label

    parsed = parse_row_id(row_id)
    if parsed.kind not in ("page", "branch"):
        return None
    assert parsed.event_id is not None and parsed.page_idx is not None
    return parsed.map_id, page_label(parsed.map_id, parsed.event_id, parsed.page_idx + 1)


def resolved_trigger_scripts(chapter: "Chapter") -> dict[int, set[str]]:
    """Per map id, the page scripts an INHERITED beat of `chapter` already
    exercised -- so they are no longer "foreign" to this chapter's own walks.

    A foreign trigger is one a walk has no business firing. The rule that
    finds them asks only "does this beat own that script", which is right
    within a chapter and wrong across a predecessor replay: an inherited beat
    runs before EVERY beat this chapter owns (`ChapterBuilder`'s
    `predecessor` prepends them), so what it resolved stays resolved.

    CH05 is the case. Its approach from CH04's handover cell must pass
    Youngster Timothy's event-touch tile -- `routing.pathing.plan_segment`
    tries a trigger-free path first and there is none, so it is geography,
    not a search failure. `CH04:B4` fights and defeats him during the replay
    and latches his self-switch, so by the time CH05's first beat walks past,
    the tile fires nothing. Treating it as foreign failed a beat over a
    script that cannot run.

    Two deliberate narrowings:

    * INHERITED only. A chapter's own triggers stay foreign to each other:
      B3's trainer must not be excused for firing during an approach to B8,
      which is the point of the check.
    * REGISTERED only. The claim comes from the predecessor's committed
      dispositions (`beat:B4`), but a disposition is an intent, not a run --
      CH04 disposes `beat:` on rows whose beats are in `DEFERRED_BEATS` and
      never execute. So each claim is confirmed against a beat actually
      present in `chapter.beats`, matched with `beat_model._matches` so a
      template-registered family (`B4_battle`) satisfies `beat:B4` exactly as
      the checker does.

    The predecessors are read off `chapter.beats` itself rather than walking
    `chapters.json` again -- the prefixes on the inherited beats already name
    every chapter that contributed one, transitively.

    Fail-soft: a predecessor with no dispositions file contributes nothing
    (CH01-CH03 predate the manifest). That is the pre-existing behaviour --
    every trigger stays foreign -- not a silent weakening.
    """
    from ..chapter_manifest.beat_model import _matches
    from ..chapter_manifest.dispositions import disposition_path, load_dispositions

    inherited: dict[str, set[str]] = {}
    for beat in chapter.beats:
        if ":" not in beat.name:
            continue
        owner, _, own_name = beat.name.partition(":")
        inherited.setdefault(owner, set()).add(own_name)
    if not inherited:
        return {}

    resolved: dict[int, set[str]] = {}
    for owner, beat_names in inherited.items():
        path = disposition_path(owner)
        try:
            dispositions = load_dispositions(path)
        except (OSError, ValueError) as exc:
            logger.info(
                "resolved_trigger_scripts: no usable dispositions for "
                "predecessor %s (%s) -- its triggers stay foreign", owner, exc)
            continue
        for row_id, disposition in dispositions.items():
            if disposition.verdict != "beat":
                continue
            beat_id = (disposition.argument or "").strip()
            if not beat_id:
                continue
            if not any(_matches(beat_id, name) for name in beat_names):
                continue  # dispositioned but deferred: it never ran
            named = page_row_script(row_id)
            if named is None:
                continue  # seam/terrain rows name no page script
            map_id, script = named
            resolved.setdefault(map_id, set()).add(script)
    return resolved


@dataclass(frozen=True)
class BeatGroup:
    """A run of beats the route solver must keep contiguous.

    Beats sharing a `Beat.group` value form one `BeatGroup`. A beat with no
    `group` forms its own singleton group named after itself. `index` is the
    group's position in the chapter (0-based), in the order the group's
    first beat was registered -- see `Chapter.groups`."""

    group_id: str
    beats: tuple[str, ...]
    index: int


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
    #: Where this chapter's route STARTS, when that is not the first beat's
    #: own interaction cell. The route solver otherwise takes the entry from
    #: `own_beats[0].locations[0]`, which is also what it uses as that
    #: group's interaction cell -- the point later segments are costed FROM.
    #: Those are the same cell for a beat that begins where it acts, and a
    #: different one for a beat that begins on the far side of its own warp
    #: (`warp_beat(start_side="dest")`).
    #:
    #: CH05's B1 is the case that forced the split: it is authored on the
    #: cave's exit warp, which is where it acts and where it leaves the
    #: player, but the chapter begins on Route 02 where CH04 hands the player
    #: over. Overloading `locations[0]` to mean both costs the solver its
    #: departure point -- measured, not guessed: it moved CH05 from 141 to
    #: 258 tiles and reordered the cave into a backtracking sweep, because
    #: every segment after B1 was then costed from Route 02 rather than from
    #: inside the cave.
    #:
    #: Declaring it leaves `locations[0]` meaning exactly what it meant
    #: before for every chapter, so CH01-CH04 re-solve unchanged.
    route_entry: BeatLocation | None = None

    def index_of(self, beat_name: str) -> int:
        for i, b in enumerate(self.beats):
            if b.name == beat_name:
                return i
        raise KeyError(
            f"chapter {self.name!r} has no beat {beat_name!r}; "
            f"beats are {[b.name for b in self.beats]}")

    def groups(self) -> tuple[BeatGroup, ...]:
        """Beats collapsed into contiguous `BeatGroup`s, in registration
        order. `build()` already validated contiguity and the singleton-
        name-vs-explicit-group-id collision, so this is a pure reshape --
        one pass, no re-validation."""
        result: list[BeatGroup] = []
        current_id: str | None = None
        current_beats: list[str] = []
        for beat in self.beats:
            group_id = beat.group if beat.group is not None else beat.name
            if group_id != current_id:
                if current_id is not None:
                    result.append(BeatGroup(group_id=current_id,
                                             beats=tuple(current_beats),
                                             index=len(result)))
                current_id = group_id
                current_beats = []
            current_beats.append(beat.name)
        if current_id is not None:
            result.append(BeatGroup(group_id=current_id,
                                     beats=tuple(current_beats),
                                     index=len(result)))
        return tuple(result)


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
    not double-prefixing).

    `group` is namespaced the same way as `name`, and for the same reason:
    without it, an explicit group id chosen in a predecessor chapter could
    collide with a same-named group (or singleton beat name) chosen
    independently in a downstream chapter. A beat with no explicit group
    needs no separate handling here -- its singleton group id is its own
    (already-prefixed) name."""
    if ":" in beat.name:
        return beat
    prefixed_group = (beat.group if beat.group is None or ":" in beat.group
                       else f"{owner}:{beat.group}")
    return Beat(name=f"{owner}:{beat.name}",
                description=f"[{owner}] {beat.description}", run=beat.run,
                locations=beat.locations, entry_at=beat.entry_at,
                group=prefixed_group, rows=beat.rows, archetype=beat.archetype,
                assertions=beat.assertions)


@dataclass
class ChapterBuilder:
    """Collects `@beat`-decorated functions in declaration order."""

    name: str
    doc: str
    predecessor: str | None = None
    route_entry: BeatLocation | None = None
    #: Which suite THIS builder belongs to. "hand" (the default) always
    #: resolves its predecessor from the hand suite, exactly as before this
    #: field existed. "gen" (set by the generator's emitted modules,
    #: `beat_gen/emit.py`) replays its predecessor from the gen suite when
    #: that gen module exists, else falls back to the hand suite -- see
    #: `build()`.
    suite: Suite = "hand"
    _beats: list[Beat] = field(default_factory=list)

    def beat(self, name: str, description: str, *,
             map_constant: str | None = None,
             at: tuple[int, int] | None = None,
             locations: tuple[BeatLocation, ...] | None = None,
             entry_at: tuple[int, int] | None = None,
             group: str | None = None,
             rows: tuple[str, ...] = (),
             archetype: str | Mapping[str, str] | None = None,
             assertions: frozenset[FloorAssertion] | None = None,
             ) -> Callable[[BeatFn], BeatFn]:
        """Register a beat, optionally declaring where it triggers.

        `group=` and `rows=` feed the offline route solver (not consulted by
        the beat body or the runner):

        - `group=`: this beat's group id. Beats sharing a group id must be
          registered contiguously (checked at `build()` time) -- the
          solver treats a group as one indivisible stop, so its beats can
          never be reordered apart. A beat with no `group` gets its own
          singleton group, named after the beat itself.
        - `rows=`: chapter-manifest row ids (`page_row_id`/`seam_row_id`
          shape, e.g. `"map035/ev014/p1"` or `"map035/seam/NORTH/map036"`)
          this beat exercises, letting the solver derive page-precedence
          constraints. Validated against those shapes at registration time.
        - `archetype=`: which recognized RPG Maker event archetype
          (`chapter_manifest.archetypes.ARCHETYPE_NAMES` -- "trainer",
          "item_ball", "warp", "arrival_nudge") this beat claims to be
          exercising, or `None` (the default) for a beat that isn't one of
          the four recognized shapes. Feeds `playtest.archetypes.
          ChapterArchetypeModel`, which the checker's
          `RULE_ARCHETYPE_CONFORMANCE` uses to confirm a `beat`-
          dispositioned archetype row actually has a beat claiming it, not
          just a disposition saying it does (the B14 shape). Validated
          against `ARCHETYPE_NAMES` at registration time. A single name
          tags every row in `rows=`. A beat whose rows are of different
          archetypes passes a `{row_id: archetype}` mapping instead; each
          key must be one of this beat's `rows=`, and a listed row left out
          of the mapping is claimed under no archetype (a story page riding
          along with a warp crossing, say). Added 2026-09-14: before it,
          about ten CH01-CH03 beats were untaggable.

        Two mutually exclusive ways to declare location:

        - Shorthand, a single point: pass both `map_constant=` and `at=`.
        - Multi-point: pass `locations=` (a tuple of `BeatLocation`).

        Passing both forms, or only one half of the shorthand pair, fails
        loud -- an ambiguous or incomplete declaration is worse than none.

        **`at=` records where the beat triggers, and does NOT move the
        player** -- a beat still runs from wherever the PREVIOUS beat left
        off; declaring `at=`/`locations=` never teleports anyone. It must
        name a cell the offline traversable graph says is reachable
        (`verify_chapter_locations`, static, checked before the ROM runs).
        It is NOT, by itself, a claim about *inherited* position -- see
        `entry_at=` below for that.

        **`entry_at=` is the separate, opt-in claim that this beat starts
        from a specific cell.** `_check_beat_continuity` (`runner.py`)
        checks a beat's declared `entry_at` against where the PREVIOUS beat
        actually left the player, at run time, and is a no-op for any beat
        that doesn't set it. A beat whose `entry_at` disagrees with the
        inherited position fails loud, at the point of disagreement, naming
        both positions -- it no longer silently starts somewhere else and
        fails later as a misleading pathfinding "stuck" error near the
        target.

        `entry_at=` was split out from `at=`/`locations[0]` on 2026-09-05
        (PLAYTEST_AUTHORING_IMPROVEMENT_V2 follow-up) after the first ROM
        run since continuity checking landed (2026-08-28) falsified the
        premise it used to rest on. `_check_beat_continuity` used to read
        `beat.locations[0]` as the inherited-position claim, on the theory
        that the corpus's own authoring convention always lists the entry
        door/threshold first in a multi-point beat. An offline audit of
        every inherited CH01 beat replayed by CH05, against the recorded
        entry/exit positions from the last green run, found that premise
        false: 40 of 51 declared `locations[0]` values disagreed with the
        beat's recorded entry position (11 matched entry, 13 matched exit
        instead, 27 were neither -- a mid-beat cell), and multi-point beats
        scored *worse* than single-`at=` ones (1 match against 12
        mismatches), the opposite of what the old docstring claimed. The
        corpus-wide convention `at=`/`locations=` actually encode is "the
        tile the beat triggers on" -- the NPC talked to, the door stepped
        on -- which is neither reliably the beat's entry nor its exit.
        `entry_at=` exists so a beat can make the inherited-position claim
        explicitly, only where it's actually true, instead of it being
        inferred (wrongly, most of the time) from a declaration meant for
        something else.

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

        if group is not None and not group.strip():
            raise ValueError(
                f"beat {name!r}: group= must be a non-empty string, "
                f"got {group!r}")
        for row in rows:
            _validate_row_id(row, beat_name=name)
        resolved_archetype: str | tuple[tuple[str, str], ...] | None
        if archetype is None or isinstance(archetype, str):
            archetype_names = () if archetype is None else (archetype,)
            resolved_archetype = archetype
        else:
            if not archetype:
                raise ValueError(
                    f"beat {name!r}: archetype= mapping is empty -- pass None "
                    "for a beat that claims no archetype")
            unlisted = sorted(set(archetype) - set(rows))
            if unlisted:
                raise ValueError(
                    f"beat {name!r}: archetype= maps row(s) {unlisted} that "
                    "are not in this beat's rows=")
            archetype_names = tuple(archetype.values())
            resolved_archetype = tuple(
                (row, archetype[row]) for row in rows if row in archetype)
        for archetype_name in archetype_names:
            if archetype_name not in ARCHETYPE_NAMES:
                raise ValueError(
                    f"beat {name!r}: archetype={archetype_name!r} is not one of "
                    f"{sorted(ARCHETYPE_NAMES)} (chapter_manifest.archetypes."
                    "ARCHETYPE_NAMES)")
        if assertions is not None:
            stray = sorted({a.row_id for a in assertions} - set(rows))
            if stray:
                raise ValueError(
                    f"beat {name!r}: assertions= name row(s) {stray} that are "
                    "not in this beat's rows=")
        if entry_at is not None:
            if (not isinstance(entry_at, tuple) or len(entry_at) != 2
                    or not all(isinstance(v, int) for v in entry_at)):
                raise ValueError(
                    f"beat {name!r}: entry_at= must be a (x, y) tuple of "
                    f"ints, got {entry_at!r}")

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
                                    run=fn, locations=resolved_locations,
                                    entry_at=entry_at, group=group, rows=rows,
                                    archetype=resolved_archetype,
                                    assertions=assertions))
            return fn

        return decorate

    def claimed_rows(self) -> frozenset[str]:
        """Every row id claimed by a beat registered so far, across the
        whole `_beats` list (registration order not required -- callers
        that need order-sensitivity, none do today, can walk `_beats`
        directly).

        Exists so a caller like `generic.generic_beat`'s `skip_claimed=`
        can ask "has anything already claimed this row?" without reaching
        into `builder._beats` itself -- exactly the private-attribute
        access a public method exists to prevent (Task 7 brief)."""
        return frozenset(row for beat in self._beats for row in beat.rows)

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
                predecessor_chapter: Chapter | None = None
                predecessor_suite: Suite = "hand"
                if self.suite == "gen":
                    try:
                        predecessor_chapter = load_chapter(self.predecessor, suite="gen")
                        predecessor_suite = "gen"
                    except KeyError:
                        predecessor_chapter = None
                if predecessor_chapter is None:
                    try:
                        predecessor_chapter = load_chapter(self.predecessor, suite="hand")
                        predecessor_suite = "hand"
                    except KeyError as exc:
                        raise ValueError(
                            f"chapter {self.name!r} declares unknown predecessor "
                            f"{self.predecessor!r}") from exc
                logger.info(
                    "chapter %r (suite=%r): resolved predecessor %r from the %r suite",
                    self.name, self.suite, self.predecessor, predecessor_suite)
                prefixed = tuple(
                    _prefix_beat(predecessor_chapter.name, b)
                    for b in predecessor_chapter.beats)
                beats = prefixed + own_beats
        finally:
            _building_stack.pop()

        _validate_groups(beats, chapter_name=self.name)

        return Chapter(name=self.name, doc=self.doc, beats=beats,
                        predecessor=self.predecessor,
                        route_entry=self.route_entry)


def _validate_groups(beats: tuple[Beat, ...], *, chapter_name: str) -> None:
    """Enforce the two group invariants at `build()` time:

    - Contiguity: beats sharing an explicit `group` id must be adjacent in
      registration order -- the route solver treats a group as one
      indivisible stop, so a scattered group can't be expressed.
    - No singleton/explicit collision: a beat with no `group` forms a
      singleton group named after itself, and that name must not collide
      with an explicit `group` id used by some other beat in the same
      (already-composed, predecessor-included) chapter.
    """
    explicit_group_ids = {b.group for b in beats if b.group is not None}
    for beat in beats:
        if beat.group is None and beat.name in explicit_group_ids:
            raise ValueError(
                f"chapter {chapter_name!r}: beat {beat.name!r} has no "
                f"group=, so it forms a singleton group named {beat.name!r}, "
                f"but that name collides with an explicit group= used by "
                f"another beat in this chapter -- rename the beat or the "
                f"group")

    first_seen: dict[str, int] = {}
    last_seen: dict[str, int] = {}
    members: dict[str, list[str]] = {}
    for i, beat in enumerate(beats):
        if beat.group is None:
            continue
        first_seen.setdefault(beat.group, i)
        last_seen[beat.group] = i
        members.setdefault(beat.group, []).append(beat.name)

    for group_id, start in first_seen.items():
        end = last_seen[group_id]
        span = beats[start:end + 1]
        if any(b.group != group_id for b in span):
            intervening = [b.name for b in span if b.group != group_id]
            raise ValueError(
                f"chapter {chapter_name!r}: group {group_id!r} "
                f"(beats {members[group_id]}) is not contiguous -- "
                f"{intervening} register in between. A group's beats must "
                f"be registered adjacently because the route solver treats "
                f"the group as one indivisible stop.")


_SUITE_PACKAGES: dict[Suite, str] = {"hand": "chapters", "gen": "chapters_gen"}


def chapter_names() -> list[str]:
    """Every module under `rpg2gba.playtest.chapters`, sorted."""
    from . import chapters

    return sorted(m.name for m in pkgutil.iter_modules(chapters.__path__))


def gen_chapter_names() -> list[str]:
    """Every module under `rpg2gba.playtest.chapters_gen`, sorted -- the
    "gen" suite's counterpart to `chapter_names()` above. Generated modules
    land here one chapter at a time (C9 rulings), so this list is typically
    a strict subset of `chapter_names()`."""
    from . import chapters_gen

    return sorted(m.name for m in pkgutil.iter_modules(chapters_gen.__path__))


def load_chapter_module(name: str, *, suite: Suite = "hand") -> ModuleType:
    """Import and return `rpg2gba.playtest.chapters.<name>` (`suite="hand"`,
    the default) or `rpg2gba.playtest.chapters_gen.<name>` (`suite="gen"`).

    `load_chapter` (below) is what most callers want -- it hands back the
    built `Chapter`, which holds only the beats that were actually
    registered. But `Chapter` cannot answer "what was deliberately left
    unregistered, and why?": `DEFERRED_BEATS` is, by definition, the set of
    beats that never went through `@beat(...)`, so it exists only as a
    module-level attribute on the chapter module, never on `Chapter` itself.
    A caller that needs that half -- e.g. an adapter reconciling a
    `beat:Bn` disposition against what the chapter module actually declares
    -- has to reach the module object directly, which is what this function
    is for.

    Modules are named for their atlas chapter id, lowercased so the filename
    is a conventional Python module name (`CH01` -> `ch01.py`, 2026-09-01,
    CH05_DECISIONS E1). The lookup is case-insensitive so the atlas id can be
    passed through verbatim from `reference/chapters.json` without a caller
    having to know which case a filesystem wants.
    """
    package = _SUITE_PACKAGES[suite]
    target = f"{__package__}.{package}.{name.lower()}"
    try:
        return importlib.import_module(target)
    except ModuleNotFoundError as exc:
        # Only the chapter module itself being absent is "no such chapter".
        # A module that exists but fails one of ITS imports must surface, or a
        # broken gen module would fall back to the hand suite without a word.
        if exc.name != target:
            raise
        if suite == "hand":
            raise KeyError(
                f"no chapter {name!r}; known chapters: {chapter_names()}") from exc
        raise KeyError(
            f"no chapter {name!r} in suite {suite!r}; "
            f"known gen chapters: {gen_chapter_names()}") from exc


def load_chapter(name: str, *, suite: Suite = "hand") -> Chapter:
    """Import `rpg2gba.playtest.chapters(_gen).<name>` and return its
    `CHAPTER` (`suite="hand"` by default -- unchanged for every existing
    caller)."""
    module = load_chapter_module(name, suite=suite)
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
    which -- documented there -- checks only the separate, opt-in `entry_at=`
    field, not any `locations` entry -- `locations[0]` turned out not to be
    a reliable inherited-position claim; see `ChapterBuilder.beat`'s
    docstring for the 2026-09-05 measurement that found this.)

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
