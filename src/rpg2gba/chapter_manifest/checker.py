"""The rules that fail a chapter's manifest (Q1, Q6, Q8.2, Q11).

`check_chapter` joins the generated rows against the authored dispositions
and reports every way the two can disagree. Nothing here mutates either
side — CLAUDE.md §11 forbids editing generated output, and the disposition
file is edited only by a human (or `dispositions.write_dispositions`, for
tooling, never from this module).
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Literal, Protocol

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor
from rpg2gba.beat_floor.coverage import graded_gaps

from .archetypes import classify_manifest
from .derivation import DerivedEntry, derive_entry
from .generator_status import GeneratorStatus
from .schema import Disposition, ManifestRow, parse_blocked_argument

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Finding:
    """One thing wrong with one row (or, for orphans, one disposition)."""

    row_id: str
    rule: str
    message: str
    severity: Severity


# --- rule ids ----------------------------------------------------------
#
# One constant per rule so callers/tests can filter or assert on `rule`
# without restating the literal string.

RULE_UNDISPOSITIONED = "undispositioned"
RULE_ORPHAN_DISPOSITION = "orphan_disposition"
RULE_STALE_DISPOSITION = "stale_disposition"
RULE_UNAFFIRMED_DISPOSITION = "unaffirmed_disposition"
RULE_UNDISPOSITIONABLE_ROW_DECIDED = "undispositionable_row_decided"
RULE_ILLEGAL_COSMETIC = "illegal_cosmetic"
RULE_MISSING_CITATION = "missing_citation"
RULE_BLOCKED_NO_GRANT_SITE = "blocked_no_grant_site"
RULE_BLOCKED_ALREADY_GRANTED = "blocked_already_granted"
RULE_CAPABILITY_MODEL_UNENFORCED = "capability_model_unenforced"
RULE_BLOCKED_MISSED_ASSERTION = "blocked_missed_assertion"
RULE_APPROACH_MODEL_UNENFORCED = "approach_model_unenforced"
RULE_REACHABILITY_UNENFORCED = "reachability_unenforced"
RULE_ROUTE_ORDER = "route_order"
RULE_ROUTE_MODEL_UNENFORCED = "route_model_unenforced"
RULE_ROUTE_APPROACH = "route_approach"
RULE_ARCHETYPE_CONFORMANCE = "archetype_conformance"
RULE_ARCHETYPE_MODEL_UNENFORCED = "archetype_model_unenforced"
RULE_UNREGISTERED_BEAT = "unregistered_beat"
RULE_BEAT_MODEL_UNENFORCED = "beat_model_unenforced"
RULE_TRIGGER_OVERLAY_VACUOUS = "trigger_overlay_vacuous"
RULE_TRIGGER_OVERLAY_MODEL_UNENFORCED = "trigger_overlay_model_unenforced"
RULE_BOUNDARY_NOT_CROSSING = "boundary_not_crossing"
RULE_BOUNDARY_UNCLAIMED = "boundary_unclaimed"
RULE_BOUNDARY_MODEL_UNENFORCED = "boundary_model_unenforced"
RULE_DERIVED_HASH_INELIGIBLE = "derived_hash_ineligible"
RULE_DERIVED_VERDICT_MISMATCH = "derived_verdict_mismatch"
RULE_DERIVED_UNAFFIRMED = "derived_unaffirmed"
RULE_FLOOR_UNCOVERED = "floor_uncovered"
RULE_FLOOR_UNDECLARED = "floor_undeclared"
RULE_FLOOR_MISSING = "floor_missing"
RULE_FLOOR_MODEL_UNENFORCED = "floor_model_unenforced"
# 2026-10-04 operator ruling (2), PROJECT_TODO #124: a beat-generator
# refusal is tracked backlog -- a WARNING per row plus a chapter count,
# never an error.
RULE_GENERATOR_REFUSED = "generator_refused"


@dataclass(frozen=True)
class CapabilityGrant:
    """One map-event site that grants a capability token -- the unit
    `CapabilityModel` reports in, instead of a chapter id.

    Deliberately keyed to a manifest row, not a chapter (operator ruling,
    `REDERIVATION_PLAN.md` P8): a chapter id is a *plan* -- `reference/
    chapters.json` is 5-of-60 built and the rest is a proposed carve-up that
    will change, so "unblocked by CH57" rots silently when chapters are
    re-cut. `map199/ev001/p0` is a fact about the game data and survives any
    re-plan. It is also not the same fact as "CH57 owns map199" -- a chapter
    *owning* a map is not the same as the specific event on it having been
    implemented/verified as the grant, and event-level granularity is what
    makes the discharge condition mechanically checkable.

    `chapter_id` is the owning chapter of `map_id` in `reference/
    chapters.json` at derivation time, or None if no chapter claims that map
    yet -- carried through only for `granted_within`'s same-chapter-or-
    predecessor test and for readable messages; it is not the identity of
    the grant.
    """

    row_id: str
    map_id: int
    chapter_id: str | None


class CapabilityModel(Protocol):
    """The seam `blocked:<capability set>` validation plugs into (Q8.2, Q3).

    Not implemented here — deliberately. `check_chapter`'s `capabilities`
    argument accepts anything satisfying this Protocol. The concrete adapter
    (`capability_model.py`) is built over `rpg2gba.capability_sites`'
    corpus-wide scan for `code 121`/`code 122` writes that turn a named
    switch/variable-threshold ON -- see that module's docstring for why
    grants are keyed to map-event sites, not chapters.
    """

    def grant_sites(self, name: str) -> tuple[CapabilityGrant, ...] | None:
        """Sites that turn capability `name` on.

        Three-state, not boolean-or-list, because "nobody grants this" and
        "we cannot tell" must never collapse into the same answer:

          None      -- undetermined; the derivation cannot answer at all
                       (no switch/variable in the corpus even slugs to this
                       token, or every write it found was a computed/
                       relative operation it cannot resolve to a constant)
                       => `RULE_CAPABILITY_MODEL_UNENFORCED`, a warning.
          ()         -- the derivation looked and nothing anywhere grants
                       `name` => the row is unreachable, not blocked
                       (`RULE_BLOCKED_NO_GRANT_SITE`, an error).
          non-empty  -- the grant sites themselves.
        """
        ...

    def granted_within(self, name: str) -> tuple[CapabilityGrant, ...]:
        """The subset of `grant_sites(name)` (or `()` if that is `None`)
        lying in THIS chapter or one of its predecessors -- i.e. the player
        already holds `name` by the time this chapter runs, so a `blocked:`
        row naming it is a false claim (`RULE_BLOCKED_ALREADY_GRANTED`).

        Lives on the model, not in the checker, precisely so `checker.py`
        stays free of the chapter-chain import (`chapter_atlas.binding`)
        this needs to walk predecessors.
        """
        ...


class ApproachModel(Protocol):
    """The offline-reachability check behind `RULE_BLOCKED_MISSED_ASSERTION`
    (Q3 decision 3's checker half).

    Not implemented here — deliberately, same reasoning as `CapabilityModel`:
    `check_chapter`'s `approach` argument accepts anything satisfying this
    Protocol. `approach_model.GraphApproachModel` is the concrete adapter the
    CLI wires in, built over `traversal.reachability.adjacent_approach_cells`
    and `MapGraph.is_walkable`.
    """

    def has_walkable_approach(self, row: ManifestRow) -> bool | None:
        """Three-state, not boolean, because "no" and "can't tell" must never
        collapse into the same answer -- a `False` here SUPPRESSES
        `RULE_BLOCKED_MISSED_ASSERTION`, so treating "unanswerable" as False
        would silently swallow a real missed-assertion warning.

        True: `row`'s event has at least one orthogonally-adjacent tile that
        is walkable RIGHT NOW (no capability held) -- i.e. the player can
        already stand next to the blocked thing and press A, whatever the
        verdict says. Ground truth from the graph, not the author's own
        `assertable` self-report -- that is what lets this rule catch a row
        the author marked `assertable: false` (or left unjudged) by mistake.

        False: every adjacent tile is genuinely not walkable.

        None: this model cannot derive an answer for `row` at all -- e.g. a
        seam row (no event, so no cell to test), or a row on a map this
        model has no vetted traversal data for. Treated by `check_chapter`
        exactly like "no approach model was supplied"
        (`RULE_APPROACH_MODEL_UNENFORCED`), never as False.
        """
        ...


@dataclass(frozen=True)
class RoutePrecedence:
    """One `before` must come strictly ahead of `after`, and `reason` says why.

    Deliberately a local, minimal shape rather than importing
    `rpg2gba.routing.plan.PrecedenceEdge` -- this module must not import
    `rpg2gba.routing` (or `rpg2gba.playtest`) at module load time, the same
    seam discipline as `CapabilityModel`/`ApproachModel`. The CLI's concrete
    `RouteModel` adapter is the thing that knows about the real
    `RoutePlan`/`PrecedenceEdge` types and translates them into this shape.
    """

    before: str  # group id
    after: str  # group id
    reason: str


@dataclass(frozen=True)
class PlannedApproach:
    """One plan node's committed approach side, translated to the local
    shape `RULE_ROUTE_APPROACH` compares -- same reasoning as
    `RoutePrecedence`: this module must not import `rpg2gba.routing`, so it
    never sees the real `RouteNode`/`chosen_approach` JSON shape directly.

    Mirrors the plan artifact's per-node `chosen_approach` object
    (`{"side": ..., "resolver": ...}`) plus the node fields
    `RULE_ROUTE_APPROACH` needs to locate and report the mismatch: which
    group/beats the node covers, which map, and the cell the solver planned
    against.
    """

    group: str
    map_id: int
    cell: tuple[int, int]
    beats: tuple[str, ...]
    side: str
    resolver: str


class RouteModel(Protocol):
    """The seam `RULE_ROUTE_ORDER` plugs into: does the chapter's registered
    beat-group order match the order the offline route solver actually
    planned?

    Motivating incident: on CH04, group B2 was registered ahead of group B3
    in the chapter module, but the solver's plan walked B3 before B2. Nothing
    checked that the two agreed. The walk crossed Timothy's event-touch tile
    on the way to Larrie, fired the wrong trainer battle, and both the
    manifest checker and the boot-walk gate passed clean -- because neither
    one compared registration order against plan order at all. It read as a
    converter bug and ate three sessions before anyone thought to diff the
    two orders by hand. This rule makes that diff automatic.

    Not implemented here -- deliberately, same reasoning as
    `CapabilityModel`/`ApproachModel`: `check_chapter`'s `route` argument
    accepts anything satisfying this Protocol. The concrete adapter the CLI
    wires in loads a chapter's `RoutePlan` (`rpg2gba.routing.plan.load_plan`)
    for `planned_group_order`/`precedence_edges`, and its `Chapter.groups()`
    (`rpg2gba.playtest.chapter.load_chapter`) for `registered_group_order`.
    """

    def planned_group_order(self) -> tuple[str, ...]:
        """Group ids in the order the route solver planned to walk them --
        i.e. the `group` of each `kind == "group"` node in `RoutePlan.nodes`,
        in node order."""
        ...

    def registered_group_order(self) -> tuple[str, ...]:
        """Group ids in the order they were registered in the chapter module
        -- i.e. `BeatGroup.group_id` for each entry of `Chapter.groups()`, in
        registration order. Registration order IS playthrough order
        (`chapter.py`'s own docstring), so this is "the order the chapter
        will actually be walked when the ROM runs it"."""
        ...

    def precedence_edges(self) -> tuple[RoutePrecedence, ...]:
        """The solver's own `RoutePlan.precedence` edges, translated to the
        local `RoutePrecedence` shape. An edge with `before`/`after` group
        ids not present in `registered_group_order()` is ignored by the
        rule (a name mismatch there is already reported by the missing-group
        half of `RULE_ROUTE_ORDER`, once, not twice)."""
        ...

    def planned_approaches(self) -> tuple[PlannedApproach, ...]:
        """One entry per plan node that carries a non-null
        `chosen_approach` -- the approach side the route solver committed
        to for that node's group, plus enough to locate it (map, cell,
        which beats it covers). Empty for a plan that carries no
        `chosen_approach` data at all (an older artifact, or a chapter with
        no side-sensitive stops) -- `RULE_ROUTE_APPROACH` then has nothing
        to check and reports nothing, same as `RULE_ROUTE_ORDER` on an
        entirely-agreeing plan."""
        ...

    def declared_beat_cell(self, beat_id: str) -> tuple[int, int] | None:
        """The cell `beat_id` actually declares -- `Beat.locations[0]`'s
        `(x, y)`, the same point `runner.py`'s own continuity check treats
        as "where this beat expects to be standing" -- or None if `beat_id`
        is not a registered beat at all, or is registered but declares no
        location (`at=`/`locations=` are optional). `RULE_ROUTE_APPROACH`
        treats both None cases identically: it cannot compare a cell that
        was never declared, so it degrades to
        `RULE_ROUTE_MODEL_UNENFORCED` rather than reporting either a false
        pass or a false mismatch."""
        ...


class TriggerOverlayModel(Protocol):
    """The seam `RULE_TRIGGER_OVERLAY_VACUOUS` plugs into: did the trigger
    overlay a route was solved against actually see a `TRAINER_SIGHT` tile
    on every map this chapter has a dispositioned trainer row on?

    Motivating incident (PROJECT_TODO #75): CH05's first solve reported a
    clean 155-tile route with zero `CROSSING` lines -- read as "the route
    avoids every trainer's sight cone" when the true state was "the trigger
    overlay measured nothing at all" (the object event data it reads,
    `traversal.triggers.build_trigger_overlay`, did not exist yet). Once
    real object events landed, the identical walk order crossed five
    trainer sight cones and both the solver and a human reading its zero
    `CROSSING` output had passed it clean. Nothing distinguished "checked
    and found nothing to avoid" from "had nothing to check against"
    (CLAUDE.md §4.5).

    Not implemented here -- deliberately, same reasoning as `RouteModel`:
    `check_chapter`'s (and the standalone `check_trigger_overlay`'s)
    `trigger_overlay` argument accepts anything satisfying this Protocol.
    The CLI's concrete adapter wraps the `TriggerOverlay` objects the route
    solver itself builds (`routing.__main__._LazyOverlays`), keyed by map
    id, so this rule runs at the ROUTE step -- the point a vacuous overlay
    is actually detectable -- rather than only later when
    `chapter_manifest check` re-examines an already-written route plan.
    """

    def has_trainer_sight_tiles(self, map_id: int) -> bool:
        """True iff the overlay for `map_id` carries at least one tile with
        a `TriggerKind.TRAINER_SIGHT` ref -- i.e.
        `build_trigger_overlay` found at least one trainer object event on
        this map whose sight line reaches at least one tile.

        False means the overlay measured nothing on this map: either no
        trainer object event exists there at all (the CH05 case: the map
        hadn't been emitted with real object events yet), or one does but
        every sight line it casts is empty after occlusion/blockers. The
        rule below treats both identically -- neither can back a claim that
        a route "avoids" trainer sight on this map, because there was
        nothing on the map to avoid in the overlay's own eyes."""
        ...


class ArchetypeModel(Protocol):
    """The seam `RULE_ARCHETYPE_CONFORMANCE`'s beat-registry half plugs into.

    Classification itself (`archetypes.classify_manifest`) lives in this
    package and is imported directly -- it is a pure function of
    `ManifestRow`, no seam needed. But "is there a registered beat that
    actually claims this row, tagged with this archetype?" is a fact about
    the playtest chapter modules, and `checker.py` deliberately does not
    import `rpg2gba.playtest` or `rpg2gba.routing` at module load (same
    discipline as `CapabilityModel`/`ApproachModel`/`RouteModel`). The CLI's
    concrete adapter walks a chapter's registered beats and their declared
    archetype tags to answer this.
    """

    def claimed_archetype(self, row_id: str) -> str | None:
        """The archetype name a registered beat claims for `row_id`, or None
        if no registered beat claims it at all.

        A value that disagrees with `archetypes.classify_manifest`'s own
        verdict for the row (or is None where a claim was expected) is what
        `RULE_ARCHETYPE_CONFORMANCE` reports -- the row's disposition head
        can be correct while the beat that owns it is still tagged wrong or
        missing, and that gap is invisible without this model.
        """
        ...


class BeatModel(Protocol):
    """The seam `RULE_UNREGISTERED_BEAT` plugs into: does a `beat:Bn`
    disposition actually name a beat that is registered and running?

    Not implemented here -- deliberately, same reasoning as
    `CapabilityModel`/`ApproachModel`/`RouteModel`/`ArchetypeModel`:
    `checker.py` deliberately never imports `rpg2gba.playtest`, so "is this
    beat registered?" is a fact about the playtest chapter modules and
    arrives through a Protocol the CLI supplies. The concrete adapter walks
    a chapter module's `@chapter.beat(...)` registrations and its
    `DEFERRED_BEATS` tuple to answer both methods below.

    A registered beat id may be matched as a *prefix family* -- `beat:B4`
    satisfied by a template-registered `B4_battle` -- but that matching is
    the model's business, not this rule's; `is_registered` returns the
    already-resolved answer.
    """

    def is_registered(self, beat_id: str) -> bool:
        """True if some registered beat (by exact id or prefix family)
        claims `beat_id`."""
        ...

    def deferral_reason(self, beat_id: str) -> str | None:
        """The recorded reason `beat_id` is unregistered because it was
        deliberately written and then deferred (found in a chapter module's
        `DEFERRED_BEATS`), or None if `beat_id` is not deferred at all --
        i.e. no playtest module knows about it under any name, registered
        or deferred. `RULE_UNREGISTERED_BEAT` uses this to distinguish "this
        beat is known but intentionally not running" from "this name is a
        typo or a stale rename"."""
        ...

    def claiming_beats(self, row_id: str) -> tuple[str, ...]:
        """Names of the registered beats whose `rows=` list `row_id`, sorted;
        `()` if none. `derivation.derive_entry` uses this: `beat` outranks
        `cosmetic`/`blocked:`, so a row a beat walks derives `beat:<family
        head>` rather than falling through to a weaker verdict, and the
        checker's `RULE_DERIVED_VERDICT_MISMATCH` catches a sidecar that
        disagrees with that."""
        ...


class BoundaryModel(Protocol):
    """The seam `RULE_BOUNDARY_NOT_CROSSING`/`RULE_BOUNDARY_UNCLAIMED` plug
    into: is a `boundary` disposition telling the truth, on both of its
    claims -- that the row really is on this chapter's forward boundary, and
    that the chapter which arrives actually claims it?

    Not implemented here -- deliberately, same reasoning as
    `CapabilityModel`/`ApproachModel`/`RouteModel`/`ArchetypeModel`/
    `BeatModel`: `checker.py` must not import `rpg2gba.slice_growth`,
    `rpg2gba.seam_growth`, `rpg2gba.chapter_atlas`, or `rpg2gba.playtest` at
    module load time. The CLI's concrete adapter (`boundary_model.py`) is
    built over `slice_growth.gated_chapter_slices` /
    `find_slice_growth_events` and `seam_growth.find_seam_growth_edges` for
    the "is this really a crossing" half, and over
    `chapter_atlas.binding.ChapterBinding.successor` plus
    `playtest.chapter.load_chapter`'s `Beat.rows` for the "does the arrival
    claim it" half.
    """

    def is_forward_crossing(self, row_id: str) -> bool:
        """True iff `row_id` names an event or seam that
        `slice_growth`/`seam_growth` actually detected as one of this
        chapter's own maps carrying a transfer or connection toward a map
        outside this chapter's authoring-time slice.

        A `boundary` disposition on a row that fails this is a false claim:
        the row doesn't lead anywhere outside the chapter, and the
        `boundary` verdict exists only for rows that do (Q72/Q73).
        """
        ...

    def successor_chapter_id(self) -> str | None:
        """The chapter id of the chapter that arrives after this one
        (`ChapterBinding.successor`'s result for this chapter), or None if
        this chapter is terminal -- nothing in the chain arrives after it,
        so nothing could ever claim a `boundary` row here."""
        ...

    def successor_has_module(self) -> bool:
        """True iff the successor chapter (if any) has a playtest module at
        all. False is the ordinary, expected state of a `boundary` row
        authored before its successor chapter has been started -- the
        outgoing chapter's own manifest and dispositions are finished and
        gated well before the next chapter's beats exist. The rule degrades
        to `RULE_BOUNDARY_MODEL_UNENFORCED` in that case, the same
        unenforced-not-silent idiom `RULE_UNREGISTERED_BEAT` uses for a
        chapter with no playtest module of its own yet."""
        ...

    def successor_claims(self, row_id: str) -> bool:
        """True iff some beat registered in the successor chapter's
        (fully-composed) `Chapter.beats` lists `row_id` in its own `rows`.

        Deliberately checked against the successor's registered beats, not
        the successor's own manifest/dispositions file: the boundary row's
        map is not necessarily one of the successor chapter's *own* maps in
        `chapters.json` (CH04's boundary event lives on Map035, which is
        CH04's map, not one of CH05's [36, 37]) -- generating a manifest row
        for it under CH05 at all would be an orphan there. `Beat.rows` is
        already how every other archetype/beat check in this package makes
        a claim ("this beat covers this row") independent of which
        chapter's own map roster the row's map happens to sit in
        (`playtest.archetypes.ChapterArchetypeModel` does the identical
        `beat.rows` walk for the same reason).
        """
        ...


class FloorCoverageModel(Protocol):
    """The seam `RULE_FLOOR_UNCOVERED`/`RULE_FLOOR_UNDECLARED`/
    `RULE_FLOOR_MISSING` plug into (REDERIVATION_PLAN.md §16.3 C5, R11): does
    every row a registered beat claims carry declared assertions that cover
    the generic per-command floor `beat_floor` derives from source?

    Not implemented here -- deliberately, same reasoning as every other
    seam in this module (`CapabilityModel`/`ApproachModel`/.../
    `BoundaryModel`): `checker.py` must not import `rpg2gba.playtest` at
    module load time, so "which beats claim this row, and what do they
    declare" is a fact about the playtest chapter modules that arrives
    through this Protocol. `rpg2gba.beat_floor.assertion`/`.coverage` ARE
    imported directly, unlike `rpg2gba.playtest` -- they are leaves (pure
    record types and the `covers`/`uncovered` relation, no chapter-module
    dependency), the same way `archetypes.classify_manifest` is imported
    directly rather than routed through a Protocol.

    The concrete adapter (`floor_model.py`) is built over a chapter's
    (already predecessor-composed) `playtest.chapter.load_chapter(...).beats`
    for `claims`/`declared`, and `beat_floor.lookup.floor_for_row` for
    `floor`.
    """

    def floor(self, row_id: str) -> RowFloor:
        """The generic floor for `row_id`, computed from RMXP source. Raises
        `KeyError` if `row_id`'s map yields no floor for it at all (a
        claimed row the floor cannot see) -- `check_chapter` treats that as
        `RULE_FLOOR_MISSING`, an error, not a crash: the claim exists, the
        floor doesn't, and that disagreement is exactly the kind of thing
        this rule exists to surface, not raise through the CLI."""
        ...

    def declared(self, row_id: str) -> frozenset[FloorAssertion] | None:
        """The union of `assertions` over every registered beat that claims
        `row_id` (`claims(row_id)` is True) AND declares (`Beat.assertions
        is not None`).

        `None` means at least one beat claims `row_id` but NONE of the
        claiming beats declares -- an undeclared, hand-written beat
        (`RULE_FLOOR_UNDECLARED`). This is deliberately not the same as an
        empty `frozenset()`, which would mean every claiming beat declared
        and none of them checks anything at all -- that is a real (and
        total) `RULE_FLOOR_UNCOVERED` failure, not an undeclared beat.

        Only meaningful when `claims(row_id)` is True; the rule never calls
        this otherwise."""
        ...

    def claims(self, row_id: str) -> bool:
        """True iff some registered beat (predecessor-inherited beats
        included, same as `BeatModel.claiming_beats`/`ArchetypeModel`'s own
        `chapter.beats` walk) lists `row_id` in its `rows`. The ⊇ rule is
        not applied to a row nothing claims -- R11 has nothing to say about
        a row no beat has reached yet."""
        ...

    def is_generated(self) -> bool:
        """True iff this chapter's playtest module is a C6-generated module
        (its docstring/header begins `GENERATED -- do not edit`). None exist
        yet (C6 is still TODO in the plan); every chapter today answers
        False, so `RULE_FLOOR_UNDECLARED` reports rather than fails on a
        hand-written chapter until C9 replaces the hand suites (C5 shape
        (e))."""
        ...

    def exempt(self, row_id: str) -> bool:
        """True iff the C9 grader does not hold `row_id` to the floor: a
        `WALK_CHECKED` random arm (ruling 19) or a row claimed only by a
        boundary warp, graded against the successor's crossing (ruling 9).
        The floor rules skip such rows entirely."""
        ...


def check_chapter(
    rows: list[ManifestRow],
    dispositions: dict[str, Disposition],
    *,
    capabilities: CapabilityModel | None = None,
    approach: ApproachModel | None = None,
    route: RouteModel | None = None,
    trigger_overlay: TriggerOverlayModel | None = None,
    archetype_model: ArchetypeModel | None = None,
    beat_model: BeatModel | None = None,
    boundary_model: BoundaryModel | None = None,
    floor_coverage: FloorCoverageModel | None = None,
    derived: dict[str, DerivedEntry] | None = None,
    generator_status: GeneratorStatus | None = None,
    live_chapter: bool = False,
) -> list[Finding]:
    """Check one chapter's generated rows against its authored dispositions.

    `rows` is the generated manifest (already loaded by the caller — see
    the module docstring on why this module does not read the manifest
    file itself). `dispositions` is `row_id -> Disposition`, as returned by
    `dispositions.load_dispositions`.

    `trigger_overlay`, if supplied, backs `RULE_TRIGGER_OVERLAY_VACUOUS` (see
    `check_trigger_overlay`, which this delegates to): every map with a
    dispositioned trainer row must show at least one `TRAINER_SIGHT` tile in
    the overlay, or a zero-`CROSSING` route across it is unenforced/unproven.

    `beat_model`, if supplied, backs `RULE_UNREGISTERED_BEAT`: every `beat:`
    disposition must name a beat that is actually registered, not deferred
    or nonexistent (see `BeatModel`'s docstring and `_check_unregistered_beat`
    for the CH04 evidence this exists to catch).

    `boundary_model`, if supplied, backs `RULE_BOUNDARY_NOT_CROSSING`/
    `RULE_BOUNDARY_UNCLAIMED`: every `boundary` disposition must both name a
    row that actually crosses out of this chapter's authoring-time slice,
    and be claimed by a beat registered in the chapter that arrives next
    (see `BoundaryModel`'s docstring and `_check_boundary`).

    `floor_coverage`, if supplied, backs `RULE_FLOOR_UNCOVERED`/
    `RULE_FLOOR_UNDECLARED`/`RULE_FLOOR_MISSING`: every row a registered beat
    claims must have a generic floor (`RULE_FLOOR_MISSING` otherwise), that
    floor must be declared by at least one claiming beat unless refused
    (`RULE_FLOOR_UNDECLARED` otherwise), and the union of what claiming beats
    declare must cover the floor (`RULE_FLOOR_UNCOVERED` otherwise). See
    `FloorCoverageModel`'s docstring and `_check_floor_coverage`. Applied to
    this chapter's own `rows` only -- unlike `capabilities`/`approach`, this
    rule has no per-row author-facing disposition to key off, so it walks
    the generated manifest directly.

    `derived`, if supplied, is the machine-derived sidecar (`row_id ->
    DerivedEntry`, `dispositions.load_derived`, format v2). For a row the
    hand dispositions file omits, this checker never trusts a sidecar
    entry's mere presence: it recomputes `derivation.derive_entry(row,
    beat_model=..., boundary_model=...)` itself and compares. A stale hash,
    or a recomputed verdict that disagrees with the sidecar (including
    disagreeing about whether it's a `proposed` `blocked:` candidate),
    reports `RULE_UNDISPOSITIONED`/`RULE_DERIVED_VERDICT_MISMATCH` rather
    than trusting the file. A CLERICAL entry that matches (`cosmetic`,
    `beat:`, `boundary`) dispositions the row -- every per-row verdict rule
    a hand disposition goes through also runs against it, except the
    affirmation rules (`RULE_UNAFFIRMED_DISPOSITION`/`RULE_STALE_
    DISPOSITION`), which apply only to hand dispositions. A `blocked:`
    entry is only ever PROPOSED (`DerivedEntry.proposed`) -- a matching
    proposal reports `RULE_DERIVED_UNAFFIRMED` with paste-ready JSON and
    the row is left undispositioned; a human must copy it into the
    dispositions file with an `affirmed_hash` before it counts.
    `_check_derived_hash` additionally tallies the sidecar's contents,
    per verdict and including proposals, as a chapter-level warning
    (`RULE_DERIVED_HASH_INELIGIBLE`). Unlike `capabilities`/`approach`/
    `route`/etc., there is no "unenforced" degradation for a missing
    sidecar: `None` (or an empty dict) just means nothing was machine-
    derived yet, which is the ordinary state for a brand-new pipeline with
    no sidecar at all, not a gap in coverage.

    `live_chapter` governs `RULE_ARCHETYPE_CONFORMANCE`'s (and, identically,
    `RULE_UNREGISTERED_BEAT`'s, and `RULE_BOUNDARY_NOT_CROSSING`'s/
    `RULE_BOUNDARY_UNCLAIMED`'s) severity: True for the chapter currently
    being authored (ERROR), False for a chapter already through its §9
    boot-walk gate (WARNING). This module does not read
    `reference/chapters.json` itself -- same file-I/O discipline as
    `capabilities`/`approach`/`route` -- so the caller derives it (the CLI
    reads a chapter's `status` field there: `"built"` means gated, anything
    else means live) and passes the bool through. Defaults to False
    (gated/warning) rather than True, so a caller that forgets to pass it
    does not retroactively turn every already-gated chapter's manifest red.
    """
    findings: list[Finding] = []
    rows_by_id = {row.row_id: row for row in rows}

    # Computed here, ahead of the per-row loop below, rather than at its
    # original call site further down: RULE_BLOCKED_MISSED_ASSERTION's
    # cleared-state exemption (`_cleared_state_page`) needs to ask what a
    # SIBLING page's effective verdict is while still inside this same
    # row's own verdict check, and `_effective_dispositions` has no
    # dependency on anything the loop accumulates -- only on `rows`,
    # `dispositions`, `derived`, `beat_model`, `boundary_model`, all already
    # in scope. One computation, used by both the per-row rules and the
    # chapter-scale rules below.
    effective = _effective_dispositions(
        rows, dispositions, derived, beat_model=beat_model, boundary_model=boundary_model,
        generator_status=generator_status)

    for row in rows:
        disp = dispositions.get(row.row_id)
        if disp is not None:
            # Hand wins outright -- a sidecar entry on this row_id, if any,
            # is not even consulted.
            if disp.affirmed_hash is None:
                findings.append(Finding(
                    row_id=row.row_id,
                    rule=RULE_UNAFFIRMED_DISPOSITION,
                    message="disposition has never been affirmed against a content_hash",
                    severity="error",
                ))
            elif disp.affirmed_hash != row.content_hash:
                findings.append(Finding(
                    row_id=row.row_id,
                    rule=RULE_STALE_DISPOSITION,
                    message=(
                        f"affirmed_hash {disp.affirmed_hash!r} does not match current "
                        f"content_hash {row.content_hash!r}; row content changed since "
                        "this decision was made and it must be re-affirmed"
                    ),
                    severity="error",
                ))
            findings.extend(_check_row_verdict_rules(
                row, disp, capabilities=capabilities, approach=approach,
                rows=rows, effective=effective))
            continue

        # No hand disposition. The derived default (REDERIVATION_PLAN.md
        # §14.6 ruling 1, narrowed by the 2026-09-14 four-verdict ruling): a
        # row the dispositions file omits may still be dispositioned by a
        # CLERICAL sidecar entry (`cosmetic`, `beat:`, `boundary`) -- but
        # never a `blocked:` proposal, and never on the sidecar's word
        # alone. This checker recomputes `derive_entry` itself and compares.
        entry = (derived or {}).get(row.row_id)
        if entry is None:
            findings.append(Finding(
                row_id=row.row_id,
                rule=RULE_UNDISPOSITIONED,
                message="row has no disposition entry",
                severity="error",
            ))
            continue

        if entry.derived_hash != row.content_hash:
            findings.append(Finding(
                row_id=row.row_id,
                rule=RULE_UNDISPOSITIONED,
                message=(
                    f"row has no disposition entry, and its derived_hash "
                    f"{entry.derived_hash!r} does not match content_hash "
                    f"{row.content_hash!r} -- regenerate the sidecar"
                ),
                severity="error",
            ))
            continue

        recomputed = derive_entry(row, beat_model=beat_model, boundary_model=boundary_model,
                                  generator_status=generator_status,
                                  hand_dispositions=dispositions)
        if (recomputed is None
                or recomputed.disposition != entry.disposition
                or recomputed.proposed != entry.proposed):
            recomputed_desc = (
                repr(recomputed.disposition) if recomputed is not None else "nothing"
            )
            findings.append(Finding(
                row_id=row.row_id,
                rule=RULE_DERIVED_VERDICT_MISMATCH,
                message=(
                    f"sidecar says {entry.disposition!r}"
                    f"{' (proposed)' if entry.proposed else ''}, but this "
                    f"checker's own recheck derives {recomputed_desc} -- "
                    "regenerate the sidecar"
                ),
                severity="error",
            ))
            continue

        if entry.proposed:
            snippet = json.dumps({
                "disposition": entry.disposition,
                "affirmed_hash": row.content_hash,
            })
            findings.append(Finding(
                row_id=row.row_id,
                rule=RULE_DERIVED_UNAFFIRMED,
                message=(
                    f"sidecar proposes {entry.disposition!r} for this row, but "
                    "a blocked: proposal is never accepted without a human "
                    "affirming it -- if correct, copy this into the "
                    f"dispositions file: \"{row.row_id}\": {snippet}"
                ),
                severity="error",
            ))
            continue

        # CLERICAL and matching -- the row is dispositioned. Every per-row
        # verdict rule a hand disposition goes through also runs against it,
        # except the affirmation rules above (a derived entry has no
        # affirmed_hash to check; its derived_hash already passed).
        findings.extend(_check_row_verdict_rules(
            row, entry.to_disposition(row.row_id),
            capabilities=capabilities, approach=approach,
            rows=rows, effective=effective, generator_cited=True))

    for row_id, disp in dispositions.items():
        if row_id not in rows_by_id:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_ORPHAN_DISPOSITION,
                message=(
                    f"disposition {disp.spec!r} matches no row in the generated "
                    "manifest; content was likely deleted or renamed"
                ),
                severity="error",
            ))

    unconsulted_maps = sorted({row.map_id for row in rows if not row.reachability_consulted})
    for map_id in unconsulted_maps:
        findings.append(Finding(
            row_id=f"map{map_id:03d}",
            rule=RULE_REACHABILITY_UNENFORCED,
            message=(
                f"map{map_id:03d}: the offline reachability source was not "
                "consulted for this map, so terrain-gated capabilities (surf, "
                "waterfall) cannot appear in requires[] for any row here, and "
                "_HEAD_REQUIRES structurally cannot express them either -- "
                "blocked: verdicts on this map's rows have not been checked "
                "against the terrain-gate half of the capability model"
            ),
            severity="warning",
        ))

    # RULE_ROUTE_ORDER: registered beat-group order must match the offline
    # route solver's planned order -- see `RouteModel`'s docstring for the
    # CH04 incident this exists to catch. Chapter-scale, like
    # RULE_REACHABILITY_UNENFORCED above, but there is no natural map/row
    # to key it to (it's about the whole walk, not one map's data), so it
    # uses the fixed row_id "chapter" -- same non-row convention as that
    # rule's synthetic map-scoped id, just with nothing narrower available.
    if route is None:
        findings.append(Finding(
            row_id="chapter",
            rule=RULE_ROUTE_MODEL_UNENFORCED,
            message=(
                "could not check registered beat-group order (or planned "
                "approach sides) against the route plan because no route "
                "model was supplied (this rule is unenforced without one)"
            ),
            severity="warning",
        ))
    else:
        findings.extend(_check_route_order(route))
        findings.extend(_check_route_approach(route))

    # Chapter-scale rules read the EFFECTIVE verdict: hand dispositions plus
    # every row the hand file omits that this checker independently
    # recomputes as a matching, ACCEPTED clerical derived entry -- never a
    # `blocked:` proposal, which is not yet a disposition
    # (`RULE_DERIVED_UNAFFIRMED`). An archetype page (or boundary/beat row)
    # left to a clerical default is seen as that verdict, not as "no
    # disposition". (`effective` itself was computed above, ahead of the
    # per-row loop -- see the comment there.)
    findings.extend(
        check_trigger_overlay(rows, effective, trigger_overlay=trigger_overlay)
    )

    findings.extend(
        _check_archetype_conformance(
            rows, effective, archetype_model=archetype_model, live_chapter=live_chapter
        )
    )

    findings.extend(
        _check_unregistered_beat(
            effective, beat_model=beat_model, live_chapter=live_chapter
        )
    )

    findings.extend(
        _check_boundary(
            effective, boundary_model=boundary_model, live_chapter=live_chapter
        )
    )

    findings.extend(_check_derived_hash(rows_by_id, derived))

    findings.extend(_check_generator_refused(rows, effective))

    findings.extend(_check_floor_coverage(rows, floor_coverage=floor_coverage))

    findings.sort(key=lambda f: (f.row_id, f.rule))
    return findings


