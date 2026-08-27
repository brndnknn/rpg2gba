"""Seam warps (`reference/seam_warps.json`) — CLAUDE.md §4.3 source of truth.

A seam warp REPLACES a pokeemerald map CONNECTION with a synthetic two-cell
direction-gated ARROW-WARP pair (`MB_NORTH_ARROW_WARP` / `MB_SOUTH_ARROW_WARP`
/ `MB_EAST_ARROW_WARP` / `MB_WEST_ARROW_WARP` —
`engine/include/constants/metatile_behaviors.h`). This is a fidelity
substitution used ONLY when a scroll connection is impossible: the two maps'
combined tileset needs more than 1024 8x8 tiles and neither dedup nor
unreferenced-metatile pruning gets it under the cap (the Kevlar Town <->
Route 2 seam, CH04, is the first case — measured 1028 tiles).

Because the engine's arrow-warp metatile behaviors are DIRECTION-gated
(`TryArrowWarp`/`IsArrowWarpMetatileBehavior`,
`engine/src/field_control_avatar.c`) — they only fire when the player is
standing on the tile AND pressing the matching direction — the two warps of
a seam can point directly at each other with no separate "arrival" warp_event:
an arriving player is moving in a direction that does NOT match the tile
they land on (e.g. arriving on a south-arrow tile after walking north never
re-triggers the south arrow). See `metadata_wiring.WarpSpec.direct_pair` and
`_resolve_all_warp_events`, which implement that direct pairing.

This module only loads/validates the declaration and derives the two
generic, data-driven shapes the rest of the pipeline consumes:

  - `behavior_cells_for()` -> `{map_id: {(x, y): kind}}`, mergeable into the
    `stair_cells` dict `build_slice_tilesets`/`convert_layout` already accept
    (the "behavior_overrides" mechanism is kind-generic, not stairs-specific
    — see `tile_map.BEHAVIOR_KINDS`).
  - `warp_pairs_for()` -> raw `(map_a, xa, ya, map_b, xb, yb)` rows; the
    caller (normally `stage_slice_scripts.py`) turns these into reciprocal
    `metadata_wiring.WarpSpec(..., direct_pair=True)` objects (kept out of
    this module to avoid a metadata_wiring <-> seam_warps import cycle).

Does NOT hardcode any map id — every seam is data (CLAUDE.md's "next chapter
needs data, not code" rule).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SEAM_WARPS_PATH = Path("reference/seam_warps.json")

# pokeemerald-connection-style direction vocabulary (matches
# connections.EDGE_TO_DIRECTION's *values*, not its N/S/E/W edge letters —
# a seam warp cell's arrow direction is the direction of TRAVEL that fires
# it, same convention `WarpSpec.dest_dir`/connections.Connection.direction
# use elsewhere in this codebase).
DIRECTIONS = frozenset({"up", "down", "left", "right"})

_ARROW_KIND_PREFIX = "arrow_warp_"


def behavior_kind(direction: str) -> str:
    """The `tile_map.BEHAVIOR_KINDS` string for an arrow-warp travel direction."""
    if direction not in DIRECTIONS:
        raise ValueError(
            f"seam_warps: direction {direction!r} not one of {sorted(DIRECTIONS)}"
        )
    return f"{_ARROW_KIND_PREFIX}{direction}"


@dataclass(frozen=True)
class SeamWarp:
    """One declared seam: replaces the map_a<->map_b CONNECTION.

    `cells_a[i]` pairs 1:1 with `cells_b[i]` — the same seam index names one
    reciprocal cell pair (the offset-consistent pairing the geometry oracle
    verified against the decoded map.bin collision bits). `direction_a` is
    the arrow direction map_a's cells carry (the direction of travel OUT of
    map_a, into map_b); `direction_b` is map_b's own arrow direction, into
    map_a. They are each other's opposite by construction of a straight seam,
    but this is not enforced here — see `load_seam_warps`."""

    seam_id: str
    map_a: int
    map_b: int
    cells_a: tuple[tuple[int, int], ...]
    cells_b: tuple[tuple[int, int], ...]
    direction_a: str
    direction_b: str

    @property
    def pair_key(self) -> frozenset[int]:
        return frozenset((self.map_a, self.map_b))


def load_seam_warps(path: Path = DEFAULT_SEAM_WARPS_PATH) -> list[SeamWarp]:
    """Load + validate `reference/seam_warps.json`.

    Fails loud on: a missing required field, `map_a == map_b`, mismatched or
    empty `cells_a`/`cells_b` lengths (must pair 1:1), an unknown direction,
    a duplicate seam id, or two seams naming the same unordered map pair
    (mirrors `connections._check_duplicates` — a seam should appear once)."""
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    seams_raw = raw.get("seams", [])
    if not isinstance(seams_raw, list):
        raise ValueError(f"{path}: 'seams' must be a list")

    out: list[SeamWarp] = []
    seen_ids: set[str] = set()
    seen_pairs: dict[frozenset[int], str] = {}
    for i, s in enumerate(seams_raw):
        where = f"{path} seams[{i}]"
        for key in ("id", "map_a", "map_b", "cells_a", "cells_b", "direction_a", "direction_b"):
            if key not in s:
                raise ValueError(f"{where}: missing {key!r}")

        seam_id = s["id"]
        if seam_id in seen_ids:
            raise ValueError(f"{where}: duplicate seam id {seam_id!r}")
        seen_ids.add(seam_id)

        map_a, map_b = int(s["map_a"]), int(s["map_b"])
        if map_a == map_b:
            raise ValueError(f"{where}: map_a == map_b ({map_a})")

        cells_a = [tuple(c) for c in s["cells_a"]]
        cells_b = [tuple(c) for c in s["cells_b"]]
        if not cells_a or len(cells_a) != len(cells_b):
            raise ValueError(
                f"{where}: cells_a ({len(cells_a)}) and cells_b ({len(cells_b)}) "
                "must be equal-length and non-empty (1:1 reciprocal pairing)"
            )

        direction_a, direction_b = s["direction_a"], s["direction_b"]
        for label, direction in (("direction_a", direction_a), ("direction_b", direction_b)):
            if direction not in DIRECTIONS:
                raise ValueError(f"{where}: {label}={direction!r} not one of {sorted(DIRECTIONS)}")

        pair_key = frozenset((map_a, map_b))
        if pair_key in seen_pairs:
            raise ValueError(
                f"{where}: map pair {sorted(pair_key)} already declared by seam "
                f"{seen_pairs[pair_key]!r} — a seam should appear once"
            )
        seen_pairs[pair_key] = seam_id

        out.append(SeamWarp(
            seam_id=seam_id, map_a=map_a, map_b=map_b,
            cells_a=tuple(cells_a), cells_b=tuple(cells_b),
            direction_a=direction_a, direction_b=direction_b,
        ))
    return out


def seams_for_slice(seams: list[SeamWarp], map_ids: set[int]) -> list[SeamWarp]:
    """Frontier rule (mirrors `connections.build_connections`): a seam only
    applies once BOTH endpoints are staged in this build's map set. A seam
    naming an unstaged map is simply omitted (not an error) — the same
    behaviour a real connections.json row gets."""
    return [s for s in seams if s.map_a in map_ids and s.map_b in map_ids]


def behavior_cells_for(seams: list[SeamWarp]) -> dict[int, dict[tuple[int, int], str]]:
    """`{map_id: {(x, y): kind}}` for every seam-warp cell on both sides of every
    seam — merge this into the `stair_cells` dict handed to
    `build_slice_tilesets`/`layout.convert_layout`'s `behavior_overrides`."""
    out: dict[int, dict[tuple[int, int], str]] = {}
    for seam in seams:
        kind_a = behavior_kind(seam.direction_a)
        kind_b = behavior_kind(seam.direction_b)
        for cell in seam.cells_a:
            out.setdefault(seam.map_a, {})[cell] = kind_a
        for cell in seam.cells_b:
            out.setdefault(seam.map_b, {})[cell] = kind_b
    return out


def warp_pairs_for(seams: list[SeamWarp]) -> list[tuple[int, int, int, int, int, int]]:
    """`[(map_a, xa, ya, map_b, xb, yb), ...]`, one row per reciprocal cell pair
    across every seam. The caller mints two `metadata_wiring.WarpSpec`s per
    row (map_a's cell -> map_b's cell, and the reverse), each with
    `direct_pair=True` so `_resolve_all_warp_events` pairs them to each
    other's own warp_event index instead of minting a redundant arrival."""
    out: list[tuple[int, int, int, int, int, int]] = []
    for seam in seams:
        for (xa, ya), (xb, yb) in zip(seam.cells_a, seam.cells_b):
            out.append((seam.map_a, xa, ya, seam.map_b, xb, yb))
    return out


def suppressed_pairs(seams: list[SeamWarp]) -> frozenset[frozenset[int]]:
    """The set of map-id pairs whose CONNECTION `connections.build_slice_connections`
    must omit (superseded by these seam warps)."""
    return frozenset(s.pair_key for s in seams)
