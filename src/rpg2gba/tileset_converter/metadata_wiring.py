"""Phase 5 §5.3 — Map metadata wiring (the map.json assembler).

ASSIGNMENT
==========
Objective
    Assemble each `data/maps/<Name>/map.json`: the header, the OBJECT EVENTS
    (every Uranium event placed at its (x, y) with its `script` pointing at the
    Phase 4-generated dispatcher), the WARP EVENTS, and the WILD-ENCOUNTER hookup.

The interesting part — the per-page dispatcher (deterministic; build-agent work)
    An RMXP event has multiple *pages*, chosen at runtime by the page `condition`
    (switch on / variable >= N / self-switch). pokeemerald has no page concept:
    one object_event points at one script label. So we generate a small dispatcher
    per multi-page event, gotoing the page bodies (`Map{m}_EV{e}_Page{n}`) Phase 4
    produced. This is deterministic control flow, NOT a conversion-agent task.

PATHFINDER v1 scope (user decision 2026-06-15: "build S5 now, defer dispatchers")
    Global FLAG_*/VAR_* names are only minted when S6 converts a map, so for the
    slice (run before S6) we emit dispatchers ONLY for events whose pages gate on
    self-switches (a pure deterministic name) or nothing. A multi-page event with
    any GLOBAL switch/variable page condition falls back to its base page
    (`Map{m}_EV{e}_Page1`) with a logged TODO — full dispatch returns once S6 has
    minted the globals. Other v1 simplifications (all logged in PATHFINDER_FINDINGS):
      - graphics: boot-state page selection + `reference/npc_gfx_map.json` (see
        `npc_gfx.py`) resolve a real per-sheet OBJ_EVENT_GFX_*; a sheet with no
        map entry fails loud rather than falling back to a generic NPC.
      - region_map_section: a vanilla MAPSEC reused for all slice maps (the minted
        MAPSEC_* aren't in the fork's region_map_sections enum yet — S4 open item).
      - warp arrival: an extra plain-floor "arrival" warp_event is emitted on the
        destination map at Uranium's true arrival coords, and the source warp's
        dest_warp_id points at it (vanilla-Emerald landing trick) — exact Uranium
        coords, not the destination's door tile. Falls back to the old
        return-warp pairing only if the arrival coords are out of the
        destination map's bounds. out-of-slice doors are dropped (NO-EMIT, S1).
      - move routes / autorun cutscenes: placed static (S7 degrade).

Inputs
    MapNNN.json (events: id/name/x/y/pages[].condition/graphic/trigger/list),
    the MapConstantRegistry, intermediate/wild_encounters.json (Uranium map id),
    intermediate/map_metadata.json (outdoor flag -> map_type).
Output
    output/uranium-build/porymap/maps/<Name>/map.json + per-map dispatcher .pory,
    plus the per-map warp-source coords (S3 walkable-overrides).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..conversion_agent.flag_registry import (
    FlagRegistry,
    resolve_switch_flag,
    resolve_variable_var,
    self_switch_flag_name,
)
from .map_constants import MapConstantRegistry, MapConstants
from .npc_gfx import _DIR_VECTOR as _TRAINER_DIR_VECTOR
from .npc_gfx import _DIRECTION_TO_FACING as _TRAINER_SIGHT_FACING
from .npc_gfx import (
    MOVEMENT_TYPE_CUSTOM_ROUTE,
    MapPassability,
    is_door_sheet,
    movement_spec_for,
    select_boot_page,
    static_face_spec,
)
from .route_bytecode import RouteRegistry
from .route_sim import simulate_route

logger = logging.getLogger(__name__)

# v1 defaults (all logged simplifications — see module docstring).
DEFAULT_ELEVATION = 3
DEFAULT_MUSIC = "MUS_LITTLEROOT"
DEFAULT_WEATHER = "WEATHER_NONE"
DEFAULT_MAPSEC = "MAPSEC_LITTLEROOT_TOWN"  # vanilla section reused (minted MAPSEC_* deferred)
NO_SCRIPT = "0x0"

TRANSFER_CODE = 201  # RMXP "Transfer Player"; params [method, dest_map, x, y, dir, fade]

# RMXP Transfer Player `dir` param -> the direction the player faces on arrival
# (numpad convention). 0 = "retain current facing" and is deliberately absent:
# nothing in script land can read the pre-warp facing, so a dir=0 arrival keeps
# the engine's own `GetAdjustedInitialDirection` result (overworld.c) — which for
# our plain-floor arrival tiles is DIR_SOUTH, the correct vanilla door
# convention. User decision 2026-07-16; revisit only if a map visibly needs it.
_ARRIVAL_DIR_CONST = {2: "DIR_SOUTH", 4: "DIR_WEST", 6: "DIR_EAST", 8: "DIR_NORTH"}

# Scratch vars for the on-warp facing script. VAR_TEMP_1 == 0 is the vanilla
# ON_WARP_INTO_MAP_TABLE trigger idiom (temp vars are zeroed by
# ClearTempFieldEventData on every map transition, event_data.c); TEMP_2/3 hold
# the getplayerxy readback. All three are scratch inside one synchronous script.
_FACING_GUARD_VAR = "VAR_TEMP_1"
_FACING_X_VAR = "VAR_TEMP_2"
_FACING_Y_VAR = "VAR_TEMP_3"

# ON_FRAME_TABLE guard var: 0 while the per-visit autorun dispatch is still
# live, set to 1 the first frame no autorun page's guard matches (see
# `compute_autorun_entries` / `_render_onframe_script`). Written ONLY there.
_ON_FRAME_GUARD_VAR = "VAR_TEMP_C"

# Coord-event ("trigger" type) firing gate. Every coord event on a map shares
# this one var/value pair (`CoordEvent.var`/`var_value`) — pokeemerald only
# runs a trigger's script when var == value (ShouldTriggerScriptRun,
# field_control_avatar.c). VAR_TEMP_0 is unusable here: it's the transpiler's
# generic getplayerxy scratch register (transpiler.py _ALIGN_AXIS_VAR / door
# onEvent? / align loops / every Map032_EV009.pory page), so the first coord
# event to fire on a map poisons every other coord event on it for the rest of
# the visit (findings §3.1 BUG A). VAR_TEMP_F is reserved instead: temp vars
# zero on map entry, so an unwritten reserved var reads as "always eligible to
# fire this visit" — the per-event dispatchers already do the real story
# gating, so "always fire, let the dispatcher decide" is correct semantics.
# The transpile-gate guard (owned elsewhere) fails loud if any emitted script
# ever writes VAR_TEMP_F.
_COORD_GATE_VAR = "VAR_TEMP_F"

TRIGGER_ACTION = 0  # RMXP trigger: fires on the action button (a sign/NPC talk)
TRIGGER_PLAYER_TOUCH = 1  # RMXP trigger: a door/stairs fires on step-on
TRIGGER_EVENT_TOUCH = 2  # RMXP trigger: fires when the player touches the event's tile
TRIGGER_AUTORUN = 3  # RMXP trigger: fires automatically, once, map-script territory
TRIGGER_PARALLEL = 4  # RMXP trigger: runs continuously in the background

# Essentials line-of-sight trainer convention: an event whose NAME matches
# `Trainer(N)` and whose ACTIVE page is trigger-2 (event touch) gets automatic
# line-of-sight triggering instead of an ordinary touch trigger —
# `022_Game_Event_v17.rb:60` `pbCheckEventTriggerAfterTurning` recognizes the
# name pattern, and `101__PField_Field.rb:2454` `pbEventCanReachPlayer?` fires
# it when the player stands within N tiles of the event along its FACING
# direction. If the page's trigger isn't 2, the name is inert — Essentials'
# own check requires trigger==2, so ordinary classification applies unchanged.
# Two corpus shapes carry this name (203 visible battle trainers / 68 invisible
# tripwires / 8 invisible-with-battle, also tripwires):
#   - INVISIBLE (opacity 0, or no graphic at all): a sight-ray tripwire. These
#     are parked on their own (often impassable) tile purely as a script host;
#     their real trigger area is the N-tile ray in front of them, so they
#     convert to a RUN of pokeemerald coord_events painted along that ray (the
#     native Emerald idiom — vanilla maps duplicate one script across a row of
#     coord_events) rather than a single coord_event at the event's own tile.
#   - VISIBLE (opacity 255): a real battle trainer. These need the native
#     trainer-object conversion path (trainer_type + sight radius), which
#     isn't built yet — fail loud rather than silently mis-converting one as a
#     tripwire (none exist in the current slice; this is deliberate so
#     slice-2 Route 01 work lands on the right architecture).
_TRAINER_NAME_RE = re.compile(r"Trainer\((\d+)\)")

# Drop-report reasons (metadata_wiring.build_object_events) — informational tags,
# not an exhaustive enum; new reasons are fine as long as they're logged loud.
DROP_NO_BOOT_PAGE = "no_boot_page"  # no page's condition holds at boot state
DROP_BLANK_TRIGGER1 = "blank_trigger1"  # blank graphic, player-touch (non-warp)
DROP_AUTORUN = "autorun"  # blank graphic, autorun trigger — map-script territory
DROP_PARALLEL = "parallel"  # blank graphic, parallel trigger — map-script territory
DROP_DOOR_SHEET = "door_sheet"  # visible graphic is a door-tile sheet (stripped)
DROP_OPACITY0 = "opacity0"  # invisible (opacity 0) graphic, non-touch trigger

# Object-event traits (upstream transpile-driver sidecar, `Map{id:03d}.traits.json`
# — see stage_slice_scripts.py). TRAIT_SMASHABLE_ROCK is the only trait defined
# today; any other string is a fail-loud forward-compat error (CLAUDE.md §4.5).
TRAIT_SMASHABLE_ROCK = "smashable_rock"
KNOWN_TRAITS = {TRAIT_SMASHABLE_ROCK}

# Vanilla obstacle-flag convention (event_object_movement.c SetHideObstacleFlag /
# GraniteCave_B2F/map.json): smashable rocks get FLAG_TEMP_11..FLAG_TEMP_1F
# assigned sequentially per map, ascending event-id order. `removeobject` does
# FlagSet(flagId) and respawn is gated on !FlagGet(flagId); temp flags auto-clear
# on map re-entry (rock re-forms per visit, matching RMXP behavior) — flag "0" is
# a null sentinel (FlagGet always FALSE) and would respawn the rock immediately.
ROCK_FLAG_FIRST = 0x11
ROCK_FLAG_LAST = 0x1F
ROCK_FLAG_CAPACITY = ROCK_FLAG_LAST - ROCK_FLAG_FIRST + 1  # 15


# Uranium per-event temp-switch page-gate idiom (Game_Event#tempSwitches, see
# reference/scripts_dump/022_Game_Event_v17.rb): a page condition switch whose
# LABEL (not value) is `s:tsOn?("X")` / `s:tsOff?("X")` is an Essentials
# script-switch eval'd with `self` = the specific Game_Event, i.e. "this
# event's own temp switch X is on/off" — resolvable to a deterministic
# per-event flag even though the switch id itself can never be minted.
_TEMP_SWITCH_COND_RE = re.compile(r'^s:ts(On|Off)\?\(\s*"([A-Za-z0-9]+)"\s*\)\s*$')


def _resolve_switch_gate_term(
    flag_registry: FlagRegistry | None, switch_id: int, uid: int, eid: int
) -> str | None:
    """Resolve one page-condition switch id (switch1 or switch2) to a Poryscript
    guard term, or ``None`` to tell the caller to defer the WHOLE dispatch.

    Tries ``resolve_switch_flag`` first (an ordinary global switch with a
    preseeded/proposed name) -> ``flag(FLAG_*)``.

    If that returns ``None`` and the switch is an Essentials script-switch
    (``s:``-prefixed label) whose label matches Uranium's per-event temp-switch
    idiom (see ``_TEMP_SWITCH_COND_RE`` above), mints/reads the deterministic
    per-event temp-switch flag instead (``flag_registry.mint_temp_switch``,
    keyed by (map, event, key) — the same path the transpiler's
    ``setTempSwitchOn`` idiom uses, so the two converge on one name).
    ``tsOn?`` -> ``flag(NAME)``; ``tsOff?`` -> ``!flag(NAME)`` (``tsOff?`` is
    true when the temp switch was never set OR was set false — a cleared GBA
    flag covers both).

    Any other script-switch label (e.g. ``s:pbIsWeekday(...)``), a missing
    label (a ``load()``ed registry that never had ``seed_labels`` called on
    it), or no registry at all -> ``None``.

    Never mints anything for the switch id itself — ``resolve_switch_flag``
    already refuses script-switches, and this function only ever mints the
    per-event temp-switch key, never ``propose_flag(switch_id, ...)``
    (CLAUDE.md §6: never hand-mint a flag for a runtime-evaluated switch)."""
    if flag_registry is None:
        return None
    flag = resolve_switch_flag(flag_registry, switch_id)
    if flag is not None:
        return f"flag({flag})"
    if not flag_registry.is_script_switch(switch_id):
        return None
    label = flag_registry.label_for_switch(switch_id)
    if not label:
        return None
    m = _TEMP_SWITCH_COND_RE.match(label)
    if not m:
        return None
    polarity, key = m.group(1), m.group(2)
    name = flag_registry.mint_temp_switch(uid, eid, key)
    return f"flag({name})" if polarity == "On" else f"!flag({name})"


def page_label(map_id: int, event_id: int, page_num: int) -> str:
    """The Phase-4 .pory block label for a page body (1-based page_num)."""
    return f"Map{int(map_id):03d}_EV{int(event_id):03d}_Page{page_num}"


def dispatch_label(map_id: int, event_id: int) -> str:
    """The label of the multi-page dispatcher this module emits."""
    return f"Map{int(map_id):03d}_EV{int(event_id):03d}_Dispatch"


@dataclass
class ObjectEvent:
    """One placed event -> a pokeemerald object_event entry in map.json."""

    x: int
    y: int
    graphics_id: str
    script: str
    flag: str = "0"  # visibility flag (0 = always shown)
    movement_type: str = "MOVEMENT_TYPE_NONE"
    movement_range_x: int = 0
    movement_range_y: int = 0
    elevation: int = DEFAULT_ELEVATION
    route_id: str = "0"  # custom-route registry id ("0" = no route)

    def to_dict(self) -> dict:
        return {
            "graphics_id": self.graphics_id,
            "x": self.x,
            "y": self.y,
            "elevation": self.elevation,
            "movement_type": self.movement_type,
            "movement_range_x": self.movement_range_x,
            "movement_range_y": self.movement_range_y,
            "trainer_type": "TRAINER_TYPE_NONE",
            "trainer_sight_or_berry_tree_id": self.route_id,
            "script": self.script,
            "flag": self.flag,
        }


@dataclass
class BgEvent:
    """A `sign` background event: a blank-graphic, action-trigger boot page (an
    RMXP event whose visible body is a sign/plaque, not an object sprite)."""

    x: int
    y: int
    script: str
    elevation: int = 0
    player_facing_dir: str = "BG_EVENT_PLAYER_FACING_ANY"
    kind: str = "sign"

    def to_dict(self) -> dict:
        return {
            "type": self.kind,
            "x": self.x,
            "y": self.y,
            "elevation": self.elevation,
            "player_facing_dir": self.player_facing_dir,
            "script": self.script,
        }


@dataclass
class CoordEvent:
    """A `trigger` coordinate event: a blank- or invisible-graphic, event-touch
    boot page (an invisible script host standing on a tile, e.g. the Map032 EV9
    Pokedex-ceremony host)."""

    x: int
    y: int
    script: str
    elevation: int = 3
    var: str = _COORD_GATE_VAR
    var_value: str = "0"
    kind: str = "trigger"

    def to_dict(self) -> dict:
        return {
            "type": self.kind,
            "x": self.x,
            "y": self.y,
            "elevation": self.elevation,
            "var": self.var,
            "var_value": self.var_value,
            "script": self.script,
        }


@dataclass
class ObjectBuildResult:
    """Everything `build_object_events` produces for one map: the placed
    objects, the dispatcher .pory bodies, the bg/coord events split out of the
    same boot-page decision, the local-id table (RMXP event id -> 1-based
    `object_events` position — the id porymap actually compiles), and the drop
    report (every event that resolved to nothing, and why — CLAUDE.md §4.5, no
    silent drops). `transition_lines` are the ON_TRANSITION visibility
    lines for this map's hidden cutscene actors (findings §3.3/§5) — feed
    straight into `render_map_scripts`."""

    object_events: list[ObjectEvent] = field(default_factory=list)
    dispatchers: list[str] = field(default_factory=list)
    coord_events: list[CoordEvent] = field(default_factory=list)
    bg_events: list[BgEvent] = field(default_factory=list)
    local_id_map: dict[str, int] = field(default_factory=dict)
    drops: list[tuple[int, str]] = field(default_factory=list)
    transition_lines: list[str] = field(default_factory=list)


@dataclass
class WarpSpec:
    """A kept code-201 transfer, before cross-map dest_warp_id pairing."""

    src_x: int
    src_y: int
    dest_uid: int  # Uranium map id of the destination
    dest_x: int  # Uranium arrival coord: where an extra "arrival" warp_event is
    dest_y: int  # placed on the destination map (the vanilla-Emerald landing trick)
    dest_dir: int | None = None  # RMXP Transfer Player `dir` param (0/2/4/6/8)


@dataclass
class WarpEvent:
    """A resolved pokeemerald warp_event. dest_map is a MAP_* const."""

    x: int
    y: int
    dest_map: str
    dest_warp_id: int = 0

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "elevation": 0,
            "dest_map": self.dest_map,
            "dest_warp_id": str(self.dest_warp_id),
        }


@dataclass
class MapFile:
    """The assembled map.json. Serialize with `to_json_dict()`."""

    consts: MapConstants
    map_type: str = "MAP_TYPE_TOWN"
    music: str = DEFAULT_MUSIC
    weather: str = DEFAULT_WEATHER
    region_map_section: str = DEFAULT_MAPSEC
    object_events: list[ObjectEvent] = field(default_factory=list)
    warp_events: list[WarpEvent] = field(default_factory=list)
    coord_events: list[CoordEvent] = field(default_factory=list)
    bg_events: list[BgEvent] = field(default_factory=list)
    connections: list[dict] | None = None  # filled by connections.py (5.4)
    # Not part of the porymap schema (never serialized) — the RMXP event id ->
    # 1-based object_events position table, exposed here for whatever assembles
    # this MapFile to hand to `write_local_id_tables` (a pinned cross-module
    # contract; see build_object_events/ObjectBuildResult).
    local_id_map: dict[str, int] = field(default_factory=dict)

    def to_json_dict(self) -> dict:
        """Build the dict matching the fork's data/maps/<Name>/map.json schema."""
        is_town = self.map_type == "MAP_TYPE_TOWN"
        return {
            "id": self.consts.map_const,
            "name": self.consts.dir_name,
            "layout": self.consts.layout_const,
            "music": self.music,
            "region_map_section": self.region_map_section,
            "requires_flash": False,
            "weather": self.weather,
            "map_type": self.map_type,
            "allow_cycling": is_town,
            "allow_escaping": False,
            "allow_running": is_town,
            "show_map_name": is_town,
            "battle_scene": "MAP_BATTLE_SCENE_NORMAL",
            "connections": self.connections,
            "object_events": [oe.to_dict() for oe in self.object_events],
            "warp_events": [we.to_dict() for we in self.warp_events],
            "coord_events": [ce.to_dict() for ce in self.coord_events],
            "bg_events": [be.to_dict() for be in self.bg_events],
        }


