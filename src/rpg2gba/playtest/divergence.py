"""Compare a playtest runner's walked tile path against the approved offline
route plan (`rpg2gba.routing.plan.RoutePlan`), and classify any divergence.

## Why trigger divergence fails and other divergence does not

Slice 4 exists because of one incident: a walk to trainer Larrie crossed
trainer Timothy's event-touch tile, fought the wrong trainer, and both the
route-planning guard and the playtest guard passed anyway. A tile the walk
steps onto that fires a script belonging to some OTHER destination is
unambiguously wrong -- it changes what happened in the beat, silently. That
case must fail the beat (`WalkComparison.failed`, driven by
`trigger_violations`).

Every other kind of divergence -- the walk took a different, still-safe path
than the plan predicted -- is explicitly NOT a failure. `PLAYTEST_AUTHORING_
IMPROVEMENT_V2.md`'s 2026-08-28 decision ("trigger divergence fails; all
other divergence is a Q8 carried contradiction") is explicit about why: a
legitimate re-plan around a patrolling NPC diverges on every single run (the
NPC is never in exactly the cell the offline graph assumed), and
`CH02:B14` already demonstrated that blocking a beat on ambiguous evidence
throws away real, otherwise-valid work. Non-trigger divergence is instead
recorded as a carried contradiction between the offline routing model and
the measured walk (`WalkComparison.off_plan`) -- evidence the offline graph
might be wrong (sideways-stairs collision, sight-cone semantics, an object
spawn window), surfaced for a human/viewer to reconcile, never blocking.

## Why plan-declared crossings are exempt

`RouteSegment.crossed_foreign_triggers` is the route solver's own admission
that a particular segment must cross a tile it doesn't own, generally
because the map graph makes it geometrically unavoidable (a corridor with a
trainer's sight line laid across it, say). A human already reviewed and
accepted that crossing when the plan was authored (`TriggerCrossing.
declared`). Re-flagging it here as a fresh violation would just make the
approved plan permanently unrunnable -- so `PlanIndex.declared_crossings`
short-circuits before the foreign-trigger check ever runs.

## Why the plan tile set is unioned over the whole plan, not matched leg-by-leg

A naive comparison would match each beat's walk only against the specific
segment/leg the router assigned to that beat. That fails constantly for a
mundane reason: chapters double back on themselves (return trips through an
earlier room, a corridor shared by two beats' approaches), so a later beat's
walk legitimately re-treads tiles a strictly earlier segment owns. Matching
leg-by-leg would report every one of those retreads as a divergence, which
is noise, not signal. `PlanIndex.tiles` therefore unions every tile the
*whole* plan walks, across every segment and leg, and the comparison asks
the question that is actually being asked here: "did the walk step
somewhere the approved route never goes at all" -- not "did this beat's walk
match this beat's assigned leg stroke-for-stroke."
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

Cell = tuple[int, int]


@dataclass(frozen=True)
class WalkedTile:
    """One step of the runner's actually-walked path, as logged live during a
    playtest beat. `map_id` is the Uranium map id resolved from the live
    (map_group, map_num) pair the emulator reports; it is `None` when that
    resolution failed (an unminted or unmapped live map). A tile with
    `map_id is None` cannot be compared against anything -- the plan is keyed
    by Uranium map id -- but CLAUDE.md §4.5 forbids silently dropping data we
    can't interpret, so it must still be counted (`WalkComparison.
    unresolved`) rather than vanish from the record."""

    map_id: int | None
    map_group: int
    map_num: int
    x: int
    y: int


@dataclass(frozen=True)
class TriggerFact:
    """A JSON-safe flattening of one `rpg2gba.traversal.triggers.TriggerRef`,
    so this module never has to import the traversal package's enums into
    its own (de)serialization path -- `divergence.py` only needs to carry
    the trigger's identity through to a report, not reason about it."""

    script: str
    kind: str
    certainty: str
    detail: str

    @classmethod
    def from_ref(cls, ref: Any) -> TriggerFact:
        def _stringify(value: Any) -> str:
            enum_value = getattr(value, "value", None)
            return enum_value if enum_value is not None else str(value)

        return cls(
            script=ref.script,
            kind=_stringify(ref.kind),
            certainty=_stringify(ref.certainty),
            detail=ref.detail,
        )


@dataclass(frozen=True)
class Divergence:
    """One walked tile the approved plan does not account for. `kind` is
    exactly `"trigger"` (the tile fires a foreign script -- a beat-failing
    violation) or `"off_plan"` (off the approved route but not a trigger --
    a recorded, non-blocking contradiction). `step_index` is the index into
    the beat's `walked` sequence of the FIRST visit to this tile (see the
    dedup note on `compare_walk`)."""

    map_id: int
    cell: Cell
    step_index: int
    kind: str
    triggers: tuple[TriggerFact, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "map_id": self.map_id,
            "cell": [self.cell[0], self.cell[1]],
            "step": self.step_index,
            "kind": self.kind,
            "triggers": [
                {
                    "script": t.script,
                    "kind": t.kind,
                    "certainty": t.certainty,
                    "detail": t.detail,
                }
                for t in self.triggers
            ],
        }


@dataclass(frozen=True)
class WalkComparison:
    """The result of comparing one beat's walked path against the approved
    route plan. `failed` is the only signal a beat gate should act on --
    `off_plan` is deliberately non-blocking (see module docstring)."""

    beat: str
    compared: bool
    steps: int
    unresolved: int
    off_plan: tuple[Divergence, ...] = ()
    trigger_violations: tuple[Divergence, ...] = ()
    note: str = ""

    @property
    def failed(self) -> bool:
        return bool(self.trigger_violations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "beat": self.beat,
            "compared": self.compared,
            "steps": self.steps,
            "unresolved": self.unresolved,
            "off_plan": [d.to_dict() for d in self.off_plan],
            "trigger_violations": [d.to_dict() for d in self.trigger_violations],
            "note": self.note,
            "failed": self.failed,
        }


@dataclass(frozen=True)
class PlanIndex:
    """The comparison oracle derived from an approved `RoutePlan`: every tile
    the plan walks anywhere in the chapter, and every tile the plan already
    declares it must cross, both keyed by Uranium map id. See the module
    docstring for why `tiles` is a union over the whole plan rather than
    scoped per segment."""

    tiles: Mapping[int, frozenset[Cell]]
    declared_crossings: Mapping[int, frozenset[Cell]]
    chapter_id: str

    @classmethod
    def from_plan(cls, plan: Any) -> PlanIndex:
        tiles: dict[int, set[Cell]] = {}
        declared: dict[int, set[Cell]] = {}
        for segment in plan.segments:
            for leg in segment.legs:
                tiles.setdefault(leg.map_id, set()).update(leg.tiles)
            for crossing in segment.crossed_foreign_triggers:
                if crossing.declared:
                    declared.setdefault(crossing.map_id, set()).add(crossing.cell)
        return cls(
            tiles={map_id: frozenset(cells) for map_id, cells in tiles.items()},
            declared_crossings={
                map_id: frozenset(cells) for map_id, cells in declared.items()
            },
            chapter_id=plan.chapter_id,
        )


def load_plan_index(chapter_id: str, *, root: Path | None = None) -> PlanIndex | None:
    """Load the approved route plan for `chapter_id` and index it, or return
    `None` when no plan artifact exists yet for this chapter.

    Route plans are enforced forward from CH05 (per `PLAYTEST_AUTHORING_
    IMPROVEMENT_V2.md`'s slice ordering) -- earlier chapters were built and
    gated before the routing solver existed, and have no plan artifact and
    never will. Absence is therefore the ordinary case today, not an error:
    `compare_walk` degrades to "not compared" rather than raising. A file
    that DOES exist but fails to parse is a different situation entirely --
    a corrupted or hand-edited approved artifact -- and that must propagate
    loud (CLAUDE.md §4.5), not be swallowed alongside the "doesn't exist"
    case.

    `rpg2gba.routing.plan` is imported lazily inside this function, not at
    module scope, so that every other function in this module -- the actual
    comparison logic -- stays importable and testable without dragging the
    routing package (and its own dependencies) into a pure-data code path
    that has no need of them.
    """
    from rpg2gba.routing.plan import load_plan, route_path

    path = route_path(chapter_id, root=root)
    if not path.exists():
        logger.info(
            "no route plan artifact for %s at %s -- walk comparison will report "
            "compared=False rather than enforcing divergence",
            chapter_id,
            path,
        )
        return None
    plan = load_plan(path)
    return PlanIndex.from_plan(plan)


def load_plan_index_for_module(
    module_name: str, *, root: Path | None = None
) -> PlanIndex | None:
    """The approved plan for the chapter *playtest module* `module_name`
    (`"CH04"`, `"CH03"`, ...), or `None` when no plan claims it.

    The runner knows which playtest module it is running; route plans are
    named by *atlas chapter id* (`CH04.route.json`). Playtest modules are now
    named for their atlas chapter id (`CH04` -> `chapters/ch04.py`,
    2026-09-01), so the join is derivable by convention. This function still
    doesn't rely on that convention, though: it reads the binding out of the
    artifacts themselves, since a module can still be run under an explicit
    `--module` that differs from its chapter id (see `test_routing_cli.py`'s
    `test_plan_chapter_id_and_module_are_distinct_names`) -- every plan
    records the `chapter_module` it was solved for, so the join is a scan of
    `reference/routes/*.route.json` for the one that names this module.

    Two plans claiming the same module is a genuine fault -- the operator
    approved two different routes for one chapter and neither can be said
    to be the approved one -- and raises rather than picking either
    (CLAUDE.md §4.5).
    """
    from rpg2gba.routing.plan import load_plan, route_path

    routes_dir = route_path("_", root=root).parent
    if not routes_dir.is_dir():
        logger.info(
            "no route plan directory at %s -- walk comparison is unenforced "
            "for chapter module %r", routes_dir, module_name)
        return None
    matches = []
    for path in sorted(routes_dir.glob("*.route.json")):
        plan = load_plan(path)
        if plan.chapter_module == module_name:
            matches.append((path, plan))
    if not matches:
        logger.info(
            "no route plan in %s names chapter module %r -- walk comparison "
            "will report compared=False rather than enforcing divergence "
            "(route plans are enforced forward from CH05, PROJECT_TODO #67)",
            routes_dir, module_name)
        return None
    if len(matches) > 1:
        names = ", ".join(str(p) for p, _ in matches)
        raise ValueError(
            f"chapter module {module_name!r} is claimed by more than one "
            f"approved route plan ({names}) -- exactly one plan per chapter "
            "module, or there is no approved route to compare against")
    return PlanIndex.from_plan(matches[0][1])


def compare_walk(
    beat: str,
    walked: Sequence[WalkedTile],
    *,
    plan: PlanIndex | None,
    foreign_triggers: Mapping[int, Mapping[Cell, Sequence[TriggerFact]]],
) -> WalkComparison:
    """Compare one beat's walked tile path against the approved route plan.

    Rules (see module docstring for the reasoning behind each):

    1. No plan (`plan is None`) -> `compared=False`, no violations reported
       at all. We never fail a beat against an oracle that doesn't exist.
    2. A walked tile whose `map_id` is `None` (unresolved live map) is
       counted in `unresolved` and skipped -- it cannot be checked against
       anything keyed by Uranium map id, and CLAUDE.md §4.5 forbids just
       dropping it silently.
    3. A tile on the plan's unioned walk set, or in the plan's declared
       foreign-trigger crossings, is fine -- nothing recorded, even if it
       happens to also carry a trigger, because the plan already approved
       stepping there.
    4. A tile off the plan that keys into `foreign_triggers[map_id]` is a
       `"trigger"` divergence -- fails the beat.
    5. Any other off-plan tile is an `"off_plan"` divergence -- recorded,
       does not fail the beat.
    6. Repeated visits to the same (map_id, cell) within this one beat are
       deduplicated to a single `Divergence` at the first step index, so an
       oscillating walk over one bad tile produces one row, not fifty. The
       returned `note` reports both the deduplicated violation count and the
       raw step count so the dedup is legible rather than silently lossy.
    """
    if plan is None:
        return WalkComparison(
            beat=beat,
            compared=False,
            steps=len(walked),
            unresolved=0,
            note=(
                f"no route plan exists for this chapter -- walk not compared "
                f"against a plan; {len(walked)} step(s) unchecked"
            ),
        )

    unresolved = 0
    off_plan: list[Divergence] = []
    trigger_violations: list[Divergence] = []
    seen: set[tuple[int, Cell]] = set()
    raw_off_plan_steps = 0
    raw_trigger_steps = 0

    for step_index, tile in enumerate(walked):
        if tile.map_id is None:
            unresolved += 1
            continue

        map_id = tile.map_id
        cell: Cell = (tile.x, tile.y)

        if cell in plan.tiles.get(map_id, frozenset()):
            continue
        if cell in plan.declared_crossings.get(map_id, frozenset()):
            continue

        map_triggers = foreign_triggers.get(map_id, {})
        facts = map_triggers.get(cell)
        if facts:
            raw_trigger_steps += 1
            key = (map_id, cell)
            if key in seen:
                continue
            seen.add(key)
            trigger_violations.append(
                Divergence(
                    map_id=map_id,
                    cell=cell,
                    step_index=step_index,
                    kind="trigger",
                    triggers=tuple(facts),
                )
            )
        else:
            raw_off_plan_steps += 1
            key = (map_id, cell)
            if key in seen:
                continue
            seen.add(key)
            off_plan.append(
                Divergence(
                    map_id=map_id,
                    cell=cell,
                    step_index=step_index,
                    kind="off_plan",
                )
            )

    note = (
        f"{len(trigger_violations)} trigger violation(s) "
        f"({raw_trigger_steps} raw step(s)), "
        f"{len(off_plan)} off-plan divergence(s) "
        f"({raw_off_plan_steps} raw step(s)), "
        f"{unresolved} unresolved step(s) of {len(walked)} total"
    )

    return WalkComparison(
        beat=beat,
        compared=True,
        steps=len(walked),
        unresolved=unresolved,
        off_plan=tuple(off_plan),
        trigger_violations=tuple(trigger_violations),
        note=note,
    )


def foreign_trigger_index(
    overlays: Mapping[int, Any],
    destination_scripts: Mapping[int, set[str]] | None = None,
) -> dict[int, dict[Cell, tuple[TriggerFact, ...]]]:
    """Build the `foreign_triggers` argument `compare_walk` needs, from
    slice 2's per-map `TriggerOverlay`s (`rpg2gba.traversal.triggers`).

    For each map, a tile counts as "foreign" per `TriggerOverlay.
    foreign_tiles` -- every trigger on that tile belongs to some script
    other than the ones this beat's walk is destined for. `destination_
    scripts` supplies that per-map destination set; a map absent from it is
    treated as having no destination script of its own (an empty set), so
    every trigger tile on that map counts as foreign -- correct for a map
    the walk is only passing through, never aiming at.
    """
    destinations = destination_scripts or {}
    index: dict[int, dict[Cell, tuple[TriggerFact, ...]]] = {}
    for map_id, overlay in overlays.items():
        dest = destinations.get(map_id, set())
        foreign_cells = overlay.foreign_tiles(dest)
        index[map_id] = {
            cell: tuple(TriggerFact.from_ref(ref) for ref in overlay.refs_at(cell))
            for cell in foreign_cells
        }
    return index
