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
from dataclasses import dataclass, field
from pathlib import Path

from ..conversion_agent.flag_registry import self_switch_flag_name
from .map_constants import MapConstantRegistry, MapConstants
from .npc_gfx import is_door_sheet, movement_type_for, select_boot_page

logger = logging.getLogger(__name__)

# v1 defaults (all logged simplifications — see module docstring).
DEFAULT_ELEVATION = 3
DEFAULT_MUSIC = "MUS_LITTLEROOT"
DEFAULT_WEATHER = "WEATHER_NONE"
DEFAULT_MAPSEC = "MAPSEC_LITTLEROOT_TOWN"  # vanilla section reused (minted MAPSEC_* deferred)
NO_SCRIPT = "0x0"

TRANSFER_CODE = 201  # RMXP "Transfer Player"; params [method, dest_map, x, y, dir, fade]
TRIGGER_ACTION = 0  # RMXP trigger: fires on the action button (a sign/NPC talk)
TRIGGER_PLAYER_TOUCH = 1  # RMXP trigger: a door/stairs fires on step-on
TRIGGER_EVENT_TOUCH = 2  # RMXP trigger: fires when the player touches the event's tile
TRIGGER_AUTORUN = 3  # RMXP trigger: fires automatically, once, map-script territory
TRIGGER_PARALLEL = 4  # RMXP trigger: runs continuously in the background

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
    elevation: int = DEFAULT_ELEVATION

    def to_dict(self) -> dict:
        return {
            "graphics_id": self.graphics_id,
            "x": self.x,
            "y": self.y,
            "elevation": self.elevation,
            "movement_type": self.movement_type,
            "movement_range_x": 0,
            "movement_range_y": 0,
            "trainer_type": "TRAINER_TYPE_NONE",
            "trainer_sight_or_berry_tree_id": "0",
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
    var: str = "VAR_TEMP_0"
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
    silent drops)."""

    object_events: list[ObjectEvent] = field(default_factory=list)
    dispatchers: list[str] = field(default_factory=list)
    coord_events: list[CoordEvent] = field(default_factory=list)
    bg_events: list[BgEvent] = field(default_factory=list)
    local_id_map: dict[str, int] = field(default_factory=dict)
    drops: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class WarpSpec:
    """A kept code-201 transfer, before cross-map dest_warp_id pairing."""

    src_x: int
    src_y: int
    dest_uid: int  # Uranium map id of the destination
    dest_x: int  # Uranium arrival coord: where an extra "arrival" warp_event is
    dest_y: int  # placed on the destination map (the vanilla-Emerald landing trick)


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

def _event_transfers(event: dict) -> list[tuple[int, int, int]]:
    """Every code-201 (dest_uid, x, y) across all of an event's pages."""
    out = []
    for page in event["pages"]:
        for cmd in page.get("list", []):
            if cmd["code"] == TRANSFER_CODE:
                p = cmd["parameters"]
                out.append((p[1], p[2], p[3]))
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
            dest_uid, dx, dy = transfers[0]
            return ("warp", WarpSpec(event["x"], event["y"], dest_uid, dx, dy))
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

def _has_global_gate(condition: dict) -> bool:
    """True if a page condition tests a global switch or variable (needs S6 names)."""
    return bool(
        condition.get("switch1_valid")
        or condition.get("switch2_valid")
        or condition.get("variable_valid")
    )


