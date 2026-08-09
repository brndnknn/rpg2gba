"""Phase 5 §5.3 support — Uranium NPC graphic sheet -> pokeemerald OBJ_EVENT_GFX_*.

Uranium places NPCs by RMXP "character sheet" filename (``graphic.character_name``
on a page, e.g. ``"HGSS_000"``, ``"PU-Chyinmunk"``); pokeemerald object_events need
an ``OBJ_EVENT_GFX_*`` constant. This module is the single source of truth (CLAUDE.md
§4.3) for that mapping (`reference/npc_gfx_map.json`, validated against the fork's
real constants — CLAUDE.md §4.7), plus the RMXP boot-state semantics
`metadata_wiring` needs to decide WHICH of an event's pages is even active before it
can ask "what's this event's graphic":

  - `select_boot_page` — RMXP shows the highest-index page whose condition holds at
    boot (all switches off, all variables 0, all self-switches off).
  - `movement_spec_for` — RMXP `move_type` (+ `graphic.direction` for the fixed
    case, + a `move_route` classifier for the custom case) -> a `MovementSpec`
    (pokeemerald `MOVEMENT_TYPE_*` plus `movement_range_x`/`_y`). Recovers real
    patrol/look/pace behavior from Uranium's move_type 3 repeating routes
    instead of freezing every NPC in place; a route this can't represent
    natively is demoted to a static facing (`MovementSpec.demoted` set, logged
    loud by the caller, never silent).
  - `is_door_sheet` — the two Uranium door-tile sheet families, which are STRIPPED
    (never emitted as an object_event; a warp_event/tileset door tile is what
    actually makes the door work) rather than mapped to a gfx constant.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from ..pbs_converter._naming import to_constant
from .route_bytecode import encode_route

logger = logging.getLogger(__name__)

DEFAULT_NPC_GFX_MAP = Path("reference/npc_gfx_map.json")

#: Prefix for every minted Uranium NPC gfx constant (mirrors `_naming.to_constant`
#: usage elsewhere: PREFIX + normalized name -> PREFIX_NORMALIZED_NAME).
GFX_PREFIX = "OBJ_EVENT_GFX_URANIUM"

# RMXP page.move_type values (Essentials/RGSS EventPage#move_type).
MOVE_TYPE_FIXED = 0
MOVE_TYPE_RANDOM = 1
MOVE_TYPE_APPROACH = 2
MOVE_TYPE_CUSTOM = 3

#: pokeemerald movement type for a bytecode-interpreted Uranium custom route
#: (`reference/guides/custom_route_interpreter.md`). `_spec_for_custom_route`
#: assigns this, ahead of the native/static classifier below, whenever
#: `route_bytecode.encode_route` can encode the whole move_route; routes it
#: demotes (diagonals, move-random, toward/away-player, jump, unknown/empty)
#: fall through to the existing classifier unchanged.
MOVEMENT_TYPE_CUSTOM_ROUTE = "MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE"

# RMXP graphic.direction values -> the facing suffix on MOVEMENT_TYPE_FACE_*.
_DIRECTION_TO_FACING = {2: "DOWN", 4: "LEFT", 6: "RIGHT", 8: "UP"}

# RMXP move_route command codes (Game_Character move_type 3 == custom route;
# RPG::MoveCommand#code — see `movement_spec_for`'s docstring for the full
# classification these feed). A TRANSLATION command displaces the sprite, a
# TURN command only reorients it, code 15 is a bare wait, and everything >= 27
# (switches, speed/frequency, graphic swap, opacity, blend, SE, script) is
# neutral — irrelevant to movement and never inspected below.
ROUTE_CODE_TRANSLATION = frozenset(range(1, 15))  # 1 down .. 14 jump
ROUTE_CODE_WAIT = 15
ROUTE_CODE_TURN = frozenset(range(16, 27))  # 16 down..19 up, 20..26 relative/random/player-relative
ROUTE_CODE_TURN_RELATIVE = frozenset(range(20, 27))  # no fixed direction -> LOOK_AROUND tier
ROUTE_CODE_HORIZONTAL = frozenset({2, 3})  # move left, move right
ROUTE_CODE_VERTICAL = frozenset({1, 4})  # move down, move up
ROUTE_CODE_RANDOM_MOVE = 9

# Absolute-turn codes -> the direction they face (16..19 only; 20..26 are the
# relative/random/player-relative turns folded into ROUTE_CODE_TURN_RELATIVE).
_TURN_CODE_TO_DIR = {16: "DOWN", 17: "LEFT", 18: "RIGHT", 19: "UP"}

# RMXP cardinal move codes -> direction name + unit vector (RMXP y grows DOWN,
# matching pokeemerald map coords).
_MOVE_CODE_TO_DIR = {1: "DOWN", 2: "LEFT", 3: "RIGHT", 4: "UP"}
_DIR_VECTOR = {"DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1)}

# pokeemerald MOVEMENT_TYPE_WALK_SEQUENCE_* loop-closure quirks, transcribed from
# the fork's MovementType_WalkSequence<Dirs>_Step1 bodies (event_object_movement.c
# ~5178-5460): each sequence advances early from leg `index` to `index + 1` when
# the object is back on its initial column ("x") / row ("y"). Together with the
# shared MoveNextDirectionInSequence rules (reset to leg 0 when at leg 3 AND back
# at the initial coords; advance a leg on COLLISION_OUTSIDE_RANGE), this is the
# complete obstacle-free automaton `_simulate_walk_sequence` replays.
# `tests/test_npc_gfx.py` re-derives this table from the fork source (CLAUDE.md
# §4.7 — the C file is the source of truth, this dict is a pinned copy).
_WALK_SEQUENCE_QUIRKS: dict[tuple[str, str, str, str], tuple[int, str]] = {
    ("UP", "RIGHT", "LEFT", "DOWN"): (2, "x"),
    ("RIGHT", "LEFT", "DOWN", "UP"): (1, "x"),
    ("DOWN", "UP", "RIGHT", "LEFT"): (1, "y"),
    ("LEFT", "DOWN", "UP", "RIGHT"): (2, "y"),
    ("UP", "LEFT", "RIGHT", "DOWN"): (2, "x"),
    ("LEFT", "RIGHT", "DOWN", "UP"): (1, "x"),
    ("DOWN", "UP", "LEFT", "RIGHT"): (1, "y"),
    ("RIGHT", "DOWN", "UP", "LEFT"): (2, "y"),
    ("LEFT", "UP", "DOWN", "RIGHT"): (2, "y"),
    ("UP", "DOWN", "RIGHT", "LEFT"): (1, "y"),
    ("RIGHT", "LEFT", "UP", "DOWN"): (1, "x"),
    ("DOWN", "RIGHT", "LEFT", "UP"): (2, "x"),
    ("RIGHT", "UP", "DOWN", "LEFT"): (2, "y"),
    ("UP", "DOWN", "LEFT", "RIGHT"): (1, "y"),
    ("LEFT", "RIGHT", "UP", "DOWN"): (1, "x"),
    ("DOWN", "LEFT", "RIGHT", "UP"): (2, "x"),
    ("UP", "LEFT", "DOWN", "RIGHT"): (2, "y"),
    ("DOWN", "RIGHT", "UP", "LEFT"): (2, "y"),
    ("LEFT", "DOWN", "RIGHT", "UP"): (2, "x"),
    ("RIGHT", "UP", "LEFT", "DOWN"): (2, "x"),
    ("UP", "RIGHT", "DOWN", "LEFT"): (2, "y"),
    ("DOWN", "LEFT", "UP", "RIGHT"): (2, "y"),
    ("LEFT", "UP", "RIGHT", "DOWN"): (2, "x"),
    ("RIGHT", "DOWN", "LEFT", "UP"): (2, "x"),
}

# RMXP directional passage bits (Game_Map#passable?): moving down/left/right/up
# is blocked by a tile whose passage has the matching bit set.
_RMXP_PASSAGE_BITS = {"DOWN": 0x01, "LEFT": 0x02, "RIGHT": 0x04, "UP": 0x08}

# The direction a step's REVERSE-side check consults (021_Game_Character_v17.rb
# `passableEx?` calls `Game_Map#passable?(new_x, new_y, 10 - d, self)` — RMXP
# direction codes 2/4/6/8 for down/left/right/up satisfy `10 - d` = the
# opposite code in every case: 10-2=8, 10-4=6, 10-6=4, 10-8=2).
_REVERSE_FACING = {"DOWN": "UP", "UP": "DOWN", "LEFT": "RIGHT", "RIGHT": "LEFT"}

# Two/three-direction FACE_* combos the fork defines
# (engine/include/constants/event_object_movement.h), keyed by the exact
# direction set `_look_spec_for` can produce — every non-empty proper subset
# of {DOWN, LEFT, RIGHT, UP} that isn't a single direction or all four (those
# have their own branches: MOVEMENT_TYPE_FACE_<DIR> and
# MOVEMENT_TYPE_LOOK_AROUND respectively).
_TURN_COMBO_TO_MOVEMENT_TYPE: dict[frozenset[str], str] = {
    frozenset({"DOWN", "UP"}): "MOVEMENT_TYPE_FACE_DOWN_AND_UP",
    frozenset({"LEFT", "RIGHT"}): "MOVEMENT_TYPE_FACE_LEFT_AND_RIGHT",
    frozenset({"UP", "LEFT"}): "MOVEMENT_TYPE_FACE_UP_AND_LEFT",
    frozenset({"UP", "RIGHT"}): "MOVEMENT_TYPE_FACE_UP_AND_RIGHT",
    frozenset({"DOWN", "LEFT"}): "MOVEMENT_TYPE_FACE_DOWN_AND_LEFT",
    frozenset({"DOWN", "RIGHT"}): "MOVEMENT_TYPE_FACE_DOWN_AND_RIGHT",
    frozenset({"DOWN", "UP", "LEFT"}): "MOVEMENT_TYPE_FACE_DOWN_UP_AND_LEFT",
    frozenset({"DOWN", "UP", "RIGHT"}): "MOVEMENT_TYPE_FACE_DOWN_UP_AND_RIGHT",
    frozenset({"UP", "LEFT", "RIGHT"}): "MOVEMENT_TYPE_FACE_UP_LEFT_AND_RIGHT",
    frozenset({"DOWN", "LEFT", "RIGHT"}): "MOVEMENT_TYPE_FACE_DOWN_LEFT_AND_RIGHT",
}

# Uranium's two door-tile sheet families (case-insensitive prefix match).
_DOOR_SHEET_PREFIXES = ("pu-doors", "fkdoors")

_DEFINE_RE = re.compile(r"^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)")


def gfx_constant_for_sheet(sheet_stem: str) -> str:
    """Deterministic ``OBJ_EVENT_GFX_URANIUM_*`` constant for an RMXP character
    sheet stem (the `character_name` string, e.g. ``"HGSS_000"``,
    ``"PU-Chyinmunk"``). Routes through `_naming.to_constant`, the same
    normalizer every Phase 2 converter uses (CLAUDE.md §4.3 — one normalizer,
    not a bespoke regex here)."""
    return to_constant(GFX_PREFIX, sheet_stem)


def _collect_header_defines(header_paths: list[Path]) -> set[str]:
    """Every ``#define NAME`` identifier across `header_paths`. Fails loud if a
    header doesn't exist — a missing header means we CAN'T validate, which is not
    the same as "nothing to validate" (CLAUDE.md §4.5)."""
    names: set[str] = set()
    for path in header_paths:
        if not path.is_file():
            raise FileNotFoundError(f"npc gfx header not found: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _DEFINE_RE.match(line)
            if m:
                names.add(m.group(1))
    return names


def load_npc_gfx_map(json_path: Path, header_paths: list[Path]) -> dict[str, str]:
    """Load + validate `reference/npc_gfx_map.json`: character_name -> gfx
    constant, every constant checked against real ``#define``s in `header_paths`
    (CLAUDE.md §4.7 forward gate — an invented constant fails loud here, not at
    `make modern`). Also fails loud on a duplicate JSON key or an entry missing
    the required ``"gfx"`` field; ``"fallback"``/``"note"`` are informational and
    unchecked."""
    if not json_path.is_file():
        raise FileNotFoundError(f"npc gfx map not found: {json_path}")
    if not header_paths:
        raise ValueError("load_npc_gfx_map requires at least one header_paths entry")

    def _dict_no_dupes(pairs: list[tuple[str, object]]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"{json_path}: duplicate key {key!r}")
            out[key] = value
        return out

    raw = json.loads(
        json_path.read_text(encoding="utf-8"), object_pairs_hook=_dict_no_dupes
    )
    defines = _collect_header_defines(header_paths)

    result: dict[str, str] = {}
    for character_name, entry in raw.items():
        if "gfx" not in entry:
            raise ValueError(f"{json_path}: entry {character_name!r} missing required 'gfx' field")
        gfx = entry["gfx"]
        if gfx not in defines:
            raise ValueError(
                f"{json_path}: entry {character_name!r} gfx constant {gfx!r} is not "
                f"#define'd in any of {[str(p) for p in header_paths]}"
            )
        result[character_name] = gfx
    return result


def load_npc_gfx_states(
    json_path: Path, header_paths: list[Path]
) -> dict[str, dict[tuple[int, int], str]]:
    """The optional per-STATE half of the same map: character_name ->
    {(RMXP direction, RMXP pattern): gfx constant}, for sheets that carry more
    than one selectable visual state.

    A "state" is what an RMXP code-41 Change Graphic selects when it names a
    sheet the event is ALREADY wearing and moves only `direction`/`pattern` —
    how RMXP animates a static prop. The sprite pass emits one
    `ObjectEventGraphicsInfo` (and one `OBJ_EVENT_GFX_URANIUM_*` id) per state
    for such a sheet, so the swap converts to an ordinary gfx swap; see
    `graphics/sprite_emit.py`. Sheets with no ``"states"`` field are absent
    from the returned dict entirely (not present with an empty value), so a
    caller can tell "no states" from "state not in the art".

    JSON shape: ``"states": {"2,1": "OBJ_EVENT_GFX_URANIUM_X_D2P1", ...}`` —
    the key is ``"<direction>,<pattern>"``. Every constant is checked against
    real ``#define``s exactly like `load_npc_gfx_map`'s (CLAUDE.md §4.7
    forward gate), and a malformed key fails loud rather than being skipped."""
    if not json_path.is_file():
        raise FileNotFoundError(f"npc gfx map not found: {json_path}")
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    defines = _collect_header_defines(header_paths)

    out: dict[str, dict[tuple[int, int], str]] = {}
    for character_name, entry in raw.items():
        states = entry.get("states")
        if not states:
            continue
        parsed: dict[tuple[int, int], str] = {}
        for key, gfx in states.items():
            try:
                direction, pattern = (int(part) for part in str(key).split(","))
            except ValueError as exc:
                raise ValueError(
                    f"{json_path}: entry {character_name!r} has malformed state key "
                    f"{key!r}; expected \"<direction>,<pattern>\""
                ) from exc
            if direction not in _DIRECTION_TO_FACING:
                raise ValueError(
                    f"{json_path}: entry {character_name!r} state key {key!r} has "
                    f"direction {direction}, not an RMXP direction code (2/4/6/8)"
                )
            if gfx not in defines:
                raise ValueError(
                    f"{json_path}: entry {character_name!r} state {key!r} gfx constant "
                    f"{gfx!r} is not #define'd in any of "
                    f"{[str(p) for p in header_paths]}"
                )
            parsed[(direction, pattern)] = gfx
        out[character_name] = parsed
    return out


def select_boot_page(event: dict) -> dict | None:
    """The page RMXP displays at BOOT (all switches off, all variables 0, all
    self-switches off): the highest-index page whose condition holds, or `None`
    if every page is gated off at boot (e.g. an event that only appears after a
    story switch flips).

    RMXP semantics: a page's condition holds at boot iff it has no switch1/
    switch2/self-switch gate (those all read as OFF at boot) AND either it has no
    variable gate or the variable gate is ``value <= 0`` (the RMXP test is
    ``game_variables[id] >= value``; every variable reads 0 at boot, so
    ``0 >= value`` holds iff ``value <= 0``)."""
    for page in reversed(event["pages"]):
        cond = page["condition"]
        if cond.get("switch1_valid") or cond.get("switch2_valid") or cond.get("self_switch_valid"):
            continue
        if cond.get("variable_valid") and cond.get("variable_value", 0) > 0:
            continue
        return page
    return None


@dataclass(frozen=True)
class MovementSpec:
    """The pokeemerald movement wiring for one placed object_event:
    `movement_type` (a `MOVEMENT_TYPE_*` constant) plus its `movement_range_x`/
    `_y`. `demoted` is `None` for every legitimate static/looking/wandering/
    patrolling classification; it carries a short human-readable reason only
    when `movement_spec_for` had to fall back a translating custom route to a
    static facing because pokeemerald has no native movement type for it
    (CLAUDE.md §4.5 — never silent; see `movement_spec_for`'s docstring case h
    and `metadata_wiring.build_object_events`, which logs every non-`None`
    `demoted` loud).

    Walk-sequence loops (case g2) also carry:

    - `anchor_dx`/`anchor_dy` — spawn shift the caller must apply to the
      object's placement. pokeemerald's WALK_SEQUENCE loop closes at the
      object's INITIAL coords, which must be a corner of the loop; when the
      RMXP spawn sits mid-leg the object is placed at the nearest loop corner
      instead (never more than the loop's own extent, always a cell the RMXP
      route itself walks).
    - `path_cells` — every (dx, dy) offset FROM THE RMXP SPAWN the loop
      visits, for callers that can check map passability: a loop crossing a
      blocked cell would stall walking-in-place forever in-engine (RMXP
      routes may cross such cells via `through`), so
      `metadata_wiring.build_object_events` demotes those loud.

    `route_bytecode` is set instead of the above when `movement_type ==
    MOVEMENT_TYPE_CUSTOM_ROUTE`: the `encode_route`-produced byte sequence
    the engine's `MovementType_UraniumCustomRoute` interpreter plays back
    directly (`reference/guides/custom_route_interpreter.md`). `None` for
    every other movement type."""

    movement_type: str
    range_x: int = 0
    range_y: int = 0
    demoted: str | None = None
    anchor_dx: int = 0
    anchor_dy: int = 0
    path_cells: tuple[tuple[int, int], ...] = ()
    route_bytecode: tuple[int, ...] | None = None


def movement_spec_for(page: dict, *, allow_custom_route: bool = True) -> MovementSpec:
    """The pokeemerald movement (`MOVEMENT_TYPE_*` + `movement_range_x`/`_y`)
    for a page's RMXP `move_type`, recovering the patrol/look/pace behavior
    Uranium actually encodes in move_type 3 repeating `move_route`s instead of
    freezing every NPC in place (the corpus-census finding — SLICE1_TODO #12 —
    this function exists to fix; the old `movement_type_for` collapsed every
    move_type 0/2/3 page to a static facing).

    Tiering by `page["move_type"]`:

    - 0 (fixed) -> static ``MOVEMENT_TYPE_FACE_<DIR>`` from `graphic.direction`
      (2/4/6/8 -> DOWN/LEFT/RIGHT/UP). Unchanged from the old function.
    - 1 (random) -> ``MOVEMENT_TYPE_WANDER_AROUND`` with `range_x = range_y = 0`.
      Range 0 is what we always emit for a "no explicit range" RMXP random
      walker (Essentials' `move_type_random` is passability-bounded only, no
      stored radius) — but verify against the fork before treating that as
      "unrestricted" (CLAUDE.md §4.7): `InitObjectEventStateFromTemplate`
      (event_object_movement.c) bumps a spawned object's rangeX/rangeY from 0
      up to 1 for every movement type in `sMovementTypeHasRange`, and
      WANDER_AROUND is one of them — so a (0, 0) WANDER_AROUND actually runs
      as a tight radius-1 wander around the spawn tile at runtime, not a
      literal "no bound" mode. It is still the closest native analog
      available and the value this module always emits for move_type 1.
    - 2 (approach player) -> raises `ValueError`. No native pokeemerald
      analog and zero occurrences in the Uranium corpus (verified) — fail
      loud rather than guess at a substitute.
    - 3 (custom route) -> classifies `page["move_route"]` (below). `KeyError`
      propagates if the page has no `move_route` at all — a move_type 3 page
      always carries one in the RMXP data, so a missing key means malformed
      input, not "nothing to do".

    move_type 3 is INTERPRETER-FIRST: `_spec_for_custom_route` tries
    `route_bytecode.encode_route` on the whole route before any of cases a-h
    below; an encodable route (most cardinal steps/turns/through-toggles)
    returns `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` with `route_bytecode` set,
    played back verbatim by the engine's bytecode interpreter — no native
    approximation needed. Cases a-h are the fallback for what `encode_route`
    demotes (see its docstring): diagonals, move-random, toward/away-player,
    forward/backward, jump, relative/random turns, or an unrecognized code.

    move_type 3 classification (checked in this order; `codes` is the route's
    command codes with the trailing code-0 sentinel entry stripped):

    a. `move_route["repeat"]` is False -> static FACE_<dir>. The route plays
       once at boot and then the NPC stands — not a demotion, just what a
       one-shot route does.
    b. `repeat` True: partition `codes` into TRANSLATION (`ROUTE_CODE_
       TRANSLATION`, 1..14 — 4 cardinal directions, 4 diagonals, move-random,
       toward/away-player, forward, backward, jump: every command that
       displaces the sprite), TURN (`ROUTE_CODE_TURN`, 16..26 — 16..19 the
       four absolute turns, 20..26 relative/random/player-relative), WAIT
       (code 15), and neutral (27+ — switches, speed/frequency, graphic swap,
       opacity, blend, SE, script; never inspected).
    c. No TRANSLATION and no TURN -> static FACE_<dir>. A loop of pure waits
       and neutral commands (graphic-flicker props, SE stingers) — not a
       demotion.
    d. TURN codes present, no TRANSLATION -> a "look" variant; the NPC never
       walks. Map each absolute code to a direction (16/17/18/19 ->
       DOWN/LEFT/RIGHT/UP); if ANY relative/random/player-relative code
       (20..26, `ROUTE_CODE_TURN_RELATIVE`) appears, treat the direction set
       as all four regardless of what else is present (those turns have no
       fixed direction of their own). The resulting set: all four ->
       ``MOVEMENT_TYPE_LOOK_AROUND``; one direction ->
       ``MOVEMENT_TYPE_FACE_<that direction>`` (the turn's own direction, NOT
       the page's `graphic.direction`); two or three directions -> the exact
       fork combo constant (`_TURN_COMBO_TO_MOVEMENT_TYPE`:
       ``MOVEMENT_TYPE_FACE_DOWN_AND_UP``, `..._LEFT_AND_RIGHT`, and the
       eight other two/three-direction combos pokeemerald defines).
    e. Both TRANSLATION and TURN nonempty -> demoted (case h) — "translation
       mixed with turns" has no native equivalent (a route can walk or spin
       in place, not both).
    f. TRANSLATION == `{ROUTE_CODE_RANDOM_MOVE}` only (a bare move-random
       loop; waits/neutral commands don't disqualify it) ->
       ``MOVEMENT_TYPE_WANDER_AROUND`` (0, 0), same as move_type 1.
    g. TRANSLATION is a non-empty subset of `ROUTE_CODE_HORIZONTAL` ({left,
       right}) or of `ROUTE_CODE_VERTICAL` ({down, up}) -> simulate walking
       that one axis over a single pass of the route (only the axis's own two
       codes move the position; every other code — waits, neutrals — is a
       no-op): if the position hasn't returned to 0 by the end of the pass,
       the route drifts a little further every loop and can't be represented
       as a bounded pokeemerald patrol -> demoted (case h), reason naming the
       net drift. Otherwise the patrol's span is `max position - min
       position` seen during the pass (the starting 0 included, so a route
       that never returns toward 0 before drifting back still counts its
       farthest excursion); `range_{x,y} = max(1, ceil(span / 2))` centers a
       symmetric pokeemerald patrol on the RMXP route's (one-sided) midpoint.
       A WAIT code anywhere in the route, or `move_frequency` below 6 (RMXP
       idle-gates EVERY route command by `(40-2f)(6-f)` frames — only freq 6
       is gap-free), means the patrol pauses between steps ->
       ``MOVEMENT_TYPE_WANDER_LEFT_AND_RIGHT`` / `..._UP_AND_DOWN`; freq-6
       wait-free -> continuous ``MOVEMENT_TYPE_WALK_LEFT_AND_RIGHT`` /
       `..._UP_AND_DOWN`.
    g2. TRANSLATION all cardinal, tracing a CLOSED four-leg loop over all
       four directions -> the exact ``MOVEMENT_TYPE_WALK_SEQUENCE_*`` patrol,
       validated by replaying pokeemerald's automaton (`_spec_for_loop_route`
       — rectangle rings and out-and-back walks; may carry an `anchor_dx`/
       `anchor_dy` spawn shift and always carries `path_cells` for the
       caller's map-passability gate).
    h. Everything else that translates — TRANSLATION mixing both axes, a
       diagonal (5..8), toward/away-player/forward/backward/jump (10..14)
       alone or mixed with other translation codes, a net-drift loop, or
       translation mixed with turns (case e above) — demotes to static
       FACE_<dir> with `MovementSpec.demoted` set to a short reason naming
       the offending codes. This is a deliberate v1 fidelity cut (decorative
       patrol shapes pokeemerald's object movement can't reproduce), NOT an
       error: the event is still placed, just standing instead of
       patrolling. Callers must surface `demoted` loudly, never silently —
       see `metadata_wiring.build_object_events`.

    Fails loud (`ValueError`) on an unknown `move_type` or an unknown
    `graphic.direction` in any facing branch — no silent default movement
    (CLAUDE.md §4.5).

    `allow_custom_route` (keyword-only, default `True` — no existing caller's
    behavior changes) gates whether move_type 3's INTERPRETER-FIRST
    `encode_route` attempt runs at all. `False` skips that attempt entirely
    and goes straight to the native/static classification (cases a-h) —
    exactly the path already taken when `encode_route` itself returns `None`.
    This exists for callers that structurally cannot use
    `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` even though the interpreter could
    encode the route (`metadata_wiring.build_object_events`'s battle-trainer
    branch: that movement type rides the same object_event template field as
    the trainer's sight radius). The native approximation this falls back to
    is lossy relative to the RMXP route — it can lose waits, speed/frequency
    pacing, and exact throw distance — but for a caller that has ruled out
    the interpreter that trade-off is accepted; see the call site."""
    move_type = page["move_type"]

    if move_type == MOVE_TYPE_FIXED:
        return MovementSpec(_face_from_graphic(page))

    if move_type == MOVE_TYPE_RANDOM:
        return MovementSpec("MOVEMENT_TYPE_WANDER_AROUND", 0, 0)

    if move_type == MOVE_TYPE_APPROACH:
        raise ValueError(
            "RMXP move_type 2 (approach player) has no native pokeemerald "
            "analog and is unused in the Uranium corpus"
        )

    if move_type != MOVE_TYPE_CUSTOM:
        raise ValueError(f"unknown RMXP move_type {move_type!r}")

    return _spec_for_custom_route(page, allow_custom_route=allow_custom_route)


def _face_from_graphic(page: dict) -> str:
    """``MOVEMENT_TYPE_FACE_<DIR>`` from `page["graphic"]["direction"]`.
    Fails loud on an unknown direction (CLAUDE.md §4.5)."""
    direction = page["graphic"]["direction"]
    facing = _DIRECTION_TO_FACING.get(direction)
    if facing is None:
        raise ValueError(f"unknown RMXP facing direction {direction!r}")
    return f"MOVEMENT_TYPE_FACE_{facing}"


def _spec_for_custom_route(page: dict, *, allow_custom_route: bool = True) -> MovementSpec:
    """move_type 3 classification. `page["move_route"]` (`KeyError` propagates
    if absent) always carries ``"repeat"`` and a ``"list"`` of ``{"code": int,
    "parameters": [...]}`` entries ending in a code-0 sentinel.

    INTERPRETER-FIRST: before any of the native/static classification below,
    try `route_bytecode.encode_route` on the whole route — unless
    `allow_custom_route` is `False`, in which case this attempt is skipped
    entirely and classification proceeds straight to cases a-h below, exactly
    as if `encode_route` had returned `None` (see `movement_spec_for`'s
    docstring for why a caller would pass `False`). When the attempt does
    run: success (not `None`) means the engine's bytecode interpreter
    (`MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`) can play the route verbatim —
    deterministic pacing and arbitrary step/turn/through sequences the
    native classifier below can't (or can only approximate) — so that wins
    outright, no fall-through. `encode_route` returns `None` only for the v1
    demote set (diagonals, move-random, toward/away-player, forward/
    backward, jump, relative/random turns, unknown codes) or a route with no
    real ops once no-op codes are dropped; only THEN do cases a-h below run,
    completely unchanged, as the fallback for what the interpreter can't
    encode (`reference/guides/custom_route_interpreter.md`)."""
    route = page["move_route"]

    bytecode = encode_route(route, page["move_frequency"]) if allow_custom_route else None
    if bytecode is not None:
        return MovementSpec(MOVEMENT_TYPE_CUSTOM_ROUTE, route_bytecode=tuple(bytecode))

    static_face = MovementSpec(_face_from_graphic(page))

    if not route["repeat"]:
        return static_face  # (a) one-shot route, then stands — not a demotion

    codes = [entry["code"] for entry in route["list"] if entry["code"] != 0]
    translation = [c for c in codes if c in ROUTE_CODE_TRANSLATION]
    turns = [c for c in codes if c in ROUTE_CODE_TURN]
    has_wait = ROUTE_CODE_WAIT in codes

    if not translation and not turns:
        return static_face  # (c) flicker/wait-only prop loop — not a demotion

    if not translation:
        return MovementSpec(_look_spec_for(turns))  # (d) turn-only look variant

    if turns:
        # (e) -> (h): a route that both walks and spins has no native analog.
        return _demote(page, translation + turns, "custom route translates and turns")

    translation_set = set(translation)

    if translation_set == {ROUTE_CODE_RANDOM_MOVE}:
        return MovementSpec("MOVEMENT_TYPE_WANDER_AROUND", 0, 0)  # (f)

    if translation_set <= ROUTE_CODE_HORIZONTAL:
        return _spec_for_axis(  # (g), horizontal
            page, codes, translation, plus_code=3, minus_code=2,
            wander_type="MOVEMENT_TYPE_WANDER_LEFT_AND_RIGHT",
            walk_type="MOVEMENT_TYPE_WALK_LEFT_AND_RIGHT",
            has_wait=has_wait, is_horizontal=True,
        )

    if translation_set <= ROUTE_CODE_VERTICAL:
        return _spec_for_axis(  # (g), vertical
            page, codes, translation, plus_code=1, minus_code=4,
            wander_type="MOVEMENT_TYPE_WANDER_UP_AND_DOWN",
            walk_type="MOVEMENT_TYPE_WALK_UP_AND_DOWN",
            has_wait=has_wait, is_horizontal=False,
        )

    spec = _spec_for_loop_route(page, translation)  # (g2), 4-leg closed loop
    if spec is not None:
        return spec

    # (h): mixed axes, diagonals, toward/away-player, forward/backward, jump.
    return _demote(page, translation, "unsupported custom-route translation code(s)")


def _spec_for_axis(
    page: dict,
    codes: list[int],
    translation: list[int],
    *,
    plus_code: int,
    minus_code: int,
    wander_type: str,
    walk_type: str,
    has_wait: bool,
    is_horizontal: bool,
) -> MovementSpec:
    """Simulate one pass of `codes` along a single axis (`plus_code` advances
    the position by +1, `minus_code` by -1, everything else is a no-op) and
    turn the result into a WANDER_/WALK_ patrol, or a net-drift demotion — see
    `movement_spec_for` docstring case (g)."""
    net, lo, hi = _walk_axis(codes, plus_code, minus_code)
    if net != 0:
        return _demote(
            page, translation,
            f"custom route nets a {net:+d}-tile drift over one move_route pass",
        )
    span = hi - lo
    magnitude = max(1, -(-span // 2))  # ceil(span / 2) via negated floor division
    # RMXP gates EVERY route command behind the page's move_frequency idle timer
    # ((40 - 2f)(6 - f) frames, 021_Game_Character_v17.rb) — only frequency 6 is
    # gap-free. So a pacing loop pauses between steps unless freq is 6, explicit
    # code-15 waits or not; WANDER_* (steps with random 32..128-frame pauses) is
    # the faithful engine analog, WALK_* (continuous) only for freq-6 wait-free
    # routes.
    paused = has_wait or page["move_frequency"] < 6
    movement_type = wander_type if paused else walk_type
    if is_horizontal:
        return MovementSpec(movement_type, range_x=magnitude, range_y=0)
    return MovementSpec(movement_type, range_x=0, range_y=magnitude)


def _spec_for_loop_route(page: dict, translation: list[int]) -> MovementSpec | None:
    """move_type 3 classification case (g2): a repeating route whose cardinal
    moves trace a CLOSED loop of exactly four cyclic legs covering all four
    directions -> the matching ``MOVEMENT_TYPE_WALK_SEQUENCE_<D1>_<D2>_<D3>_
    <D4>`` patrol (rectangle rings like Map032 EV008's town-square Chyinmunk,
    out-and-back "L" walks like EV048/EV072/EV073).

    pokeemerald's walk-sequence automaton is leg-per-direction with three
    advance rules (range boundary / per-type initial-row-or-column quirk /
    at-anchor reset — see `_WALK_SEQUENCE_QUIRKS`), and its loop closes at the
    object's INITIAL coords, so the candidate is only accepted when
    `_simulate_walk_sequence` replays the automaton (obstacle-free) and the
    traced cycle reproduces the RMXP route's cell sequence exactly, twice
    over. The anchor must be a leg corner; when the RMXP spawn isn't one
    (EV008 spawns one tile below its ring's top-left corner), the accepted
    spec carries the spawn shift in `anchor_dx`/`anchor_dy`.

    Returns `None` (caller falls through to the case-h demotion) when the
    moves aren't all cardinal, the loop doesn't close, the cyclic legs aren't
    exactly the four directions, or no rotation survives simulation.

    Cadence note: walk sequences are continuous (no idle gate), so a
    sub-frequency-6 loop loses its RMXP between-step pauses — a deliberate
    fidelity cut in favor of the patrol shape (no paused sequence type
    exists in the fork)."""
    if any(c not in _MOVE_CODE_TO_DIR for c in translation):
        return None
    dirs_seq = [_MOVE_CODE_TO_DIR[c] for c in translation]

    pos: list[tuple[int, int]] = [(0, 0)]  # pos[j] = spawn-relative after j moves
    for d in dirs_seq:
        dx, dy = _DIR_VECTOR[d]
        pos.append((pos[-1][0] + dx, pos[-1][1] + dy))
    if pos[-1] != (0, 0):
        return None  # net drift — not a loop
    n = len(dirs_seq)
    pos = pos[:n]  # drop the duplicate closing spawn entry

    legs: list[list] = []  # [direction, start move index]
    for i, d in enumerate(dirs_seq):
        if legs and legs[-1][0] == d:
            continue
        legs.append([d, i])
    if len(legs) > 1 and legs[0][0] == legs[-1][0]:
        legs.pop(0)  # cyclically the first leg is the tail of the last one
    if len(legs) != 4 or {d for d, _ in legs} != {"DOWN", "LEFT", "RIGHT", "UP"}:
        return None

    candidates = []
    for r in range(4):
        k = legs[r][1]
        anchor = pos[k]
        seq = tuple(legs[(r + i) % 4][0] for i in range(4))
        range_x = max(abs(p[0] - anchor[0]) for p in pos)
        range_y = max(abs(p[1] - anchor[1]) for p in pos)
        if range_x == 0 or range_y == 0:
            continue  # range 0 disables the axis bound in-engine — can't close
        expected = [pos[(k + 1 + j) % n] for j in range(2 * n)]
        traced = _simulate_walk_sequence(
            seq, _WALK_SEQUENCE_QUIRKS[seq], anchor, range_x, range_y, 2 * n
        )
        if traced == expected:
            candidates.append((abs(anchor[0]) + abs(anchor[1]), r, seq, anchor,
                               range_x, range_y))
    if not candidates:
        return None
    _, _, seq, anchor, range_x, range_y = min(candidates)
    return MovementSpec(
        "MOVEMENT_TYPE_WALK_SEQUENCE_" + "_".join(seq),
        range_x=range_x, range_y=range_y,
        anchor_dx=anchor[0], anchor_dy=anchor[1],
        path_cells=tuple(pos),
    )


def _simulate_walk_sequence(
    seq: tuple[str, str, str, str],
    quirk: tuple[int, str],
    anchor: tuple[int, int],
    range_x: int,
    range_y: int,
    steps: int,
) -> list[tuple[int, int]] | None:
    """Replay pokeemerald's walk-sequence automaton for `steps` moves on an
    obstacle-free grid, starting at `anchor` (the object's initial coords) on
    leg 0. Per move (MovementType_WalkSequence*_Step1 +
    MoveNextDirectionInSequence): apply the per-type quirk (back on the
    initial row/column at leg `quirk[0]` -> next leg), reset to leg 0 when on
    leg 3 back at the anchor, walk the current leg's direction, advancing one
    leg if the step would leave the centered inclusive range box (the fork
    retries exactly once). Returns the visited cells, or `None` when the
    automaton runs off the four-leg sequence / stalls — an inconsistent
    candidate the caller must reject."""
    qidx, qaxis = quirk
    ax, ay = anchor
    x, y = anchor
    idx = 0
    out: list[tuple[int, int]] = []
    for _ in range(steps):
        if idx == qidx and ((x == ax) if qaxis == "x" else (y == ay)):
            idx += 1
        if idx == 3 and (x, y) == anchor:
            idx = 0
        for attempt in range(2):
            dx, dy = _DIR_VECTOR[seq[idx]]
            nx, ny = x + dx, y + dy
            if abs(nx - ax) <= range_x and abs(ny - ay) <= range_y:
                break
            idx += 1
            if idx > 3:
                return None
        else:
            return None  # both the leg and its successor leave the range box
        x, y = nx, ny
        out.append((x, y))
    return out


def _walk_axis(codes: list[int], plus_code: int, minus_code: int) -> tuple[int, int, int]:
    """Walk `codes` in order, moving +1/-1 on `plus_code`/`minus_code` and
    leaving every other code a no-op. Returns `(net, min_offset, max_offset)`
    — the final position, and the min/max position seen at any point during
    the walk, including the starting 0."""
    pos = lo = hi = 0
    for code in codes:
        if code == plus_code:
            pos += 1
        elif code == minus_code:
            pos -= 1
        lo = min(lo, pos)
        hi = max(hi, pos)
    return pos, lo, hi


def _look_spec_for(turns: list[int]) -> str:
    """Turn-only custom route (`movement_spec_for` docstring case d) ->
    ``MOVEMENT_TYPE_LOOK_AROUND`` / a `FACE_*` single or combo constant."""
    if any(c in ROUTE_CODE_TURN_RELATIVE for c in turns):
        dirs = {"DOWN", "LEFT", "RIGHT", "UP"}
    else:
        dirs = {_TURN_CODE_TO_DIR[c] for c in turns}
    if dirs == {"DOWN", "LEFT", "RIGHT", "UP"}:
        return "MOVEMENT_TYPE_LOOK_AROUND"
    if len(dirs) == 1:
        (only,) = dirs
        return f"MOVEMENT_TYPE_FACE_{only}"
    return _TURN_COMBO_TO_MOVEMENT_TYPE[frozenset(dirs)]


def _demote(page: dict, offending_codes: list[int], reason: str) -> MovementSpec:
    """A translating custom route pokeemerald has no native movement for ->
    static FACE_<dir> with `demoted` set (`movement_spec_for` docstring case
    h). Never silent — see `metadata_wiring.build_object_events`."""
    codes = sorted(set(offending_codes))
    return static_face_spec(page, f"{reason} (codes {codes})")


def static_face_spec(page: dict, reason: str, facing: str | None = None) -> MovementSpec:
    """A static ``MOVEMENT_TYPE_FACE_<dir>`` spec with `demoted` set. For
    callers that must fall a moving spec back to standing for reasons the
    route alone can't show (`metadata_wiring.build_object_events`'s
    map-passability gates) — always paired with a loud log, never silent
    (CLAUDE.md §4.5).

    By default `<dir>` comes from the page's authored `graphic.direction`
    (`_face_from_graphic`) — this is what `_demote` (case-h unrepresentable
    custom routes, no passability data available) relies on and must keep
    getting.

    `facing` lets a caller override that with a direction derived from an
    RMXP route SIMULATION instead of the authored graphic: RMXP's blocked-move
    rule means an NPC that stalls against an obstacle has already turned to
    face the blocked direction and stays turned that way, so its real
    on-PC-arrival facing is the simulated stall facing, not whatever the page
    happened to author as `graphic.direction`. Must be one of the
    `_DIRECTION_TO_FACING` values (`"DOWN"`/`"LEFT"`/`"RIGHT"`/`"UP"`); any
    other string fails loud rather than minting a garbage
    ``MOVEMENT_TYPE_FACE_*`` constant (CLAUDE.md §4.5)."""
    if facing is None:
        movement = _face_from_graphic(page)
    else:
        if facing not in _DIRECTION_TO_FACING.values():
            raise ValueError(f"unknown facing {facing!r}")
        movement = f"MOVEMENT_TYPE_FACE_{facing}"
    return MovementSpec(movement, demoted=reason)


@dataclass(frozen=True)
class MapPassability:
    """RMXP tile-passability oracle for one map (Game_Map#passable? semantics,
    001x_Game_Map — the same layered scan `scripts/compare_collision.py`
    mirrors), for the two movement questions `metadata_wiring.
    build_object_events` must answer that the route alone can't:

    - `exit_blocked(x, y)` — can an event standing at (x, y) leave its own
      tile in ANY direction? RMXP checks the CURRENT tile's directional
      passage bits before every step, so an event spawned on a fully blocked
      tile (e.g. Map032 EV012 on its passage-15 decoration) never moves at
      all on PC, whatever its route says — pokeemerald only checks the
      DESTINATION tile, so without this demotion the object walks off its
      spawn and can never path back.
    - `cell_clear(x, y)` — is the cell fully passable (no directional bit on
      any deciding layer)? Conservative gate for walk-sequence loop paths: a
      loop crossing a non-clear cell stalls walking-in-place in-engine.

    `open_cells` are converter-level collision unblocks (the same cells the
    layout pass forces walkable, e.g. Map032's (38, 43) tree-crown cell the
    town-square patrol ghosts through on PC) — both queries treat them as
    fully open."""

    xsize: int
    ysize: int
    zsize: int
    data: tuple[int, ...]
    passages: tuple[int, ...]
    priorities: tuple[int, ...]
    open_cells: frozenset[tuple[int, int]] = frozenset()

    @classmethod
    def from_map(
        cls,
        map_json: dict,
        tileset: dict,
        open_cells: set[tuple[int, int]] | frozenset[tuple[int, int]] = frozenset(),
    ) -> "MapPassability":
        """Build from a Phase-3 map JSON (`tiles`) + its tilesets.json entry
        (`passages`/`priorities`)."""
        tiles = map_json["tiles"]
        return cls(
            xsize=tiles["xsize"], ysize=tiles["ysize"], zsize=tiles["zsize"],
            data=tuple(tiles["data"]),
            passages=tuple(tileset["passages"]),
            priorities=tuple(tileset["priorities"]),
            open_cells=frozenset(open_cells),
        )

    def _direction_blocked(self, x: int, y: int, bit: int) -> bool:
        """RMXP Game_Map#passable? layer scan, top layer down: a tile with the
        direction bit (or all four bits) blocks; a priority-0 tile without
        them decides passable; empty/undecided layers fall through."""
        for z in reversed(range(self.zsize)):
            tid = self.data[(z * self.ysize + y) * self.xsize + x]
            if tid == 0:
                continue
            if self.passages[tid] & bit or (self.passages[tid] & 0x0F) == 0x0F:
                return True
            if self.priorities[tid] == 0:
                return False
        return False

    def _in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.xsize and 0 <= y < self.ysize

    def exit_blocked(self, x: int, y: int) -> bool:
        if (x, y) in self.open_cells or not self._in_bounds(x, y):
            return False
        return all(
            self._direction_blocked(x, y, bit) for bit in _RMXP_PASSAGE_BITS.values()
        )

    def cell_clear(self, x: int, y: int) -> bool:
        if not self._in_bounds(x, y):
            return False
        if (x, y) in self.open_cells:
            return True
        return not any(
            self._direction_blocked(x, y, bit) for bit in _RMXP_PASSAGE_BITS.values()
        )

    def standable(self, x: int, y: int) -> bool:
        """Can a character occupy `(x, y)` at all? This is the GBA-collision
        question (`layout._cell_blocked`'s aggregate scan), not RMXP's
        directional `can_step`: pokeemerald collision is a single blocked/clear
        bit per metatile, decided by the same top-down layer scan the layout
        pass uses to build it, so `standable` must agree with it exactly
        (`metadata_wiring.build_object_events`'s bump-trigger relocation
        depends on that equivalence — a coord event can only be relocated onto
        a tile the layout pass actually marks walkable).

        Layers top to bottom: skip empty tiles (id 0); the first non-empty
        tile with ANY directional passage bit set (`passage & 0x0F != 0`) means
        blocked; the first non-empty tile at priority 0 that clears that check
        decides passable (stop scanning); an all-empty column is void (not
        standable). `open_cells` (converter-level collision unblocks) force a
        cell walkable regardless of tile data."""
        if not self._in_bounds(x, y):
            return False
        if (x, y) in self.open_cells:
            return True
        for z in reversed(range(self.zsize)):
            tid = self.data[(z * self.ysize + y) * self.xsize + x]
            if tid == 0:
                continue
            if (self.passages[tid] & 0x0F) != 0:
                return False
            if self.priorities[tid] == 0:
                return True
        return False

    def can_step(self, x: int, y: int, facing: str) -> bool:
        """Can a character standing at `(x, y)` take one step `facing`?

        RMXP passability is two-sided and directional, NOT an aggregate
        "is the destination cell clear" test. `021_Game_Character_v17.rb`
        `move_left` (and `move_down`/`move_right`/`move_up`, symmetric):

            def move_left(turn_enabled = true)
              turn_left if turn_enabled
              if passable?(@x, @y, 4)
                turn_left
                @x -= 1
                ...

        `Game_Character#passable?(x, y, d)` is `passableEx?(x, y, d, false)`
        (lines 106-117 of the same file):

            def passableEx?(x, y, d, strict=false)
              new_x = x + (d == 6 ? 1 : d == 4 ? -1 : 0)
              new_y = y + (d == 2 ? 1 : d == 8 ? -1 : 0)
              return false unless self.map.valid?(new_x, new_y)
              return true if @through
              ...
              return false unless self.map.passable?(x, y, d, self)
              return false unless self.map.passable?(new_x, new_y, 10 - d, self)

        i.e. leaving `(x, y)` in direction `d` requires the DESTINATION to be
        in bounds, the SOURCE tile's own directional passage bit for `d` clear
        (`Game_Map#passable?(x, y, d, ...)`, `025__Game_Map_v17.rb` lines
        163-243 — the same top-down layered scan `_direction_blocked` already
        implements: a tile with the bit set, or fully sealed (`0x0F`), blocks;
        a priority-0 tile without the bit decides passable), AND the
        DESTINATION tile's passage bit for the REVERSE direction (`10 - d`,
        e.g. leaving west checks the destination's EAST bit) also clear via
        that same scan. One sentence: a step is blocked if either the tile
        you're leaving seals its own exit in that direction, or the tile
        you're entering seals its entry from the opposite side — never a
        same-tile aggregate "any direction blocked" test.

        `open_cells` (converter-level collision unblocks) makes a cell fully
        open on whichever side it participates as source or destination,
        matching `exit_blocked`/`cell_clear`.

        Out of bounds: RMXP's own `valid?(new_x, new_y)` bounds check fails
        closed (`passableEx?` returns `false`), and a character can never be
        standing at an out-of-bounds `(x, y)` in the first place — so both
        sides of this query treat out-of-bounds as BLOCKED (unlike
        `exit_blocked`'s OOB-is-open convention; RMXP cannot walk off the map
        edge)."""
        if facing not in _RMXP_PASSAGE_BITS:
            raise ValueError(f"unknown facing {facing!r}")
        if not self._in_bounds(x, y):
            return False
        dx, dy = _DIR_VECTOR[facing]
        nx, ny = x + dx, y + dy
        if not self._in_bounds(nx, ny):
            return False

        source_blocked = (
            False if (x, y) in self.open_cells
            else self._direction_blocked(x, y, _RMXP_PASSAGE_BITS[facing])
        )
        if source_blocked:
            return False

        reverse_bit = _RMXP_PASSAGE_BITS[_REVERSE_FACING[facing]]
        dest_blocked = (
            False if (nx, ny) in self.open_cells
            else self._direction_blocked(nx, ny, reverse_bit)
        )
        return not dest_blocked


def is_door_sheet(character_name: str) -> bool:
    """True for Uranium's two door-tile sheet families (case-insensitive prefix
    match on ``"PU-doors"`` / ``"FKdoors"``). These are the door's own tile
    graphic riding along as an "event" — the real door behavior is the warp_event
    plus the tileset's door metatile, so a door-sheet event is stripped rather
    than mapped to a gfx constant."""
    name = (character_name or "").lower()
    return name.startswith(_DOOR_SHEET_PREFIXES)
