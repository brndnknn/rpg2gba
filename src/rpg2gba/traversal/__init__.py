"""Offline traversable graph — single source of truth for "where can the
player walk on map N", derived purely from decoded RMXP data (no ROM, no
emulator). See `graph.py` for the full model docstring.

Public API::

    build_map_graph(map_id, maps_dir=..., tilesets_json=..., terrain_tag_map=...) -> MapGraph
    MapGraph.is_walkable(cell) -> bool
    MapGraph.neighbors(cell) -> list[Edge]
    MapGraph.reachable_from(start) -> set[Cell]
    MapGraph.shortest_path(start, goal) -> list[Cell] | None
    MapGraph.connected_components() -> list[set[Cell]]
"""
from __future__ import annotations

from .direction import CARDINALS, Direction
from .graph import Cell, Edge, MapGraph, build_map_graph
from .ledges import derive_ledge_direction, load_ledge_direction_overrides
from .warps import WarpExit, extract_warp_exits

__all__ = [
    "CARDINALS",
    "Direction",
    "Cell",
    "Edge",
    "MapGraph",
    "build_map_graph",
    "derive_ledge_direction",
    "load_ledge_direction_overrides",
    "WarpExit",
    "extract_warp_exits",
]