def _cleared_state_page(
    row: ManifestRow,
    rows: list[ManifestRow],
    effective: dict[str, Disposition],
) -> bool:
    """True iff `row` is a "cleared-state" page of an obstacle event --
    gated on its own event's self-switch -- that can only ever exist after
    ANOTHER page of the same event has already run and set that switch, so
    RULE_BLOCKED_MISSED_ASSERTION's "the player can walk up and be refused"
    claim is structurally impossible for it: nobody reaches this page
    empty-handed, because nobody reaches it at all until the prerequisite
    page's own `blocked:` capability has already been spent (Moki Town rock
    map032/ev014 -- p0 is the rock, smashing it writes self-switch A and
    erases the event; p1 is the smashed state, condition `self_switch_ch:
    "A"`; a negative beat on p1 is unauthorable because no route to it
    skips p0).

    The approach model (`ApproachModel.has_walkable_approach`) only tests
    the event's cell in isolation, so it cannot see this page-sequencing
    fact -- this is a second, narrower source of truth layered on top of
    it, not a relaxation of it.

    Deliberately reads only generated row facts (`condition`, `effects`)
    and `effective` dispositions, never `disp.assertable` or a note: this
    exemption is a structural claim about reachability, not the author's
    self-report, exactly like the rule it narrows.
    """
    if row.kind != "page" or row.condition is None or row.condition.self_switch_ch is None:
        return False
    writers = [
        sibling for sibling in rows
        if sibling.kind == "page"
        and sibling.map_id == row.map_id
        and sibling.event_id == row.event_id
        and sibling.row_id != row.row_id
        and "self_switch_write" in sibling.effects
    ]
    if not writers:
        # Nothing on this event writes a self-switch -- something else must
        # gate the condition (another event's write, or it's simply
        # unauthored), and this exemption has no evidence for that. Fall
        # through to the ordinary warning.
        return False
    return all(
        effective.get(sibling.row_id) is not None
        and effective[sibling.row_id].verdict == "blocked"
        for sibling in writers
    )


