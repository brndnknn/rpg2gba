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
    TERMINAL_HIDE_FLAG_PLACEHOLDER,
    FlagRegistry,
    resolve_switch_flag,
    resolve_variable_var,
    self_switch_flag_name,
)
from ..conversion_agent.orchestrator import load_map_event_strips
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
from .stairs import StairSide, stair_cell_sides, stair_event_ids

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
#   - VISIBLE (opacity 255): a real battle trainer. These take the ordinary
#     `emit_kind = "object"` path (a normal NPC object_event) but with
#     movement forced to static and `trainer_type = TRAINER_TYPE_NORMAL` /
#     `trainer_sight_or_berry_tree_id = N` — the native trainer-object
#     conversion path (see `ObjectEvent`'s docstring for the field-collision
#     rationale). Guarded by `trainer_battle_event_ids` in
#     `build_object_events`: a visible Trainer(N) whose script never reaches
#     a `trainerbattle_*` call converts as an ordinary NPC instead (a sight
#     trainer with no battle at the end is a dead trigger engine-side).
_TRAINER_NAME_RE = re.compile(r"Trainer\((\d+)\)")

# Drop-report reasons (metadata_wiring.build_object_events) — informational tags,
# not an exhaustive enum; new reasons are fine as long as they're logged loud.
DROP_NO_BOOT_PAGE = "no_boot_page"  # no page's condition holds at boot state
DROP_BLANK_TRIGGER1 = "blank_trigger1"  # blank graphic, player-touch (non-warp)
DROP_AUTORUN = "autorun"  # blank graphic, autorun trigger — map-script territory
DROP_PARALLEL = "parallel"  # blank graphic, parallel trigger — map-script territory
DROP_DOOR_SHEET = "door_sheet"  # visible graphic is a door-tile sheet (stripped)
DROP_OPACITY0 = "opacity0"  # invisible (opacity 0) graphic, non-touch trigger
DROP_STRIPPED = "stripped"  # explicit reference/strip_list.json map_events entry (CLAUDE.md §4.3)
DROP_STAIR = "stair"  # diagonal-stair event — native metatile behavior replaces the script

# Object-event traits (upstream transpile-driver sidecar, `Map{id:03d}.traits.json`
# — see stage_slice_scripts.py). Any string outside KNOWN_TRAITS is a fail-loud
# forward-compat error (CLAUDE.md §4.5).
TRAIT_SMASHABLE_ROCK = "smashable_rock"
# A move route that ends in a permanent opacity-0 hide (transpiler.py
# `_insert_terminal_hide_removeobject`) — the transpiler emits `removeobject`
# and a matching `setflag`; this trait tells us which object template needs
# the SAME flag (`FlagRegistry.mint_hide_flag`) instead of the "0" null
# sentinel, or the respawn gate (`TrySpawnObjectEvents`) brings the NPC back
# on the next step (the Map050 boot-walk regression).
TRAIT_TERMINAL_HIDE = "terminal_hide"
# The idiom-collapse classifier layer (conversion_agent/deterministic.py,
# entered via deterministic.try_deterministic) sometimes folds a WHOLE
# multi-page event into a single Poryscript block on purpose — e.g. the
# trainer-battle classifier folding a line-of-sight trainer's pre-battle page
# and its "already beaten" chat page into one block whose
# trainerbattle_single(...) call carries the after-battle text natively, so
# only page 1 is emitted. transpile_driver.py records this trait when the
# classifier claims an event but emits only SOME of its canonical page
# labels; `_resolve_script` reads it to skip building a dispatcher (which
# would otherwise fail loud on the "missing" pages) and resolve straight to
# the page-1 label instead.
TRAIT_COLLAPSED_PAGES = "collapsed_pages"
KNOWN_TRAITS = {TRAIT_SMASHABLE_ROCK, TRAIT_TERMINAL_HIDE, TRAIT_COLLAPSED_PAGES}


# --- native item ball / berry tree templates (upstream transpile-driver sidecar,
# `Map{id:03d}.template_fields.json` — see stage_slice_scripts.py) ------------
#
# CLAUDE.md §4.7: item balls and berry plants convert to the fork's NATIVE
# object-event systems (engine/src/item_ball.c, engine/data/scripts/
# berry_tree.inc) instead of transpiled Ruby — the engine already implements
# both, so hand-transpiling their Ruby would be reinventing a system that
# already exists. `kind: "item_ball"` / `kind: "berry_tree"` are the only two
# discriminators; any other value is a forward-compat fail-loud error, exactly
# like `KNOWN_TRAITS` above.
TF_KIND_ITEM_BALL = "item_ball"
TF_KIND_BERRY_TREE = "berry_tree"
KNOWN_TEMPLATE_KINDS = {TF_KIND_ITEM_BALL, TF_KIND_BERRY_TREE}

# engine/include/constants/event_objects.h (verified 2026-08-08: OBJ_EVENT_GFX_
# ITEM_BALL=59, OBJ_EVENT_GFX_BERRY_TREE=60). Fixed engine constants, not
# per-event data — never needs a fork_index lookup, unlike `item`/`berry_item`
# below (per-event data straight from the sidecar).
ITEM_BALL_GFX = "OBJ_EVENT_GFX_ITEM_BALL"
BERRY_TREE_GFX = "OBJ_EVENT_GFX_BERRY_TREE"
# engine/include/constants/event_object_movement.h:17.
BERRY_TREE_MOVEMENT_TYPE = "MOVEMENT_TYPE_BERRY_TREE_GROWTH"
# engine/data/scripts/item_ball_scripts.inc:1 / engine/data/scripts/berry_tree.inc:1
# — native asm labels, not #define constants, so they're outside fork_index's
# constants table (which only extracts #define/enum symbols) and are instead
# verified by direct inspection of the vendored engine source.
ITEM_BALL_SCRIPT = "Common_EventScript_FindItem"
BERRY_TREE_SCRIPT = "BerryTreeScript"

# Uranium-minted berry tree ids are RAW INTEGERS (as strings), not named
# BERRY_TREE_* fork #defines. Vanilla names its ids for readability
# (engine/include/constants/berry.h), but this pipeline already puts raw
# integer strings in the very same `trainer_sight_or_berry_tree_id` field for
# a sight trainer's radius (`trainer_route_id`, a plain `str(N)`) and for a
# custom movement route (`RouteRegistry.intern`'s 1-based id) — so a raw int
# needs no fork-side symbol at all, and consuming it here needs NO engine-side
# change. `BERRY_TREE_ID_FIRST` starts past the fork's own named range
# (1..89, berry.h) so a Uranium tree can never collide with a vanilla Hoenn
# tree's save-slot if those maps are still compiled into the ROM alongside the
# converted ones. `BERRY_TREES_COUNT` mirrors engine/include/constants/
# berry.h:148 (`gSaveBlock1Ptr->berryTrees[BERRY_TREES_COUNT]`,
# engine/include/global.h:1134) — the hard cap shared by vanilla AND Uranium
# trees, since it's one save array for the whole ROM.
BERRY_TREE_ID_FIRST = 90
BERRY_TREES_COUNT = 128
BERRY_TREE_ID_CAPACITY = BERRY_TREES_COUNT - BERRY_TREE_ID_FIRST  # 38

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


def action_dispatch_label(map_id: int, event_id: int) -> str:
    """The label of the SECONDARY, action-button dispatcher emitted for an
    event whose primary host is a walk-on `coord_event` but which also has
    action-trigger pages (see `CHANNEL_ACTION` / `build_object_events`)."""
    return f"Map{int(map_id):03d}_EV{int(event_id):03d}_ActionDispatch"


# RMXP gives every PAGE its own trigger, but a converted event reaches the
# player through one of two pokeemerald channels, and a page is only reachable
# on the channel that matches its trigger. Dispatching a page on the wrong
# channel is how an action-button page ends up firing by walking over a tile
# (Map032 EV009 page 4 printed its post-ceremony line on every crossing).
#
# CHANNEL_TOUCH -- a `coord_event`: fires by STANDING on the tile. Only RMXP
#   touch pages (1 Player Touch / 2 Event Touch) belong here.
# CHANNEL_ACTION -- an event's PRIMARY talkable host (a `bg_event` sign whose
#   boot page is action-triggered, or an `object_event`): fires on A. Action
#   pages (0) belong here, and touch pages are ALSO dispatched here: RMXP
#   touch fires on bumping into the event, pokeemerald has no bump-script for
#   a talkable host, and talking to it is the long-standing approximation
#   (228 corpus events depend on it) -- an approximation, not a wrong channel.
# CHANNEL_ACTION_ONLY -- the SECONDARY A-press host an otherwise walk-on event
#   gets for its action pages (`_emit_action_host`). The approximation above
#   must not apply here: this event already has a walk-on host that owns its
#   touch pages, so letting A fire them too would add a trigger RMXP doesn't
#   have (pressing A at Map032 EV009's tile would start the ceremony instead
#   of walking into it).
#
# Autorun/parallel pages (3/4) belong to none of them: their channel is the
# map's ON_FRAME_TABLE (`compute_autorun_entries`).
CHANNEL_TOUCH = "touch"
CHANNEL_ACTION = "action"
CHANNEL_ACTION_ONLY = "action_only"
_CHANNEL_TRIGGERS: dict[str, frozenset[int]] = {
    CHANNEL_TOUCH: frozenset({TRIGGER_PLAYER_TOUCH, TRIGGER_EVENT_TOUCH}),
    CHANNEL_ACTION: frozenset(
        {TRIGGER_ACTION, TRIGGER_PLAYER_TOUCH, TRIGGER_EVENT_TOUCH}
    ),
    CHANNEL_ACTION_ONLY: frozenset({TRIGGER_ACTION}),
}


