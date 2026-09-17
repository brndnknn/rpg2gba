"""Move-route (RMXP code 209, "Set Move Route") extractor for the generic
beat floor (REDERIVATION_PLAN.md §16.3 C4, R11).

Operator ruling (C4 shape, 2026-09-16): assert net displacement where the
route's own steps make it predictable; otherwise assert only that the page
completes (visual-only). Collision with the map is NOT modelled — the floor
asserts the source's *intended* displacement, computed purely from the
route's step list. If the ROM's actual character ends up somewhere else
because a wall or another event blocked the route, that is a real
divergence between source intent and ROM behaviour and the checker should
fail it, not silently accept wherever the ROM walker landed.

A route is predictable when every step is one this module can resolve to a
known (dx, dy) contribution and, for facing-relative steps, the facing at
that point in the route is itself known (facing is NOT known at route
start — RMXP does not expose a character's current facing statically, so
`step forward`/`step backward`/relative turns are only predictable once an
earlier absolute turn or unfixed walk in *this* route has established a
facing). Diagonal steps (5-8) always clear facing back to unknown afterward
(RMXP's diagonal-facing rule is ambiguous enough between engine versions
that asserting a guessed facing risks a false floor).

Unpredictable reasons (all downgrade the row to a `visual`
`unpredictable_route:<reason>` assertion, never a refusal):
  - `repeat` — the route's own flag (`skippable` is not a reason: it only
    changes what a blocked step does, and collision is not modelled)
  - `random_move` / `toward_player` / `away_player` — codes 9/10/11
  - `random_turn` — codes 23/24
  - `toward_player_turn` / `away_player_turn` — codes 25/26
  - `step_forward_unknown_facing` / `step_backward_unknown_facing` — 12/13
    reached before any facing is established
  - `relative_turn_unknown_facing` — 20/21/22 reached before any facing is
    established
  - `route_switch_write` — codes 27/28; story_state does not model switch
    writes that happen inside a move route, so the write is invisible to
    the model and the row is flagged rather than silently dropped
  - `script` — code 45
  - `unknown_step_code:<n>` — a step code outside RMXP's documented 0-45
    range (logged as a warning; still downgrades, never refuses)
"""

from __future__ import annotations

import logging
from typing import Any

from .assertion import ExtractContext, ExtractResult, FloorAssertion, make_params

logger = logging.getLogger(__name__)

# RMXP walk codes 1-4: (dx, dy, facing name). y grows downward.
_WALK_DELTAS: dict[int, tuple[int, int, str]] = {
    1: (0, 1, "down"),
    2: (-1, 0, "left"),
    3: (1, 0, "right"),
    4: (0, -1, "up"),
}

# RMXP diagonal codes 5-8: (dx, dy). Facing is always cleared to None after
# one of these (see module docstring).
_DIAG_DELTAS: dict[int, tuple[int, int]] = {
    5: (-1, 1),   # lower-left
    6: (1, 1),    # lower-right
    7: (-1, -1),  # upper-left
    8: (1, -1),   # upper-right
}

# RMXP absolute-turn codes 16-19.
_TURN_FACE: dict[int, str] = {16: "down", 17: "left", 18: "right", 19: "up"}

# (dx, dy) for a one-tile step in a known facing, used by step forward/back.
_FACING_DELTA: dict[str, tuple[int, int]] = {
    "down": (0, 1), "left": (-1, 0), "right": (1, 0), "up": (0, -1),
}

# Game_Character#turn_right_90 / #turn_left_90 / #turn_180 (RMXP source).
_TURN_RIGHT: dict[str, str] = {"down": "left", "left": "up", "up": "right", "right": "down"}
_TURN_LEFT: dict[str, str] = {"down": "right", "right": "up", "up": "left", "left": "down"}
_TURN_180: dict[str, str] = {"down": "up", "up": "down", "left": "right", "right": "left"}

# Codes with no position/facing effect at all — accepted, contribute nothing.
_NEUTRAL_CODES: frozenset[int] = frozenset({
    15,       # wait N frames
    29, 30,   # change speed, change frequency
    31, 32,   # move-animation on/off
    33, 34,   # stop-animation (step anime) on/off
    37, 38,   # through on/off
    39, 40,   # always-on-top on/off
    41,       # change graphic
    42,       # change opacity
    43,       # blending mode
    44,       # play SE
})