# --- event classification ----------------------------------------------------

def _event_transfers(event: dict) -> list[tuple[int, int, int, int | None]]:
    """Every code-201 (dest_uid, x, y, dir) across all of an event's pages. `dir`
    is `None` if the command's parameter list is too short to carry one (a
    malformed/legacy event) rather than assuming 0 ("retain")."""
    out = []
    for page in event["pages"]:
        for cmd in page.get("list", []):
            if cmd["code"] == TRANSFER_CODE:
                p = cmd["parameters"]
                out.append((p[1], p[2], p[3], p[4] if len(p) > 4 else None))
    return out


def classify_event(event: dict, slice_ids: set[int]) -> tuple[str, WarpSpec | str | None]:
    """Decide how an event is realized (generic rule that reproduces the S1 keep-list):

    - any code-201 to an OUT-of-slice map -> ("skip", reason): emit nothing (NO-EMIT
      building doors + WALL cave exits — nothing references the missing maps).
    - a code-201 to an IN-slice map on a player-touch trigger -> ("warp", WarpSpec):
      a real door/stairs warp_event (the object_event is dropped to avoid a double
      warp; its .pory body goes unreferenced).
    - everything else -> ("object", None): an object_event (incl. scripted story
      transfers like the Letter, whose .pory body keeps the warp() call)."""
    transfers = _event_transfers(event)
    if transfers:
        targets = {t[0] for t in transfers}
        if any(t not in slice_ids for t in targets):
            return ("skip", "out-of-slice warp")
        if event["pages"][0].get("trigger") == TRIGGER_PLAYER_TOUCH:
            dest_uid, dx, dy, ddir = transfers[0]
            return ("warp", WarpSpec(event["x"], event["y"], dest_uid, dx, dy, ddir))
    return ("object", None)


def classify_map_events(
    map_json: dict, slice_ids: set[int]
) -> tuple[list[dict], list[tuple[dict, WarpSpec]], list[tuple[dict, str]]]:
    """Split a map's events (id-sorted) into object / warp / skipped buckets."""
    objects: list[dict] = []
    warps: list[tuple[dict, WarpSpec]] = []
    skipped: list[tuple[dict, str]] = []
    for event in sorted(map_json["events"], key=lambda e: e["id"]):
        kind, payload = classify_event(event, slice_ids)
        if kind == "warp":
            warps.append((event, payload))  # type: ignore[arg-type]
        elif kind == "skip":
            skipped.append((event, payload))  # type: ignore[arg-type]
        else:
            objects.append(event)
    return objects, warps, skipped


# --- builders ----------------------------------------------------------------

def _page_condition_terms(
    cond: dict, uid: int, eid: int, flag_registry: FlagRegistry | None
) -> list[str] | None:
    """One page condition -> its guard terms (to be ANDed), shared by
    `build_page_dispatcher` and `compute_autorun_entries` (and the hidden-actor
    visibility-clause builder) — one notion of "how does a page condition
    become Poryscript", not three copies of it (CLAUDE.md §4.3).

      - ``switch1_valid`` / ``switch2_valid`` -> ``flag(FLAG_*)``, resolved
        through the registry (``resolve_switch_flag``); OR, for a script-switch
        (``s:``) whose label matches Uranium's per-event temp-switch idiom —
        ``s:tsOn?("X")`` / ``s:tsOff?("X")`` — a per-event temp-switch flag
        (see ``_resolve_switch_gate_term``).
      - ``variable_valid`` -> ``var(VAR_*) >= value`` (RMXP's own semantics —
        a page is active iff ``$game_variables[id] >= value``).
      - ``self_switch_valid`` -> ``flag(FLAG_MAP{m}_EVENT{e}_SS{ch})``, a pure
        deterministic name, minted into the registry when one is given.

    Returns `[]` for an unconditional page (no gate at all) — NOT the same as
    `None`. `None` means "can't resolve one of the gates present" (no
    registry, an unresolvable script-switch, or an unnamed switch/var) — the
    caller decides what unresolvable means for its own purpose (defer a whole
    dispatch, fail loud on an autorun guard, etc.)."""
    terms: list[str] = []

    if cond.get("switch1_valid"):
        term = _resolve_switch_gate_term(flag_registry, cond["switch1_id"], uid, eid)
        if term is None:
            return None
        terms.append(term)

    if cond.get("switch2_valid"):
        term = _resolve_switch_gate_term(flag_registry, cond["switch2_id"], uid, eid)
        if term is None:
            return None
        terms.append(term)

    if cond.get("variable_valid"):
        if flag_registry is None:
            return None
        var = resolve_variable_var(flag_registry, cond["variable_id"])
        if var is None:
            return None
        terms.append(f"var({var}) >= {cond['variable_value']}")

    if cond.get("self_switch_valid"):
        letter = cond["self_switch_ch"]
        flag = self_switch_flag_name(uid, eid, letter)
        terms.append(f"flag({flag})")
        if flag_registry is not None:
            flag_registry.mint_self_switch(uid, eid, letter)

    return terms