@dataclass
class ObjectEvent:
    """One placed event -> a pokeemerald object_event entry in map.json.

    `route_id` backs the object_event's `trainer_sight_or_berry_tree_id`
    field, which the engine reads TWO different ways depending on
    `trainer_type`/`movement_type` — a dual use, not two fields, so callers
    must pick exactly one meaning per object:

    - `trainer_type == TRAINER_TYPE_NORMAL`: read as the LOS sight range in
      tiles, checked along the object's facing direction
      (engine/src/trainer_see.c:643-655, `GetTrainerApproachDistance`).
    - `movement_type == MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE`: read as this
      project's custom Uranium route id
      (`sUraniumRoutes[objectEvent->trainerRange_berryTreeId]`,
      engine/src/event_object_movement.c:6251).

    These two uses collide on one field, so an object can never carry both a
    nonzero `trainer_type` and `MOVEMENT_TYPE_URANIUM_CUSTOM_ROUTE` —
    `__post_init__` fails loud on that combination rather than emitting a
    map.json where one meaning silently clobbers the other."""

    x: int
    y: int
    graphics_id: str
    script: str
    flag: str = "0"  # visibility flag (0 = always shown)
    movement_type: str = "MOVEMENT_TYPE_NONE"
    movement_range_x: int = 0
    movement_range_y: int = 0
    elevation: int = DEFAULT_ELEVATION
    route_id: str = "0"  # custom-route registry id, OR a trainer's sight radius — see docstring
    trainer_type: str = "TRAINER_TYPE_NONE"

    def __post_init__(self) -> None:
        if self.trainer_type != "TRAINER_TYPE_NONE" and self.movement_type == MOVEMENT_TYPE_CUSTOM_ROUTE:
            raise ValueError(
                f"ObjectEvent at ({self.x}, {self.y}): trainer_type "
                f"{self.trainer_type!r} collides with movement_type "
                f"{MOVEMENT_TYPE_CUSTOM_ROUTE!r} — both are backed by the same "
                f"trainer_sight_or_berry_tree_id field (trainer_see.c "
                f"GetTrainerApproachDistance vs event_object_movement.c "
                f"sUraniumRoutes), so an object cannot be both a sight trainer "
                f"and a custom-route mover"
            )

    def to_dict(self) -> dict:
        return {
            "graphics_id": self.graphics_id,
            "x": self.x,
            "y": self.y,
            "elevation": self.elevation,
            "movement_type": self.movement_type,
            "movement_range_x": self.movement_range_x,
            "movement_range_y": self.movement_range_y,
            "trainer_type": self.trainer_type,
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
    # Door cells of GATED doors (classify_event). They carry a coord_event
    # instead of a warp_event, but still need the warp metatile override
    # (MB_NON_ANIMATED_DOOR, collision 0) so the player can step into the
    # doorway and trip the gate script — `build_slice_maps` unions these into
    # the per-map override set it returns.
    gated_door_cells: set[tuple[int, int]] = field(default_factory=set)


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


def _page_has_transfer(page: dict) -> bool:
    """Does this single page carry a code-201 Transfer Player?"""
    return any(cmd["code"] == TRANSFER_CODE for cmd in page.get("list", []))


def classify_event(event: dict, slice_ids: set[int]) -> tuple[str, WarpSpec | str | None]:
    """Decide how an event is realized (generic rule that reproduces the S1 keep-list):

    - any code-201 to an OUT-of-slice map -> ("skip", reason): emit nothing (NO-EMIT
      building doors + WALL cave exits — nothing references the missing maps).
    - a player-touch event whose pages ALL transfer to in-slice maps -> ("warp",
      WarpSpec): a real door/stairs warp_event (the object_event is dropped to
      avoid a double warp; its .pory body goes unreferenced).
    - everything else -> ("object", None): an object_event (incl. scripted story
      transfers like the Letter, whose .pory body keeps the warp() call).

    **The every-touch-page requirement is load-bearing** (`reference/findings/
    gated_door_collapse_2026-07-26.md`). A *gated door* — an event whose
    player-touch pages don't ALL transfer — must NOT collapse into an
    unconditional warp_event: doing so silently discards the refusal pages.
    Uranium Map049 EV002 is the canonical case: page 0 (no condition) says
    "I'd better say goodbye to Auntie first." and shoves the player back, page 1
    (switch 52 `Mum`) actually transfers. Collapsing it let the player walk out
    of the starting house before the gate, which is what playtest beat B2
    caught. Map050 EV001 is the same shape (the lab exit, gated `VAR_QUEST_LOG
    >= 1`). Such events fall through to ("object", None) so the normal
    multi-page dispatcher picks the live page and that page's own .pory body
    runs its `warp()` — RMXP semantics preserved, no warp_event to race it.

    Only **player-touch** pages are considered, because only they compete for
    the step-on behavior a warp_event would implement. An autorun/parallel page
    reaches the player through a different channel (ON_FRAME_TABLE) and does not
    make the door conditional: Moki Town's five house doors each pair a
    touch-triggered transfer page with a switch-22 autorun cutscene page, and
    they are correctly still plain warps."""
    transfers = _event_transfers(event)
    if transfers:
        targets = {t[0] for t in transfers}
        if any(t not in slice_ids for t in targets):
            return ("skip", "out-of-slice warp")
        if event["pages"][0].get("trigger") == TRIGGER_PLAYER_TOUCH:
            touch_pages = [
                (i, p) for i, p in enumerate(event["pages"])
                if p.get("trigger") == TRIGGER_PLAYER_TOUCH
            ]
            gate_pages = [i for i, p in touch_pages if not _page_has_transfer(p)]
            if not gate_pages:
                dest_uid, dx, dy, ddir = transfers[0]
                return ("warp", WarpSpec(event["x"], event["y"], dest_uid, dx, dy, ddir))
            logger.info(
                "EV%03d at (%d, %d): gated door — player-touch pages %s carry no "
                "transfer, so it stays an event (dispatcher + per-page warp()), "
                "not a warp_event",
                event["id"], event["x"], event["y"], gate_pages,
            )
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


def _goto_or_end(
    pages: list[dict], uid: int, eid: int, page_idx: int, channel: str
) -> str:
    """``goto(<page label>)``, or bare ``end`` when the target page's own RMXP
    trigger doesn't belong to `channel` (`_CHANNEL_TRIGGERS`).

    Two cases this covers:

    - autorun/parallel (3/4) on either channel — an autorun body is invoked
      only through ON_FRAME_TABLE (`compute_autorun_entries` /
      `_render_onframe_script`), so talking to (or walking onto) such an event
      while that page is active must do nothing (findings §3.2 BUG B);
    - an ACTION page (0) on `CHANNEL_TOUCH` — reachable in RMXP only by
      pressing A at the event, never by walking over it. Dispatching it from
      the `coord_event` made Map032 EV009's post-ceremony line fire on every
      crossing of the west-exit tiles (chapter beat B14, 2026-07-27). Where
      that page still needs an A-press host, `build_object_events` emits one
      (`action_dispatch_label`); this side just refuses to fire it by walking.

    A page silenced here is silenced for THIS channel only — RMXP page
    selection still stops at it, exactly as it does on PC when the active page
    has a trigger the player isn't performing."""
    if pages[page_idx].get("trigger") not in _CHANNEL_TRIGGERS[channel]:
        return "end"
    return f"goto({page_label(uid, eid, page_idx + 1)})"


def build_page_dispatcher(
    event: dict,
    consts: MapConstants,
    flag_registry: FlagRegistry | None = None,
    *,
    channel: str = CHANNEL_ACTION,
    label: str | None = None,
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
    `_goto_or_end` against `channel` (`CHANNEL_ACTION` by default,
    `CHANNEL_TOUCH` for a walk-on `coord_event` host): a page whose own RMXP
    trigger isn't reachable on this channel becomes a bare ``end``. `label`
    overrides the emitted script label (used for the secondary action-button
    dispatcher an otherwise walk-on event gets)."""
    pages = event["pages"]
    uid, eid = consts.uranium_id, event["id"]
    if channel not in _CHANNEL_TRIGGERS:
        raise ValueError(f"unknown dispatch channel {channel!r}")

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

    lines = [f"script {label or dispatch_label(uid, eid)} {{"]
    for cond_str, idx in guards:
        lines += [
            f"    if ({cond_str}) {{",
            f"        {_goto_or_end(pages, uid, eid, idx, channel)}",
            "    }",
        ]
    if fallback_idx is not None:
        lines += [f"    {_goto_or_end(pages, uid, eid, fallback_idx, channel)}", "}"]
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
    *,
    channel: str = CHANNEL_ACTION,
    label: str | None = None,
    collapsed: bool = False,
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
    into a real dispatcher instead of deferring (see its docstring).

    `channel` / `label` pass straight through to `build_page_dispatcher`, so
    the walk-on host of an event resolves against `CHANNEL_TOUCH` while its
    A-press host resolves against `CHANNEL_ACTION`. Note the no-dispatcher
    fallback (page-1 label) is channel-independent by construction: it is only
    reached when dispatch is deferred, and the deferred case already points
    every host at the base page.

    `collapsed` (set by the caller from `TRAIT_COLLAPSED_PAGES`) means the
    idiom-collapse classifier deliberately folded this event's whole
    behavior into ONE block (see the trait's module comment) — no dispatcher
    is built at all and resolution goes straight to the page-1 label, which
    still passes through the bodyless/page-body-gap checks above (a
    collapsed event with no page-1 block at all is a real gap, not a
    legitimate collapse, and must still fail loud)."""
    uid, eid = consts.uranium_id, event["id"]
    if pory_labels is not None and not _event_has_body(event, consts, pory_labels):
        logger.info("map %d EV%03d: no converted .pory body -> static script", uid, eid)
        return NO_SCRIPT, None

    if collapsed:
        script = page_label(uid, eid, 1)
        if pory_labels is not None and script not in pory_labels:
            raise KeyError(
                f"map {uid} EV{eid:03d}: {TRAIT_COLLAPSED_PAGES!r} trait set but "
                f"resolved script label {script} not in the converted .pory — "
                f"the classifier's collapsed block is missing its page-1 label"
            )
        return script, None

    dispatcher = build_page_dispatcher(
        event, consts, flag_registry, channel=channel, label=label
    )
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
        return label or dispatch_label(uid, eid), dispatcher

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


def _emit_action_host(
    event: dict,
    consts: MapConstants,
    result: "ObjectBuildResult",
    pory_labels: set[str] | None,
    flag_registry: FlagRegistry | None,
    *,
    collapsed: bool = False,
) -> None:
    """Give an event whose host is a walk-on `coord_event` a second, A-press
    host for its ACTION pages — a `bg_event` sign on the event's own tile.

    `CHANNEL_TOUCH` silences action pages on the coord side (they must not
    fire by walking), but in RMXP those pages ARE reachable: an action trigger
    responds to pressing A at the event's tile whether or not the event draws
    anything, which is how Map032 EV009's post-ceremony line is meant to be
    read. The sign goes on the event's OWN tile even when the coord events
    were relocated to standable neighbours — a sign is read by facing its
    tile, so an impassable tile is the normal case for one. It dispatches on
    `CHANNEL_ACTION_ONLY`, so it adds exactly the A-press pages and never
    becomes a second way to fire the walk-on ones.

    Emits nothing when the action-channel dispatcher has no reachable page
    (all `end` branches), when the event has no converted body, or when some
    other event already owns a bg_event on that tile (first writer wins; the
    collision is logged rather than silently stacked, since only one would
    ever fire)."""
    uid, eid = consts.uranium_id, event["id"]
    if not any(p.get("trigger") == TRIGGER_ACTION for p in event["pages"]):
        return
    script, dispatcher = _resolve_script(
        event, consts, pory_labels, flag_registry,
        channel=CHANNEL_ACTION_ONLY, label=action_dispatch_label(uid, eid),
        collapsed=collapsed,
    )
    if script == NO_SCRIPT:
        return
    if dispatcher is None:
        # Dispatch deferred (unresolvable gate): the coord host already points
        # at the base page, and a second host on the same body would double it.
        logger.info(
            "map %d EV%03d: action pages present but dispatch deferred — no "
            "separate A-press host emitted", uid, eid,
        )
        return
    if "goto(" not in dispatcher:
        return  # no page is action-reachable after the channel check
    if any((bg.x, bg.y) == (event["x"], event["y"]) for bg in result.bg_events):
        logger.warning(
            "map %d EV%03d: another bg_event already occupies (%d, %d) — "
            "action-page sign not emitted (only one can fire)",
            uid, eid, event["x"], event["y"],
        )
        return
    result.dispatchers.append(dispatcher)
    result.bg_events.append(
        BgEvent(x=event["x"], y=event["y"], script=script)
    )
    logger.info(
        "map %d EV%03d: action pages get an A-press bg_event at (%d, %d) "
        "alongside the walk-on coord event(s)",
        uid, eid, event["x"], event["y"],
    )


DEFAULT_STRIP_LIST_DIR = Path("reference")


def load_stripped_event_ids(
    reference_dir: Path = DEFAULT_STRIP_LIST_DIR,
) -> dict[int, dict[int, str | None]]:
    """Per-map view of reference/strip_list.json's `map_events` (CLAUDE.md §4.3)
    for `build_slice_maps`' `stripped_event_ids` default: {map_id: {event_id:
    expect_name}}. Reuses `conversion_agent.orchestrator.load_map_event_strips`
    — the shared parser for the two accepted entry shapes — grouping its flat
    `{(map_id, event_id): expect_name}` result by map id, so the schema is
    parsed in exactly one place (the orchestrator also reads it, for CE strips
    and its own map-event bookkeeping)."""
    out: dict[int, dict[int, str | None]] = {}
    for (map_id, event_id), expect_name in load_map_event_strips(reference_dir).items():
        out.setdefault(map_id, {})[event_id] = expect_name
    return out


def _validate_event_traits(event_traits: dict[int, list[str]], uid: int) -> None:
    """Fail loud on any trait string outside `KNOWN_TRAITS` (forward-compat)."""
    for eid, traits in event_traits.items():
        for trait in traits:
            if trait not in KNOWN_TRAITS:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: unknown trait {trait!r} in traits "
                    f"sidecar (known traits: {sorted(KNOWN_TRAITS)})"
                )


def _validate_template_fields(
    template_fields: dict[int, dict], uid: int, fork_constants: set[str] | None
) -> None:
    """Fail loud (CLAUDE.md §4.5) on a `template_fields` sidecar entry that's
    malformed, or that names an `item`/`berry_item` ITEM_* constant the fork
    doesn't actually define.

    `fork_constants`, when given (the `fork_index.ForkIndex.constants` set —
    see `build_object_events`'s docstring), gates every `item`/`berry_item`
    value against the REAL fork (CLAUDE.md §4.7 forward check):
    `reference/uranium_id_map.json` is known to carry at least five
    `ITEM_*_BERRY` constants that don't exist in the fork, so a name arriving
    via the sidecar is never treated as proof it's real. `None` skips the
    fork check (unit-test/legacy path) but still validates shape."""
    for eid, payload in template_fields.items():
        kind = payload.get("kind")
        if kind not in KNOWN_TEMPLATE_KINDS:
            raise ValueError(
                f"map {uid} EV{eid:03d}: unknown template_fields kind {kind!r} "
                f"(known kinds: {sorted(KNOWN_TEMPLATE_KINDS)})"
            )
        if kind == TF_KIND_ITEM_BALL:
            item = payload.get("item")
            amount = payload.get("amount")
            if not isinstance(item, str) or not item:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: item_ball missing/invalid 'item' "
                    f"(expected a non-empty ITEM_* constant string)"
                )
            if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: item_ball 'amount' must be an int "
                    f">= 1, got {amount!r}"
                )
            if fork_constants is not None and item not in fork_constants:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: item_ball item {item!r} is not a "
                    f"real fork ITEM_* constant (engine/include/constants/items.h)"
                )
        elif kind == TF_KIND_BERRY_TREE:
            if "berry_item" not in payload:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: berry_tree missing 'berry_item' key"
                )
            berry_item = payload["berry_item"]
            planted = payload.get("planted")
            if not isinstance(planted, bool):
                raise ValueError(
                    f"map {uid} EV{eid:03d}: berry_tree 'planted' must be a "
                    f"bool, got {planted!r}"
                )
            if berry_item is not None:
                if not isinstance(berry_item, str) or not berry_item:
                    raise ValueError(
                        f"map {uid} EV{eid:03d}: berry_tree 'berry_item' must "
                        f"be a non-empty ITEM_*_BERRY constant string, or null"
                    )
                if fork_constants is not None and berry_item not in fork_constants:
                    raise ValueError(
                        f"map {uid} EV{eid:03d}: berry_tree berry_item "
                        f"{berry_item!r} is not a real fork ITEM_*_BERRY "
                        f"constant (engine/include/constants/items.h)"
                    )


