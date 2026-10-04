"""Concrete `checker.RouteModel` over the offline route plan.

`checker.py` deliberately never imports `routing` or `playtest` (CLAUDE.md
§4.3 -- the checker judges rules, not routes; a `Protocol` is the seam).
This module is the thin adapter the CLI wires into
`checker.check_chapter`'s `route=` argument so `RULE_ROUTE_ORDER` can
actually run instead of degrading to `RULE_ROUTE_MODEL_UNENFORCED`.

It joins the two halves the rule compares, which live in different places
on purpose:

- the **planned** order is `reference/routes/<chapter>.route.json`, the
  artifact the operator approves before a chapter is built (Q13 decision 4:
  "what the operator approves is the route, not just the beat set");
- the **registered** order is the chapter's own playtest module, where
  registration order is playthrough order.

Ordering was convention until slice 3 -- enforced by nothing and recorded
only in a commit message. Wiring this adapter is what makes it checkable.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from rpg2gba.playtest.chapter import load_chapter
from rpg2gba.routing.plan import RoutePlan, RoutePlanError, load_plan, route_path

from .checker import PlannedApproach, RoutePrecedence

logger = logging.getLogger(__name__)

_CHOSEN_APPROACH_KEYS = frozenset({"side", "resolver"})


def _read_chosen_approaches(route_file: Path) -> dict[int, tuple[str, str] | None]:
    """Node index -> `(side, resolver)`, read directly off the plan JSON.

    Deliberately bypasses `routing.plan.RouteNode`/`plan_from_dict` for this
    one field: `chosen_approach` is not yet part of that dataclass's schema
    (it is landing there alongside the route-solver work this adapter must
    not block on -- see the task brief). Reading the raw JSON ourselves
    means this adapter works whether or not `RouteNode` has caught up, and
    never needs to change again once it does (the node's `group`/`map_id`/
    `cell`/`beats` -- already on `RouteNode` -- still come from `RoutePlan`
    itself; only the new key is read here).

    Still fails loud (CLAUDE.md §4.5) on a `chosen_approach` that IS present
    but malformed -- missing/extra keys are a real fault in the artifact,
    not "the field doesn't exist yet"."""
    raw: dict[str, Any] = json.loads(route_file.read_text(encoding="utf-8"))
    result: dict[int, tuple[str, str] | None] = {}
    for i, node in enumerate(raw.get("nodes", [])):
        if not isinstance(node, dict):
            continue
        index = node.get("index", i)
        chosen = node.get("chosen_approach")
        if chosen is None:
            result[index] = None
            continue
        if not isinstance(chosen, dict):
            raise RoutePlanError(
                f"{route_file}: nodes[{i}].chosen_approach must be an object "
                f"or null, got {chosen!r}"
            )
        got = set(chosen)
        if missing := _CHOSEN_APPROACH_KEYS - got:
            raise RoutePlanError(
                f"{route_file}: nodes[{i}].chosen_approach is missing "
                f"{sorted(missing)}"
            )
        if unknown := got - _CHOSEN_APPROACH_KEYS:
            raise RoutePlanError(
                f"{route_file}: nodes[{i}].chosen_approach carries unknown "
                f"keys {sorted(unknown)}"
            )
        result[index] = (chosen["side"], chosen["resolver"])
    return result


class PlanRouteModel:
    """`checker.RouteModel` backed by a real `RoutePlan` and `Chapter`."""

    def __init__(
        self,
        plan: RoutePlan,
        registered: tuple[str, ...],
        *,
        beat_locations: dict[str, tuple[int, int]] | None = None,
        chosen_approaches: dict[int, tuple[str, str] | None] | None = None,
    ) -> None:
        self._plan = plan
        self._registered = registered
        self._beat_locations = beat_locations or {}
        self._chosen_approaches = chosen_approaches or {}

    def planned_group_order(self) -> tuple[str, ...]:
        return tuple(
            node.group for node in self._plan.nodes
            if node.kind == "group" and node.group is not None
        )

    def registered_group_order(self) -> tuple[str, ...]:
        return self._registered

    def precedence_edges(self) -> tuple[RoutePrecedence, ...]:
        return tuple(
            RoutePrecedence(before=edge.before, after=edge.after, reason=edge.reason)
            for edge in self._plan.precedence
        )

    def planned_approaches(self) -> tuple[PlannedApproach, ...]:
        result: list[PlannedApproach] = []
        for node in self._plan.nodes:
            if node.kind != "group":
                continue
            chosen = self._chosen_approaches.get(node.index)
            if chosen is None:
                continue
            side, resolver = chosen
            result.append(PlannedApproach(
                group=node.group,  # type: ignore[arg-type]
                map_id=node.map_id,
                cell=node.cell,
                beats=node.beats,
                side=side,
                resolver=resolver,
            ))
        return tuple(result)

    def declared_beat_cell(self, beat_id: str) -> tuple[int, int] | None:
        return self._beat_locations.get(beat_id)


def build_route_model(
    chapter_id: str,
    *,
    route: Path | None = None,
    root: Path | None = None,
) -> PlanRouteModel | None:
    """Adapter for `chapter_id`, or None when the rule cannot be enforced yet.

    Returns None -- leaving `RULE_ROUTE_ORDER` to degrade to its
    `*_unenforced` warning -- in exactly two cases, both of which are the
    ordinary state of a chapter that has not been routed yet rather than an
    error: no route plan on disk, and no playtest module of that name. Both
    are logged so the reason is visible in the check output.

    A route plan that exists but does not load is NOT one of those cases: a
    corrupt or stale artifact is a real fault and `load_plan` raises through
    (CLAUDE.md §4.5).
    """
    route_file = route or route_path(chapter_id, root=root)
    if not route_file.exists():
        logger.info(
            "no route plan at %s -- route order is unenforced for %s; "
            "generate one with `python -m rpg2gba.routing plan --chapter %s`",
            route_file, chapter_id, chapter_id,
        )
        return None

    plan = load_plan(route_file)

    try:
        try:
            chapter = load_chapter(plan.chapter_module)
        except KeyError:
            # No generated module of that name: the plan may name a hand-suite
            # module, which is the only kind a route plan can approve.
            chapter = load_chapter(plan.chapter_module, suite="hand")
    except KeyError as exc:
        # KeyError specifically -- `load_chapter` raises it, and only it, for
        # "no module of that name". Anything else (a TypeError for a module
        # missing its CHAPTER, an ImportError from a broken chapter body) is a
        # real fault in a module that does exist, and propagates: a chapter
        # that fails to import must not read as a chapter that is merely
        # unrouted (CLAUDE.md §4.5).
        logger.info(
            "route plan %s names chapter module %r, which does not exist (%s) -- "
            "route order is unenforced for %s",
            route_file, plan.chapter_module, exc, chapter_id,
        )
        return None

    if chapter.suite == "gen":
        # A generated suite loads no route plan (operator ruling 2026-10-02,
        # `runner._WalkOracle.for_chapter`): the generator solves its own route
        # every run into `output/beats/CHnn.route.json`, and a plan under
        # `reference/routes/` approved the deleted HAND walks. Comparing the two
        # reported every regenerated group as unplanned (CH05: 27 errors).
        # Re-keyed 2026-10-04, PROJECT_TODO #124; #120 tracks gen-side plans.
        logger.info(
            "route plan %s predates the generated suite for %s -- route order is "
            "unenforced for a generated chapter (PROJECT_TODO #120)",
            route_file, chapter_id,
        )
        return None

    # Own groups only. `ChapterBuilder(predecessor=...)` prepends the
    # predecessor chapter's beats transitively, renamed `<owner>:<name>`
    # (`playtest.chapter._prefix_beat`), so `chapter.groups()` also returns
    # groups for those inherited beats -- 60 of CH04's 73, all of them
    # replay-to-reach-the-state and already covered by their own chapter's
    # route plan. The solver drops them by exactly this test
    # (`routing.solver._solvable_groups`); the rule compares the two orders,
    # so it has to drop the same ones or every inherited group reads as
    # "registered but never planned".
    registered = tuple(
        group.group_id for group in chapter.groups() if ":" not in group.group_id)

    # Same "own beats only" filter as `registered` above -- an inherited
    # predecessor beat's declared location belongs to that predecessor's
    # own chapter and route plan, not this one.
    beat_locations = {
        beat.name: (beat.locations[0].x, beat.locations[0].y)
        for beat in chapter.beats
        if ":" not in beat.name and beat.locations
    }
    chosen_approaches = _read_chosen_approaches(route_file)

    return PlanRouteModel(
        plan, registered,
        beat_locations=beat_locations,
        chosen_approaches=chosen_approaches,
    )