_VAR_TERM_RE = re.compile(r"^var\((.+)\) >= (-?\d+)$")


def _negate_term(term: str) -> str:
    """Negate one `_page_condition_terms` guard term: ``flag(F)`` <->
    ``!flag(F)``, ``var(X) >= n`` -> ``var(X) < n``. Fails loud on a term shape
    this doesn't recognize rather than emitting a wrong guard."""
    if term.startswith("!flag("):
        return "flag(" + term[len("!flag(") :]
    if term.startswith("flag("):
        return "!" + term
    m = _VAR_TERM_RE.match(term)
    if m:
        return f"var({m.group(1)}) < {m.group(2)}"
    raise ValueError(f"cannot negate unrecognized guard term {term!r}")


def _negate_terms(terms: list[str]) -> str:
    """De Morgan negation of a conjunction of guard terms: a single term
    negates in place; multiple terms negate to a parenthesized disjunction
    (``!c1 || !c2``) so it composes safely inside an outer ``&&`` chain."""
    negated = [_negate_term(t) for t in terms]
    if len(negated) == 1:
        return negated[0]
    return "(" + " || ".join(negated) + ")"


def _goto_or_end(pages: list[dict], uid: int, eid: int, page_idx: int) -> str:
    """``goto(<page label>)``, or bare ``end`` when the target page is
    autorun/parallel (RMXP trigger 3/4). Autorun/parallel page bodies must
    never be reachable from the action-button interaction dispatcher
    (findings §3.2 BUG B — an autorun body is invoked only via the
    ON_FRAME_TABLE channel, `compute_autorun_entries` /
    `_render_onframe_script`); talking to such an event when it's the
    active page does nothing."""
    if pages[page_idx].get("trigger") in (TRIGGER_AUTORUN, TRIGGER_PARALLEL):
        return "end"
    return f"goto({page_label(uid, eid, page_idx + 1)})"


def build_page_dispatcher(
    event: dict, consts: MapConstants, flag_registry: FlagRegistry | None = None
) -> str | None:
    """Emit a Poryscript dispatcher for a multi-page event, or None to defer.

    Returns None for a single-page event whose page carries no condition (no
    dispatch needed). Otherwise tests pages high->low — INCLUDING index 0: RMXP
    activates the highest-index satisfiable page, and the base page's own
    condition counts too (Map032 EV080: page 1 is itself gated on switch 125
    "FINAL EVENT"; treating it as an unconditional fallback fired the postgame
    Champion scene at boot). Each page's condition becomes a conjunction of
    guard terms via `_page_condition_terms`; no condition at all -> an
    unconditional page becomes the fallback and the scan stops (a higher
    unconditional page always wins). When EVERY page is gated and none holds,
    the dispatcher falls through to a bare ``end`` — RMXP's "no active page"
    means the event is inert, not "run the base page anyway".

    A switch/variable gate that can't be resolved to a name (`_page_condition_
    terms` returns `None`) — no registry given (``flag_registry=None``), an
    unresolvable script-switch, or an unnamed switch/variable — defers the
    WHOLE event's dispatch: returns None and the caller points the
    object_event at the base page instead (until the name is mintable).

    Every ``goto()`` target (guards AND the fallback) is trigger-checked via
    `_goto_or_end`: a page whose own trigger is autorun/parallel (3/4) is
    never a valid action-button target and becomes a bare ``end`` instead
    (findings §3.2 BUG B)."""
    pages = event["pages"]
    uid, eid = consts.uranium_id, event["id"]

    guards: list[tuple[str, int]] = []
    fallback_idx: int | None = None
    for idx in range(len(pages) - 1, -1, -1):  # high -> low, base page included
        terms = _page_condition_terms(pages[idx]["condition"], uid, eid, flag_registry)
        if terms is None:
            return None  # deferred: no registry, unresolvable script-switch, or unnamed
        if terms:
            guards.append((" && ".join(terms), idx))
        else:
            fallback_idx = idx  # unconditional page wins outright
            break

    if not guards and fallback_idx == 0 and len(pages) == 1:
        return None  # single unconditional page: no dispatch needed

    lines = [f"script {dispatch_label(uid, eid)} {{"]
    for cond_str, idx in guards:
        lines += [
            f"    if ({cond_str}) {{",
            f"        {_goto_or_end(pages, uid, eid, idx)}",
            "    }",
        ]
    if fallback_idx is not None:
        lines += [f"    {_goto_or_end(pages, uid, eid, fallback_idx)}", "}"]
    else:
        # every page gated, none matched at runtime -> inert (RMXP: no active page)
        lines += ["    end", "}"]
    return "\n".join(lines)


@dataclass(frozen=True)
class AutorunEntry:
    """One RMXP trigger=3 (autorun) page eligible to dispatch from the
    ON_FRAME_TABLE channel: the page-body label to `goto()` and the boolean
    guard expression reproducing RMXP's "is THIS page the active one" test.
    `guard == ""` means unconditionally active (no own condition, no higher
    page to negate) — see `compute_autorun_entries`."""

    event_id: int
    page_index: int  # 0-based RMXP page index
    page_label: str
    guard: str


def compute_autorun_entries(
    events: list[dict], uid: int, flag_registry: FlagRegistry | None
) -> list[AutorunEntry]:
    """Every trigger=3 (autorun) page across `events`, each paired with the
    guard expression that reproduces RMXP's page-activation semantics: RMXP
    autoruns only the highest-index page whose condition holds, so an autorun
    page's guard is its own condition terms AND the negation of every
    HIGHER-index page's condition on the same event (regardless of that
    higher page's own trigger — any higher page winning page-selection
    suppresses this one, autorun or not).

    A higher page with NO condition terms at all is unconditionally
    satisfiable, so this (lower) autorun page can never be the active page —
    skipped (logged), not emitted with a vacuous always-false guard.

    Fails loud (`ValueError`) if any needed condition term — this page's own,
    or a higher page's (needed to negate it) — can't be resolved
    (`_page_condition_terms` returns `None`): a story-critical autorun must
    never be silently dropped (findings §3.2/§5).

    Sorted by (event_id, page_index) ascending — deterministic, independent
    of the caller's event dict ordering."""
    entries: list[AutorunEntry] = []
    for event in sorted(events, key=lambda e: e["id"]):
        eid = event["id"]
        pages = event["pages"]
        for idx, page in enumerate(pages):
            if page.get("trigger") != TRIGGER_AUTORUN:
                continue
            own_terms = _page_condition_terms(page["condition"], uid, eid, flag_registry)
            if own_terms is None:
                raise ValueError(
                    f"map {uid} EV{eid:03d} page {idx}: autorun page's own "
                    f"condition can't be resolved to a guard term (unnamed "
                    f"switch/var, or an unsupported script-switch)"
                )
            guard_terms = list(own_terms)
            skip = False
            for higher_idx in range(idx + 1, len(pages)):
                higher_terms = _page_condition_terms(
                    pages[higher_idx]["condition"], uid, eid, flag_registry
                )
                if higher_terms is None:
                    raise ValueError(
                        f"map {uid} EV{eid:03d} page {idx}: can't resolve "
                        f"higher page {higher_idx}'s condition to negate it "
                        f"(needed to compute this autorun page's guard)"
                    )
                if not higher_terms:
                    logger.info(
                        "map %d EV%03d: autorun page %d never active — "
                        "unconditional higher page %d always wins",
                        uid, eid, idx, higher_idx,
                    )
                    skip = True
                    break
                guard_terms.append(_negate_terms(higher_terms))
            if skip:
                continue
            entries.append(
                AutorunEntry(
                    event_id=eid, page_index=idx,
                    page_label=page_label(uid, eid, idx + 1),
                    guard=" && ".join(guard_terms),
                )
            )
    return entries


def _render_onframe_script(label: str, entries: list[AutorunEntry]) -> str:
    """The ``<Dir>_OnFrame`` dispatcher body: one guarded `goto` per autorun
    entry (unconditional entries — `guard == ""` — get a bare `goto`, no
    `if`), then `setvar(VAR_TEMP_C, 1)` to stop per-frame dispatch for the
    rest of the visit once nothing matches (see module docstring / findings
    §3.2 for the per-frame termination semantics)."""
    lines = [f"script {label} {{"]
    for entry in entries:
        if entry.guard:
            lines += [
                f"    if ({entry.guard}) {{",
                f"        goto({entry.page_label})",
                "    }",
            ]
        else:
            lines.append(f"    goto({entry.page_label})")
    lines.append(f"    setvar({_ON_FRAME_GUARD_VAR}, 1)")
    lines.append("}")
    return "\n".join(lines)


_ONFRAME_REARM_COMMENT = "# re-arm ON_FRAME dispatch (autorun guard input changed)"
ONFRAME_REARM_LINE = f"setvar({_ON_FRAME_GUARD_VAR}, 0) {_ONFRAME_REARM_COMMENT}"

_TOP_BLOCK_HEADER_RE = re.compile(r"^(script|movement|text|mapscripts)\s+(\S+)\s*\{")
_REARM_FLAG_WRITE_RE = re.compile(r"^(\s*)(?:setflag|clearflag)\(\s*(FLAG_[A-Z0-9_]+)\s*\)")
_REARM_VAR_WRITE_RE = re.compile(r"^(\s*)(?:setvar|addvar|subvar|copyvar)\(\s*(VAR_[A-Z0-9_]+)")