def _check_row_verdict_rules(
    row: ManifestRow,
    disp: Disposition,
    *,
    capabilities: CapabilityModel | None,
    approach: ApproachModel | None,
    rows: list[ManifestRow],
    effective: dict[str, Disposition],
    generator_cited: bool = False,
) -> list[Finding]:
    """Every per-row verdict rule a disposition must satisfy, whether it is
    hand-authored or an accepted CLERICAL derived entry
    (`entry.to_disposition(row_id)`) -- everything `check_chapter`'s row
    loop used to inline, EXCEPT the two affirmation rules
    (`RULE_UNAFFIRMED_DISPOSITION`/`RULE_STALE_DISPOSITION`), which apply
    only to a hand disposition's `affirmed_hash`: a derived entry has no
    such field (its `derived_hash` already passed a stricter, hash-equality
    check before this function is ever called for it), so those two rules
    would have nothing to check and are the caller's job, not this one's.

    `rows` (the full chapter roster) and `effective` (hand-plus-accepted-
    derived dispositions, keyed by row_id -- computed once by the caller,
    see `check_chapter`) back `RULE_BLOCKED_MISSED_ASSERTION`'s
    cleared-state exemption (`_cleared_state_page`) below.
    """
    findings: list[Finding] = []
    row_id = row.row_id

    # `generator_cited`: an accepted derived entry. On a row owing a
    # classification or citation, derivation admits ONLY the generator's
    # verdict (`derivation._generator_cited_entry`), and that verdict is the
    # citation (operator ruling 2026-10-04, #124) -- so the two rules below,
    # which ask a HUMAN for one, do not apply to it.
    if not row.is_dispositionable and not generator_cited:
        findings.append(Finding(
            row_id=row_id,
            rule=RULE_UNDISPOSITIONABLE_ROW_DECIDED,
            message=(
                "row carries an unrecognized script head or command code "
                f"(unrecognized_heads={list(row.unrecognized_heads)}, "
                f"other_codes={list(row.other_codes)}) and must be classified "
                "by a human before it can be dispositioned"
            ),
            severity="error",
        ))
        # Still worth checking the other rules on this row's disposition; an
        # unrecognized row that is ALSO stale, uncited, etc. should surface
        # every problem, not just this one.

    if disp.verdict == "cosmetic" and not row.may_be_cosmetic:
        # Checked first, and deliberately: `None` is falsy, so without this
        # arm a never-staged row (`unhandled is None`) would fall through
        # into the state-writing-tags `else` below and report a misleading
        # "state-writing tags" message even when the row carries none -- the
        # real problem is that the transpile queue was never consulted for
        # this row at all.
        if row.unhandled is None:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_ILLEGAL_COSMETIC,
                message=(
                    "disposed cosmetic but this row's map was never "
                    "transpiled (no entry under the transpiler's "
                    "scripts/ output) -- the unhandled-queue veto could "
                    "not be evaluated, so 'cosmetic' cannot be "
                    "justified; stage the map and regenerate the "
                    "manifest"
                ),
                severity="error",
            ))
        elif row.unhandled:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_ILLEGAL_COSMETIC,
                message=(
                    f"disposed cosmetic but row has {row.unhandled} unhandled "
                    "transpile queue entr(y/ies) - this is a dead conversion "
                    "with no beat written at all, not decoration"
                ),
                severity="error",
            ))
        elif row.is_player_observable:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_ILLEGAL_COSMETIC,
                message=(
                    f"disposed cosmetic but this {row.trigger} page shows the "
                    f"player something (effects {list(row.effects)}) -- "
                    "cosmetic means decoration nobody triggers (PROJECT_TODO "
                    "#43(b)); write the beat, or disposition it unreachable "
                    "if the page can't be reached"
                ),
                severity="error",
            ))
        else:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_ILLEGAL_COSMETIC,
                message=(
                    "disposed cosmetic but row carries state-writing effect "
                    f"tags {list(row.blocking_tags())}"
                ),
                severity="error",
            ))

    if row.needs_citation and not disp.source and not generator_cited:
        findings.append(Finding(
            row_id=row_id,
            rule=RULE_MISSING_CITATION,
            message=(
                "row has an unrecognized script head or an unclassified "
                "script-typed conditional (code-111 params[0]==12 not "
                "matched by any idiom family in conditions.py) and needs "
                "a source citation, but the disposition has none"
            ),
            severity="error",
        ))

    if disp.verdict == "blocked":
        capability_spec = disp.argument or ""
        if capability_spec.startswith("tooling:"):
            # blocked:tooling:<primitive> is a harness debt, not a
            # chapter-granted capability -- CapabilityModel has nothing to
            # say about it (Q10).
            pass
        elif capabilities is None:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_CAPABILITY_MODEL_UNENFORCED,
                message=(
                    f"blocked:{capability_spec} could not be checked against a "
                    "granting chapter because no capability model was supplied "
                    "(this rule is unenforced without one)"
                ),
                severity="warning",
            ))
        else:
            # `blocked:a|b+c` is a DISJUNCTION of minimal capability sets
            # (schema.py): any ONE alternative set opening the row is
            # enough, so the fold below is across alternatives, not a
            # per-token loop -- the old grammar's `|` meant AND, and a
            # per-token loop was the right fold for that. Under the new
            # grammar a disjunction is only impossible when EVERY
            # alternative is (one impossible alternative next to a
            # viable one is exactly what a correct `blocked` still
            # claims, not an error), and it is only "already granted" --
            # i.e. secretly reachable now -- when at least one
            # alternative's every member is already held.
            alternatives = parse_blocked_argument(capability_spec)

            satisfied: list[tuple[frozenset[str], tuple[CapabilityGrant, ...]]] = []
            impossible: list[tuple[frozenset[str], tuple[str, ...]]] = []
            undetermined: list[tuple[frozenset[str], tuple[str, ...]]] = []

            for alt in alternatives:
                sites_by_cap = {cap: capabilities.grant_sites(cap) for cap in alt}
                missing = tuple(sorted(
                    cap for cap, sites in sites_by_cap.items() if sites == ()
                ))
                if missing:
                    impossible.append((alt, missing))
                    continue
                unresolved = tuple(sorted(
                    cap for cap, sites in sites_by_cap.items() if sites is None
                ))
                if unresolved:
                    undetermined.append((alt, unresolved))
                    continue
                within_by_cap = {cap: capabilities.granted_within(cap) for cap in alt}
                if all(within_by_cap.values()):
                    grants = tuple(g for grants in within_by_cap.values() for g in grants)
                    satisfied.append((alt, grants))

            if satisfied:
                alt, grants = satisfied[0]
                site_ids = ", ".join(sorted({g.row_id for g in grants}))
                findings.append(Finding(
                    row_id=row_id,
                    rule=RULE_BLOCKED_ALREADY_GRANTED,
                    message=(
                        f"blocked:{capability_spec} names alternative "
                        f"{'+'.join(sorted(alt))!r}, but every capability in "
                        f"it is already granted in this chapter or a "
                        f"predecessor (site(s): {site_ids}) -- the player "
                        "already holds it, so this row is reachable and "
                        "'blocked' is a false claim"
                    ),
                    severity="error",
                ))
            elif impossible and len(impossible) == len(alternatives):
                reasons = "; ".join(
                    f"{'+'.join(sorted(alt))!r} (no grant site anywhere for "
                    f"{', '.join(missing)})"
                    for alt, missing in impossible
                )
                findings.append(Finding(
                    row_id=row_id,
                    rule=RULE_BLOCKED_NO_GRANT_SITE,
                    message=(
                        f"blocked:{capability_spec} -- every alternative is "
                        f"impossible ({reasons}); this row is unreachable, "
                        "not blocked"
                    ),
                    severity="error",
                ))
            elif undetermined:
                names = ", ".join(sorted({
                    cap for _, caps in undetermined for cap in caps
                }))
                findings.append(Finding(
                    row_id=row_id,
                    rule=RULE_CAPABILITY_MODEL_UNENFORCED,
                    message=(
                        f"blocked:{capability_spec} could not be fully "
                        f"checked -- the derivation could not determine "
                        f"where (or whether) anything grants {names} -- no "
                        "switch/variable in the corpus resolves to this "
                        "token, or every write to the candidate was a "
                        "computed/relative operation rather than a "
                        "constant assignment (this rule is unenforced for "
                        "this argument)"
                    ),
                    severity="warning",
                ))
            # else: no alternative is satisfied, not every alternative is
            # impossible, and none is undetermined -- at least one
            # alternative is a viable-but-not-yet-granted route, which is
            # exactly a correct `blocked` claim. No finding.

        if approach is None:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_APPROACH_MODEL_UNENFORCED,
                message=(
                    "could not check for a missed negative-beat opportunity "
                    "because no approach model was supplied (this rule is "
                    "unenforced without one)"
                ),
                severity="warning",
            ))
        else:
            approach_answer = approach.has_walkable_approach(row)
            if approach_answer is None:
                findings.append(Finding(
                    row_id=row_id,
                    rule=RULE_APPROACH_MODEL_UNENFORCED,
                    message=(
                        "the approach model could not determine a walkable-"
                        "approach answer for this row (no event cell to test, "
                        "or this row's map has no vetted traversal data) -- "
                        "this rule is unenforced for this row, not negative"
                    ),
                    severity="warning",
                ))
            elif (approach_answer and disp.negative_beat is None
                    and not _cleared_state_page(row, rows, effective)):
                findings.append(Finding(
                    row_id=row_id,
                    rule=RULE_BLOCKED_MISSED_ASSERTION,
                    message=(
                        "row is blocked but an adjacent tile is reachable from the "
                        "chapter's start cell with nothing held, and no "
                        "negative beat recorded -- the player can already walk up "
                        "and be refused; this is a missed authoring opportunity, "
                        "not an error"
                    ),
                    severity="warning",
                ))

    return findings


