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

import logging
from pathlib import Path

from rpg2gba.playtest.chapter import load_chapter
from rpg2gba.routing.plan import RoutePlan, load_plan, route_path

from .checker import RoutePrecedence

logger = logging.getLogger(__name__)


class PlanRouteModel:
    """`checker.RouteModel` backed by a real `RoutePlan` and `Chapter`."""

    def __init__(self, plan: RoutePlan, registered: tuple[str, ...]) -> None:
        self._plan = plan
        self._registered = registered

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
        chapter = load_chapter(plan.chapter_module)
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
    return PlanRouteModel(plan, registered)