def insert_onframe_rearms(pory_text: str, guard_flags: set[str], guard_vars: set[str]) -> str:
    """Re-arm the per-map ON_FRAME latch (``VAR_TEMP_C``) whenever a NON-dispatched
    script writes a symbol one of the map's autorun guards reads.

    RMXP autorun (trigger=3) page conditions are re-evaluated continuously —
    every frame, forever. Our ``<Dir>_OnFrame`` dispatcher (`_render_onframe_script`)
    only approximates that: it dispatches once per frame until no autorun guard
    matches, then latches ``setvar(VAR_TEMP_C, 1)`` to stop per-frame dispatch for
    the rest of the map visit (a perf optimization RMXP doesn't need). That latch
    goes stale the moment something the guards depend on changes outside the
    dispatcher's own reach — e.g. an interactive NPC script that clears a flag an
    autorun page's guard tests, expecting the autorun to reconsider itself. Without
    a re-arm, the dispatcher never dispatches again for the rest of the visit and
    the autorun becomes permanently unstartable (see the Map050 quiz/retake bug
    this function fixes).

    The fix: scan every top-level ``script Name { ... }`` block in `pory_text`
    (never ``movement``/``text``/``mapscripts`` blocks, and never a block whose
    name ends in ``_OnFrame`` — the dispatcher itself must not re-arm its own
    latch mid-body) for a line that writes one of `guard_flags` (``setflag``/
    ``clearflag``) or `guard_vars` (``setvar``/``addvar``/``subvar``/``copyvar``).
    Immediately after such a line, insert ``setvar(VAR_TEMP_C, 0)`` at the same
    indentation — unless it's already there (idempotent: applying this twice is
    a no-op, so staging can re-run it safely).

    Top-level blocks are found the same way `_find_script_block` finds them:
    they open at column 0 and close at the next column-0 ``}`` — nested
    ``if``/``switch`` bodies are always indented, so no brace-depth counter is
    needed. A simple line-based scan (rather than a real parser) is safe because
    the transpiler emits one command per line and writes are only recognized at
    the start of a line, so a string or comment containing e.g. ``setflag(`` text
    is never mistaken for a real write.
    """
    lines = pory_text.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        header = _TOP_BLOCK_HEADER_RE.match(line)
        if not header:
            out.append(line)
            i += 1
            continue
        kind, name = header.group(1), header.group(2)
        j = i + 1
        while j < n and not re.match(r"^\}\s*$", lines[j]):
            j += 1
        block_lines = lines[i:j + 1] if j < n else lines[i:]
        if kind != "script" or name.endswith("_OnFrame"):
            out.extend(block_lines)
            i = j + 1
            continue
        out.append(block_lines[0])
        body = block_lines[1:]
        k = 0
        while k < len(body):
            bline = body[k]
            out.append(bline)
            write_symbol = None
            indent = ""
            fm = _REARM_FLAG_WRITE_RE.match(bline)
            if fm and fm.group(2) in guard_flags:
                write_symbol = fm.group(2)
                indent = fm.group(1)
            if write_symbol is None:
                vm = _REARM_VAR_WRITE_RE.match(bline)
                if vm and vm.group(2) in guard_vars:
                    write_symbol = vm.group(2)
                    indent = vm.group(1)
            if write_symbol is not None:
                nxt = k + 1
                while nxt < len(body) and body[nxt].strip() == "":
                    nxt += 1
                already_armed = nxt < len(body) and body[nxt].strip() == ONFRAME_REARM_LINE
                if not already_armed:
                    out.append(f"{indent}{ONFRAME_REARM_LINE}")
            k += 1
        i = j + 1
    text = "\n".join(out)
    if pory_text.endswith("\n"):
        text += "\n"
    return text


def _event_has_body(event: dict, consts: MapConstants, pory_labels: set[str]) -> bool:
    """True if S6 converted any of the event's pages into a `.pory` block.

    Keyed across every page (by `Map{m}_EV{e}_Page{n}`), so a command-less event —
    a standing NPC, or a cutscene-sprite actor whose pages carry no real commands —
    is recognized regardless of page count or gating. `pory_labels` must be the
    *canonical* (name-normalized) definition set, since the agent's raw labels are
    name-qualified (`..._Chyinmunk_Page1`); see `assembly.normalize_labels`."""
    uid, eid = consts.uranium_id, event["id"]
    return any(
        page_label(uid, eid, n) in pory_labels for n in range(1, len(event["pages"]) + 1)
    )


def _resolve_script(
    event: dict,
    consts: MapConstants,
    pory_labels: set[str] | None,
    flag_registry: FlagRegistry | None = None,
) -> tuple[str, str | None]:
    """Resolve the .pory script label an event's converted behavior lives at
    (dispatcher label / page-1 label / the static "0x0"), and the dispatcher body
    to emit alongside it (or None). Shared by every emission path — object, bg
    sign, coord trigger — so a sign or invisible trigger host points at the exact
    same label an object_event for that event would have gotten (CLAUDE.md §4.3:
    one label-resolution rule, not three copies of it).

    When `pory_labels` is given (post-S6, the canonical def set), an event S6 left
    bodyless — a standing NPC / globally-gated cutscene actor with no real
    commands — resolves to the STATIC script ("0x0"), not a dangling page label.
    An event with *some* converted body but whose resolved page label is missing
    is a genuine page-body gap and fails loud (CLAUDE.md §4.5). `flag_registry`,
    when given, lets `build_page_dispatcher` resolve global switch/var page gates
    into a real dispatcher instead of deferring (see its docstring)."""
    uid, eid = consts.uranium_id, event["id"]
    if pory_labels is not None and not _event_has_body(event, consts, pory_labels):
        logger.info("map %d EV%03d: no converted .pory body -> static script", uid, eid)
        return NO_SCRIPT, None

    dispatcher = build_page_dispatcher(event, consts, flag_registry)
    if dispatcher is not None:
        if pory_labels is not None:
            referenced = set(re.findall(r"goto\(([^)]+)\)", dispatcher))
            missing = referenced - pory_labels
            if missing:
                raise KeyError(
                    f"map {uid} EV{eid:03d}: dispatcher references page label(s) "
                    f"{sorted(missing)} not in the converted .pory, yet other "
                    f"pages of this event were converted — a page-body gap"
                )
        return dispatch_label(uid, eid), dispatcher

    script = page_label(uid, eid, 1)
    if len(event["pages"]) > 1:
        logger.info(
            "map %d EV%03d: multi-page dispatch deferred (global gate) -> %s",
            uid, eid, script,
        )
    if pory_labels is not None and script not in pory_labels:
        raise KeyError(
            f"map {uid} EV{eid:03d}: resolved script label {script} not in the "
            f"converted .pory, yet other pages of this event were converted — "
            f"a page-body gap (base page empty but a later page has commands)"
        )
    return script, None


def _validate_event_traits(event_traits: dict[int, list[str]], uid: int) -> None:
    """Fail loud on any trait string outside `KNOWN_TRAITS` (forward-compat)."""
    for eid, traits in event_traits.items():
        for trait in traits:
            if trait not in KNOWN_TRAITS:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: unknown trait {trait!r} in traits "
                    f"sidecar (known traits: {sorted(KNOWN_TRAITS)})"
                )


def _assign_visibility_flags(
    rock_ids: list[int], actor_ids: list[int], uid: int
) -> dict[int, str]:
    """FLAG_TEMP_11.._1F, shared by `smashable_rock` events AND hidden
    cutscene actors (findings §3.3/§5) — one sequential pool, ascending
    event-id order across BOTH kinds (vanilla obstacle-flag convention; see
    the ROCK_FLAG_* module comment). Raises if the map has more
    traited/choreographed events than the range holds."""
    all_ids = sorted(set(rock_ids) | set(actor_ids))
    if len(all_ids) > ROCK_FLAG_CAPACITY:
        raise ValueError(
            f"map {uid}: {len(all_ids)} smashable_rock/hidden-actor events "
            f"exceed the FLAG_TEMP_{ROCK_FLAG_FIRST:X}..FLAG_TEMP_{ROCK_FLAG_LAST:X} "
            f"capacity ({ROCK_FLAG_CAPACITY})"
        )
    return {
        eid: f"FLAG_TEMP_{ROCK_FLAG_FIRST + i:X}" for i, eid in enumerate(all_ids)
    }


def _visibility_transition_lines(
    pages: list[dict],
    uid: int,
    eid: int,
    name: str,
    flag: str,
    flag_registry: FlagRegistry | None,
) -> tuple[list[str], bool]:
    """ON_TRANSITION lines for one hidden cutscene actor: unconditionally hide
    it (`setflag`), then clear the flag when RMXP's page-selection state would
    make it visible — a page with a graphic AND `opacity > 0` whose own
    condition holds and every higher page's does not (same highest-active-page
    semantics as `compute_autorun_entries`). A page with a graphic but
    `opacity == 0` never counts as visible (findings §5) — those actors stay
    flag-hidden until a hand-authored script `addobject`s them.

    Returns `(lines, always_visible)`. `always_visible` is True when some
    visible clause has no gating at all (unconditionally satisfiable, no
    higher page to dominate it) — the actor is visible every time it's
    placed, so the caller should use flag "0" (never hide) instead of
    spending a pool slot on it, and `lines` is `[]` in that case. When no
    page ever qualifies as visible, `lines` is just the `setflag` (always
    hidden until a script `addobject`s it) — also matching findings §5.

    Fails loud (`ValueError`) on an unresolvable condition term — a
    story-critical cutscene actor's visibility must never silently default
    to "always hidden" or "always shown" (CLAUDE.md §4.5)."""
    clauses: list[str] = []
    always_visible = False
    for i, p in enumerate(pages):
        gname = p.get("graphic", {}).get("character_name") or ""
        opacity = p.get("graphic", {}).get("opacity", 255)
        if not gname or opacity <= 0:
            continue
        own = _page_condition_terms(p["condition"], uid, eid, flag_registry)
        if own is None:
            raise ValueError(
                f"map {uid} EV{eid:03d} page {i}: visibility condition can't "
                f"be resolved to a guard term"
            )
        terms = list(own)
        dominated = False
        for hi in range(i + 1, len(pages)):
            higher = _page_condition_terms(pages[hi]["condition"], uid, eid, flag_registry)
            if higher is None:
                raise ValueError(
                    f"map {uid} EV{eid:03d} page {i}: can't resolve higher "
                    f"page {hi}'s condition to negate it for the visibility "
                    f"clause"
                )
            if not higher:
                dominated = True
                break
            terms.append(_negate_terms(higher))
        if dominated:
            continue
        if not terms:
            always_visible = True
            break
        clauses.append(terms[0] if len(terms) == 1 else "(" + " && ".join(terms) + ")")

    if always_visible:
        return [], True

    lines = [f"# EV{eid:03d} {name}".rstrip(), f"setflag({flag})"]
    if clauses:
        expr = clauses[0] if len(clauses) == 1 else " || ".join(clauses)
        lines += [f"if ({expr}) {{", f"    clearflag({flag})", "}"]
    return lines, False


def collect_through_block_cells(map_json: dict) -> set[tuple[int, int]]:
    """RMXP's blank-graphic + `through == False` invisible-obstacle idiom (fix #3):
    cells (x, y) of events whose BOOT page has a blank graphic and `through` is
    False, regardless of trigger. This is purely the tile-BLOCKING half of what such
    an event is — the script/trigger behavior for the same events is unchanged,
    already handled by `build_object_events`'s bg-sign / coord-trigger / drop
    classification (this function adds no new classification, just a coordinate
    set for the layout pass to stamp collision on).

    Reuses `select_boot_page` and the same blank-graphic predicate
    (`not character_name`) `build_object_events` uses, so the two can never
    disagree about which page an event shows at boot or what counts as "blank"
    (CLAUDE.md §4.3 — one notion of blank graphic / boot page, not two).

    Events WITH a graphic are excluded even when `through` is False: pokeemerald's
    native object_event collision already blocks that tile, so stamping it again
    would be redundant (and such an event is placed as a real object_event, not a
    phantom obstacle, by `build_object_events`).

    A working (in-slice) warp door is ALSO blank-graphic + `through == False` at
    boot, matching this same predicate — but its tile must stay enterable
    (`convert_layout`'s `warp_overrides` already gives it the correct
    walkable/warp-behavior metatile). This function does NOT special-case that: an
    out-of-slice door (NO-EMIT, `classify_event`'s "skip") matches the identical
    predicate and correctly SHOULD stay blocked (nothing will ever warp there, so
    it must not read as open ground into unconverted territory) — and there is no
    slice-independent way to tell the two apart from an event dict alone. The
    caller is responsible for excluding real warp coords (its own `warp_overrides`
    set) from the result before handing it to `convert_layout` as `blocked_cells`
    (see `scripts/assemble_pathfinder.py::run_layout_pass`); `convert_layout`
    itself still fails loud if that subtraction was missed."""
    cells: set[tuple[int, int]] = set()
    for event in map_json["events"]:
        page = select_boot_page(event)
        if page is None:
            continue
        name = page.get("graphic", {}).get("character_name") or ""
        if name:
            continue
        if page["through"]:
            continue
        cells.add((event["x"], event["y"]))
    return cells


