"""Custom-route bytecode emitter — Python half of the shared contract.

SoT: ``reference/guides/custom_route_interpreter.md`` (bytecode format +
v1 scope boundary). The engine C interpreter
(``MovementType_UraniumCustomRoute``) is the other half; both cite the same
doc and neither invents encoding independently.

This module is self-contained: it does not import from or get imported by
``transpiler.py``, ``npc_gfx.py``, or ``metadata_wiring.py``. It only shares
RMXP move-route code semantics with ``transpiler.py``'s ``route_tokens``
(that path stays for cmd-209 script movement, which emits poryscript
strings, not bytecode).

Bytecode format v2: ``[idle, flags, op, op, ..., END]``. Byte 0 is the
existing idle-frames header (unchanged). Byte 1 is a new ``flags`` byte:
bit0 (``0x01``) carries the route's whole-route ``skippable`` field; all
other bits are reserved and always emitted as 0. The opcode stream starts
at byte 2. Interpreter PC starts at byte 2; ``END_LOOP`` jumps PC back to
byte 2 (bumped from byte 1 in v1).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# --- Opcodes (contract table, "Bytecode format") -----------------------

OP_END_LOOP = 0x00
OP_STEP_DOWN = 0x01
OP_STEP_LEFT = 0x02
OP_STEP_RIGHT = 0x03
OP_STEP_UP = 0x04
OP_FACE_DOWN = 0x11
OP_FACE_LEFT = 0x12
OP_FACE_RIGHT = 0x13
OP_FACE_UP = 0x14
OP_WAIT = 0x20
OP_THROUGH_ON = 0x30
OP_THROUGH_OFF = 0x31
OP_END_STOP = 0x0F

# --- Flags byte (v2 header, contract "Bytecode format") ------------------

FLAG_SKIPPABLE = 0x01

# --- RMXP move_command code -> opcode / disposition ---------------------

_STEP_OPCODE = {
    1: OP_STEP_DOWN,
    2: OP_STEP_LEFT,
    3: OP_STEP_RIGHT,
    4: OP_STEP_UP,
}

_FACE_OPCODE = {
    16: OP_FACE_DOWN,
    17: OP_FACE_LEFT,
    18: OP_FACE_RIGHT,
    19: OP_FACE_UP,
}

_CODE_WAIT = 15
_CODE_THROUGH_ON = 37
_CODE_THROUGH_OFF = 38
_CODE_TERMINATOR = 0

# Dropped from the stream but the route still plays — no movement meaning.
_DROP_CODES = frozenset(
    {
        27,
        28,  # switch on/off
        29,  # change speed
        30,  # change freq mid-route
        31,
        32,
        33,
        34,
        35,
        36,  # anim / fixed-dir toggles
        39,
        40,  # always-on-top toggles
        41,  # graphic change
        42,  # opacity
        43,  # blend mode
        44,  # SE
        45,  # script
    }
)

# Demoted — whole route falls back to the native/static path, NOT encoded.
_DEMOTE_CODES = frozenset(
    {
        5,
        6,
        7,
        8,  # diagonals
        9,  # move-random
        10,
        11,  # toward/away player
        12,
        13,  # forward/backward
        14,  # jump
        20,
        21,
        22,
        23,
        24,
        25,
        26,  # relative/random turns (incl. face-player/face-away)
    }
)


def _idle_header(move_frequency: int) -> int:
    """Per-route idle frames from move_frequency (contract: ``(40-2f)*(6-f)``)."""
    f = move_frequency
    idle = (40 - 2 * f) * (6 - f)
    return max(0, min(255, idle))


def encode_route(route: dict, move_frequency: int) -> list[int] | None:
    """Encode an RMXP move_route dict into v2 custom-route bytecode.

    ``route`` is the RMXP move_route shape: ``{"repeat": bool,
    "skippable": bool, "list": [{"code": int, "parameters": [...]}]}``.
    ``move_frequency`` is the page's move_frequency (1-6), used for the idle
    header byte.

    Returns ``[idle, flags, op, op, ..., END]`` on success, or ``None`` if the
    route must be DEMOTED to the native/static path: an out-of-scope command
    (diagonals, move-random, toward/away-player, forward/backward, jump,
    relative/random turns), an unrecognized code (fail-safe), or a route that
    reduces to zero real ops once no-op codes are dropped (a routeless mover
    is just a facing — not this module's job).

    Byte 0 is the idle header (unchanged from v1). Byte 1 is the new
    ``flags`` byte: bit0 (``0x01``) mirrors ``route["skippable"]``, all other
    bits reserved as 0. The opcode stream (and END_LOOP/END_STOP target)
    starts at byte 2.

    Raises only on a structurally broken ``route`` (e.g. missing ``"list"``
    or ``"skippable"``); malformed-but-plausible input (unknown codes,
    missing wait params) demotes instead of raising.
    """
    commands = route["list"]
    skippable = route["skippable"]

    ops: list[int] = []
    for command in commands:
        code = command["code"]
        if code == _CODE_TERMINATOR:
            break

        if code in _STEP_OPCODE:
            ops.append(_STEP_OPCODE[code])
        elif code in _FACE_OPCODE:
            ops.append(_FACE_OPCODE[code])
        elif code == _CODE_WAIT:
            params = command.get("parameters") or []
            if not params:
                logger.warning("custom route: wait command missing parameters, demoting")
                return None
            frames = max(0, min(255, params[0] * 2 - 1))
            ops.append(OP_WAIT)
            ops.append(frames)
        elif code == _CODE_THROUGH_ON:
            ops.append(OP_THROUGH_ON)
        elif code == _CODE_THROUGH_OFF:
            ops.append(OP_THROUGH_OFF)
        elif code in _DROP_CODES:
            continue
        elif code in _DEMOTE_CODES:
            logger.info("custom route: out-of-scope code %d, demoting", code)
            return None
        else:
            logger.warning("custom route: unknown code %d, demoting", code)
            return None

    if not ops:
        return None

    end = OP_END_LOOP if route.get("repeat") else OP_END_STOP
    flags = FLAG_SKIPPABLE if skippable else 0
    return [_idle_header(move_frequency), flags] + ops + [end]


# --- Route registry (dedup seam) ---------------------------------------

# Route ids ride ObjectEventTemplate.trainerRange_berryTreeId (u8): 1..255,
# id 0 reserved for "no route" / the NULL index-0 sentinel in sUraniumRoutes[].
MAX_ROUTE_ID = 255


class RouteRegistry:
    """Dedup identical route bytecode across a slice into 1-based route ids.

    One id assignment, two consumers: each object's
    ``trainer_sight_or_berry_tree_id`` in map.json and the gen.h
    ``sUraniumRoutes[]`` index table. They must agree, so both read this
    registry. Id 0 is reserved (no route / NULL sentinel). Fail-loud past the
    u8 ceiling — the field can't carry it.
    """

    def __init__(self) -> None:
        self._ids: dict[tuple[int, ...], int] = {}
        self._routes: list[tuple[int, ...]] = []

    def intern(self, bytecode: list[int] | tuple[int, ...]) -> int:
        """Return the 1-based id for ``bytecode``, assigning a new one if unseen."""
        key = tuple(bytecode)
        existing = self._ids.get(key)
        if existing is not None:
            return existing
        route_id = len(self._routes) + 1
        if route_id > MAX_ROUTE_ID:
            raise ValueError(
                f"custom-route registry overflow: >{MAX_ROUTE_ID} distinct routes "
                "won't fit trainerRange_berryTreeId (u8)"
            )
        self._routes.append(key)
        self._ids[key] = route_id
        return route_id

    def routes(self) -> list[tuple[int, ...]]:
        """Distinct routes in id order; 0-based index ``i`` has route id ``i + 1``."""
        return list(self._routes)

    def __len__(self) -> int:
        return len(self._routes)