# Every step code this extractor understands, for the census test.
MOVE_STEP_CODES: frozenset[int] = frozenset(
    {0, 9, 10, 11, 12, 13, 14, 20, 21, 22, 23, 24, 25, 26, 27, 28, 35, 36, 45}
    | set(_WALK_DELTAS)
    | set(_DIAG_DELTAS)
    | set(_TURN_FACE)
    | _NEUTRAL_CODES
)


def extract_move_route(cmd: dict[str, Any], list_index: int, ctx: ExtractContext) -> ExtractResult:
    """Code 209 (Set Move Route). `cmd["parameters"]` is `[target, route]`;
    `target` is recorded exactly as given (-1 player, 0 this event, N event
    N) — it is not resolved through `ctx`."""
    params = cmd.get("parameters", [])
    target = params[0] if len(params) > 0 else None
    route = params[1] if len(params) > 1 else {}
    if not isinstance(route, dict):
        route = {}
    steps = route.get("list", []) if isinstance(route.get("list"), list) else []

    reason: str | None = None
    # `skippable` (Ignore If Can't Move) only changes what a *blocked* step
    # does; collision is not modelled, so the intended displacement stands.
    if route.get("repeat"):
        reason = "repeat"

    dx = 0
    dy = 0
    facing: str | None = None
    direction_fix = False

    if reason is None:
        for step in steps:
            code = step.get("code", 0)
            if code == 0:
                break
            step_params = step.get("parameters", [])

            if code in _WALK_DELTAS:
                sdx, sdy, name = _WALK_DELTAS[code]
                dx += sdx
                dy += sdy
                if not direction_fix:
                    facing = name
            elif code in _DIAG_DELTAS:
                sdx, sdy = _DIAG_DELTAS[code]
                dx += sdx
                dy += sdy
                facing = None
            elif code == 9:
                reason = "random_move"
                break
            elif code == 10:
                reason = "toward_player"
                break
            elif code == 11:
                reason = "away_player"
                break
            elif code == 12:
                if facing is None:
                    reason = "step_forward_unknown_facing"
                    break
                sdx, sdy = _FACING_DELTA[facing]
                dx += sdx
                dy += sdy
            elif code == 13:
                if facing is None:
                    reason = "step_backward_unknown_facing"
                    break
                sdx, sdy = _FACING_DELTA[facing]
                dx -= sdx
                dy -= sdy
            elif code == 14:
                if len(step_params) >= 2:
                    dx += int(step_params[0])
                    dy += int(step_params[1])
            elif code in _TURN_FACE:
                facing = _TURN_FACE[code]
            elif code == 20:
                if facing is None:
                    reason = "relative_turn_unknown_facing"
                    break
                facing = _TURN_RIGHT[facing]
            elif code == 21:
                if facing is None:
                    reason = "relative_turn_unknown_facing"
                    break
                facing = _TURN_LEFT[facing]
            elif code == 22:
                if facing is None:
                    reason = "relative_turn_unknown_facing"
                    break
                facing = _TURN_180[facing]
            elif code in (23, 24):
                reason = "random_turn"
                break
            elif code == 25:
                reason = "toward_player_turn"
                break
            elif code == 26:
                reason = "away_player_turn"
                break
            elif code in (27, 28):
                reason = "route_switch_write"
                break
            elif code == 35:
                direction_fix = True
            elif code == 36:
                direction_fix = False
            elif code in _NEUTRAL_CODES:
                pass
            elif code == 45:
                reason = "script"
                break
            else:
                logger.warning(
                    "move_route: unrecognized RMXP move-command code %r (row %s, list_index %s)",
                    code, ctx.row_id, list_index,
                )
                reason = f"unknown_step_code:{code}"
                break

    if reason is not None:
        assertion = FloorAssertion(
            row_id=ctx.row_id,
            kind="visual",
            list_index=list_index,
            code=209,
            params=make_params(code=209, detail=f"unpredictable_route:{reason}"),
            tag="visual",
        )
    else:
        assertion = FloorAssertion(
            row_id=ctx.row_id,
            kind="displacement",
            list_index=list_index,
            code=209,
            params=make_params(target=target, dx=dx, dy=dy, facing=facing),
            tag="position",
        )
    return (assertion,), ()