def _trainer_sight_ray(
    ex: int, ey: int, facing: str, n: int, through: bool,
    passability: MapPassability | None,
) -> list[tuple[int, int]]:
    """Candidate tiles for a Trainer(N) sight-ray tripwire (`pbEventCanReachPlayer?`,
    see the module comment above `_TRAINER_NAME_RE`): the N tiles from the
    event's own tile out along `facing`, distance 1..N.

    LOS clipping mirrors Essentials exactly: `through=True` never clips (all N
    candidates are live); `through=False` clips the walk at the first blocked
    step — distance 1 is always live (Essentials checks zero intermediate
    steps for the adjacent tile), and distance d>1 is live only if every step
    from the event's own tile through distance d-1 passes `can_step` (RMXP's
    two-sided directional check). `passability is None` (legacy callers with
    no map data to clip or filter against) skips both the LOS walk and the
    standable filter below and returns the full unfiltered N-tile ray.

    Live candidates are then filtered to `passability.standable` tiles (the
    GBA-collision question — a tripwire can only paint a coord_event onto a
    tile the player can actually stand on) when `passability` is given."""
    dx, dy = _TRAINER_DIR_VECTOR[facing]
    tiles: list[tuple[int, int]] = []
    for d in range(1, n + 1):
        if d >= 2 and passability is not None and not through:
            prev_x, prev_y = ex + (d - 2) * dx, ey + (d - 2) * dy
            if not passability.can_step(prev_x, prev_y, facing):
                break
        tiles.append((ex + d * dx, ey + d * dy))
    if passability is not None:
        tiles = [(x, y) for x, y in tiles if passability.standable(x, y)]
    return tiles


