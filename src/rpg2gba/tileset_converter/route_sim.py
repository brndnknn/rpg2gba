"""Phase 5 §5.3 support — RMXP move-route execution simulator.

Uranium NPCs carry a "move route" (`page["move_route"]`) the pipeline plays
back against pokeemerald's engine. But RMXP move-route semantics differ from
a naive "walk the route" model in one load-bearing way: a blocked cardinal
step (`021_Game_Character_v17.rb` `move_down`/`move_left`/`move_right`/
`move_up`) TURNS FIRST, THEN checks passability — if the destination is
blocked, the character has already turned, does not move, and stays turned.
Combined with `move_type_custom` only advancing its route index `if
@move_route.skippable or moving? or jumping?`, a non-skippable route (the
RMXP default — true of 1036 of the corpus's 1065 routes) that hits a blocked
step STALLS AT THAT INDEX FOREVER, retrying every tick. Scenery collision is
static, so this is decidable the instant it happens: the net effect in-game
is a statue facing the direction of its first permanently-blocked command.

This module answers exactly that question — "does this route stall, and if
so facing which way" — by faithfully replaying RMXP move-route execution
against a `MapPassability` oracle (reused from `npc_gfx`, not re-derived
here — CLAUDE.md §4.3 one source of truth). It does not attempt to model
every route command that could exist in principle; commands whose motion it
can't safely characterize (diagonals, move-random, toward/away-player,
forward/backward, jump, relative/random turns) are UNMODELABLE and cause an
immediate "no verdict" `RouteSim(stalled=False, ...)` return — the safe
answer, since it means the caller leaves the route alone rather than acting
on a guess (CLAUDE.md §4.5: never a silent wrong default).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .npc_gfx import (
    _DIR_VECTOR,
    _DIRECTION_TO_FACING,
    _MOVE_CODE_TO_DIR,
    _TURN_CODE_TO_DIR,
    MapPassability,
)

logger = logging.getLogger(__name__)

#: Route commands this simulator cannot safely characterize the motion of:
#: diagonals (5-8), move-random (9), toward/away-player (10/11), forward/
#: backward (12/13), jump (14), and relative/random/player-relative turns
#: (20-26). Encountering any of these means "no verdict, keep the route" —
#: the caller must not act on a guess about a stall this simulator can't see.
_UNMODELABLE_CODES = frozenset(range(5, 15)) | frozenset(range(20, 27))

#: Non-movement bookkeeping codes: no time cost, no facing/position effect.
_NEUTRAL_CODES = frozenset({41, 42})

#: Through-mode toggles.
_THROUGH_ON = 37
_THROUGH_OFF = 38

#: Bare wait: costs a step, no movement.
_CODE_WAIT = 15

#: Route terminator sentinel.
_CODE_TERMINATOR = 0

#: Hard step budget. Exceeding this means the cycle detector missed a state
#: — a bug, not a legitimately-long route — so it raises rather than
#: returning a guessed verdict (CLAUDE.md §4.5).
_STEP_BUDGET = 4096


@dataclass(frozen=True)
class RouteSim:
    """Verdict for one move-route simulation.

    `stalled` is True only for a permanent, non-skippable block — the RMXP
    statue-NPC idiom this module exists to detect. `moved` records whether
    the sim displaced at least one tile before that stall (a route that
    stalls on its very first command never moved). `stall_facing`/
    `stall_pos` are set only when `stalled` is True. `steps` counts route
    commands executed (time-costing ones) before the verdict was reached."""

    stalled: bool
    moved: bool
    stall_facing: str | None
    stall_pos: tuple[int, int] | None
    steps: int


def _no_stall(moved: bool, steps: int) -> RouteSim:
    """The "never permanently blocked" verdict — the route loops clean, ends,
    or hit a command we can't model. All three tell the caller the same thing:
    leave the route alone."""
    return RouteSim(stalled=False, moved=moved, stall_facing=None, stall_pos=None, steps=steps)


def simulate_route(page: dict, x: int, y: int, passability: MapPassability) -> RouteSim:
    """Replay `page["move_route"]` starting at map cell `(x, y)` against
    `passability`, per RMXP `Game_Character`/`Game_Event` move-route
    semantics (see module docstring). Returns the first permanent-stall
    verdict, the "route ends/loops clean" verdict, or an immediate
    unmodelable-code "no verdict" bailout — whichever comes first."""
    route = page["move_route"]
    commands = route["list"]
    skippable = bool(route["skippable"])
    repeat = bool(route["repeat"])
    direction_fix = bool(page["direction_fix"])

    facing = _DIRECTION_TO_FACING.get(page["graphic"]["direction"])
    if facing is None:
        raise ValueError(f"unknown RMXP facing direction {page['graphic']['direction']!r}")

    through = bool(page["through"])
    cur_x, cur_y = x, y
    moved = False
    steps = 0
    index = 0
    visited: set[tuple[int, int, int, int, str, bool]] = set()

    while True:
        if index >= len(commands):
            raise ValueError(
                f"move_route index {index} ran off the end of a {len(commands)}-command "
                "list without hitting the code-0 terminator — malformed route data"
            )

        state = (index, cur_x, cur_y, facing, through)
        if state in visited:
            # Revisited a state without ever stalling -> cycles forever clean.
            return _no_stall(moved, steps)
        visited.add(state)

        if steps > _STEP_BUDGET:
            raise ValueError(
                f"route_sim exceeded its {_STEP_BUDGET}-step budget without stalling or "
                "revisiting a cycle-detector state — the cycle detector missed something"
            )

        entry = commands[index]
        code = entry["code"]

        if code == _CODE_TERMINATOR:
            if repeat:
                index = 0
                continue
            return _no_stall(moved, steps)

        if code in _UNMODELABLE_CODES:
            logger.debug(
                "route_sim: unmodelable code %d at index %d — no verdict, keeping route",
                code, index,
            )
            return _no_stall(moved, steps)

        if code in _MOVE_CODE_TO_DIR:
            direction = _MOVE_CODE_TO_DIR[code]
            if not direction_fix:
                facing = direction
            dx, dy = _DIR_VECTOR[direction]
            nx, ny = cur_x + dx, cur_y + dy
            if through or passability.can_step(cur_x, cur_y, direction):
                cur_x, cur_y = nx, ny
                moved = True
                steps += 1
                index += 1
                continue
            # Blocked destination.
            if skippable:
                steps += 1
                index += 1
                continue
            return RouteSim(
                stalled=True, moved=moved, stall_facing=facing,
                stall_pos=(cur_x, cur_y), steps=steps,
            )

        if code in _TURN_CODE_TO_DIR:
            if not direction_fix:
                facing = _TURN_CODE_TO_DIR[code]
            steps += 1
            index += 1
            continue

        if code == _CODE_WAIT:
            steps += 1
            index += 1
            continue

        if code == _THROUGH_ON:
            through = True
            index += 1
            continue

        if code == _THROUGH_OFF:
            through = False
            index += 1
            continue

        if code in _NEUTRAL_CODES:
            index += 1
            continue

        # Any other neutral/bookkeeping code (speed/frequency, blend, SE,
        # script, switch toggles, ...): no time cost, no motion effect.
        index += 1