def assign_berry_tree_ids(
    template_fields: dict[int, dict[int, dict]],
) -> dict[tuple[int, int], int]:
    """Deterministic, STABLE save-slot ids for every `kind="berry_tree"` sidecar
    entry across the WHOLE slice (`build_slice_maps`' outer `template_fields`
    dict: Uranium map id -> event id -> payload).

    One shared save array backs every berry tree in the ROM
    (`gSaveBlock1Ptr->berryTrees[BERRY_TREES_COUNT]`, engine/include/
    global.h:1134), so ids must be globally unique and assigned in a fixed
    order independent of whatever order the caller's dicts happen to iterate
    in — sorted ascending by `(map_id, event_id)`, mirroring this module's
    other budget-pool assignments (`_assign_visibility_flags`). Re-running
    with the SAME template_fields input always produces the SAME ids
    (CLAUDE.md §4.2 idempotence).

    Fails loud (CLAUDE.md §4.5) if the count exceeds `BERRY_TREE_ID_CAPACITY`
    (the reserved `BERRY_TREE_ID_FIRST..BERRY_TREES_COUNT-1` band — see its
    module comment for why the band starts past the fork's own named ids)."""
    pairs = sorted(
        (uid, eid)
        for uid, events in template_fields.items()
        for eid, payload in events.items()
        if payload.get("kind") == TF_KIND_BERRY_TREE
    )
    if len(pairs) > BERRY_TREE_ID_CAPACITY:
        raise ValueError(
            f"{len(pairs)} berry_tree template_fields entries exceed the "
            f"reserved id band {BERRY_TREE_ID_FIRST}..{BERRY_TREES_COUNT - 1} "
            f"capacity ({BERRY_TREE_ID_CAPACITY}) — engine/include/constants/"
            f"berry.h BERRY_TREES_COUNT={BERRY_TREES_COUNT}"
        )
    return {pair: BERRY_TREE_ID_FIRST + i for i, pair in enumerate(pairs)}


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


