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
    `demoted` loud)."""

    movement_type: str
    range_x: int = 0
    range_y: int = 0
    demoted: str | None = None


def movement_spec_for(page: dict) -> MovementSpec:
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
       A WAIT code anywhere in the route means the patrol pauses at its ends
       -> ``MOVEMENT_TYPE_WANDER_LEFT_AND_RIGHT`` / `..._UP_AND_DOWN`; no
       waits -> continuous ``MOVEMENT_TYPE_WALK_LEFT_AND_RIGHT`` /
       `..._UP_AND_DOWN`.
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
    (CLAUDE.md §4.5)."""
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

    return _spec_for_custom_route(page)


def _face_from_graphic(page: dict) -> str:
    """``MOVEMENT_TYPE_FACE_<DIR>`` from `page["graphic"]["direction"]`.
    Fails loud on an unknown direction (CLAUDE.md §4.5)."""
    direction = page["graphic"]["direction"]
    facing = _DIRECTION_TO_FACING.get(direction)
    if facing is None:
        raise ValueError(f"unknown RMXP facing direction {direction!r}")
    return f"MOVEMENT_TYPE_FACE_{facing}"


def _spec_for_custom_route(page: dict) -> MovementSpec:
    """move_type 3 classification — see `movement_spec_for`'s docstring cases
    a-h. `page["move_route"]` (`KeyError` propagates if absent) always carries
    ``"repeat"`` and a ``"list"`` of ``{"code": int, "parameters": [...]}``
    entries ending in a code-0 sentinel."""
    route = page["move_route"]
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
    movement_type = wander_type if has_wait else walk_type
    if is_horizontal:
        return MovementSpec(movement_type, range_x=magnitude, range_y=0)
    return MovementSpec(movement_type, range_x=0, range_y=magnitude)


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
    return MovementSpec(_face_from_graphic(page), demoted=f"{reason} (codes {codes})")


def is_door_sheet(character_name: str) -> bool:
    """True for Uranium's two door-tile sheet families (case-insensitive prefix
    match on ``"PU-doors"`` / ``"FKdoors"``). These are the door's own tile
    graphic riding along as an "event" — the real door behavior is the warp_event
    plus the tileset's door metatile, so a door-sheet event is stripped rather
    than mapped to a gfx constant."""
    name = (character_name or "").lower()
    return name.startswith(_DOOR_SHEET_PREFIXES)