def build_object_events(
    map_json: dict,
    consts: MapConstants,
    slice_ids: set[int],
    *,
    pory_labels: set[str] | None = None,
    npc_gfx: dict[str, str] | None = None,
    event_traits: dict[int, list[str]] | None = None,
    flag_registry: FlagRegistry | None = None,
    passability: MapPassability | None = None,
    route_registry: RouteRegistry | None = None,
    required_actor_ids: set[int] | None = None,
) -> ObjectBuildResult:
    """Place every non-warp, non-skipped event per its BOOT-STATE page (RMXP shows
    the highest-index page whose condition holds at boot; `npc_gfx.select_boot_page`).

    - no boot-active page -> dropped (`no_boot_page`).
    - boot page's graphic is blank (no character_name):
        trigger 0 (action)      -> a `sign` bg_event.
        trigger 2 (event touch) -> a `trigger` coord_event.
        trigger 1 / 3 / 4       -> dropped (`blank_trigger1` / `autorun` /
                                   `parallel` — autorun/parallel are future
                                   map-script territory, not object placement).
    - boot page has a graphic but opacity 0 (an invisible script host, e.g. the
      Map032 EV9 Pokedex-ceremony host and EV74):
        trigger 2 -> a `trigger` coord_event (their script MUST stay referenced
                     so assembly pruning doesn't drop it).
        otherwise -> dropped (`opacity0`).
    - boot page has a visible graphic:
        a door sheet (`npc_gfx.is_door_sheet`) -> dropped (`door_sheet`) — the
        real door is the warp_event + tileset door tile, not this sprite.
        otherwise -> an object_event with `graphics_id = npc_gfx[character_name]`
                     (KeyError if `npc_gfx` is None or the name is unmapped — no
                     silent default, CLAUDE.md §4.5) and `movement_type`/
                     `movement_range_x`/`movement_range_y` from the boot page's
                     move_type/move_route (`npc_gfx.movement_spec_for`). A route
                     `movement_spec_for` had to demote to a static facing (no
                     native pokeemerald analog) is logged loud via
                     `logger.warning`, never silent — the event is still placed.

    Every emission path resolves its script label via `_resolve_script`. Returns
    an `ObjectBuildResult`: the placed events, dispatcher bodies, the local-id
    table (RMXP event id -> 1-based `object_events` position, the id porymap
    actually compiles), and the drop report (no silent drops).

    `event_traits` (event id -> trait list, from the transpile driver's
    `Map{id:03d}.traits.json` sidecar) assigns `smashable_rock` events sequential
    FLAG_TEMP_11.._1F visibility flags (see ROCK_FLAG_* / CLAUDE.md §4.5 — >15
    such events, an unknown trait string, or a trait on an event id that resolves
    to no emitted object_event all fail loud). `None` is legacy behavior: every
    `ObjectEvent.flag` stays the "0" default.

    `flag_registry`, when given, is forwarded to `_resolve_script` /
    `build_page_dispatcher` so multi-page events gated on a global switch/var can
    get a real dispatcher instead of deferring to the base page; `None` keeps
    today's defer-on-global-gate behavior.

    `passability` (an `npc_gfx.MapPassability` for THIS map), when given,
    gates every moving spec against the map data (both demotions log loud):

    - a moving NPC whose spawn tile blocks leaving in all four directions
      (RMXP checks the CURRENT tile before each step, so it never moves on PC
      — pokeemerald checks only the destination, so it would walk off and
      never path back) -> static facing;
    - a walk-sequence loop crossing a non-clear cell (would stall
      walking-in-place in-engine) -> static facing.

    A walk-sequence spec's `anchor_dx`/`anchor_dy` spawn shift is applied to
    the placed coords (the engine closes the loop at the object's initial
    coords, which must be a loop corner). `None` skips the passability gates
    (unit-test/legacy path) but still applies anchor shifts.

    `route_registry` (a `route_bytecode.RouteRegistry`), when an emitted spec
    carries `route_bytecode` (`movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE`),
    interns the bytecode and sets the resulting 1-based id as
    `ObjectEvent.route_id` (serialized as `trainer_sight_or_berry_tree_id`).
    `route_registry=None` with an encodable route present raises `ValueError`
    (fail loud — CLAUDE.md §4.5): the caller must own and share one registry
    per slice, exactly like `flag_registry`.

    `required_actor_ids` (RMXP event ids some OTHER event's script
    choreographs via applymovement/setobjectxy/addobject/removeobject/
    turnobject — see `scripts/stage_slice_scripts.py`'s pory scan) are
    emitted as hidden cutscene actors (findings §3.3/§5) for every id that
    has NO boot-active page (would otherwise be silently absent, leaving the
    choreography's object-command targets dangling/colliding): placed at the
    event's (x, y) using its first graphic-bearing page, static-facing,
    behind a sequential FLAG_TEMP_11.._1F visibility flag shared with
    `smashable_rock` traited events (`_assign_visibility_flags`), with a
    normal page dispatcher for interaction and a `local_id_map` entry so
    `write_local_id_tables` covers it. An id already emitted normally (has a
    boot-active page) is left alone. An id absent from `map_json["events"]`
    entirely, or one that resolves to a warp/out-of-slice event, fails loud.
    `ObjectBuildResult.transition_lines` carries the matching ON_TRANSITION
    visibility lines for `render_map_scripts`. `None` (default) emits no
    hidden actors — legacy behavior."""
    objects, _, _ = classify_map_events(map_json, slice_ids)
    uid = consts.uranium_id
    result = ObjectBuildResult()
    event_by_id = {e["id"]: e for e in map_json["events"]}
    objects_by_id = {e["id"]: e for e in objects}

    hidden_actor_ids: list[int] = []
    if required_actor_ids:
        for eid in sorted(required_actor_ids):
            req_event = event_by_id.get(eid)
            if req_event is None:
                raise ValueError(
                    f"map {uid}: required_actor_ids references event {eid} "
                    f"absent from this map's events"
                )
            if eid not in objects_by_id:
                # A warp/out-of-slice event (e.g. an animated-door sprite whose
                # only object-command refs live in its own page block, which the
                # prune pass removes). Not placeable — skip here; if a LIVE
                # script still references it after pruning, the strict
                # local_id_remap pass fails loud at staging.
                logger.info(
                    "map %d EV%03d: required-actor scan hit a warp/skip event; "
                    "leaving to the strict remap pass", uid, eid,
                )
                continue
            boot = select_boot_page(req_event)
            if boot is not None:
                # Mirror the emit-kind branch below: a required actor whose
                # boot page yields a real object event is handled normally; a
                # boot page the loop would DROP (opacity-0 non-touch — e.g.
                # Map032 EV075, the invisible Theo runner — or a blank-graphic
                # autorun/parallel page) still needs a hidden-actor placement
                # so its choreography targets a real local id. A boot page
                # that becomes a bg/coord event can't double as an actor —
                # fail loud.
                b_name = boot.get("graphic", {}).get("character_name") or ""
                b_opacity = boot.get("graphic", {}).get("opacity", 255)
                b_trigger = boot.get("trigger")
                if b_name and b_opacity > 0 and not is_door_sheet(b_name):
                    continue  # emits as a normal object below
                if (not b_name and b_trigger in (TRIGGER_ACTION, TRIGGER_EVENT_TOUCH)) or (
                    b_name and b_opacity == 0 and b_trigger == TRIGGER_EVENT_TOUCH
                ):
                    raise ValueError(
                        f"map {uid} EV{eid:03d}: required actor's boot page emits "
                        f"as a bg/coord event — cannot also place it as an actor"
                    )
            hidden_actor_ids.append(eid)

    rock_ids: list[int] = []
    if event_traits is not None:
        _validate_event_traits(event_traits, uid)
        rock_ids = sorted(
            eid for eid, traits in event_traits.items() if TRAIT_SMASHABLE_ROCK in traits
        )
    vis_flags = _assign_visibility_flags(rock_ids, hidden_actor_ids, uid)

    def _drop(event_id: int, reason: str) -> None:
        result.drops.append((event_id, reason))
        logger.info("map %d EV%03d: dropped (%s)", uid, event_id, reason)

    for event in objects:
        eid = event["id"]
        page = select_boot_page(event)
        if page is None:
            # A Trainer(N) sight-ray tripwire is invisible and exists purely
            # as a script host — unlike a real object, it has nothing to
            # "boot into"; its page dispatcher (built from the FULL event
            # below via `_resolve_script`) already gates which page's body
            # actually runs at runtime. So a tripwire whose page 1 happens to
            # be story-gated (no page holds at boot -> `select_boot_page`
            # returns None) must still get its ray coord events — the tiles
            # are just as live as EV074's (whose page 1 happens to be
            # boot-active, letting it slip through the ordinary path). Map032
            # EV078 (ceremony's second exit column, gated on var101==2) and
            # EV080 (a later Theo catch-up tripwire) were both silently
            # dropped before this: pick the FIRST page that's a plausible
            # tripwire host (trigger 2, invisible graphic) as a stand-in for
            # ray parameters (direction/through/opacity); a non-Trainer(N)
            # event, or a Trainer(N) event with no such page, still drops.
            trainer_match = _TRAINER_NAME_RE.search(event.get("name") or "")
            if trainer_match and int(trainer_match.group(1)) >= 1:
                page = next(
                    (
                        p for p in event["pages"]
                        if p.get("trigger") == TRIGGER_EVENT_TOUCH
                        and (
                            p.get("graphic", {}).get("opacity", 255) == 0
                            or not p.get("graphic", {}).get("character_name")
                        )
                    ),
                    None,
                )
            if page is None:
                _drop(eid, DROP_NO_BOOT_PAGE)
                continue

        graphic = page.get("graphic", {})
        name = graphic.get("character_name") or ""
        trigger = page.get("trigger")
        opacity = graphic.get("opacity", 255)

        # Trainer(N) line-of-sight convention (see the module comment above
        # `_TRAINER_NAME_RE`): the name is only live when the SELECTED page is
        # trigger-2 — Essentials' own pbCheckEventTriggerAfterTurning requires
        # that, so a Trainer(N)-named event on any other trigger is inert and
        # falls through to ordinary classification below.
        trainer_sight_n: int | None = None
        if trigger == TRIGGER_EVENT_TOUCH:
            trainer_match = _TRAINER_NAME_RE.search(event.get("name") or "")
            if trainer_match and int(trainer_match.group(1)) >= 1:
                trainer_sight_n = int(trainer_match.group(1))
                if not (opacity == 0 or not name):
                    raise ValueError(
                        f"map {uid} EV{eid:03d} ({event.get('name', '')!r}): "
                        f"visible Trainer({trainer_sight_n}) battle trainer needs "
                        f"the native trainer-object conversion path (trainer_type "
                        f"+ sight radius), which is not built yet"
                    )

        emit_kind: str  # "bg" | "coord" | "object"
        if not name:
            if trigger == TRIGGER_ACTION:
                emit_kind = "bg"
            elif trigger == TRIGGER_EVENT_TOUCH:
                emit_kind = "coord"
            elif trigger == TRIGGER_PLAYER_TOUCH:
                _drop(eid, DROP_BLANK_TRIGGER1)
                continue
            elif trigger == TRIGGER_AUTORUN:
                _drop(eid, DROP_AUTORUN)
                continue
            elif trigger == TRIGGER_PARALLEL:
                _drop(eid, DROP_PARALLEL)
                continue
            else:
                raise ValueError(f"map {uid} EV{eid:03d}: unknown trigger {trigger!r}")
        elif opacity == 0:
            if trigger == TRIGGER_EVENT_TOUCH:
                emit_kind = "coord"
            else:
                _drop(eid, DROP_OPACITY0)
                continue
        elif is_door_sheet(name):
            _drop(eid, DROP_DOOR_SHEET)
            continue
        else:
            emit_kind = "object"

        script, dispatcher = _resolve_script(event, consts, pory_labels, flag_registry)

        if emit_kind == "object":
            # BUG B (findings §3.2): a visible-graphic autorun/parallel page
            # must never be action-button reachable — its body runs only via
            # the ON_FRAME_TABLE channel (compute_autorun_entries). Two
            # shapes: a dispatcher that (thanks to build_page_dispatcher's
            # own trigger check) collapsed to nothing but `end` branches, or
            # a bare page-1 fallback (dispatcher deferred/absent — always
            # page index 0, see `_resolve_script`) whose page is itself
            # trigger 3/4.
            if dispatcher is not None:
                if "goto(" in dispatcher:
                    result.dispatchers.append(dispatcher)
                else:
                    script, dispatcher = NO_SCRIPT, None
            elif script != NO_SCRIPT and event["pages"][0].get("trigger") in (
                TRIGGER_AUTORUN, TRIGGER_PARALLEL,
            ):
                script = NO_SCRIPT
        elif dispatcher is not None:
            result.dispatchers.append(dispatcher)

        if emit_kind == "bg":
            result.bg_events.append(BgEvent(x=event["x"], y=event["y"], script=script))
        elif emit_kind == "coord":
            # RMXP touch triggers (trigger 1 Player Touch / 2 Event Touch) fire on
            # a BUMP — the player pressing into a blocked tile — but porymap
            # coord_events only fire when the player STANDS on the tile (x/y/
            # elevation match). An invisible touch-trigger event sitting on a
            # blocked tile (e.g. Map032 EV074 on a passage-15 decoration) can
            # never be stood on, so its coord event would be dead code on PC.
            # When the event's own tile isn't standable, relocate the coord
            # event to every standable orthogonal neighbor instead (same
            # script/gate), deduped against coords already used. Trainer(N)
            # sight tripwires never reach this branch — the ray path below
            # handles them.
            ex, ey = event["x"], event["y"]
            if trainer_sight_n is not None:
                graphic_dir = graphic.get("direction")
                facing = _TRAINER_SIGHT_FACING.get(graphic_dir)
                if facing is None:
                    raise ValueError(
                        f"map {uid} EV{eid:03d}: Trainer({trainer_sight_n}) "
                        f"tripwire has unrecognized RMXP direction {graphic_dir!r}"
                    )
                through = bool(page.get("through", False))
                ray = _trainer_sight_ray(
                    ex, ey, facing, trainer_sight_n, through, passability
                )
                if not ray:
                    raise ValueError(
                        f"map {uid} EV{eid:03d}: Trainer({trainer_sight_n}) "
                        f"tripwire's sight ray has no standable tile — it could "
                        f"never fire"
                    )
                used = {(ce.x, ce.y) for ce in result.coord_events}
                for tx, ty in ray:
                    if (tx, ty) in used:
                        continue
                    result.coord_events.append(CoordEvent(x=tx, y=ty, script=script))
                    used.add((tx, ty))
            elif passability is not None and not passability.standable(ex, ey):
                used = {(ce.x, ce.y) for ce in result.coord_events}
                neighbors = [
                    (nx, ny)
                    for nx, ny in ((ex + 1, ey), (ex - 1, ey), (ex, ey + 1), (ex, ey - 1))
                    if passability.standable(nx, ny)
                ]
                if not neighbors:
                    raise ValueError(
                        f"map {uid} EV{eid:03d}: touch trigger at ({ex}, {ey}) sits "
                        f"on a blocked tile with no standable orthogonal neighbor — "
                        f"bump-trigger relocation has nowhere to go"
                    )
                for nx, ny in neighbors:
                    if (nx, ny) in used:
                        continue
                    result.coord_events.append(CoordEvent(x=nx, y=ny, script=script))
                    used.add((nx, ny))
            else:
                result.coord_events.append(CoordEvent(x=ex, y=ey, script=script))
        else:
            if npc_gfx is None:
                raise KeyError(
                    f"map {uid} EV{eid:03d}: visible graphic {name!r} needs the npc "
                    f"gfx map — call build_object_events(..., npc_gfx=load_npc_gfx_map"
                    f"(...))"
                )
            try:
                graphics_id = npc_gfx[name]
            except KeyError:
                raise KeyError(
                    f"map {uid} EV{eid:03d}: sheet {name!r} has no reference/"
                    f"npc_gfx_map.json entry"
                ) from None
            spec = movement_spec_for(page)
            if passability is not None and spec.movement_type.startswith(
                ("MOVEMENT_TYPE_WANDER", "MOVEMENT_TYPE_WALK")
            ):
                if passability.exit_blocked(event["x"], event["y"]):
                    spec = static_face_spec(
                        page,
                        "spawn tile blocks leaving in every direction (RMXP "
                        "passage data) — the NPC never moves on PC either",
                    )
                elif spec.path_cells:
                    blocked = [
                        (event["x"] + dx, event["y"] + dy)
                        for dx, dy in spec.path_cells
                        if not passability.cell_clear(event["x"] + dx, event["y"] + dy)
                    ]
                    if blocked:
                        spec = static_face_spec(
                            page,
                            f"walk-sequence loop crosses blocked cell(s) "
                            f"{blocked} — would stall walking-in-place in-engine",
                        )
            elif passability is not None and spec.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE:
                # RMXP move_type_custom only advances the route index when the
                # move actually happened (`skippable or moving? or jumping?`),
                # and a move turns BEFORE it checks passability — so a
                # non-skippable route blocked by static scenery stalls at that
                # command forever, already turned toward it. Simulating the
                # route is the only way to see this: the blocking cell is
                # usually not the spawn tile (an `exit_blocked` spawn check
                # only catches the sealed-in-place case), and the first move
                # command is rarely `list[0]` (409 of 1065 corpus routes open
                # with a change_graphic).
                sim = simulate_route(page, event["x"], event["y"], passability)
                if sim.stalled and not sim.moved:
                    # Never moves on PC: a statue facing its first blocked
                    # command. Drop the route id too — no point interning a
                    # program that never plays, and the interpreter would
                    # force-face it DIR_SOUTH.
                    spec = static_face_spec(
                        page,
                        f"RMXP route stalls at its first executed move without "
                        f"ever moving — blocked at {sim.stall_pos}, leaving it "
                        f"facing {sim.stall_facing} on PC",
                        facing=sim.stall_facing,
                    )
                # sim.stalled and sim.moved -> keep the route: it walks, then
                # freezes where it stalls, which the fixed engine interpreter
                # (collision checked before the PC advances) reproduces exactly.
                # not sim.stalled -> keep the route.
            if spec.demoted is not None:
                logger.warning(
                    "map %d EV%03d: movement demoted to static facing (%s)",
                    uid, eid, spec.demoted,
                )
            if (spec.anchor_dx, spec.anchor_dy) != (0, 0):
                logger.info(
                    "map %d EV%03d: walk-sequence anchor shifts spawn (%d,%d) -> (%d,%d)",
                    uid, eid, event["x"], event["y"],
                    event["x"] + spec.anchor_dx, event["y"] + spec.anchor_dy,
                )
            route_id = "0"
            if spec.route_bytecode is not None:
                if route_registry is None:
                    raise ValueError(
                        f"map {uid} EV{eid:03d}: encodable custom route but no "
                        f"route_registry given — call build_object_events(..., "
                        f"route_registry=RouteRegistry())"
                    )
                route_id = str(route_registry.intern(spec.route_bytecode))
            result.object_events.append(
                ObjectEvent(
                    x=event["x"] + spec.anchor_dx, y=event["y"] + spec.anchor_dy,
                    graphics_id=graphics_id,
                    script=script, movement_type=spec.movement_type,
                    movement_range_x=spec.range_x, movement_range_y=spec.range_y,
                    flag=vis_flags.get(eid, "0"),
                    route_id=route_id,
                )
            )
            result.local_id_map[str(eid)] = len(result.object_events)

    # --- hidden cutscene actors (findings §3.3/§5) ---------------------------
    for eid in hidden_actor_ids:
        actor_event = event_by_id[eid]
        actor_pages = actor_event["pages"]
        graphic_idx = next(
            (i for i, p in enumerate(actor_pages) if p.get("graphic", {}).get("character_name")),
            None,
        )
        if graphic_idx is None:
            raise ValueError(
                f"map {uid} EV{eid:03d}: required actor has no page with a "
                f"character_name graphic to place it with"
            )
        actor_page = actor_pages[graphic_idx]
        actor_name = actor_page["graphic"]["character_name"]
        if npc_gfx is None:
            raise KeyError(
                f"map {uid} EV{eid:03d}: hidden cutscene actor {actor_name!r} "
                f"needs the npc gfx map — call build_object_events(..., "
                f"npc_gfx=load_npc_gfx_map(...))"
            )
        try:
            actor_gfx = npc_gfx[actor_name]
        except KeyError:
            raise KeyError(
                f"map {uid} EV{eid:03d}: sheet {actor_name!r} has no "
                f"reference/npc_gfx_map.json entry"
            ) from None

        actor_spec = static_face_spec(
            actor_page,
            "hidden cutscene actor: choreographed by another event's "
            "script, placed static behind a visibility flag (findings "
            "§3.3/§5)",
        )

        actor_script, actor_dispatcher = _resolve_script(
            actor_event, consts, pory_labels, flag_registry
        )
        if actor_dispatcher is not None:
            if "goto(" in actor_dispatcher:
                result.dispatchers.append(actor_dispatcher)
            else:
                actor_script, actor_dispatcher = NO_SCRIPT, None
        elif actor_script != NO_SCRIPT and actor_pages[0].get("trigger") in (
            TRIGGER_AUTORUN, TRIGGER_PARALLEL,
        ):
            actor_script = NO_SCRIPT

        lines, always_visible = _visibility_transition_lines(
            actor_pages, uid, eid, actor_event.get("name", ""),
            vis_flags[eid], flag_registry,
        )
        actor_flag = "0" if always_visible else vis_flags[eid]
        if lines:
            result.transition_lines.extend(lines)

        result.object_events.append(
            ObjectEvent(
                x=actor_event["x"], y=actor_event["y"], graphics_id=actor_gfx,
                script=actor_script, movement_type=actor_spec.movement_type,
                flag=actor_flag,
            )
        )
        result.local_id_map[str(eid)] = len(result.object_events)

    if len(result.object_events) > 64:
        raise ValueError(
            f"map {uid}: {len(result.object_events)} object_events exceeds "
            f"the 64-slot OBJECT_EVENT_TEMPLATES_COUNT budget"
        )

    if event_traits is not None:
        emitted_ids = {int(k) for k in result.local_id_map}
        for eid in event_traits:
            if eid not in emitted_ids:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: traits sidecar references this event "
                    f"but no object event was emitted for it (stale sidecar, or "
                    f"the event was dropped by boot-page classification — "
                    f"re-run the transpile driver)"
                )

    return result