def _effective_dispositions(
    rows: list[ManifestRow],
    dispositions: dict[str, Disposition],
    derived: dict[str, DerivedEntry] | None,
    *,
    beat_model: BeatModel | None,
    boundary_model: BoundaryModel | None,
    generator_status: GeneratorStatus | None = None,
) -> dict[str, Disposition]:
    """Hand dispositions, plus a `Disposition` for every row the hand file
    omits that this checker independently recomputes as a matching,
    ACCEPTED clerical derived entry -- the same acceptance test
    `check_chapter`'s row loop applies (never a `blocked:` proposal, which
    is not yet a disposition). The hand entry always wins.
    """
    effective = dict(dispositions)
    for row in rows:
        if row.row_id in effective:
            continue
        entry = (derived or {}).get(row.row_id)
        if entry is None or entry.derived_hash != row.content_hash:
            continue
        if entry.proposed:
            continue
        recomputed = derive_entry(row, beat_model=beat_model, boundary_model=boundary_model,
                                  generator_status=generator_status,
                                  hand_dispositions=dispositions)
        if (recomputed is None
                or recomputed.disposition != entry.disposition
                or recomputed.proposed != entry.proposed):
            continue
        effective[row.row_id] = entry.to_disposition(row.row_id)
    return effective


def _check_generator_refused(
    rows: list[ManifestRow],
    effective: dict[str, Disposition],
) -> list[Finding]:
    """`RULE_GENERATOR_REFUSED` (2026-10-04 operator ruling 2, PROJECT_TODO
    #124): every row whose effective disposition is `refused:<blocker>...`
    -- the beat generator could not produce its beat -- is a WARNING naming
    the blocker, plus one chapter-level WARNING with the count. A refusal is
    tracked backlog, not a red chapter; the count makes its growth visible.
    """
    findings: list[Finding] = []
    for row in rows:
        disp = effective.get(row.row_id)
        if disp is None or disp.verdict != "refused":
            continue
        findings.append(Finding(
            row_id=row.row_id,
            rule=RULE_GENERATOR_REFUSED,
            message=(
                f"the beat generator refused this row ({disp.argument}) -- "
                "tracked backlog until the named blocker is fixed upstream"
            ),
            severity="warning",
        ))
    if findings:
        by_blocker = Counter(
            (effective[f.row_id].argument or "").partition(":")[0].strip()
            for f in findings)
        breakdown = ", ".join(f"{b}={n}" for b, n in sorted(by_blocker.items()))
        findings.append(Finding(
            row_id="chapter",
            rule=RULE_GENERATOR_REFUSED,
            message=f"{len(findings)} row(s) refused by the beat generator ({breakdown})",
            severity="warning",
        ))
    return findings