# Code-123 RMXP "Control Self Switch" command (mirrors
# conversion_agent.transpiler.CONTROL_SELF_SWITCH's literal — kept as a local
# constant rather than an import so this module doesn't reach across into the
# transpiler for a single value). Parameters are `[letter: str, value: int]`;
# value 0 means ON.
_CONTROL_SELF_SWITCH_CODE = 123
_SELF_SWITCH_ON = 0


def _self_switch_letters_set_on(page: dict) -> set[str]:
    """Letters this page's raw RMXP command `list` turns ON via a direct
    code-123 "Control Self Switch" command, found anywhere in the list.
    Nesting/indent doesn't matter — this is a conservative "could this page
    set it" scan, not a control-flow simulation (a switch set inside an `if`
    branch still counts; the branch condition isn't evaluated)."""
    letters: set[str] = set()
    for cmd in page.get("list", []):
        if cmd.get("code") != _CONTROL_SELF_SWITCH_CODE:
            continue
        params = cmd.get("parameters") or []
        if len(params) < 2 or not isinstance(params[0], str):
            continue
        if params[1] == _SELF_SWITCH_ON:
            letters.add(params[0])
    return letters


def _terminal_self_switch_hide_flags(
    objects: list[dict], uid: int, flag_registry: FlagRegistry | None
) -> dict[int, str]:
    """General "event hides itself via self switch" idiom (fix B, boot-walk
    finding — Map033 item balls EV002/EV003/EV025/EV050: page 1 gives an item
    and sets self switch A; page 2, gated purely on self switch A, has a
    blank graphic). Once the boot page's script runs, RMXP's page selection
    (highest-index page whose condition holds) permanently shows that blank
    page instead of the sprite. pokeemerald has no "become blank" template
    state — the object must instead DESPAWN, via the SAME self-switch flag
    the transpiled script already sets (`_page_condition_terms` /
    `self_switch_flag_name` / `FlagRegistry.mint_self_switch`) at exactly the
    right moment — reusing it is free; minting a second flag would be both
    wasteful and wrong (the script never sets a second flag to clear).

    Matches an event when:
      * its BOOT page (`select_boot_page`) sets some self-switch letter(s)
        ON via a direct code-123 command (`_self_switch_letters_set_on`);
      * exactly one OTHER page is gated PURELY on one of those letters (no
        switch1/switch2/variable gate alongside it) AND has a blank graphic.

    Returns `{event_id: flag_name}` only for events that match unambiguously;
    every other event is left for the caller's "0" default — this function
    never assigns "0" itself.

    Fails loud (`ValueError`, CLAUDE.md §4.5) when more than one page (or
    more than one distinct letter) qualifies as a blank, purely
    self-switch-gated terminal page for the same event: which page really
    despawns the object can't be resolved from the event alone, and
    guessing risks despawning the wrong thing or missing the real one."""
    result: dict[int, str] = {}
    for event in objects:
        eid = event["id"]
        boot = select_boot_page(event)
        if boot is None:
            continue
        onset_letters = _self_switch_letters_set_on(boot)
        if not onset_letters:
            continue
        matches: list[tuple[dict, str]] = []
        for page in event["pages"]:
            if page is boot:
                continue
            cond = page["condition"]
            if not cond.get("self_switch_valid"):
                continue
            if cond.get("switch1_valid") or cond.get("switch2_valid") or cond.get("variable_valid"):
                continue  # not a PURE self-switch gate
            letter = cond.get("self_switch_ch")
            if letter not in onset_letters:
                continue
            name = page.get("graphic", {}).get("character_name") or ""
            if name:
                continue  # a visible terminal page is a real state change, not a hide
            matches.append((page, letter))
        if not matches:
            continue
        distinct_letters = {letter for _, letter in matches}
        if len(matches) > 1 or len(distinct_letters) > 1:
            raise ValueError(
                f"map {uid} EV{eid:03d}: boot page sets self-switch(es) "
                f"{sorted(onset_letters)} ON and {len(matches)} other "
                f"page(s) (letters {sorted(distinct_letters)}) each qualify "
                f"as a blank, purely self-switch-gated terminal page — "
                f"ambiguous which one despawns this object; resolve by hand"
            )
        _, letter = matches[0]
        flag = self_switch_flag_name(uid, eid, letter)
        if flag_registry is not None:
            flag_registry.mint_self_switch(uid, eid, letter)
        result[eid] = flag
    return result


def collect_through_block_cells(map_json: dict) -> set[tuple[int, int]]:
    """RMXP's real player-passability rule for events (fix A, boot-walk
    finding — Route 1's shoreline cancel-surf triggers Map033 EV143-EV147
    reading as solid walls, (43,11)-(47,11)): `Game_Character#passableEx?`
    (`reference/scripts_dump/021_Game_Character_v17.rb:118-124`) checks, for
    each event on the destination tile with `through == False`::

        return false if self != $game_player || event.character_name != ""

    For the PLAYER (`self == $game_player`), the left operand is always
    false, so the clause collapses to `event.character_name != ""` — the
    OTHER event blocks the player only when it has a NON-BLANK graphic. A
    blank-graphic event — through or not — NEVER blocks the player; that
    branch only matters when `self` is another NPC event doing ITS OWN
    passability check, which is irrelevant here (this function's whole
    purpose is the PLAYER-collision cell set baked into the static layout,
    consumed as `blocked_cells` by `layout.convert_layout`,
    `layout.py:366-367`). Blank-graphic + `through == False` is in fact the
    canonical Essentials way to place a touch-trigger with ZERO player
    collision (a script host, not an obstacle) — the previous version of
    this function had the rule backwards and blocked every one of them.

    A non-blank-graphic event with `through == False` DOES block the player
    per the same rule — but it's already placed as a real `object_event` by
    `build_object_events` (bg-sign / coord-trigger / drop classification
    doesn't apply to it; it gets an actual sprite), and pokeemerald's native
    object_event collision blocks that tile on its own. Stamping it again
    here would be redundant, so it's still excluded — same as before the fix,
    just no longer the load-bearing half of the rule.

    Net effect: this function no longer contributes any cells from ordinary
    RMXP event blocking (neither branch above adds one) — RMXP genuinely
    never uses a blank invisible sprite to block the player; every case that
    LOOKED like it did (working warp doors, out-of-slice NO-EMIT doors, the
    Map033 EV101 empty berry-soil patch) was this same inverted premise, not
    a real RMXP mechanic. The Map033 EV101 case is a KNOWN, ACCEPTED
    regression for now — a genuinely solid empty berry-soil patch that reads
    passable until a separate wave converts Uranium berry plants to native
    pokeemerald berry trees (real object-event collision restores there).
    Deliberately NOT special-cased here.

    Reuses `select_boot_page` and the same blank-graphic predicate
    (`not character_name`) `build_object_events` uses, so the two can never
    disagree about which page an event shows at boot or what counts as
    "blank" (CLAUDE.md §4.3 — one notion of blank graphic / boot page).

    Diagonal-stair events (`stairs.stair_event_ids`) are excluded up front
    too, for symmetry with `build_object_events` (which also skips them via
    `DROP_STAIR`) even though, under the corrected rule, they would never
    have contributed a cell anyway — kept so this function's exclusion set
    still lines up 1:1 with `build_object_events`'s, not because removing it
    would change behavior."""
    stair_ids = stair_event_ids(map_json)
    cells: set[tuple[int, int]] = set()
    for event in map_json["events"]:
        if event["id"] in stair_ids:
            continue
        page = select_boot_page(event)
        if page is None:
            continue
        if page["through"]:
            continue
        name = page.get("graphic", {}).get("character_name") or ""
        if not name:
            continue  # blank graphic: never blocks the player (see docstring)
        # Non-blank + through=False DOES block the player, but it's already
        # a real object_event with native collision elsewhere — no cell added.
        continue
    return cells