def write_local_id_tables(out_dir: Path, tables: dict[int, dict[str, int]]) -> None:
    """Write one local-id table per map: `Map{map_id:03d}.json` holding exactly
    `{str(rmxp_event_id): 1_based_local_id}` for that map's emitted objects
    (`ObjectBuildResult.local_id_map`). PINNED contract — another module consumes
    this exact shape; do not deviate (CLAUDE.md §4.3)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for map_id, table in tables.items():
        path = out_dir / f"Map{map_id:03d}.json"
        path.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")


def _return_warp_index(dest_warps: list[WarpSpec], source_uid: int) -> int:
    """Index of the destination map's warp that returns to `source_uid` (the player
    arrives on it). Falls back to 0 with a warning if there's no clean return."""
    for i, spec in enumerate(dest_warps):
        if spec.dest_uid == source_uid:
            return i
    logger.warning("no return warp to map %d found; defaulting dest_warp_id=0", source_uid)
    return 0


def _map_dims(map_json: dict) -> tuple[int, int]:
    return map_json["width"], map_json["height"]


@dataclass(frozen=True)
class ArrivalFacing:
    """Where the player lands, and which way Uranium says they should face."""

    x: int
    y: int
    dir_const: str  # an engine DIR_* constant


def compute_arrival_facings(
    warp_lists: dict[int, list[WarpSpec]],
    maps: dict[int, dict],
) -> dict[int, list[ArrivalFacing]]:
    """Per-map arrival coord -> post-warp facing, from each spec's `dest_dir`.

    Realized as an ON_WARP_INTO_MAP_TABLE map script rather than arrival-tile
    metatile behaviors: the `MB_*_ARROW_WARP` behaviors that would produce the
    same facing natively are also *live step-triggers* (`TryArrowWarp`), and the
    engine pairs each one's trigger direction with the direction a player
    naturally looks right after arriving — so they re-warp on the way out. See
    `WARP_FACING_HANDOFF.md` (git stash) for the full trace.

    Skips `dest_dir` 0/None (no override -> engine default; see
    `_ARRIVAL_DIR_CONST`) and out-of-bounds arrivals, which get no arrival
    warp_event of their own in `_resolve_all_warp_events` and so have no distinct
    landing tile to key on.

    Fail-loud (§4.5) on an unknown non-zero direction, and on two arrivals
    sharing one coord with different facings — coordinate dispatch cannot tell
    those apart, and silently picking one would be wrong half the time.
    """
    out: dict[int, list[ArrivalFacing]] = {}
    seen: dict[tuple[int, int, int], str] = {}
    for src_uid, specs in warp_lists.items():
        for spec in specs:
            if spec.dest_dir in (0, None):
                continue
            dir_const = _ARRIVAL_DIR_CONST.get(spec.dest_dir)
            if dir_const is None:
                raise ValueError(
                    f"map {src_uid} warp -> {spec.dest_uid}: unknown RMXP transfer "
                    f"direction {spec.dest_dir!r} (expected one of 0/2/4/6/8)"
                )
            dest_map_json = maps.get(spec.dest_uid)
            if dest_map_json is not None:
                width, height = _map_dims(dest_map_json)
                if not (0 <= spec.dest_x < width and 0 <= spec.dest_y < height):
                    continue  # no arrival warp_event exists; nothing to key on

            key = (spec.dest_uid, spec.dest_x, spec.dest_y)
            existing = seen.get(key)
            if existing is not None:
                if existing != dir_const:
                    raise ValueError(
                        f"map {spec.dest_uid} arrival ({spec.dest_x}, {spec.dest_y}): "
                        f"conflicting arrival facings {existing} vs {dir_const} — two "
                        f"warps land on one tile wanting different directions, which "
                        f"coordinate dispatch cannot distinguish"
                    )
                continue  # same coord, same facing: one table row covers both
            seen[key] = dir_const
            out.setdefault(spec.dest_uid, []).append(
                ArrivalFacing(spec.dest_x, spec.dest_y, dir_const)
            )
    return out


def _on_warp_block(
    consts: MapConstants, facings: list[ArrivalFacing]
) -> tuple[str, str] | None:
    """The ON_WARP_INTO_MAP_TABLE entry + its facing script, shared by
    `render_arrival_facing_script` (standalone caller/tests) and
    `render_map_scripts` (the unified emitter). Returns
    `(table_entry, script_text)`, or `None` for no facings.

    Uses the vanilla ON_WARP_INTO_MAP_TABLE idiom (see any Battle Frontier
    lobby): the table fires when VAR_TEMP_1 == 0, and the script guards
    itself by setting it. The hook runs in `InitObjectEventsLocal`
    (overworld.c) *after* `InitPlayerAvatar` has applied the engine's default
    facing and well before the screen fades in, so the turn is invisible.

    Every command here must be non-blocking: `TryRunOnWarpIntoMapScript` uses
    `RunScriptImmediately`, which runs the script to completion in one call."""
    if not facings:
        return None
    label = f"{consts.dir_name}_OnWarpFacing"
    table_entry = f"{_FACING_GUARD_VAR}, 0: {label}"
    lines = [
        f"script {label} {{",
        f"    setvar({_FACING_GUARD_VAR}, 1)",
        f"    getplayerxy({_FACING_X_VAR}, {_FACING_Y_VAR})",
    ]
    for i, f in enumerate(sorted(facings, key=lambda a: (a.y, a.x))):
        kw = "if" if i == 0 else "elif"
        lines.append(
            f"    {kw} (var({_FACING_X_VAR}) == {f.x} "
            f"&& var({_FACING_Y_VAR}) == {f.y}) {{"
        )
        lines.append(f"        turnobject(LOCALID_PLAYER, {f.dir_const})")
        lines.append("    }")
    lines.append("}")
    return table_entry, "\n".join(lines)


def render_arrival_facing_script(
    consts: MapConstants, facings: list[ArrivalFacing]
) -> str | None:
    """The `mapscripts` + on-warp facing script for one map, as poryscript —
    a thin wrapper around `_on_warp_block` kept for its own callers/tests.
    `render_map_scripts` is the unified emitter (ON_TRANSITION +
    ON_FRAME_TABLE + this table, whichever sections are non-empty) that
    `build_slice_maps` actually wires up now.

    Returns None when the map has no arrival needing an override — the caller
    then leaves the empty `mapscripts` stub alone."""
    on_warp = _on_warp_block(consts, facings)
    if on_warp is None:
        return None
    table_entry, script_text = on_warp
    return (
        f"mapscripts {consts.dir_name}_MapScripts {{\n"
        "    MAP_SCRIPT_ON_WARP_INTO_MAP_TABLE [\n"
        f"        {table_entry}\n"
        "    ]\n"
        "}\n\n"
        f"{script_text}"
    )


def render_map_scripts(
    consts: MapConstants,
    facings: list[ArrivalFacing],
    frame_entries: list[AutorunEntry],
    transition_lines: list[str],
) -> str | None:
    """The unified per-map `mapscripts` block: one `<Dir>_MapScripts` symbol
    carrying whichever of ON_TRANSITION / ON_FRAME_TABLE / ON_WARP_INTO_MAP_
    TABLE are non-empty, in that order (findings §3.2/§5) — there can be only
    ONE mapscripts block per map, so this generalizes what
    `render_arrival_facing_script` did for the warp-facing case alone.

    - ON_TRANSITION: inlined, body = `transition_lines` (hidden cutscene
      actor visibility — `ObjectBuildResult.transition_lines`).
    - ON_FRAME_TABLE: one row (`VAR_TEMP_C, 0: <Dir>_OnFrame`) plus the
      `<Dir>_OnFrame` dispatcher script, from `frame_entries`
      (`compute_autorun_entries`).
    - ON_WARP_INTO_MAP_TABLE: unchanged from `render_arrival_facing_script`
      (`_on_warp_block`), byte-compatible with the existing warp-facing pins.

    Returns None when all three sections are empty — the caller keeps
    today's empty-`mapscripts`-stub behavior."""
    sections: list[str] = []
    scripts: list[str] = []

    if transition_lines:
        body = "\n".join(f"        {ln}" for ln in transition_lines)
        sections.append("    MAP_SCRIPT_ON_TRANSITION {\n" + body + "\n    }")

    if frame_entries:
        onframe_label = f"{consts.dir_name}_OnFrame"
        sections.append(
            "    MAP_SCRIPT_ON_FRAME_TABLE [\n"
            f"        {_ON_FRAME_GUARD_VAR}, 0: {onframe_label}\n"
            "    ]"
        )
        scripts.append(_render_onframe_script(onframe_label, frame_entries))

    on_warp = _on_warp_block(consts, facings)
    if on_warp is not None:
        table_entry, warp_script = on_warp
        sections.append(
            "    MAP_SCRIPT_ON_WARP_INTO_MAP_TABLE [\n"
            f"        {table_entry}\n"
            "    ]"
        )
        scripts.append(warp_script)

    if not sections:
        return None

    block = f"mapscripts {consts.dir_name}_MapScripts {{\n" + "\n".join(sections) + "\n}"
    return "\n\n".join([block] + scripts)


def _resolve_all_warp_events(
    warp_lists: dict[int, list[WarpSpec]],
    registry: MapConstantRegistry,
    maps: dict[int, dict],
) -> dict[int, list[WarpEvent]]:
    """Batch-level warp resolution (needs every map's warp list up front).

    Pairing (the vanilla-Emerald landing trick): a warp from map A to map B lands
    the player on B's warp_event index `dest_warp_id` — there is no free-coordinate
    landing in the schema. So for every source warp A->B at Uranium arrival coords
    (dx, dy) we emit an extra plain-floor "arrival" warp_event on B at (dx, dy) and
    point the source warp's dest_warp_id at it. The arrival tile is plain floor
    (MB_NORMAL), so it never step-triggers on its own. Two source warps landing on
    the same (dx, dy) in B share one arrival (deduped by (dx, dy, source_uid)).

    Source warps keep their original per-map indices 0..n-1 (stable); arrivals are
    appended after, so source indices never shift regardless of arrival ordering.

    If (dx, dy) falls outside the destination map's bounds, no arrival is emitted
    for that warp and it falls back to the old `_return_warp_index` pairing (paired
    to the destination's return warp) — logged loud, not silently dropped.

    Returns the full per-map warp_event list (source warps first, then arrivals),
    keyed by Uranium map id.
    """
    # Pass 1: source warps, stable original order/index.
    events: dict[int, list[WarpEvent]] = {
        uid: [WarpEvent(s.src_x, s.src_y, registry.get(s.dest_uid).map_const) for s in specs]
        for uid, specs in warp_lists.items()
    }

    # Pass 2: append arrivals to each destination map, wiring dest_warp_id back.
    arrival_index: dict[tuple[int, int, int], int] = {}  # (dest_uid, dx, dy, src_uid) key below
    for src_uid, specs in warp_lists.items():
        for i, spec in enumerate(specs):
            dest_uid = spec.dest_uid
            dest_map_json = maps.get(dest_uid)
            in_bounds = False
            if dest_map_json is not None:
                width, height = _map_dims(dest_map_json)
                in_bounds = 0 <= spec.dest_x < width and 0 <= spec.dest_y < height
            if not in_bounds:
                logger.warning(
                    "warp %d -> %d: arrival coords (%d, %d) out of bounds for map %d; "
                    "falling back to return-warp pairing",
                    src_uid, dest_uid, spec.dest_x, spec.dest_y, dest_uid,
                )
                events[src_uid][i].dest_warp_id = _return_warp_index(
                    warp_lists.get(dest_uid, []), src_uid
                )
                continue

            dedup_key = (dest_uid, spec.dest_x, spec.dest_y, src_uid)
            if dedup_key in arrival_index:
                events[src_uid][i].dest_warp_id = arrival_index[dedup_key]
                continue

            source_const = registry.get(src_uid).map_const
            dest_events = events.setdefault(dest_uid, [])
            arrival_idx = len(dest_events)
            dest_events.append(WarpEvent(spec.dest_x, spec.dest_y, source_const, i))
            arrival_index[dedup_key] = arrival_idx
            events[src_uid][i].dest_warp_id = arrival_idx

    return events