def _check_archetype_conformance(
    rows: list[ManifestRow],
    dispositions: dict[str, Disposition],
    *,
    archetype_model: ArchetypeModel | None,
    live_chapter: bool,
) -> list[Finding]:
    """`RULE_ARCHETYPE_CONFORMANCE`: does every row a recognized archetype
    covers carry a verdict at least as strong as the archetype prescribes,
    and (for `beat` rows) is a registered beat actually claiming it as that
    archetype?

    "At least as strong" and not "equal to" -- see the floor-semantics
    comment in the loop below for the two legitimate departures and the
    CH04 evidence for each.

    Severity mirrors `PRE_MANIFEST_CHAPTER`'s reasoning: a chapter already
    through its §9 boot-walk gate passed under rules that predate this one,
    so a brand-new rule going straight to ERROR on old, already-approved
    content is a false alarm, not a regression -- and a permanently-red
    check is one people learn to scroll past. A chapter still being
    authored gets ERROR, because there nothing has been approved yet and
    the whole point is to catch the B14 shape before it ships.
    """
    severity: Severity = "error" if live_chapter else "warning"
    findings: list[Finding] = []
    exempt_count = 0

    for match in classify_manifest(rows):
        for row_id, prescribed in match.prescribed.items():
            role = match.roles[row_id]
            disp = dispositions.get(row_id)

            if disp is not None and disp.archetype_exempt:
                exempt_count += 1
                continue

            if disp is None:
                findings.append(Finding(
                    row_id=row_id,
                    rule=RULE_ARCHETYPE_CONFORMANCE,
                    message=(
                        f"row is the {role!r} page of a {match.archetype!r} "
                        f"archetype, which prescribes {prescribed!r}, but the row "
                        "carries no disposition at all -- a disposition pass "
                        "skipped a row that was on the page the whole time (the "
                        "B14 shape); disposition it or set archetype_exempt with "
                        "a reason"
                    ),
                    severity=severity,
                ))
                continue

            # A prescription is a FLOOR ON STRENGTH, not an equality. Three
            # kinds of legitimate departure exist; the first two were found on
            # CH04's committed, gate-passed dispositions on 2026-09-01, when
            # this compared with `!=` and reported 10 rows that were all
            # correctly authored:
            #
            #   * `blocked:` / `unreachable:` supersede the prescription
            #     entirely. Reachability is a different question from what
            #     kind of event this is: eight rows north of Route 2's
            #     rockslide gate are genuine trainers and item balls AND
            #     genuinely unreachable until CH07 grants Rock Smash. An
            #     archetype cannot demand a beat for a row no player can
            #     walk to.
            #   * `beat` satisfies a `cosmetic` prescription. That is the
            #     item-ball template's `negative_beat` arm -- a real
            #     "re-touch grants nothing" assertion is strictly stronger
            #     than waving the spent page through as decoration.
            #     `map035/ev009/p1` is exactly this, and its note records
            #     the definition it was reclassified under on 2026-08-25:
            #     "cosmetic means no trigger to press, not merely no state
            #     write."
            #   * `boundary` also supersedes the prescription entirely, same
            #     reasoning as `blocked:`/`unreachable:` -- a forward-crossing
            #     warp page can classify as the `warp` archetype (prescribing
            #     `beat`) while genuinely being the arriving chapter's row to
            #     assert, not this chapter's (PROJECT_TODO #72/#73). Listed
            #     explicitly rather than left to fall through the `!= "beat"`
            #     check below by accident -- both reach the same "no finding"
            #     outcome, but only one of them says so.
            #   * `elsewhere:` / `refused:` (2026-10-04, PROJECT_TODO #124) are
            #     the beat generator's own record: the row is outside this
            #     chapter's walk, or the generator could not build its beat
            #     and `RULE_GENERATOR_REFUSED` already tracks it as backlog
            #     (ruling 2: a warning, not an error -- this rule must not
            #     re-report it as one).
            #
            # What remains is the pair actually worth erroring on: a row
            # with no disposition at all (above), and a load-bearing
            # archetype page waved away as decoration (below).
            if disp.verdict in ("blocked", "unreachable", "boundary", "elsewhere", "refused"):
                continue

            if prescribed == "beat" and disp.verdict == "cosmetic":
                findings.append(Finding(
                    row_id=row_id,
                    rule=RULE_ARCHETYPE_CONFORMANCE,
                    message=(
                        f"row is the {role!r} page of a {match.archetype!r} "
                        "archetype, which prescribes 'beat', but it is "
                        f"dispositioned {disp.spec!r} -- an archetype page that "
                        "carries the chapter's mechanics is being waved through "
                        "as decoration; write the beat, or set archetype_exempt "
                        "with a reason if this instance is genuinely special"
                    ),
                    severity=severity,
                ))
                continue

            if disp.verdict != "beat":
                continue

            if archetype_model is None:
                findings.append(Finding(
                    row_id=row_id,
                    rule=RULE_ARCHETYPE_MODEL_UNENFORCED,
                    message=(
                        f"row is the {role!r} page of a {match.archetype!r} "
                        "archetype and correctly dispositioned 'beat', but "
                        "whether a registered beat actually claims it as that "
                        "archetype could not be checked because no archetype "
                        "model was supplied (this rule is unenforced without one)"
                    ),
                    severity="warning",
                ))
                continue

            claimed = archetype_model.claimed_archetype(row_id)
            if claimed != match.archetype:
                claim_desc = (
                    f"is claimed as {claimed!r} instead" if claimed is not None
                    else "no registered beat claims it"
                )
                findings.append(Finding(
                    row_id=row_id,
                    rule=RULE_ARCHETYPE_CONFORMANCE,
                    message=(
                        f"row is the {role!r} page of a {match.archetype!r} "
                        f"archetype and dispositioned {disp.spec!r}, but "
                        f"{claim_desc} -- register the beat that owns this row "
                        f"with archetype={match.archetype!r}"
                    ),
                    severity=severity,
                ))

    # Reported only when non-zero -- an empty/no-match chapter has nothing to
    # tally, and a bare `Finding(..., 0)` on every call would turn every
    # clean chapter's `findings == []` expectation into a false positive.
    # Absence already reads as "0" (see the report this rule feeds); a
    # nonzero count is exactly the "visible growth, not quiet drift" signal
    # the field exists for.
    if exempt_count:
        findings.append(Finding(
            row_id="chapter",
            rule=RULE_ARCHETYPE_CONFORMANCE,
            message=(
                f"{exempt_count} row(s) opted out of archetype conformance via "
                "archetype_exempt this chapter (corpus baseline: 2, "
                "map141/ev025/p0 and map131/ev003/*) -- tracked so a new "
                "exemption is visible growth, not quiet drift"
            ),
            severity="warning",
        ))

    return findings


