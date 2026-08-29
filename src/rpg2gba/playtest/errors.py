"""Shared exception, import-safe without the mGBA bindings installed."""


class ScenarioError(RuntimeError):
    """A scenario step failed; a diagnostic screenshot may accompany it."""


class RoutePlanningError(ScenarioError):
    """The route planner could not reach a target.

    Split out from plain `ScenarioError` so `walk_to`'s re-plan loop can tell
    "could not plan a route" from "planned a route and then got stuck walking
    it". Both are failures now -- a planning failure used to degrade silently
    to an unprotected greedy walk on the bare target -- but only the second
    has waypoints to report, and the two want different diagnoses.
    """
