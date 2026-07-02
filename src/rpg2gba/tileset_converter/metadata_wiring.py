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
      - graphics: one default OBJ_EVENT_GFX for every NPC (RMXP gfx map deferred).
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

logger = logging.getLogger(__name__)

# v1 defaults (all logged simplifications — see module docstring).
DEFAULT_ELEVATION = 3
DEFAULT_GFX = "OBJ_EVENT_GFX_NINJA_BOY"  # generic NPC; RMXP gfx mapping deferred
DEFAULT_MUSIC = "MUS_LITTLEROOT"
DEFAULT_WEATHER = "WEATHER_NONE"
DEFAULT_MAPSEC = "MAPSEC_LITTLEROOT_TOWN"  # vanilla section reused (minted MAPSEC_* deferred)
NO_SCRIPT = "0x0"

TRANSFER_CODE = 201  # RMXP "Transfer Player"; params [method, dest_map, x, y, dir, fade]
TRIGGER_PLAYER_TOUCH = 1  # RMXP trigger: a door/stairs fires on step-on


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
    connections: list[dict] | None = None  # filled by connections.py (5.4)

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
            "coord_events": [],
            "bg_events": [],
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


def build_object_events(
    map_json: dict,
    consts: MapConstants,
    slice_ids: set[int],
    *,
    pory_labels: set[str] | None = None,
) -> tuple[list[ObjectEvent], list[str]]:
    """Place every non-warp, non-skipped event as an object_event and emit the
    dispatchers. Returns (object_events, dispatcher_scripts).

    When `pory_labels` is given (post-S6, the canonical def set), an event S6 left
    bodyless — a standing NPC / globally-gated cutscene actor with no real commands
    — is wired as a STATIC object (`script "0x0"`), not a dangling page label. An
    event with *some* converted body but whose resolved page label is missing is a
    genuine page-body gap and fails loud (CLAUDE.md §4.5)."""
    objects, _, _ = classify_map_events(map_json, slice_ids)
    object_events: list[ObjectEvent] = []
    dispatchers: list[str] = []
    for event in objects:
        uid, eid = consts.uranium_id, event["id"]
        if pory_labels is not None and not _event_has_body(event, consts, pory_labels):
            logger.info("map %d EV%03d: no converted .pory body -> static object", uid, eid)
            object_events.append(
                ObjectEvent(x=event["x"], y=event["y"], graphics_id=DEFAULT_GFX, script=NO_SCRIPT)
            )
            continue
        dispatcher = build_page_dispatcher(event, consts)
        if dispatcher is not None:
            script = dispatch_label(uid, eid)
            dispatchers.append(dispatcher)
        else:
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
        object_events.append(
            ObjectEvent(x=event["x"], y=event["y"], graphics_id=DEFAULT_GFX, script=script)
        )
    return object_events, dispatchers


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
) -> dict[int, set[tuple[int, int]]]:
    """Assemble map.json + dispatcher .pory for every slice map. Returns the per-map
    warp-source coords (S3 walkable-overrides) so S8 can force those cells walkable.
    Warp pairing needs every map's warp list first, so this is a slice-level pass."""
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
    for uid in slice_ids:
        consts = registry.get(uid)
        warp_events = resolved.get(uid, [])
        src_coords = {(s.src_x, s.src_y) for s in warp_lists[uid]}
        object_events, dispatchers = build_object_events(
            maps[uid], consts, slice_set, pory_labels=pory_labels
        )
        overrides[uid] = src_coords

        map_file = MapFile(
            consts=consts,
            map_type=_map_type_for(uid, metadata_path),
            object_events=object_events,
            warp_events=warp_events,
        )
        map_out = out_dir / consts.dir_name / "map.json"
        map_out.parent.mkdir(parents=True, exist_ok=True)
        map_out.write_text(json.dumps(map_file.to_json_dict(), indent=2) + "\n", encoding="utf-8")
        if dispatchers:
            disp_out = dispatcher_dir / f"Map{uid:03d}_dispatch.pory"
            disp_out.parent.mkdir(parents=True, exist_ok=True)
            disp_out.write_text("\n\n".join(dispatchers) + "\n", encoding="utf-8")
        logger.info(
            "map %d (%s): %d objects, %d warps, %d dispatchers",
            uid, consts.map_const, len(object_events), len(warp_events), len(dispatchers),
        )
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