def _check_unregistered_beat(
    dispositions: dict[str, Disposition],
    *,
    beat_model: BeatModel | None,
    live_chapter: bool,
) -> list[Finding]:
    """`RULE_UNREGISTERED_BEAT`: every `beat:Bn` disposition must name a beat
    that is actually registered -- not deferred, not a typo, not a stale
    rename.

    The original design note framed this as bidirectional: (a) every `beat:`
    disposition names a registered beat, and (b) every `DEFERRED_*` entry's
    row is dispositioned as something other than `beat:`. The two halves
    collapse into this single scan, because both key on the beat id -- a
    deferred beat is by construction not registered, so walking the
    dispositions and asking the model about each `beat:` argument catches
    (b) for free. A deferred beat whose row carries no disposition at all is
    already `RULE_UNDISPOSITIONED`'s job, not this one's.

    Motivating evidence: CH04's dispositions dispose `beat:B8` and
    `beat:B10` while `ch04.py`'s `DEFERRED_BEATS` lists both -- the manifest
    has claimed, since CH04 shipped, that something asserts those two rows
    when nothing runs. Nothing checked that a `beat:` argument round-trips
    through the registry at all.

    Deliberately scans `dispositions` directly rather than joining through
    `rows` -- a disposition whose row is not in the generated manifest is
    already reported by `RULE_ORPHAN_DISPOSITION`, but it can independently
    ALSO name an unregistered beat (both are true statements about the same
    stale entry), so this rule reports on it too rather than skipping rows
    not present in `rows_by_id`.

    Severity mirrors `RULE_ARCHETYPE_CONFORMANCE`'s policy (see that
    function's docstring for the full reasoning): ERROR while the chapter is
    still being authored, WARNING once it is through its §9 gate, so CH04's
    two real contradictions surface as counted debt on a chapter that has
    already shipped, not a build-breaking regression.
    """
    severity: Severity = "error" if live_chapter else "warning"
    findings: list[Finding] = []

    beat_rows = [
        (row_id, disp) for row_id, disp in dispositions.items()
        if disp.verdict == "beat"
    ]

    if beat_model is None:
        for row_id, disp in beat_rows:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_BEAT_MODEL_UNENFORCED,
                message=(
                    f"row is dispositioned {disp.spec!r} but whether beat "
                    f"{disp.argument!r} is actually registered could not be "
                    "checked because no beat model was supplied (this rule "
                    "is unenforced without one)"
                ),
                severity="warning",
            ))
        return findings

    for row_id, disp in beat_rows:
        beat_id = disp.argument or ""
        if beat_model.is_registered(beat_id):
            continue

        reason = beat_model.deferral_reason(beat_id)
        if reason is not None:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_UNREGISTERED_BEAT,
                message=(
                    f"row is dispositioned {disp.spec!r}, but beat {beat_id!r} "
                    f"is explicitly deferred ({reason!r}) and therefore never "
                    "runs -- the disposition claims this row is covered when "
                    "nothing asserts it; either register the beat, or change "
                    "this row's disposition to one that reflects that nothing "
                    "asserts it"
                ),
                severity=severity,
            ))
        else:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_UNREGISTERED_BEAT,
                message=(
                    f"row is dispositioned {disp.spec!r}, but no playtest "
                    f"module registers a beat {beat_id!r} under any name, "
                    "deferred or otherwise -- likely a rename or a typo"
                ),
                severity=severity,
            ))

    return findings