def build_page_dispatcher(event: dict, consts: MapConstants) -> str | None:
    """Emit a Poryscript dispatcher for a multi-page event, or None to defer.

    Returns None for a single-page event (no dispatch needed) OR for a multi-page
    event with any GLOBAL switch/variable page gate (deferred to S6 — caller points
    the object_event at the base page). For self-switch / unconditional gating it
    emits the selection: RMXP activates the highest-index satisfiable page, so we
    test pages high->low and goto the first whose self-switch is set, falling back
    to the base page (or an unconditional higher page that always wins)."""
    pages = event["pages"]
    if len(pages) <= 1:
        return None
    if any(_has_global_gate(p["condition"]) for p in pages):
        return None  # deferred: global names not minted until S6

    uid, eid = consts.uranium_id, event["id"]
    guards: list[tuple[str, str]] = []
    fallback = page_label(uid, eid, 1)
    for idx in range(len(pages) - 1, 0, -1):  # high -> low; index 0 is the base
        cond = pages[idx]["condition"]
        if cond.get("self_switch_valid"):
            flag = self_switch_flag_name(uid, eid, cond["self_switch_ch"])
            guards.append((flag, page_label(uid, eid, idx + 1)))
        else:
            fallback = page_label(uid, eid, idx + 1)  # unconditional page wins outright
            break

    lines = [f"script {dispatch_label(uid, eid)} {{"]
    for flag, dest in guards:
        lines += [f"    if (flag({flag})) {{", f"        goto({dest})", "    }"]
    lines += [f"    goto({fallback})", "}"]
    return "\n".join(lines)


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
    event: dict, consts: MapConstants, pory_labels: set[str] | None
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
    is a genuine page-body gap and fails loud (CLAUDE.md §4.5)."""
    uid, eid = consts.uranium_id, event["id"]
    if pory_labels is not None and not _event_has_body(event, consts, pory_labels):
        logger.info("map %d EV%03d: no converted .pory body -> static script", uid, eid)
        return NO_SCRIPT, None

    dispatcher = build_page_dispatcher(event, consts)
    if dispatcher is not None:
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


def _assign_rock_flags(event_traits: dict[int, list[str]], uid: int) -> dict[int, str]:
    """FLAG_TEMP_11.._1F, assigned to `smashable_rock` events in ascending
    event-id order. Raises if a map has more traited rocks than the range holds."""
    rock_ids = sorted(eid for eid, traits in event_traits.items() if TRAIT_SMASHABLE_ROCK in traits)
    if len(rock_ids) > ROCK_FLAG_CAPACITY:
        raise ValueError(
            f"map {uid}: {len(rock_ids)} smashable_rock events exceed the "
            f"FLAG_TEMP_{ROCK_FLAG_FIRST:X}..FLAG_TEMP_{ROCK_FLAG_LAST:X} capacity "
            f"({ROCK_FLAG_CAPACITY})"
        )
    return {
        eid: f"FLAG_TEMP_{ROCK_FLAG_FIRST + i:X}" for i, eid in enumerate(rock_ids)
    }


def build_object_events(
    map_json: dict,
    consts: MapConstants,
    slice_ids: set[int],
    *,
    pory_labels: set[str] | None = None,
    npc_gfx: dict[str, str] | None = None,
    event_traits: dict[int, list[str]] | None = None,
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
                     silent default, CLAUDE.md §4.5) and `movement_type` from the
                     boot page's move_type/facing (`npc_gfx.movement_type_for`).

    Every emission path resolves its script label via `_resolve_script`. Returns
    an `ObjectBuildResult`: the placed events, dispatcher bodies, the local-id
    table (RMXP event id -> 1-based `object_events` position, the id porymap
    actually compiles), and the drop report (no silent drops).

    `event_traits` (event id -> trait list, from the transpile driver's
    `Map{id:03d}.traits.json` sidecar) assigns `smashable_rock` events sequential
    FLAG_TEMP_11.._1F visibility flags (see ROCK_FLAG_* / CLAUDE.md §4.5 — >15
    such events, an unknown trait string, or a trait on an event id that resolves
    to no emitted object_event all fail loud). `None` is legacy behavior: every
    `ObjectEvent.flag` stays the "0" default."""
    objects, _, _ = classify_map_events(map_json, slice_ids)
    uid = consts.uranium_id
    result = ObjectBuildResult()

    rock_flags: dict[int, str] = {}
    if event_traits is not None:
        _validate_event_traits(event_traits, uid)
        rock_flags = _assign_rock_flags(event_traits, uid)

    def _drop(event_id: int, reason: str) -> None:
        result.drops.append((event_id, reason))
        logger.info("map %d EV%03d: dropped (%s)", uid, event_id, reason)

    for event in objects:
        eid = event["id"]
        page = select_boot_page(event)
        if page is None:
            _drop(eid, DROP_NO_BOOT_PAGE)
            continue

        graphic = page.get("graphic", {})
        name = graphic.get("character_name") or ""
        trigger = page.get("trigger")
        opacity = graphic.get("opacity", 255)

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

        script, dispatcher = _resolve_script(event, consts, pory_labels)
        if dispatcher is not None:
            result.dispatchers.append(dispatcher)

        if emit_kind == "bg":
            result.bg_events.append(BgEvent(x=event["x"], y=event["y"], script=script))
        elif emit_kind == "coord":
            result.coord_events.append(CoordEvent(x=event["x"], y=event["y"], script=script))
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
            movement_type = movement_type_for(page)
            result.object_events.append(
                ObjectEvent(
                    x=event["x"], y=event["y"], graphics_id=graphics_id,
                    script=script, movement_type=movement_type,
                    flag=rock_flags.get(eid, "0"),
                )
            )
            result.local_id_map[str(eid)] = len(result.object_events)

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
) -> dict[int, set[tuple[int, int]]]:
    """Assemble map.json + dispatcher .pory for every slice map. Returns the per-map
    warp-source coords (S3 walkable-overrides) so S8 can force those cells walkable.
    Warp pairing needs every map's warp list first, so this is a slice-level pass.

    `npc_gfx` (character_name -> OBJ_EVENT_GFX_* — see `npc_gfx.load_npc_gfx_map`)
    is forwarded to `build_object_events`; omit it only for callers that don't
    place any visible NPC (a visible graphic with no map raises loud). When
    `local_id_dir` is given, the per-map RMXP-id -> porymap-local-id tables are
    also written there via `write_local_id_tables` (the pinned local-id contract).

    `event_traits` is keyed by Uranium map id -> that map's `build_object_events`
    `event_traits` dict (event id -> trait list; see `Map{id:03d}.traits.json`,
    stage_slice_scripts.py). A map absent from the outer dict, or `event_traits`
    itself being `None`, is legacy behavior for that map (all flags "0")."""
    slice_set = set(slice_ids)
    maps = {
        uid: json.loads((maps_dir / f"Map{uid:03d}.json").read_text(encoding="utf-8"))
        for uid in slice_ids
    }
    warp_lists = {
        uid: [spec for _e, spec in classify_map_events(maps[uid], slice_set)[1]]
        for uid in slice_ids
    }
    resolved = _resolve_all_warp_events(warp_lists, registry, maps)

    overrides: dict[int, set[tuple[int, int]]] = {}
    local_id_tables: dict[int, dict[str, int]] = {}
    for uid in slice_ids:
        consts = registry.get(uid)
        warp_events = resolved.get(uid, [])
        src_coords = {(s.src_x, s.src_y) for s in warp_lists[uid]}
        map_traits = event_traits.get(uid) if event_traits is not None else None
        result = build_object_events(
            maps[uid], consts, slice_set, pory_labels=pory_labels, npc_gfx=npc_gfx,
            event_traits=map_traits,
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
        disp_out = dispatcher_dir / f"Map{uid:03d}_dispatch.pory"
        if result.dispatchers:
            disp_out.parent.mkdir(parents=True, exist_ok=True)
            disp_out.write_text("\n\n".join(result.dispatchers) + "\n", encoding="utf-8")
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
