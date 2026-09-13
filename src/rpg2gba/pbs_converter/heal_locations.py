"""White-out respawn points, derived from `pbSetPokemonCenter` call sites.

**Do not confuse this with `MetadataHome`'s `healing_spot` field.** Uranium has
two separate and unrelated systems, both readable in
`reference/scripts_dump/101__PField_Field.rb`:

* `$PokemonGlobal.healingSpot` (`Kernel.pbSetHealingSpot`, `:1678-1684`) is fed
  from the per-map `HealingSpot` metadata (`101__PField_Field.rb:1824-1825`,
  `pbs_converter/metadata.py`'s `healing_spot` field). It is consumed *only* by
  the TELEPORT hidden move (`103__PField_HiddenMoves.rb:1211,1228`) and the
  region map. It has nothing to do with white-out.
* `$PokemonGlobal.pokecenterMapId/X/Y/Direction` (`Kernel.pbSetPokemonCenter`,
  `:1666-1676`) is the actual white-out respawn: `Kernel.pbStartOver`
  (`:1920-1948`) reads exactly these four fields into
  `$game_temp.player_new_map_id/x/y/direction`. If never set, `pbStartOver`
  falls back to `MetadataHome` (the global spawn; see `metadata.py`).

So this module scans for `pbSetPokemonCenter` call sites, not `healing_spot`
metadata.

**Deriving the bare-call respawn tile.** `pbSetPokemonCenter` defaults every
argument to the player's own position/facing at call time
(`mapid=$game_map.map_id, x=$game_player.x, y=$game_player.y,
direction=$game_player.direction`), which is the overwhelmingly common call
form in the corpus (only 8 of 64 corpus-wide call sites pass explicit
literals). For a bare call on an Action-Button-triggered event (RMXP trigger
0), the candidate standing tiles are derived exactly the way RMXP itself
would let the player interact with the event, per
`Game_Player#check_event_trigger_touch` / `front_map_x`,`front_map_y`
(`reference/scripts_dump/023__Game_Player_v17.rb:196-215,343-356`, which
calls `Game_Map#counter?`,
`reference/scripts_dump/025__Game_Map_v17.rb:343-354`): for each of the four
directions `d` (the unit vector from a candidate player tile toward the
event), the tile immediately adjacent (`event - d`) is a candidate if it is
in bounds and not blocked; if THAT tile is a *counter* (furniture the player
cannot stand on but can interact across — see
`traversal.collision.build_counter_grid`, a faithful port of
`Game_Map#counter?`), the tile one further along (`event - 2*d`) is also a
candidate if in bounds and not blocked. Every candidate that survives is
then filtered by reachability: a candidate must belong to the map's walkable
component that reaches (or is orthogonally adjacent to) one of the map's own
warp/transfer trigger cells (`traversal.warps.extract_warp_exits`, via
`traversal.graph.build_map_graph`'s `MapGraph.reachable_from`) — a
geographically-open tile the player could never actually walk to (a sealed
pocket) is not a real candidate no matter how it looks locally. Exactly one
surviving candidate resolves the call; zero or more than one is reported
unresolved rather than guessed (see `RespawnResolution.resolved`).

This replaced an earlier, simpler rule ("the event's unique open orthogonal
neighbour") that was blind to both counters and reachability. On the corpus's
one staged call site (Map068, Kevlar Town Pokémon Center, event 1 @ (8,11)),
that rule resolved to (8,10) — a passable tile whose own three neighbours
((7,10), (9,10), (8,9)) are all blocked, i.e. a sealed pocket the player can
never actually stand in. The ROM-verified truth
(`src/rpg2gba/playtest/chapters/ch03.py:207-212`, CH03's gate-passed beat B4)
is (8,13) facing UP, reached by looking *across* the nurse's counter — which
is exactly the tile the counter-aware, reachability-filtered rule below
derives.

Not every bare call resolves this way: only Action-Button-triggered events
with counter/adjacency geometry that this rule (plus reachability) narrows to
one candidate. Anything else is reported unresolved (see
`RespawnResolution.resolved`).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from rpg2gba.pbs_converter._naming import to_constant
from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS
from rpg2gba.traversal.collision import (
    build_blocked_grid,
    build_counter_grid,
    build_tile_grid,
    load_map_json,
    load_tileset_arrays,
)
from rpg2gba.traversal.graph import MapGraph, build_map_graph

logger = logging.getLogger(__name__)

DEFAULT_MAPS_DIR = Path("output/uranium-build/maps")
DEFAULT_TILESETS_JSON = Path("output/uranium-build/tilesets.json")
DEFAULT_MAP_CONSTANTS_JSON = Path("output/uranium-build/porymap/map_constants.json")
DEFAULT_METADATA_HEADER = Path("output/uranium-build/include/constants/metadata.h")
DEFAULT_OUTPUT_JSON = Path("output/uranium-build/heal_locations.json")

CODE_SCRIPT = 355
TRIGGER_ACTION_BUTTON = 0

# Stable id for the pre-any-Pokémon-Center-visit spawn (`MetadataHome`, see
# `initial_anchor` below). Deliberately NOT derived from a display name
# (`to_constant`'s usual mint path) — engine C references this id literally,
# so it must not shift if Uranium's map naming ever changes.
START_ANCHOR_ID = "HEAL_LOCATION_URANIUM_START"

# `Kernel.pbSetPokemonCenter` bare, or with up to 4 literal integer args
# (mapid, x, y, direction). Every one of the 64 real call sites in the corpus
# matches one of these two shapes (verified 2026-09-12); anything else is
# unrecognized and must fail loud rather than be silently skipped.
_CALL_RE = re.compile(
    r"^\s*(?:Kernel\.)?pbSetPokemonCenter\s*(?:\(\s*([^)]*?)\s*\))?\s*$"
)
_INT_ARG_RE = re.compile(r"^-?\d+$")

# RMXP facing-direction constants (down/left/right/up), per RGSS convention.
DIR_DOWN, DIR_LEFT, DIR_RIGHT, DIR_UP = 2, 4, 6, 8


@dataclass(frozen=True)
class CallSite:
    """One `pbSetPokemonCenter` call site in the deserialized map corpus."""

    map_id: int
    event_id: int
    event_name: str
    page_index: int
    trigger: int
    event_x: int
    event_y: int
    # (mapid, x, y, direction) if the call passed literal args; None if bare.
    explicit_args: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class RespawnResolution:
    """The respawn (map, x, y[, direction]) derived for one call site."""

    call_site: CallSite
    resolved: bool
    reason: str
    map_id: int | None = None
    x: int | None = None
    y: int | None = None
    direction: int | None = None


@dataclass(frozen=True)
class HealLocationEntry:
    """One entry ready to merge into `engine/src/data/heal_locations.json`."""

    id: str
    map: str
    x: int
    y: int


@dataclass(frozen=True)
class InitialAnchor:
    """The pre-any-Pokémon-Center-visit spawn (`MetadataHome`)."""

    map_id: int
    x: int
    y: int
    direction: int


def _script_call_text(cmd: dict) -> str | None:
    """The literal script text of one code-355 command, or None."""
    if cmd.get("code") != CODE_SCRIPT:
        return None
    params = cmd.get("parameters") or []
    if not params:
        return None
    return str(params[0])


# Sentinel: *text* is not a `pbSetPokemonCenter` call at all (as opposed to a
# bare call, which parses to `None`). A dedicated object rather than `None`
# so "not a match" and "bare call" are distinguishable return values.
_NOT_A_CALL = object()


def _parse_call(text: str) -> tuple[int, int, int, int] | None | object:
    """Match *text* against `pbSetPokemonCenter(...)`.

    Returns the explicit-args tuple, `None` for a bare call, or
    `_NOT_A_CALL` if *text* is not a `pbSetPokemonCenter` call at all — the
    caller uses that to skip commands that call something else.
    """
    m = _CALL_RE.match(text)
    if not m:
        return _NOT_A_CALL
    raw_args = m.group(1)
    if raw_args is None or raw_args.strip() == "":
        return None
    parts = [p.strip() for p in raw_args.split(",")]
    if len(parts) != 4 or not all(_INT_ARG_RE.match(p) for p in parts):
        raise ValueError(
            f"pbSetPokemonCenter call has unrecognized argument form: {text!r}"
        )
    a, b, c, d = (int(p) for p in parts)
    return (a, b, c, d)


def find_call_sites(maps_dir: Path = DEFAULT_MAPS_DIR) -> list[CallSite]:
    """Every `pbSetPokemonCenter` call site across the deserialized corpus.

    Scans all `Map###.json` files under *maps_dir* (not just staged ones —
    callers that only want staged entries should filter via
    `SLICE_MAP_IDS`, e.g. `generate_entries` below). Sorted by (map_id,
    event_id, page_index) for deterministic, idempotent output.
    """
    sites: list[CallSite] = []
    for path in sorted(maps_dir.glob("Map*.json")):
        map_id_match = re.match(r"Map(\d+)\.json$", path.name)
        if not map_id_match:
            continue
        map_id = int(map_id_match.group(1))
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data.get("events", []):
            event_id = event.get("id")
            event_name = event.get("name", "")
            ex, ey = event.get("x"), event.get("y")
            for page_index, page in enumerate(event.get("pages", [])):
                trigger = page.get("trigger")
                for cmd in page.get("list") or []:
                    text = _script_call_text(cmd)
                    if text is None:
                        continue
                    parsed = _parse_call(text)
                    if parsed is _NOT_A_CALL:
                        continue
                    sites.append(
                        CallSite(
                            map_id=map_id,
                            event_id=event_id,
                            event_name=event_name,
                            page_index=page_index,
                            trigger=trigger,
                            event_x=ex,
                            event_y=ey,
                            explicit_args=parsed,
                        )
                    )
    return sites


# The four (direction, unit-vector-from-player-toward-event) pairs a bare
# Action-Button call's approach is derived over — see module docstring.
_APPROACH_VECTORS: tuple[tuple[int, tuple[int, int]], ...] = (
    (DIR_DOWN, (0, 1)),
    (DIR_UP, (0, -1)),
    (DIR_RIGHT, (1, 0)),
    (DIR_LEFT, (-1, 0)),
)


@dataclass(frozen=True)
class _Candidate:
    cell: tuple[int, int]
    direction: int
    kind: str  # "adjacent" or "across-counter"


def _candidate_approach_tiles(
    ex: int,
    ey: int,
    xsize: int,
    ysize: int,
    blocked: dict[tuple[int, int], bool],
    counters: dict[tuple[int, int], bool],
) -> list[_Candidate]:
    """Every geometrically-plausible standing tile for an Action-Button event
    at (ex, ey) — adjacent tiles, plus across-a-counter tiles — per the rule
    in the module docstring. Does not filter by reachability; see
    `_reachable_candidates`."""

    def in_bounds(x: int, y: int) -> bool:
        return 0 <= x < xsize and 0 <= y < ysize

    def open_at(x: int, y: int) -> bool:
        return in_bounds(x, y) and not blocked.get((x, y), True)

    candidates: list[_Candidate] = []
    for direction, (dx, dy) in _APPROACH_VECTORS:
        adjacent = (ex - dx, ey - dy)
        if open_at(*adjacent):
            candidates.append(_Candidate(adjacent, direction, "adjacent"))
        if counters.get(adjacent, False):
            across = (ex - 2 * dx, ey - 2 * dy)
            if open_at(*across):
                candidates.append(_Candidate(across, direction, "across-counter"))
    return candidates


def _warp_adjacent_cells(warp_cells: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """`warp_cells` plus their orthogonal neighbours — the acceptable local
    reachability anchor (module docstring): a warp trigger tile can itself
    read blocked under plain collision (Phase 5's `warp_overrides` force it
    passable at build time, which this offline graph does not model — see
    `traversal.graph`'s module docstring), so a candidate one step short of
    the trigger must count as reaching it."""
    anchors: set[tuple[int, int]] = set(warp_cells)
    for wx, wy in warp_cells:
        anchors.update({(wx, wy - 1), (wx, wy + 1), (wx - 1, wy), (wx + 1, wy)})
    return anchors


def _reachable_candidates(
    candidates: list[_Candidate],
    graph: MapGraph,
    warp_anchor_cells: set[tuple[int, int]],
) -> list[_Candidate]:
    """`candidates` filtered to those whose walkable component reaches (or
    touches) one of the map's own warp/transfer cells — discards
    geographically-open-but-unreachable pockets (see module docstring)."""
    reachable: list[_Candidate] = []
    for c in candidates:
        if not graph.is_walkable(c.cell):
            continue
        if graph.reachable_from(c.cell) & warp_anchor_cells:
            reachable.append(c)
    return reachable


def _resolve_bare(
    call: CallSite,
    maps_dir: Path,
    tilesets_json: Path,
) -> RespawnResolution:
    """Resolve a bare call's respawn tile via the counter-aware,
    reachability-filtered rule in the module docstring.

    Reachability is derived from the offline `traversal.graph.MapGraph`
    (chosen over a hand-rolled flood fill: it already exists, already
    encodes this corpus's validated collision/stair/ledge rules, and exposes
    `reachable_from` + `warp_exits` directly — reimplementing a parallel BFS
    here would just be a worse copy of it). A candidate counts as reachable
    if its walkable component contains, or is orthogonally adjacent to, one
    of the map's own warp/transfer trigger cells
    (`traversal.warps.extract_warp_exits`) — the map's own entry/exit
    points, per the module docstring's local reachability criterion.

    Only Action-Button-triggered events (RMXP trigger 0) are considered at
    all. Anything else — a different trigger type, no geometric candidates,
    or more than one surviving reachable candidate — is reported unresolved
    rather than guessed (see module docstring).
    """
    if call.trigger != TRIGGER_ACTION_BUTTON:
        return RespawnResolution(
            call_site=call,
            resolved=False,
            reason=f"trigger {call.trigger} is not Action Button (0); "
            "cannot infer approach side from event position alone",
        )
    if call.event_x is None or call.event_y is None:
        return RespawnResolution(
            call_site=call, resolved=False, reason="event has no x/y position"
        )

    map_json = load_map_json(call.map_id, maps_dir)
    grid = build_tile_grid(map_json)
    arrays = load_tileset_arrays(map_json["tileset_id"], tilesets_json)
    counters = build_counter_grid(grid, arrays)
    blocked = build_blocked_grid(grid, arrays)

    ex, ey = call.event_x, call.event_y
    candidates = _candidate_approach_tiles(ex, ey, grid.xsize, grid.ysize, blocked, counters)
    if not candidates:
        return RespawnResolution(
            call_site=call,
            resolved=False,
            reason=f"no passable adjacent-or-across-counter approach tile found "
            f"for Action-Button event ({ex},{ey})",
        )

    graph = build_map_graph(call.map_id, maps_dir, tilesets_json)
    warp_anchor_cells = _warp_adjacent_cells(set(graph.warp_exits.keys()))
    reachable = _reachable_candidates(candidates, graph, warp_anchor_cells)

    if len(reachable) != 1:
        candidate_desc = [(c.cell, c.kind) for c in candidates]
        return RespawnResolution(
            call_site=call,
            resolved=False,
            reason=f"expected exactly one reachable approach candidate for event "
            f"({ex},{ey}), found {len(reachable)} of {len(candidates)} geometric "
            f"candidates {candidate_desc} reachable to a map warp/transfer cell",
        )

    winner = reachable[0]
    px, py = winner.cell
    return RespawnResolution(
        call_site=call,
        resolved=True,
        reason=f"unique reachable {winner.kind} approach tile toward Action-Button "
        f"event ({ex},{ey})",
        map_id=call.map_id,
        x=px,
        y=py,
        direction=winner.direction,
    )


def resolve_call_site(
    call: CallSite,
    maps_dir: Path = DEFAULT_MAPS_DIR,
    tilesets_json: Path = DEFAULT_TILESETS_JSON,
) -> RespawnResolution:
    """Resolve one call site's respawn (map, x, y[, direction])."""
    if call.explicit_args is not None:
        mapid, x, y, direction = call.explicit_args
        return RespawnResolution(
            call_site=call,
            resolved=True,
            reason="explicit literal arguments",
            map_id=mapid,
            x=x,
            y=y,
            direction=direction,
        )
    return _resolve_bare(call, maps_dir, tilesets_json)


def _load_map_constants(path: Path) -> dict[int, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _mint_center_entries(
    resolutions: list[RespawnResolution],
    map_constants: dict[int, dict],
    map_constants_json: Path,
    staged: frozenset[int],
) -> tuple[list[HealLocationEntry], dict[tuple[int, int, int], str]]:
    """Shared minting logic for `generate_entries` and
    `call_site_heal_locations` — a single source of truth so a call site's id
    reported by the latter is always one `generate_entries` actually emits.

    Returns `(entries, site_to_id)`: `entries` sorted by id (Center entries
    only — the start anchor is prepended by `generate_entries`, not minted
    here), and `site_to_id` mapping every STAGED call site's
    `(map_id, event_id, page_index)` to the id minted for it (bare and
    explicit-literal calls both go through this same path).

    Fails loud (CLAUDE.md §4.5) if a staged call site cannot be resolved, if
    its target map has no `map_constants.json` entry, if two staged call
    sites mint the same id for different (map, x, y), or if a minted id
    collides with `START_ANCHOR_ID` (that id is reserved for the initial
    anchor and must never double as a Center id).
    """
    entries: list[HealLocationEntry] = []
    seen_ids: dict[str, HealLocationEntry] = {}
    site_to_id: dict[tuple[int, int, int], str] = {}
    for res in resolutions:
        if res.call_site.map_id not in staged:
            continue
        if not res.resolved:
            raise ValueError(
                f"staged call site (map {res.call_site.map_id}, event "
                f"{res.call_site.event_id}) could not be resolved: {res.reason}"
            )
        entry_map_id = res.map_id
        const_entry = map_constants.get(entry_map_id)
        if const_entry is None:
            raise KeyError(
                f"staged heal location respawns onto map {entry_map_id}, which "
                f"has no entry in {map_constants_json}"
            )
        display_name = const_entry["display_name"]
        loc_id = to_constant("HEAL_LOCATION", display_name)
        if loc_id == START_ANCHOR_ID:
            raise ValueError(
                f"minted Center id {loc_id!r} (from display name {display_name!r}) "
                f"collides with the reserved start-anchor id {START_ANCHOR_ID!r}"
            )
        entry = HealLocationEntry(
            id=loc_id, map=const_entry["map_const"], x=res.x, y=res.y
        )
        prior = seen_ids.get(loc_id)
        if prior is not None and prior != entry:
            raise ValueError(
                f"heal location id collision: {loc_id!r} minted for both "
                f"{prior} and {entry}"
            )
        if prior is None:
            seen_ids[loc_id] = entry
            entries.append(entry)
        site_to_id[
            (res.call_site.map_id, res.call_site.event_id, res.call_site.page_index)
        ] = loc_id

    entries.sort(key=lambda e: e.id)
    return entries, site_to_id


def generate_entries(
    maps_dir: Path = DEFAULT_MAPS_DIR,
    tilesets_json: Path = DEFAULT_TILESETS_JSON,
    map_constants_json: Path = DEFAULT_MAP_CONSTANTS_JSON,
    metadata_header: Path = DEFAULT_METADATA_HEADER,
    staged_map_ids: frozenset[int] | None = None,
) -> tuple[list[HealLocationEntry], list[RespawnResolution]]:
    """Heal-location entries for the staged corpus, plus every resolution.

    Only call sites whose map is in *staged_map_ids* (default:
    `SLICE_MAP_IDS`) are emitted as Center entries — an entry naming a
    `MAP_*` constant absent from the build would not compile. Fails loud if a
    staged call site's map has no `map_constants.json` entry, or if a staged
    call site cannot be resolved (an unresolved *unstaged* call site is
    reported but does not fail the run, since nothing is emitted for it) —
    see `_mint_center_entries`.

    The engine can only ever restore a respawn from a *registered* heal
    location id, so the pre-any-Center-visit spawn (`MetadataHome`, read via
    `initial_anchor(metadata_header)`) needs an entry too, even though it has
    no `pbSetPokemonCenter` call site behind it. Its id is the stable
    `START_ANCHOR_ID` (not display-name-derived — see that constant's
    docstring).

    Returns `(entries, all_resolutions)`. `entries` is ordered with the
    start-anchor entry FIRST, followed by the Center entries sorted by id —
    this ordering is a contract another module (the assembler pass,
    `scripts/assemble_pathfinder.py`) depends on. `all_resolutions` covers
    every call site in the corpus (staged and not), for reporting.
    """
    staged = staged_map_ids if staged_map_ids is not None else frozenset(SLICE_MAP_IDS)
    map_constants = _load_map_constants(map_constants_json)

    call_sites = find_call_sites(maps_dir)
    resolutions = [
        resolve_call_site(c, maps_dir, tilesets_json) for c in call_sites
    ]

    center_entries, _site_to_id = _mint_center_entries(
        resolutions, map_constants, map_constants_json, staged
    )

    anchor = initial_anchor(metadata_header)
    anchor_const = map_constants.get(anchor.map_id)
    if anchor_const is None:
        raise KeyError(
            f"initial anchor respawns onto map {anchor.map_id}, which has no "
            f"entry in {map_constants_json}"
        )
    anchor_entry = HealLocationEntry(
        id=START_ANCHOR_ID, map=anchor_const["map_const"], x=anchor.x, y=anchor.y
    )

    entries = [anchor_entry] + center_entries
    return entries, resolutions


def call_site_heal_locations(
    maps_dir: Path = DEFAULT_MAPS_DIR,
    tilesets_json: Path = DEFAULT_TILESETS_JSON,
    map_constants_json: Path = DEFAULT_MAP_CONSTANTS_JSON,
    metadata_header: Path = DEFAULT_METADATA_HEADER,
    staged_map_ids: frozenset[int] | None = None,
) -> dict[tuple[int, int, int], str]:
    """(map_id, event_id, page_index) -> HEAL_LOCATION_* id, for every STAGED
    call site.

    `page_index` is 0-based, the same `enumerate` index over `event["pages"]`
    that `CallSite.page_index` already uses. Derived from the exact same
    resolution + minting path `generate_entries` uses (`_mint_center_entries`
    — not duplicated here), so every id this returns is one
    `generate_entries` actually emits. Explicit-literal calls map to the id
    minted for their target map, same as bare calls.

    `metadata_header` is accepted for interface symmetry with
    `generate_entries` but unused here: the initial anchor has no
    `pbSetPokemonCenter` call site, so it never appears in the returned
    mapping (its id, `START_ANCHOR_ID`, is intentionally out of band for
    transpiler code driven by call sites)."""
    staged = staged_map_ids if staged_map_ids is not None else frozenset(SLICE_MAP_IDS)
    call_sites = find_call_sites(maps_dir)
    if not call_sites:
        # Nothing to resolve, so nothing to mint against: don't demand the
        # upstream artifacts. Any real call site still fails loud below.
        return {}
    map_constants = _load_map_constants(map_constants_json)

    resolutions = [
        resolve_call_site(c, maps_dir, tilesets_json) for c in call_sites
    ]
    _entries, site_to_id = _mint_center_entries(
        resolutions, map_constants, map_constants_json, staged
    )
    return site_to_id


def write_entries(
    entries: list[HealLocationEntry], out_path: Path = DEFAULT_OUTPUT_JSON
) -> Path:
    """Write the generated entries under `output/` (CLAUDE.md §4.4).

    This is a staging artifact only — this module never writes into
    `engine/`. It is no longer merged by hand: an assembler pass
    (`scripts/assemble_pathfinder.py`, owned separately) reads
    `generate_entries`' output and writes
    `engine/src/data/heal_locations.gen.json` from it.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": (
            "Generated by rpg2gba.pbs_converter.heal_locations. Staging "
            "artifact only — consumed by scripts/assemble_pathfinder.py, "
            "which writes engine/src/data/heal_locations.gen.json; this "
            "module never writes into engine/."
        ),
        "heal_locations": [
            {"id": e.id, "map": e.map, "x": e.x, "y": e.y} for e in entries
        ],
    }
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return out_path


_START_DEFINE_RE = re.compile(r"^#define\s+URANIUM_START_(MAP|X|Y|DIR)\s+(-?\d+)")


def initial_anchor(metadata_header: Path = DEFAULT_METADATA_HEADER) -> InitialAnchor:
    """The pre-any-Pokémon-Center-visit spawn, read from the emitted
    `metadata.h` header (`pbs_converter/metadata.py`'s `URANIUM_START_*`
    defines) — the single source of truth for `MetadataHome`, not a
    hardcoded 49/7/7."""
    values: dict[str, int] = {}
    for line in metadata_header.read_text(encoding="utf-8").splitlines():
        m = _START_DEFINE_RE.match(line)
        if m:
            values[m.group(1)] = int(m.group(2))
    missing = {"MAP", "X", "Y", "DIR"} - values.keys()
    if missing:
        raise ValueError(
            f"{metadata_header} is missing URANIUM_START_{{{','.join(sorted(missing))}}}"
        )
    return InitialAnchor(
        map_id=values["MAP"], x=values["X"], y=values["Y"], direction=values["DIR"]
    )