def _check_boundary(
    dispositions: dict[str, Disposition],
    *,
    boundary_model: BoundaryModel | None,
    live_chapter: bool,
) -> list[Finding]:
    """`RULE_BOUNDARY_NOT_CROSSING`/`RULE_BOUNDARY_UNCLAIMED`: does a
    `boundary` disposition tell the truth on both of its claims -- that the
    row really does lead outside this chapter's authoring-time territory,
    and that the chapter which arrives next actually claims it?

    A `boundary` disposition asserts two independent facts (`BoundaryModel`'s
    docstring), and this rule checks each one, short-circuiting after the
    first failure found for a given row -- a row that fails the
    "is this really a crossing" test hasn't earned the right to be judged on
    "did the successor claim it" too; only one finding is useful per row.

    Five outcomes, checked in order:

    1. No `boundary_model` at all: `RULE_BOUNDARY_MODEL_UNENFORCED`,
       `warning`, for every `boundary` row -- same unenforced-not-silent
       idiom as `RULE_BEAT_MODEL_UNENFORCED`.
    2. `is_forward_crossing` is False: `RULE_BOUNDARY_NOT_CROSSING`, at the
       live/gated severity -- the row doesn't lead anywhere outside the
       chapter, so `boundary` is a false claim being used to dodge a real
       disposition.
    3. `successor_chapter_id()` is None: `RULE_BOUNDARY_UNCLAIMED`, at the
       live/gated severity -- this chapter is terminal in the chain, so
       nothing will ever arrive to claim the row; this is a statement that
       can never become true, not a check that merely cannot run yet, so it
       is reported as unclaimed rather than unenforced.
    4. `successor_has_module()` is False: `RULE_BOUNDARY_MODEL_UNENFORCED`,
       `warning` -- the ordinary expected state of a `boundary` row authored
       well before its successor chapter's beats exist.
    5. `successor_claims(row_id)` is False: `RULE_BOUNDARY_UNCLAIMED`, at the
       live/gated severity -- the successor chapter exists and has beats,
       but none of them lists this row.

    Severity mirrors `RULE_ARCHETYPE_CONFORMANCE`'s/`RULE_UNREGISTERED_BEAT`'s
    policy (see either docstring for the full reasoning): ERROR while the
    chapter carrying the `boundary` row is still being authored, WARNING
    once it is through its §9 gate.
    """
    severity: Severity = "error" if live_chapter else "warning"
    findings: list[Finding] = []

    boundary_rows = [
        (row_id, disp) for row_id, disp in dispositions.items()
        if disp.verdict == "boundary"
    ]

    if boundary_model is None:
        for row_id, disp in boundary_rows:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_BOUNDARY_MODEL_UNENFORCED,
                message=(
                    f"row is dispositioned {disp.spec!r} but whether it "
                    "really crosses out of this chapter's territory, and "
                    "whether the successor chapter claims it, could not be "
                    "checked because no boundary model was supplied (this "
                    "rule is unenforced without one)"
                ),
                severity="warning",
            ))
        return findings

    for row_id, disp in boundary_rows:
        if not boundary_model.is_forward_crossing(row_id):
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_BOUNDARY_NOT_CROSSING,
                message=(
                    f"row is dispositioned {disp.spec!r}, but neither "
                    "slice_growth nor seam_growth detects it as a transfer "
                    "or connection leading outside this chapter's "
                    "authoring-time slice -- this row does not lead "
                    "anywhere outside the chapter, so 'boundary' is a false "
                    "claim; disposition it as something else"
                ),
                severity=severity,
            ))
            continue

        successor_id = boundary_model.successor_chapter_id()
        if successor_id is None:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_BOUNDARY_UNCLAIMED,
                message=(
                    f"row is dispositioned {disp.spec!r}, but this chapter "
                    "is terminal in reference/chapters.json's chain -- no "
                    "chapter ever arrives after it, so nothing could ever "
                    "claim this row; this can never become true, "
                    "disposition it as something else"
                ),
                severity=severity,
            ))
            continue

        if not boundary_model.successor_has_module():
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_BOUNDARY_MODEL_UNENFORCED,
                message=(
                    f"row is dispositioned {disp.spec!r}; the successor "
                    f"chapter {successor_id!r} exists in the chain, but has "
                    "no playtest module yet, so whether it actually claims "
                    "this row could not be checked (the ordinary state of "
                    "a boundary row authored well before its successor's "
                    "beats exist -- this rule is unenforced for it, not "
                    "negative)"
                ),
                severity="warning",
            ))
            continue

        if not boundary_model.successor_claims(row_id):
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_BOUNDARY_UNCLAIMED,
                message=(
                    f"row is dispositioned {disp.spec!r}, but no beat "
                    f"registered in successor chapter {successor_id!r} "
                    "lists this row in its own rows -- nothing actually "
                    "claims it; register a beat there that claims it, or "
                    "disposition this row as something else"
                ),
                severity=severity,
            ))

    return findings


def _check_derived_hash(
    rows_by_id: dict[str, ManifestRow],
    derived: dict[str, DerivedEntry] | None,
) -> list[Finding]:
    """`RULE_DERIVED_HASH_INELIGIBLE`: the corpus-wide automation-ratio tally
    for the machine-derived sidecar (`REDERIVATION_PLAN.md` §15.2 item 1).

    Per-row ineligibility is no longer reported here -- `check_chapter`'s
    row loop already recomputes `derive_entry` for every sidecar-covered row
    and reports `RULE_DERIVED_VERDICT_MISMATCH` for any entry it disagrees
    with, which includes an entry sitting on a now-ineligible row
    (`derive_entry` returns None for it, and None never equals a sidecar
    entry's disposition). A second per-row check here would just restate
    that same finding under a different rule name.

    This is the cross-game seam: a brand-new Essentials game starts with no
    hand-authored dispositions file at all, so `derived`'s row count against
    the generated manifest's row count IS the automation ratio -- broken
    down by verdict head (`cosmetic`/`beat`/`boundary`/`blocked`) and by how
    many of those are still-unaffirmed `blocked:` proposals.

    A `row_id` in `derived` that names no row in `rows_by_id` at all (a
    stale entry pointing at deleted/renamed content) is excluded from the
    tally -- `RULE_ORPHAN_DISPOSITION` has no sidecar equivalent, and
    adding one is scope this task does not need.
    """
    findings: list[Finding] = []
    if not derived:
        return findings

    counts: Counter[str] = Counter()
    proposals = 0
    matched = 0
    for row_id, entry in derived.items():
        if row_id not in rows_by_id:
            continue
        matched += 1
        head = entry.disposition.split(":", 1)[0]
        counts[head] += 1
        if entry.proposed:
            proposals += 1

    # Reported only when non-zero -- same idiom as the `archetype_exempt`
    # tally above: an empty/no-sidecar chapter has nothing to tally, and a
    # bare `Finding(..., 0)` on every call would turn every clean chapter's
    # `findings == []` expectation into a false positive. A nonzero count is
    # exactly the automation-ratio signal this sidecar exists to make
    # visible.
    if matched:
        breakdown = ", ".join(f"{head}={n}" for head, n in sorted(counts.items()))
        findings.append(Finding(
            row_id="chapter",
            rule=RULE_DERIVED_HASH_INELIGIBLE,
            message=(
                f"{matched} row(s) carry a machine-derived entry in the "
                f"sidecar this chapter ({breakdown}; {proposals} "
                "proposal(s) awaiting human affirmation) -- tracked so the "
                "automation ratio (machine-derived rows vs. total manifest "
                "rows) is visible growth, not quiet drift"
            ),
            severity="warning",
        ))

    return findings


def _describe_floor_assertion(a: FloorAssertion) -> str:
    """`kind@list_index` plus key params, e.g. `warp@12 (map_id=35, x=4,
    y=7, direction='down')` -- enough to locate the missing assertion in the
    source without dumping the whole `FloorAssertion` repr."""
    key_params = ", ".join(f"{name}={value!r}" for name, value in a.params)
    suffix = f" ({key_params})" if key_params else ""
    return f"{a.kind}@{a.list_index}{suffix}"


def _uncovered_message(missing: tuple[FloorAssertion, ...], *, cap: int = 8) -> str:
    shown = missing[:cap]
    remainder = len(missing) - len(shown)
    listed = "; ".join(_describe_floor_assertion(a) for a in shown)
    tail = f"; +{remainder} more" if remainder > 0 else ""
    return (
        f"row's declared assertions do not cover its generic floor -- "
        f"{len(missing)} missing: {listed}{tail}"
    )


def _check_floor_coverage(
    rows: list[ManifestRow],
    *,
    floor_coverage: FloorCoverageModel | None,
) -> list[Finding]:
    """`RULE_FLOOR_UNCOVERED`/`RULE_FLOOR_UNDECLARED`/`RULE_FLOOR_MISSING`
    (REDERIVATION_PLAN.md §16.3 C5, R11): a row's declared assertions must
    cover the generic per-command floor `beat_floor` derives from source,
    for every row a registered beat claims.

    Only asks the question of rows `floor_coverage.claims()` says something
    claims -- R11's ⊇ rule has nothing to say about a row nothing has
    reached yet, and a refused floor (`RowFloor.refused`) skips the rule
    entirely: the refusal is already the row's named blocker (C5 shape (d)).
    Restricted to THIS chapter's own `rows` (the generated manifest passed
    to `check_chapter`), same as every other per-row rule in this module --
    a beat that happens to also claim a predecessor chapter's row is
    checked when THAT chapter's own `check_chapter` call walks its own rows,
    not here.

    Without a `floor_coverage` model, which rows are even claimed is not
    knowable at all (that fact lives entirely on the model, exactly like
    `RouteModel`'s registered/planned group orders) -- so this degrades to
    one chapter-scale `RULE_FLOOR_MODEL_UNENFORCED` warning, the same shape
    as `RULE_ROUTE_MODEL_UNENFORCED`, rather than a per-row warning this
    checker cannot actually target at the claimed subset.
    """
    findings: list[Finding] = []
    if floor_coverage is None:
        findings.append(Finding(
            row_id="chapter",
            rule=RULE_FLOOR_MODEL_UNENFORCED,
            message=(
                "could not check the generic floor's superset rule against "
                "any row because no floor coverage model was supplied (this "
                "rule is unenforced without one)"
            ),
            severity="warning",
        ))
        return findings

    generated = floor_coverage.is_generated()

    for row in rows:
        row_id = row.row_id
        if not floor_coverage.claims(row_id) or floor_coverage.exempt(row_id):
            continue

        try:
            floor = floor_coverage.floor(row_id)
        except KeyError as exc:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_FLOOR_MISSING,
                message=(
                    "row is claimed by a registered beat, but beat_floor "
                    f"has no floor for it ({exc}) -- a claimed row the "
                    "floor cannot see is a bug in the claim or in the "
                    "floor, never an empty floor"
                ),
                severity="error",
            ))
            continue

        if floor.refused:
            # No defined floor to check against; the refusal is the row's
            # named blocker (beat_floor's own CLI reports it).
            continue

        declared = floor_coverage.declared(row_id)
        if declared is None:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_FLOOR_UNDECLARED,
                message=(
                    "row is claimed by a registered beat, but no claiming "
                    "beat declares its assertions -- an undeclared, "
                    "hand-written beat cannot be checked against the "
                    "generic floor's superset rule until it declares, or "
                    "until C6/C9 replace it with a generated beat"
                ),
                severity="error" if generated else "warning",
            ))
            continue

        # Same gap definition as the C9 grader (`beat_floor.coverage.
        # graded_gaps`): walk-checked kinds are not owed, a blocked_obstacle
        # floor owes only that, contradictions always count.
        gaps = graded_gaps(floor, declared)
        if gaps:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_FLOOR_UNCOVERED,
                message=_uncovered_message(gaps.contradicted + gaps.missing),
                severity="error",
            ))

    return findings