# Stair behavior-override kind strings (layout.convert_layout's
# `behavior_overrides` parameter — see its docstring) — kept in ONE place so
# no call site inlines the "stairs_left"/"stairs_right" literals (CLAUDE.md
# §4.3). Distinct from `stairs.BEHAVIOR_BY_SIDE`, which maps to the engine's
# MB_* metatile-behavior constant names, not these KIND keys.
_STAIR_KIND_BY_SIDE: dict[StairSide, str] = {
    StairSide.LEFT: "stairs_left",
    StairSide.RIGHT: "stairs_right",
}


def collect_stair_behavior_cells(map_json: dict) -> dict[tuple[int, int], str]:
    """{(x, y): "stairs_left" | "stairs_right"} for every diagonal-stair cell on
    this map (`stairs.stair_cell_sides`) — the `behavior_overrides` input
    `layout.convert_layout` stamps with the native sideways-stairs metatile
    behavior and forces passable. Logs the per-map stair-cell count at INFO
    (a conversion fact worth having in build logs, like every other
    drop/placement summary in this module)."""
    sides = stair_cell_sides(map_json)
    map_id = map_json.get("map_id")
    logger.info("map %s: %d diagonal-stair cell(s) found", map_id, len(sides))
    return {xy: _STAIR_KIND_BY_SIDE[side] for xy, side in sides.items()}


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


_EV_PAGE_BLOCK_HEADER_RE = re.compile(r"^script\s+Map(\d+)_EV(\d+)_Page\d+\s*\{")
_TRAINERBATTLE_CALL_RE = re.compile(r"\btrainerbattle_\w+\s*\(")


def trainer_battle_event_ids(pory_text: str, map_id: int) -> set[int]:
    """RMXP event ids on `map_id` whose generated Poryscript carries a
    `trainerbattle_*` call (`trainerbattle_single`/`_double`/`_earlyrival`/
    etc — the transpiler's own naming, see `transpiler.py`) in at least one
    of its `Map{map_id:03d}_EV{eid:03d}_Page{n}` blocks (the same label
    convention `page_label` emits and `assembly.normalize_labels` produces).

    This exists for `build_object_events`'s visible-Trainer(N) guard: a
    sight-trigger object whose script never reaches a `trainerbattle_*`
    opcode is a dead trigger engine-side (`CheckTrainer` in trainer_see.c
    discards the pointer and starts no battle when the script doesn't call
    it), so the caller must know — PER EVENT — whether the conversion
    actually produced a battle before marking the object a sight trainer.

    Scans line-by-line for a block header, then tracks brace depth (counting
    every `{`/`}` on each line) until the block closes, so nested `if`/
    `switch` bodies inside a page don't fool a naive "next column-0 `}`"
    scan. A block whose own text contains the call anywhere counts, even
    inside a nested conditional."""
    ids: set[int] = set()
    lines = pory_text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        header = _EV_PAGE_BLOCK_HEADER_RE.match(lines[i])
        if header is None or int(header.group(1)) != map_id:
            i += 1
            continue
        eid = int(header.group(2))
        depth = lines[i].count("{") - lines[i].count("}")
        block_lines = [lines[i]]
        j = i + 1
        while j < n and depth > 0:
            depth += lines[j].count("{") - lines[j].count("}")
            block_lines.append(lines[j])
            j += 1
        if _TRAINERBATTLE_CALL_RE.search("\n".join(block_lines)):
            ids.add(eid)
        i = j
    return ids