def wire_encounters(uranium_map_id: int, encounters_path: Path) -> dict | None:
    """The map's wild-encounter entry (for the global wild_encounters.json), or None
    if it has no wild slots. Read intermediate/wild_encounters.json (Uranium id)."""
    if not encounters_path.exists():
        return None
    table = json.loads(encounters_path.read_text(encoding="utf-8"))
    entry = table.get(str(uranium_map_id))
    return entry or None


# --- slice driver ------------------------------------------------------------

def _map_type_for(uid: int, metadata_path: Path) -> str:
    """TOWN if the map is outdoor (metadata `outdoor` flag), else INDOOR."""
    meta = json.loads(metadata_path.read_text(encoding="utf-8")).get("maps", {})
    entry = meta.get(str(uid)) or {}
    return "MAP_TYPE_TOWN" if entry.get("outdoor") else "MAP_TYPE_INDOOR"


def build_slice_maps(
    slice_ids: list[int],
    *,
    maps_dir: Path,
    registry: MapConstantRegistry,
    metadata_path: Path,
    out_dir: Path,
    dispatcher_dir: Path,
    pory_labels: set[str] | None = None,
    npc_gfx: dict[str, str] | None = None,
    local_id_dir: Path | None = None,
    event_traits: dict[int, dict[int, list[str]]] | None = None,
    flag_registry: FlagRegistry | None = None,
    tilesets_path: Path | None = None,
    walkable_overrides: dict[int, frozenset[tuple[int, int]]] | None = None,
    route_registry: RouteRegistry | None = None,
    required_actor_ids: dict[int, set[int]] | None = None,
) -> dict[int, set[tuple[int, int]]]:
    """Assemble map.json + dispatcher .pory for every slice map. Returns the per-map
    warp-source coords (S3 walkable-overrides) so S8 can force those cells walkable.
    Warp pairing needs every map's warp list first, so this is a slice-level pass.

    `route_registry` (a `route_bytecode.RouteRegistry`), when given, is
    forwarded to every `build_object_events` call so custom-route movers across
    the whole slice dedup into one shared id space (caller-owned, exactly like
    `flag_registry` — this function never constructs one internally).

    `flag_registry` (a `FlagRegistry`, distinct from `registry`'s `MapConstantRegistry`
    above), when given, is forwarded to `build_object_events` so multi-page events
    gated on a global switch/var get a real dispatcher instead of deferring.

    `npc_gfx` (character_name -> OBJ_EVENT_GFX_* — see `npc_gfx.load_npc_gfx_map`)
    is forwarded to `build_object_events`; omit it only for callers that don't
    place any visible NPC (a visible graphic with no map raises loud). When
    `local_id_dir` is given, the per-map RMXP-id -> porymap-local-id tables are
    also written there via `write_local_id_tables` (the pinned local-id contract).

    `event_traits` is keyed by Uranium map id -> that map's `build_object_events`
    `event_traits` dict (event id -> trait list; see `Map{id:03d}.traits.json`,
    stage_slice_scripts.py). A map absent from the outer dict, or `event_traits`
    itself being `None`, is legacy behavior for that map (all flags "0").

    `tilesets_path` (the Phase-3 `tilesets.json`), when given, builds a per-map
    `npc_gfx.MapPassability` and forwards it to `build_object_events` so moving
    NPCs are gated against the map data (spawn-locked NPCs and stall-prone
    walk-sequence loops demote loud — see there). `walkable_overrides` (Uranium
    map id -> cells, normally `map_set.WALKABLE_OVERRIDES`) are the converter-
    level collision unblocks those gates must treat as open — the SAME cells the
    layout pass forces walkable, or the two passes would disagree (§4.3).

    `required_actor_ids` (Uranium map id -> RMXP event ids some script on
    that map choreographs — see `build_object_events`'s hidden-actor
    parameter of the same name) is forwarded per-map; a map absent from the
    outer dict, or the dict itself being `None`, passes `None` through
    (legacy: no hidden actors on that map)."""
    slice_set = set(slice_ids)
    tilesets = (
        json.loads(tilesets_path.read_text(encoding="utf-8"))
        if tilesets_path is not None
        else None
    )
    maps = {
        uid: json.loads((maps_dir / f"Map{uid:03d}.json").read_text(encoding="utf-8"))
        for uid in slice_ids
    }
    warp_lists = {
        uid: [spec for _e, spec in classify_map_events(maps[uid], slice_set)[1]]
        for uid in slice_ids
    }
    resolved = _resolve_all_warp_events(warp_lists, registry, maps)
    arrival_facings = compute_arrival_facings(warp_lists, maps)

    overrides: dict[int, set[tuple[int, int]]] = {}
    local_id_tables: dict[int, dict[str, int]] = {}
    for uid in slice_ids:
        consts = registry.get(uid)
        warp_events = resolved.get(uid, [])
        src_coords = {(s.src_x, s.src_y) for s in warp_lists[uid]}
        map_traits = event_traits.get(uid) if event_traits is not None else None
        passability = None
        if tilesets is not None:
            tileset_id = maps[uid]["tileset_id"]
            try:
                tileset = tilesets[str(tileset_id)]
            except KeyError:
                raise KeyError(
                    f"map {uid}: tileset {tileset_id} missing from {tilesets_path}"
                ) from None
            passability = MapPassability.from_map(
                maps[uid], tileset,
                open_cells=(walkable_overrides or {}).get(uid, frozenset()),
            )
        result = build_object_events(
            maps[uid], consts, slice_set, pory_labels=pory_labels, npc_gfx=npc_gfx,
            event_traits=map_traits, flag_registry=flag_registry,
            passability=passability, route_registry=route_registry,
            required_actor_ids=(required_actor_ids or {}).get(uid),
        )
        overrides[uid] = src_coords
        local_id_tables[uid] = result.local_id_map

        map_file = MapFile(
            consts=consts,
            map_type=_map_type_for(uid, metadata_path),
            object_events=result.object_events,
            warp_events=warp_events,
            coord_events=result.coord_events,
            bg_events=result.bg_events,
            local_id_map=result.local_id_map,
        )
        map_out = out_dir / consts.dir_name / "map.json"
        map_out.parent.mkdir(parents=True, exist_ok=True)
        map_out.write_text(json.dumps(map_file.to_json_dict(), indent=2) + "\n", encoding="utf-8")
        # The unified mapscripts block rides the dispatcher channel: the
        # assembler appends this file before deciding whether to inject an
        # empty `mapscripts` stub, so a real `mapscripts` block here
        # suppresses the stub.
        blocks = list(result.dispatchers)
        # Autorun pages only exist for placeable object events — a door's
        # trigger-3 animation page (the event classifies as a WarpSpec, its
        # native warp subsumes the choreography) must not become an ON_FRAME
        # entry referencing a page block the prune pass removes.
        autorun_objects, _, _ = classify_map_events(maps[uid], slice_set)
        frame_entries = compute_autorun_entries(autorun_objects, uid, flag_registry)
        map_scripts = render_map_scripts(
            consts, arrival_facings.get(uid, []), frame_entries, result.transition_lines,
        )
        if map_scripts is not None:
            blocks.append(map_scripts)

        disp_out = dispatcher_dir / f"Map{uid:03d}_dispatch.pory"
        if blocks:
            disp_out.parent.mkdir(parents=True, exist_ok=True)
            disp_out.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
        elif disp_out.exists():
            # Idempotence (CLAUDE.md §4.2): a prior run may have emitted a
            # dispatcher for an event this run now drops (boot-page selection can
            # reclassify a multi-page event to a bg/coord/no-emit). Remove the
            # stale file so no consumer appends a dispatcher whose page bodies the
            # prune has since removed (a dangling goto).
            disp_out.unlink()
        for drop_eid, reason in result.drops:
            logger.info("map %d EV%03d: dropped (%s)", uid, drop_eid, reason)
        logger.info(
            "map %d (%s): %d objects, %d warps, %d coord, %d bg, %d dispatchers, %d dropped",
            uid, consts.map_const, len(result.object_events), len(warp_events),
            len(result.coord_events), len(result.bg_events), len(result.dispatchers),
            len(result.drops),
        )
    if local_id_dir is not None:
        write_local_id_tables(local_id_dir, local_id_tables)
    return overrides


def build_warps_only_maps(
    map_ids: list[int],
    *,
    maps_dir: Path,
    registry: MapConstantRegistry,
    metadata_path: Path,
    out_dir: Path,
) -> dict[int, set[tuple[int, int]]]:
    """Assemble a WARPS-ONLY map.json for every map in `map_ids` (the Map Walker
    corpus, map_walker_plan §5.3): only warp_events, no object/coord/bg events and no
    Poryscript dispatchers. Returns the per-map warp-source coords so the layout pass
    can stamp the warp metatile (S3 walkable-override) at each.

    Warps to maps OUTSIDE the batch are dropped (classify_event's out-of-slice "skip"
    rule) — the walker simply can't follow them (map_walker_plan decision #10). Warp
    pairing needs every batch map's warp list first, so this is a batch-level pass."""
    id_set = set(map_ids)
    maps = {
        uid: json.loads((maps_dir / f"Map{uid:03d}.json").read_text(encoding="utf-8"))
        for uid in map_ids
    }
    warp_lists = {
        uid: [spec for _e, spec in classify_map_events(maps[uid], id_set)[1]]
        for uid in map_ids
    }
    resolved = _resolve_all_warp_events(warp_lists, registry, maps)

    overrides: dict[int, set[tuple[int, int]]] = {}
    for uid in map_ids:
        consts = registry.get(uid)
        warp_events = resolved.get(uid, [])
        # Only the source-warp coords are walkable overrides — arrivals are plain
        # floor; stamping the warp metatile there would recreate the bug we fixed.
        overrides[uid] = {(s.src_x, s.src_y) for s in warp_lists[uid]}

        map_file = MapFile(
            consts=consts,
            map_type=_map_type_for(uid, metadata_path),
            object_events=[],
            warp_events=warp_events,
        )
        map_out = out_dir / consts.dir_name / "map.json"
        map_out.parent.mkdir(parents=True, exist_ok=True)
        map_out.write_text(json.dumps(map_file.to_json_dict(), indent=2) + "\n", encoding="utf-8")
        logger.info("map %d (%s): warps-only, %d warps", uid, consts.map_const, len(warp_events))
    return overrides