def _check_route_order(route: RouteModel) -> list[Finding]:
    """The substantive half of `RULE_ROUTE_ORDER`: compare planned vs.
    registered group order, and the plan's precedence edges against the
    registered order. Split out of `check_chapter` only for readability --
    it is still just one more whole-chapter pass, called exactly once."""
    findings: list[Finding] = []
    planned = route.planned_group_order()
    registered = route.registered_group_order()
    planned_set = set(planned)
    registered_set = set(registered)

    planned_only = [g for g in planned if g not in registered_set]
    for group_id in planned_only:
        findings.append(Finding(
            row_id="chapter",
            rule=RULE_ROUTE_ORDER,
            message=(
                f"group {group_id!r} appears in the planned route order but "
                "was never registered in the chapter -- a beat group was "
                "dropped, renamed, or the route plan is stale and needs "
                "re-solving"
            ),
            severity="error",
        ))

    registered_only = [g for g in registered if g not in planned_set]
    for group_id in registered_only:
        findings.append(Finding(
            row_id="chapter",
            rule=RULE_ROUTE_ORDER,
            message=(
                f"group {group_id!r} is registered in the chapter but does "
                "not appear anywhere in the planned route order -- a new or "
                "renamed beat group that the route plan has never seen; "
                "re-run the solver"
            ),
            severity="error",
        ))

    # Compare relative order only over groups common to both -- a group
    # missing from one side is already reported above, and dragging it into
    # the ordering diff too would just restate the same mistake twice.
    planned_common = [g for g in planned if g in registered_set]
    registered_common = [g for g in registered if g in planned_set]
    if planned_common != registered_common:
        planned_index = {g: i for i, g in enumerate(planned)}
        registered_index = {g: i for i, g in enumerate(registered)}
        mismatched = [i for i in range(len(planned_common))
                      if planned_common[i] != registered_common[i]]
        is_pure_swap = (
            len(mismatched) == 2
            and planned_common[mismatched[0]] == registered_common[mismatched[1]]
            and planned_common[mismatched[1]] == registered_common[mismatched[0]]
        )
        if is_pure_swap:
            # A pure transposition of one pair -- name the swap directly
            # rather than reporting each group "out of place" separately, so
            # the finding points at the one edit (swap these two) that fixes
            # it instead of two findings that could misleadingly suggest two
            # independent problems.
            a = planned_common[mismatched[0]]
            b = planned_common[mismatched[1]]
            findings.append(Finding(
                row_id="chapter",
                rule=RULE_ROUTE_ORDER,
                message=(
                    f"groups {a!r} and {b!r} are transposed: the plan walks "
                    f"{a!r} before {b!r} (plan positions {planned_index[a]}, "
                    f"{planned_index[b]}), but the chapter registers {b!r} "
                    f"before {a!r} (registered positions "
                    f"{registered_index[b]}, {registered_index[a]}) -- swap "
                    "their registration order"
                ),
                severity="error",
            ))
        else:
            for i in mismatched:
                group_id = planned_common[i]
                findings.append(Finding(
                    row_id="chapter",
                    rule=RULE_ROUTE_ORDER,
                    message=(
                        f"group {group_id!r} is out of order: the plan puts "
                        f"it at position {planned_index[group_id]}, but it "
                        f"is registered at position "
                        f"{registered_index[group_id]} in the chapter -- "
                        "reorder the chapter's beat registration to match "
                        "the planned walk"
                    ),
                    severity="error",
                ))

    registered_index = {g: i for i, g in enumerate(registered)}
    for edge in route.precedence_edges():
        if edge.before not in registered_set or edge.after not in registered_set:
            continue
        if registered_index[edge.after] < registered_index[edge.before]:
            findings.append(Finding(
                row_id="chapter",
                rule=RULE_ROUTE_ORDER,
                message=(
                    f"precedence violated: group {edge.after!r} is "
                    f"registered before group {edge.before!r} (registered "
                    f"positions {registered_index[edge.after]} < "
                    f"{registered_index[edge.before]}), but the route plan "
                    f"requires {edge.before!r} before {edge.after!r} -- "
                    f"{edge.reason}"
                ),
                severity="error",
            ))

    return findings


def _check_route_approach(route: RouteModel) -> list[Finding]:
    """`RULE_ROUTE_APPROACH`: for every plan node the solver committed to a
    side for, does the beat that node covers actually stand there?

    Motivating gap: `RULE_ROUTE_ORDER` (above) makes sure the chapter walks
    groups in the order the plan expects, but says nothing about *which
    side of an NPC or staircase* a beat stands on -- that is chosen by the
    solver too, per group, and recorded as the node's `chosen_approach`. The
    chapter module declares its own beat position independently, via `at=`
    (or the archetype templates' `approach_prefer=`, which resolves to an
    `at=`). Nothing made those two choices agree: a route can be planned
    against the north side of a passage while the registered beat stands on
    the east side, with `at=` enforcement and `RULE_ROUTE_ORDER` both
    green, and the plan the operator approved is then not the path that
    gets walked. Ruled a hard ERROR, not a warning -- this is exactly the
    "plan says one thing, ROM does another" gap the whole route-model
    family exists to close.

    Only the first of a node's `beats` with a resolvable declared cell is
    compared -- a `chosen_approach` is one side for one stop, and multiple
    beats sharing a group share that one stop's position (`RouteNode`
    requires contiguous registration for a group, same as `RULE_ROUTE_ORDER`
    treats it as indivisible). A node whose beats are all unregistered, or
    registered with no declared location at all, cannot be checked -- that
    degrades to `RULE_ROUTE_MODEL_UNENFORCED`, never a silent pass, the same
    idiom `RULE_ROUTE_ORDER` and its siblings use throughout this module.
    """
    findings: list[Finding] = []
    for approach in route.planned_approaches():
        beat_id: str | None = None
        declared: tuple[int, int] | None = None
        for candidate in approach.beats:
            cell = route.declared_beat_cell(candidate)
            if cell is not None:
                beat_id, declared = candidate, cell
                break

        if declared is None:
            findings.append(Finding(
                row_id="chapter",
                rule=RULE_ROUTE_MODEL_UNENFORCED,
                message=(
                    f"group {approach.group!r} has a planned approach side "
                    f"{approach.side!r} (resolver: {approach.resolver}), "
                    "but none of its beats "
                    f"{list(approach.beats)!r} are registered with a "
                    "declared location -- the planned approach side could "
                    "not be checked against anything (this rule is "
                    "unenforced for this group)"
                ),
                severity="warning",
            ))
            continue

        if declared == approach.cell:
            continue

        findings.append(Finding(
            row_id="chapter",
            rule=RULE_ROUTE_APPROACH,
            message=(
                f"beat {beat_id!r} (group {approach.group!r}, map "
                f"{approach.map_id}): the route plan committed to approach "
                f"side {approach.side!r} at cell {approach.cell!r} "
                f"(resolver: {approach.resolver}), but the beat is "
                f"registered at cell {declared!r} instead -- the plan the "
                "operator approved is not the path that gets walked; pass "
                f"approach_prefer={approach.side!r} (or prefer=) to the "
                "beat's archetype template to match the plan, or re-solve "
                "the route if the plan is the one that's wrong"
            ),
            severity="error",
        ))

    return findings


def _dispositioned_trainer_maps(
    rows: list[ManifestRow], dispositions: dict[str, Disposition],
) -> set[int]:
    """Map ids carrying at least one `trainer`-archetype row that also has a
    disposition on file.

    Classification comes from `archetypes.classify_manifest`, the single
    source of truth CLAUDE.md §4.3 assigns for "what counts as a trainer"
    -- never re-derived from `script_heads` here. Gated on "has a
    disposition" (rather than every row `classify_manifest` matches,
    dispositioned or not) because an undispositioned trainer row is already
    reported by `RULE_UNDISPOSITIONED`/`RULE_ARCHETYPE_CONFORMANCE`; this
    rule only needs to know a trainer is *live* on a map, and "someone
    dispositioned it" is the cheapest available proxy for "this trainer is
    a real, authored battle" rather than a stray classifier false-positive
    on dead content.
    """
    trainer_maps: set[int] = set()
    for match in classify_manifest(rows):
        if match.archetype != "trainer":
            continue
        if any(row_id in dispositions for row_id in match.roles):
            trainer_maps.add(match.map_id)
    return trainer_maps


def check_trigger_overlay(
    rows: list[ManifestRow],
    dispositions: dict[str, Disposition],
    *,
    trigger_overlay: TriggerOverlayModel | None = None,
) -> list[Finding]:
    """`RULE_TRIGGER_OVERLAY_VACUOUS`: for every map with a dispositioned
    trainer row, did the trigger overlay actually find a `TRAINER_SIGHT`
    tile there?

    Split out of `check_chapter` (which calls this too, so `chapter_manifest
    check` also reports it) specifically so `routing.__main__.plan_cmd` can
    call it directly, standalone, right after building the overlay and
    before trusting the solved route's `CROSSING` output -- see
    `TriggerOverlayModel`'s docstring for why the ROUTE step is where this
    must fire, not only the later manifest-check pass. Same
    unenforced-rather-than-silent idiom as `RULE_ROUTE_MODEL_UNENFORCED`:
    a chapter with no trainer rows at all reports nothing (there is nothing
    this rule could say), but a chapter WITH dispositioned trainer rows and
    no `trigger_overlay` supplied degrades loud rather than passing quiet.
    """
    findings: list[Finding] = []
    trainer_maps = _dispositioned_trainer_maps(rows, dispositions)
    if not trainer_maps:
        return findings

    if trigger_overlay is None:
        findings.append(Finding(
            row_id="chapter",
            rule=RULE_TRIGGER_OVERLAY_MODEL_UNENFORCED,
            message=(
                "chapter has dispositioned trainer row(s) on map(s) "
                f"{sorted(trainer_maps)} but no trigger overlay model was "
                "supplied, so a zero-CROSSING route cannot be told apart "
                "from an overlay that measured nothing (this rule is "
                "unenforced without one)"
            ),
            severity="warning",
        ))
        return findings

    for map_id in sorted(trainer_maps):
        if trigger_overlay.has_trainer_sight_tiles(map_id):
            continue
        findings.append(Finding(
            row_id=f"map{map_id:03d}",
            rule=RULE_TRIGGER_OVERLAY_VACUOUS,
            message=(
                f"map{map_id:03d} has a dispositioned trainer row, but the "
                "trigger overlay found zero TRAINER_SIGHT tiles on this "
                "map -- a route with no CROSSING lines here is "
                "indistinguishable from an overlay that measured nothing "
                "(PROJECT_TODO #75's CH05 incident: object events did not "
                "exist yet). Confirm this map's object events are actually "
                "emitted (trainer_type, movement_type, sight range) before "
                "trusting a clean route across it"
            ),
            severity="error",
        ))

    return findings


def exit_code(findings: list[Finding]) -> int:
    """0 if no finding is an error; 1 otherwise. Warnings alone do not fail."""
    return 1 if any(f.severity == "error" for f in findings) else 0