def build_object_events(
    map_json: dict,
    consts: MapConstants,
    slice_ids: set[int],
    *,
    pory_labels: set[str] | None = None,
    npc_gfx: dict[str, str] | None = None,
    npc_gfx_states: dict[str, dict[tuple[int, int], str]] | None = None,
    event_traits: dict[int, list[str]] | None = None,
    flag_registry: FlagRegistry | None = None,
    passability: MapPassability | None = None,
    route_registry: RouteRegistry | None = None,
    required_actor_ids: set[int] | None = None,
    trainer_battle_event_ids: set[int] | None = None,
    stripped_event_ids: dict[int, str | None] | None = None,
    template_fields: dict[int, dict] | None = None,
    berry_tree_ids: dict[int, int] | None = None,
    fork_constants: set[str] | None = None,
) -> ObjectBuildResult:
    """Place every non-warp, non-skipped event per its BOOT-STATE page (RMXP shows
    the highest-index page whose condition holds at boot; `npc_gfx.select_boot_page`).

    - no boot-active page -> dropped (`no_boot_page`).
    - boot page's graphic is blank (no character_name):
        trigger 0 (action)      -> a `sign` bg_event.
        trigger 2 (event touch) -> a `trigger` coord_event.
        trigger 1 (player touch) -> a `trigger` coord_event IF the event carries
                                   a code-201 anywhere (a GATED DOOR that
                                   classify_event refused to collapse into a
                                   warp_event); otherwise dropped
                                   (`blank_trigger1` — inert, no transfer).
        trigger 3 / 4           -> dropped (`autorun` / `parallel` — future
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
                     silent default, CLAUDE.md §4.5), or, for a sheet whose art
                     is emitted state by state (`npc_gfx_states` — the 64x64
                     large props), the constant for the boot page's own
                     `graphic.direction`/`graphic.pattern`, so a prop authored
                     mid-sequence boots showing that state rather than its idle
                     one; and `movement_type`/
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
    `ObjectEvent.flag` stays the "0" default. `collapsed_pages` events (see
    `TRAIT_COLLAPSED_PAGES`) skip dispatcher generation entirely and resolve
    straight to the page-1 label.

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
    hidden actors — legacy behavior.

    `trainer_battle_event_ids` (event ids on this map whose generated
    Poryscript actually contains a `trainerbattle_*` call — see the
    module-level `trainer_battle_event_ids` helper) gates the visible
    Trainer(N) conversion path: an event matching the name convention is
    only wired as a sight trainer (`trainer_type = TRAINER_TYPE_NORMAL`,
    `route_id = str(N)`, movement forced static) when its id is IN this set.
    A visible Trainer(N) whose id is given but absent converts as an
    ordinary NPC instead (logged loud) — engine-side, a sight trainer whose
    script never reaches `trainerbattle_*` is a dead trigger. `None`
    (default) treats every visible Trainer(N) as a battle trainer — this
    intentionally does NOT degrade to "ordinary NPC" for legacy/test callers
    that don't thread the set, since that would silently change behavior for
    every caller that predates this parameter; only an explicit (possibly
    empty) set can demote an event to ordinary-NPC.

    `stripped_event_ids` (event id -> `expect_name`, from THIS map's slice of
    `reference/strip_list.json`'s `map_events` — see `load_stripped_event_ids`)
    drops a whole-artifact STRIP decision (CLAUDE.md §4.3) BEFORE any
    graphics lookup, so a stripped event's sheet never needs an
    `npc_gfx_map.json` entry. Dropped via `_drop(event_id, DROP_STRIPPED)`.
    When the entry names an event (`expect_name` not `None`) and the event's
    actual name differs, fails loud (`ValueError`) — the renumbering guard
    the file's own `_comment` describes. `None` (the parameter's default)
    means no strips for this call, matching `event_traits`' legacy
    semantics — this function never reaches for the reference file itself;
    `build_slice_maps` is where a caller that passes nothing still gets
    `reference/strip_list.json` honored (see its docstring).

    `template_fields` (event id -> `{"kind": "item_ball"|"berry_tree", ...}`,
    from the transpile driver's `Map{id:03d}.template_fields.json` sidecar —
    see the module comment above `TF_KIND_ITEM_BALL`) converts an event
    STRAIGHT to a native pokeemerald object template instead of the ordinary
    NPC/trainer/movement resolution path: an `item_ball` gets
    `graphics_id=OBJ_EVENT_GFX_ITEM_BALL`, `script=Common_EventScript_
    FindItem`, `route_id` = the sidecar's ITEM_* constant, `movement_range_x`
    = its amount, and the SAME hide flag `_terminal_self_switch_hide_flags`
    already assigns it (STD_FIND_ITEM sets the last-talked object's own `flag`
    on pickup — reusing it is the whole point; a resolved "0" flag is a
    fail-loud error, since the ball would then respawn forever). A
    `berry_tree` gets `graphics_id=OBJ_EVENT_GFX_BERRY_TREE`,
    `script=BerryTreeScript`, `movement_type=MOVEMENT_TYPE_BERRY_TREE_GROWTH`,
    `route_id` = its `berry_tree_ids[event_id]` save-slot id (see
    `assign_berry_tree_ids` — must be precomputed over the WHOLE slice's
    template_fields and passed in via `berry_tree_ids`; a berry_tree entry
    with no matching `berry_tree_ids` entry is a fail-loud caller error, not
    silently skipped), and `flag="0"` ALWAYS — never the shared
    `template_flags` pool, even when the event's own RMXP shape happens to
    also match the self-switch-hide idiom (real corpus case: Map033
    EV100/EV102 give their berry once, then self-switch to a blank page —
    exactly the item_ball shape, but on a berry event). A native tree's
    pick/growth state lives entirely in its save slot, never in the object
    template's visibility flag (vanilla convention — every berry tree in
    engine/data/maps/Route102/map.json carries `"flag": "0"`).

    A template event whose boot page ALSO independently resolves a
    `trainer_sight_or_berry_tree_id` claim — a visible battle Trainer(N)'s
    sight radius, or an encodable custom movement route — fails loud: an
    object template has only one such field (mirrors `ObjectEvent`'s
    docstring / `__post_init__` guard). `fork_constants` (the `fork_index.
    ForkIndex.constants` set), when given, gates every sidecar `item`/
    `berry_item` value against the real fork (CLAUDE.md §4.7) — `None` skips
    that specific check (unit-test/legacy path). Unknown kind, a malformed
    payload, or a stale sidecar reference (an id with no emitted object
    event) all fail loud (`_validate_template_fields`, and the stale-check
    mirroring `event_traits`' below). `template_fields=None` (default) is a
    legacy no-op — no template events, matching every other sidecar
    parameter's convention here."""
    objects, _, _ = classify_map_events(map_json, slice_ids)
    uid = consts.uranium_id
    result = ObjectBuildResult()
    event_by_id = {e["id"]: e for e in map_json["events"]}
    objects_by_id = {e["id"]: e for e in objects}
    # Diagonal-stair events (see `collect_through_block_cells`'s docstring)
    # have no dialogue and no interaction under the native sideways-stairs
    # path — they're pure geometry now, so they must not become object_events
    # / bg_events / coord_events. Skipped BEFORE the placement loop below, the
    # same way a `continue` for any other drop reason works: `local_id_map`
    # only ever gets an entry from an actual `result.object_events.append`
    # call, so an event that never reaches that call simply never occupies a
    # slot — it does not shift or renumber any OTHER event's local id (the
    # RMXP-id -> 1-based-position table this module hands to
    # `write_local_id_tables`).
    stair_ids = stair_event_ids(map_json)

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
    hide_ids: list[int] = []
    collapsed_ids: set[int] = set()
    if event_traits is not None:
        _validate_event_traits(event_traits, uid)
        rock_ids = sorted(
            eid for eid, traits in event_traits.items() if TRAIT_SMASHABLE_ROCK in traits
        )
        hide_ids = sorted(
            eid for eid, traits in event_traits.items() if TRAIT_TERMINAL_HIDE in traits
        )
        collapsed_ids = {
            eid for eid, traits in event_traits.items() if TRAIT_COLLAPSED_PAGES in traits
        }
        both = sorted(set(rock_ids) & set(hide_ids))
        if both:
            raise ValueError(
                f"map {uid}: event(s) {both} carry both {TRAIT_SMASHABLE_ROCK!r} and "
                f"{TRAIT_TERMINAL_HIDE!r} traits — an object template has only one "
                f"'flag' field, so an event cannot be both"
            )
    if template_fields is not None:
        _validate_template_fields(template_fields, uid, fork_constants)
    vis_flags = _assign_visibility_flags(rock_ids, hidden_actor_ids, uid)

    # One flag per template, never two (CLAUDE.md §4.3): a terminal_hide event
    # that's ALSO a rock or a required hidden actor already has a real flag
    # from the pool above — it must REUSE that flag, not get a second one.
    # Only an event that would otherwise carry the "0" null sentinel (a plain
    # object with no other visibility mechanism — e.g. Map050 EV020 "Theo")
    # needs a freshly minted FLAG_HIDE_*.
    hide_only_ids = sorted(set(hide_ids) - set(vis_flags))
    hide_flags: dict[int, str] = {}
    if hide_only_ids:
        if flag_registry is None:
            raise ValueError(
                f"map {uid}: terminal_hide event(s) {hide_only_ids} need a "
                f"flag_registry to mint FLAG_HIDE_* — call build_object_events(..., "
                f"flag_registry=FlagRegistry(...))"
            )
        hide_flags = {eid: flag_registry.mint_hide_flag(uid, eid) for eid in hide_only_ids}

    overlap = set(hide_flags) & set(vis_flags)
    if overlap:
        raise ValueError(
            f"map {uid}: event(s) {sorted(overlap)} ended up with BOTH a "
            f"minted hide flag and a pool visibility flag — one flag per "
            f"template, never two (this indicates a bug in the assignment "
            f"rule above, not bad input)"
        )

    # General self-switch-hide idiom (fix B — see
    # `_terminal_self_switch_hide_flags`'s docstring): auto-detected purely
    # from event shape, independent of `event_traits`. An object template has
    # only one 'flag' field, so when this rule matches an event that ALREADY
    # has a flag from the rock/hidden-actor pool or a `terminal_hide` trait,
    # exactly one source must win.
    #
    # PRECEDENCE: the trait-driven sources win; this rule yields.
    #
    # Those flags come from an EXPLICIT upstream classification (the
    # transpiler recorded a trait for this event, and the emitted script is
    # written against that specific flag — a smashable rock's `removeobject`
    # / FLAG_TEMP_* pool entry, say). This rule, by contrast, INFERS intent
    # from page shape alone. Explicit beats inferred: overriding a flag the
    # emitted script already references would desynchronise script and
    # template, which is strictly worse than declining to add one.
    #
    # This is a real overlap, not a pathological one — Uranium smashable
    # rocks legitimately have the self-switch-hide shape (smash once, flip
    # self switch A, blank page 2), e.g. map 32 events 14/15/33. Yielding
    # here reproduces exactly the behaviour those events had before this
    # rule existed. The only fidelity difference is respawn semantics
    # (vanilla FLAG_TEMP_* rocks return on map reload; Uranium's self switch
    # is permanent) — tracked as a separate question, deliberately NOT
    # resolved by silently swapping the flag out from under the script.
    selfswitch_hide_flags = _terminal_self_switch_hide_flags(objects, uid, flag_registry)
    already_flagged = set(vis_flags) | set(hide_flags)
    yielded = sorted(set(selfswitch_hide_flags) & already_flagged)
    if yielded:
        logger.info(
            "map %d: event(s) %s match the self-switch-hide idiom but already "
            "carry a smashable_rock/hidden-actor/terminal_hide template flag — "
            "keeping the trait-assigned flag (explicit beats inferred)",
            uid,
            yielded,
        )
        selfswitch_hide_flags = {
            eid: flag
            for eid, flag in selfswitch_hide_flags.items()
            if eid not in already_flagged
        }

    # The single merged source of truth for "what flag does this event's
    # template carry" — used everywhere a flag is written (both placement
    # loops below) and by resolve_terminal_hide_setflags downstream.
    template_flags: dict[int, str] = {**vis_flags, **hide_flags, **selfswitch_hide_flags}

    def _drop(event_id: int, reason: str) -> None:
        result.drops.append((event_id, reason))
        logger.info("map %d EV%03d: dropped (%s)", uid, event_id, reason)

    for event in objects:
        eid = event["id"]
        if eid in stair_ids:
            _drop(eid, DROP_STAIR)
            continue
        if stripped_event_ids is not None and eid in stripped_event_ids:
            expect_name = stripped_event_ids[eid]
            actual_name = event.get("name")
            if expect_name is not None and actual_name != expect_name:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: strip_list.json expected name "
                    f"{expect_name!r} but found {actual_name!r} — likely "
                    f"re-export renumbering; update the reference/"
                    f"strip_list.json map_events entry"
                )
            _drop(eid, DROP_STRIPPED)
            continue
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

        # Native item-ball/berry-tree template (CLAUDE.md §4.7 — converts to
        # the fork's native systems, not transpiled Ruby). Intercepted HERE,
        # before the blank-graphic/opacity/door-sheet classification below,
        # because a bare-soil berry patch (`kind="berry_tree"`,
        # `berry_item=null`) has NO Uranium sprite at all — RMXP shows
        # nothing where there's no tree, but the native berry tree system
        # still needs a REAL object_event to host its growth-stage sprite
        # states (BERRY_STAGE_NO_BERRY renders as bare soil natively). Letting
        # ordinary classification run first would drop such an event as a
        # blank-graphic `bg`/`coord`/no-boot-page case (Map033 EV101 — see
        # `collect_through_block_cells`'s docstring for the earlier, now
        # superseded "known accepted regression" note about this exact
        # event). So a template_fields entry always wins, unconditionally.
        tf_payload = (template_fields or {}).get(eid)
        if tf_payload is not None:
            tf_kind = tf_payload["kind"]
            route_claim_conflicts: list[str] = []
            if trigger == TRIGGER_EVENT_TOUCH:
                trainer_match = _TRAINER_NAME_RE.search(event.get("name") or "")
                if (
                    trainer_match and int(trainer_match.group(1)) >= 1
                    and opacity != 0 and name
                    and (trainer_battle_event_ids is None or eid in trainer_battle_event_ids)
                ):
                    route_claim_conflicts.append(
                        f"visible Trainer({trainer_match.group(1)}) sight radius"
                    )
            probe_spec = movement_spec_for(page)
            if probe_spec.route_bytecode is not None:
                route_claim_conflicts.append("custom movement route (route_bytecode)")
            if route_claim_conflicts:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: trainer_sight_or_berry_tree_id "
                    f"claimed by BOTH template_fields kind={tf_kind!r} AND "
                    f"{', '.join(route_claim_conflicts)} — an object template "
                    f"has only one such field"
                )
            if tf_kind == TF_KIND_ITEM_BALL:
                flag = template_flags.get(eid, "0")
                if flag == "0":
                    raise ValueError(
                        f"map {uid} EV{eid:03d}: item_ball resolved to the "
                        f"null flag \"0\" — STD_FIND_ITEM's last-talked-object "
                        f"flag write would be a no-op and the ball would "
                        f"respawn forever"
                    )
                result.object_events.append(
                    ObjectEvent(
                        x=event["x"], y=event["y"],
                        graphics_id=ITEM_BALL_GFX,
                        script=ITEM_BALL_SCRIPT,
                        flag=flag,
                        movement_range_x=tf_payload["amount"],
                        route_id=tf_payload["item"],
                    )
                )
            elif tf_kind == TF_KIND_BERRY_TREE:
                bid = (berry_tree_ids or {}).get(eid)
                if bid is None:
                    raise ValueError(
                        f"map {uid} EV{eid:03d}: berry_tree template_fields "
                        f"entry has no assigned save-slot id — precompute one "
                        f"via assign_berry_tree_ids(...) over the WHOLE "
                        f"slice's template_fields and pass berry_tree_ids="
                    )
                # ALWAYS "0", never `template_flags.get(eid, ...)`: unlike an
                # item_ball (which genuinely needs STD_FIND_ITEM's
                # last-talked-object flag write to despawn on pickup),
                # a berry tree's growth/pick state lives entirely in its
                # save-slot (`route_id`, the `berryTrees[]` entry) — the
                # object template stays permanently visible (vanilla
                # convention: engine/data/maps/Route102/map.json's berry
                # trees all carry `"flag": "0"`). Some Uranium berry-plant
                # events ALSO happen to match the self-switch-hide idiom
                # (`_terminal_self_switch_hide_flags` — real corpus shape:
                # Map033 EV100/EV102 give the berry once, then self-switch
                # to a blank page) — that pool match must NOT leak into this
                # field, or the native tree would vanish on a flag that has
                # nothing to do with its growth stage.
                result.object_events.append(
                    ObjectEvent(
                        x=event["x"], y=event["y"],
                        graphics_id=BERRY_TREE_GFX,
                        script=BERRY_TREE_SCRIPT,
                        flag="0",
                        movement_type=BERRY_TREE_MOVEMENT_TYPE,
                        route_id=str(bid),
                    )
                )
            else:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: unknown template_fields kind "
                    f"{tf_kind!r} (known kinds: {sorted(KNOWN_TEMPLATE_KINDS)})"
                )
            result.local_id_map[str(eid)] = len(result.object_events)
            continue

        # Trainer(N) line-of-sight convention (see the module comment above
        # `_TRAINER_NAME_RE`): the name is only live when the SELECTED page is
        # trigger-2 — Essentials' own pbCheckEventTriggerAfterTurning requires
        # that, so a Trainer(N)-named event on any other trigger is inert and
        # falls through to ordinary classification below. Two shapes: an
        # invisible tripwire (`trainer_sight_n`, handled by the ray-of-
        # coord_events path below) and a visible battle trainer
        # (`visible_trainer_n`, handled by the ordinary "object" emit path —
        # see the trainer_type/route_id wiring there).
        trainer_sight_n: int | None = None
        visible_trainer_n: int | None = None
        if trigger == TRIGGER_EVENT_TOUCH:
            trainer_match = _TRAINER_NAME_RE.search(event.get("name") or "")
            if trainer_match and int(trainer_match.group(1)) >= 1:
                n = int(trainer_match.group(1))
                if opacity == 0 or not name:
                    trainer_sight_n = n
                else:
                    visible_trainer_n = n

        emit_kind: str  # "bg" | "coord" | "object"
        gated_door = False
        if not name:
            if trigger == TRIGGER_ACTION:
                emit_kind = "bg"
            elif trigger == TRIGGER_EVENT_TOUCH:
                emit_kind = "coord"
            elif trigger == TRIGGER_PLAYER_TOUCH:
                # A GATED DOOR reaches this branch only because classify_event
                # refused to collapse it into a warp_event (some player-touch
                # page has no code-201 — see its docstring and the findings
                # doc). It is a real, live door: keep it as a coord_event so the
                # dispatcher picks the page and that page's body runs its own
                # warp(). Blank player-touch events with NO transfer anywhere
                # are the original inert shape and still drop.
                if _event_transfers(event):
                    emit_kind = "coord"
                    gated_door = True
                else:
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

        # A `coord_event` fires by walking, so it dispatches only touch pages;
        # bg signs and object events fire on A and dispatch the action channel.
        channel = CHANNEL_TOUCH if emit_kind == "coord" else CHANNEL_ACTION
        script, dispatcher = _resolve_script(
            event, consts, pory_labels, flag_registry, channel=channel,
            collapsed=eid in collapsed_ids,
        )

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
            elif gated_door:
                # Do NOT relocate a gated door to its approach tile. RMXP calls
                # the door cell impassable (you BUMP into it), but the
                # warp-override pass forces exactly these cells walkable with
                # the tileset's door metatile (MB_NON_ANIMATED_DOOR, collision
                # 0) — they were warp_event cells until the gated-door fix, and
                # `assemble_pathfinder.WARP_OVERRIDES` still lists them. So the
                # player really does step INTO the doorway, and the gate script
                # must fire there. Relocating to the approach tile would fire
                # the refusal on merely walking past the door, and would leave
                # the doorway itself silently inert.
                result.coord_events.append(CoordEvent(x=ex, y=ey, script=script))
                result.gated_door_cells.add((ex, ey))
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
            _emit_action_host(
                event, consts, result, pory_labels, flag_registry,
                collapsed=eid in collapsed_ids,
            )
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
            states = (npc_gfx_states or {}).get(name)
            if states:
                # A multi-state prop's page authors WHICH state it wears; the
                # bare constant is only the idle one. Fail loud on a state the
                # art has no cell for rather than booting the wrong picture.
                boot_state = (page["graphic"]["direction"], page["graphic"]["pattern"])
                if boot_state not in states:
                    raise KeyError(
                        f"map {uid} EV{eid:03d}: sheet {name!r} boots in state "
                        f"{boot_state}, which its art has no cell for "
                        f"(emitted states: {sorted(states)})"
                    )
                graphics_id = states[boot_state]

            # Visible Trainer(N) battle trainer (see the module comment above
            # `_TRAINER_NAME_RE` and `ObjectEvent`'s docstring): movement is
            # forced static because trainer_sight_or_berry_tree_id is needed
            # for the sight radius, and that field can't also carry a custom
            # route (ObjectEvent.__post_init__'s field-collision guard).
            trainer_type = "TRAINER_TYPE_NONE"
            trainer_route_id: str | None = None
            if visible_trainer_n is not None:
                is_battle_trainer = (
                    trainer_battle_event_ids is None
                    or eid in trainer_battle_event_ids
                )
                if is_battle_trainer:
                    graphic_dir = graphic.get("direction")
                    facing = _TRAINER_SIGHT_FACING.get(graphic_dir)
                    if facing is None:
                        raise ValueError(
                            f"map {uid} EV{eid:03d}: Trainer({visible_trainer_n}) "
                            f"battle trainer has unrecognized RMXP direction "
                            f"{graphic_dir!r}"
                        )
                    spec = static_face_spec(
                        page,
                        f"visible Trainer({visible_trainer_n}) battle trainer: "
                        f"movement forced static because "
                        f"trainer_sight_or_berry_tree_id must carry the sight "
                        f"radius (trainer_see.c GetTrainerApproachDistance), "
                        f"which collides with the custom-route use of the same "
                        f"field (event_object_movement.c sUraniumRoutes) if this "
                        f"object also moved on a custom route",
                        facing=facing,
                    )
                    trainer_type = "TRAINER_TYPE_NORMAL"
                    trainer_route_id = str(visible_trainer_n)
                else:
                    logger.warning(
                        "map %d EV%03d: Trainer(%d) will not battle — no "
                        "trainerbattle() call was generated for its script, "
                        "so it converts as an ordinary NPC instead of a sight "
                        "trainer",
                        uid, eid, visible_trainer_n,
                    )
                    spec = movement_spec_for(page)
            else:
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
            if trainer_route_id is not None:
                route_id = trainer_route_id
            result.object_events.append(
                ObjectEvent(
                    x=event["x"] + spec.anchor_dx, y=event["y"] + spec.anchor_dy,
                    graphics_id=graphics_id,
                    script=script, movement_type=spec.movement_type,
                    movement_range_x=spec.range_x, movement_range_y=spec.range_y,
                    flag=template_flags.get(eid, "0"),
                    route_id=route_id,
                    trainer_type=trainer_type,
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
            actor_event, consts, pory_labels, flag_registry,
            collapsed=eid in collapsed_ids,
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
        # A terminal_hide event's transpiled script emits a `setflag` that
        # MUST latch a real flag — a "0" template flag here would make
        # resolve_terminal_hide_setflags either fail loud downstream or (if
        # this check didn't exist) leave a silent no-op setflag in the staged
        # script (CLAUDE.md §4.5). Catch it here, at the map/event that
        # caused it, rather than in the staging pass's more generic error.
        for eid in hide_ids:
            local_id = result.local_id_map.get(str(eid))
            if local_id is None:
                continue  # already reported as a stale sidecar reference above
            flag = result.object_events[local_id - 1].flag
            if flag == "0":
                raise ValueError(
                    f"map {uid} EV{eid:03d}: terminal_hide event resolved to "
                    f"the null flag \"0\" — its transpiled setflag would be a "
                    f"no-op; something upstream (e.g. an always-visible "
                    f"hidden-actor classification) discarded its flag"
                )

    if template_fields is not None:
        emitted_ids = {int(k) for k in result.local_id_map}
        for eid in template_fields:
            if eid not in emitted_ids:
                raise ValueError(
                    f"map {uid} EV{eid:03d}: template_fields sidecar references "
                    f"this event but no object event was emitted for it (stale "
                    f"sidecar, or the event was dropped/reclassified by "
                    f"boot-page classification — re-run the transpile driver)"
                )

    return result


_TERMINAL_HIDE_SETFLAG_LINE = f"setflag({TERMINAL_HIDE_FLAG_PLACEHOLDER})"
_REMOVEOBJECT_RE = re.compile(r"^(\s*)removeobject\((\d+)\)\s*$")


def resolve_terminal_hide_setflags(
    pory_text: str,
    map_json: dict,
    table: dict[str, int],
    *,
    source_name: str,
) -> str:
    """Substitute transpiler.py's ``setflag(__TERMINAL_HIDE_FLAG__)`` terminal-
    hide placeholder for the real per-event template flag now that
    ``build_object_events`` has decided it.

    The transpiler can't name the flag at transpile time (whether a hidden
    event needs a freshly-minted ``FLAG_HIDE_*`` or must REUSE an existing
    rock/hidden-actor ``FLAG_TEMP_*`` depends on the whole map's
    ``_assign_visibility_flags`` pool, computed here) — this is the ONE place
    (CLAUDE.md §4.3) that resolves it, using the SAME ``map_json``/``table``
    ``hidden_actor_ids_from_map_json`` reads. Must run BEFORE
    ``remap_pory_object_ids`` (matches ``bracket_hidden_actor_scripts``'s
    convention) — the following ``removeobject(<id>)`` line still carries the
    raw RMXP id, which is what ``table`` is keyed by.

    Fails loud (CLAUDE.md §4.5 — no silent no-op) if:
      * a placeholder line isn't immediately followed by ``removeobject(<id>)``
        — a transpiler invariant, not user data;
      * the target id has no ``table`` entry (dropped/pruned event — stale
        placeholder);
      * the resolved template flag is ``"0"`` — ``build_object_events`` should
        already have refused to emit this (its own terminal_hide/"0" check),
        so reaching this is a belt-and-suspenders catch of a mismatch between
        the map.json this call was given and the script it's resolving.
    """
    object_events = map_json.get("object_events", [])
    lines = pory_text.splitlines()
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() != _TERMINAL_HIDE_SETFLAG_LINE:
            out_lines.append(line)
            i += 1
            continue
        if i + 1 >= len(lines):
            raise ValueError(
                f"{source_name}: terminal-hide setflag placeholder at line "
                f"{i + 1} has no following line"
            )
        m = _REMOVEOBJECT_RE.match(lines[i + 1])
        if not m:
            raise ValueError(
                f"{source_name}: terminal-hide setflag placeholder at line "
                f"{i + 1} is not immediately followed by removeobject(<id>) "
                f"— transpiler invariant violated"
            )
        rmxp_id = m.group(2)
        local_id = table.get(rmxp_id)
        if local_id is None:
            raise ValueError(
                f"{source_name}: terminal-hide target event {rmxp_id} has no "
                f"local-id table entry (dropped/pruned?) — stale placeholder"
            )
        flag = object_events[local_id - 1].get("flag", "0")
        if flag == "0":
            raise ValueError(
                f"{source_name}: terminal-hide target event {rmxp_id} "
                f'resolved to the null flag "0" — the setflag would be a '
                f"no-op (CLAUDE.md §4.5)"
            )
        indent = line[: len(line) - len(line.lstrip())]
        out_lines.append(f"{indent}setflag({flag})")
        i += 1
    return "\n".join(out_lines)


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
    npc_gfx_states: dict[str, dict[tuple[int, int], str]] | None = None,
    local_id_dir: Path | None = None,
    event_traits: dict[int, dict[int, list[str]]] | None = None,
    flag_registry: FlagRegistry | None = None,
    tilesets_path: Path | None = None,
    walkable_overrides: dict[int, frozenset[tuple[int, int]]] | None = None,
    route_registry: RouteRegistry | None = None,
    required_actor_ids: dict[int, set[int]] | None = None,
    trainer_battle_event_ids: dict[int, set[int]] | None = None,
    stripped_event_ids: dict[int, dict[int, str | None]] | None = None,
    template_fields: dict[int, dict[int, dict]] | None = None,
    fork_constants: set[str] | None = None,
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
    (legacy: no hidden actors on that map).

    `trainer_battle_event_ids` (Uranium map id -> event ids whose generated
    Poryscript contains a `trainerbattle_*` call — see `build_object_events`'s
    parameter of the same name and the module-level `trainer_battle_event_ids`
    helper) is forwarded per-map; a map absent from the outer dict, or the
    dict itself being `None`, passes `None` through (every visible Trainer(N)
    on that map converts as a battle trainer — see `build_object_events`).

    `stripped_event_ids` (Uranium map id -> that map's `build_object_events`
    `stripped_event_ids` dict — event id -> `expect_name`) is forwarded
    per-map. Unlike `event_traits`/`required_actor_ids`/
    `trainer_battle_event_ids`, whose `None` means "legacy, nothing special
    for this caller", `None` HERE (the default) auto-loads
    `reference/strip_list.json` via `load_stripped_event_ids()` — this is the
    top-level entry point real callers use (`scripts/stage_slice_scripts.py`),
    and CLAUDE.md §4.3 makes strip_list.json the source of truth for
    whole-artifact strips, so a caller that simply doesn't know about this
    parameter yet must still get it honored, not silently skip it. Pass `{}`
    explicitly to opt out (e.g. an isolated unit test building a map.json
    with no reference-file dependencies).

    `template_fields` (Uranium map id -> that map's `build_object_events`
    `template_fields` dict — event id -> `{"kind": "item_ball"|"berry_tree",
    ...}`, from `Map{id:03d}.template_fields.json`) is forwarded per-map,
    matching `event_traits`' legacy convention: a map absent from the outer
    dict, or the dict itself being `None`, is legacy behavior for that map
    (no template events). `berry_tree` ids are assigned ONCE up front, across
    the WHOLE outer dict (`assign_berry_tree_ids` — see its docstring for why
    a per-map assignment wouldn't be globally unique), then each map's slice
    of the result is forwarded to its own `build_object_events` call.
    `fork_constants` (the `fork_index.ForkIndex.constants` set), when given,
    is forwarded unchanged to every `build_object_events` call for the
    `item`/`berry_item` forward check (CLAUDE.md §4.7)."""
    if stripped_event_ids is None:
        stripped_event_ids = load_stripped_event_ids()
    slice_set = set(slice_ids)
    berry_tree_ids = (
        assign_berry_tree_ids(template_fields) if template_fields is not None else {}
    )
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
        map_template_fields = (
            template_fields.get(uid) if template_fields is not None else None
        )
        map_berry_ids = {
            eid: bid for (buid, eid), bid in berry_tree_ids.items() if buid == uid
        }
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
            npc_gfx_states=npc_gfx_states,
            event_traits=map_traits, flag_registry=flag_registry,
            passability=passability, route_registry=route_registry,
            required_actor_ids=(required_actor_ids or {}).get(uid),
            trainer_battle_event_ids=(trainer_battle_event_ids or {}).get(uid),
            stripped_event_ids=stripped_event_ids.get(uid),
            template_fields=map_template_fields,
            berry_tree_ids=map_berry_ids,
            fork_constants=fork_constants,
        )
        # Gated doors have no warp_event but still need the door metatile +
        # collision 0 on their cell, or the player can't step into the doorway
        # to trip the gate script (see build_object_events' gated_door branch).
        overrides[uid] = src_coords | result.gated_door_cells
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
