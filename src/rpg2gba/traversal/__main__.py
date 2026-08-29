"""CLI for the offline traversable graph (slice 1 — see PLAYTEST_AUTHORING
_IMPROVEMENT_V2.md Q13). No ROM, no emulator: everything here reads decoded
JSON under `output/uranium-build/`.

    python -m rpg2gba.traversal dump --map 37
    python -m rpg2gba.traversal dump --map 37 --json
    python -m rpg2gba.traversal path --map 37 --from 16,27 --to 16,5
    python -m rpg2gba.traversal reachable --map 37 --from 16,27
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import click

from . import collision
from .graph import Cell, MapGraph, build_map_graph
from .ledges import DEFAULT_TERRAIN_TAG_MAP

logger = logging.getLogger(__name__)


def _cell(value: str) -> Cell:
    try:
        x_str, y_str = value.split(",")
        return (int(x_str), int(y_str))
    except (ValueError, AttributeError) as exc:
        raise click.BadParameter(f"expected 'x,y', got {value!r}") from exc


_MAP_OPTION = click.option("--map", "map_id", required=True, type=int, help="Map id, e.g. 37.")
_MAPS_DIR_OPTION = click.option(
    "--maps-dir", type=click.Path(exists=True, path_type=Path),
    default=collision.DEFAULT_MAPS_DIR,
    help="Decoded maps directory (default: output/uranium-build/maps)",
)
_TILESETS_OPTION = click.option(
    "--tilesets-json", type=click.Path(exists=True, path_type=Path),
    default=collision.DEFAULT_TILESETS_JSON,
    help="Decoded tilesets oracle (default: output/uranium-build/tilesets.json)",
)
_TERRAIN_TAG_OPTION = click.option(
    "--terrain-tag-map", type=click.Path(path_type=Path),
    default=None,
    help="Ledge direction override table (default: reference/terrain_tag_map.json)",
)


def _build(
    map_id: int, maps_dir: Path, tilesets_json: Path, terrain_tag_map: Path | None,
) -> MapGraph:
    return build_map_graph(
        map_id,
        maps_dir=maps_dir,
        tilesets_json=tilesets_json,
        terrain_tag_map=terrain_tag_map or DEFAULT_TERRAIN_TAG_MAP,
    )


@click.group()
def cli() -> None:
    """Offline traversable graph — dump / query a map's walkability."""


@cli.command("dump")
@_MAP_OPTION
@_MAPS_DIR_OPTION
@_TILESETS_OPTION
@_TERRAIN_TAG_OPTION
@click.option(
    "--json", "as_json", is_flag=True, help="Emit machine-readable JSON instead of ASCII art.",
)
def dump_cmd(
    map_id: int, maps_dir: Path, tilesets_json: Path, terrain_tag_map: Path | None, as_json: bool,
) -> None:
    """Dump one map's graph: collision + stairs + ledges + warps."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    graph = _build(map_id, maps_dir, tilesets_json, terrain_tag_map)

    if as_json:
        payload = {
            "map_id": graph.map_id,
            "width": graph.width,
            "height": graph.height,
            "tileset_id": graph.tileset_id,
            "blocked_cells": sorted(
                [f"{x},{y}" for (x, y), b in graph.blocked.items() if b]
            ),
            "stairs": {
                f"{x},{y}": side.value for (x, y), side in sorted(graph.stair_sides.items())
            },
            "ledges": {
                f"{x},{y}": d.value for (x, y), d in sorted(graph.ledge_directions.items())
            },
            "warps": {
                f"{x},{y}": [
                    {
                        "event_id": w.event_id,
                        "dest_map": w.dest_map,
                        "dest_x": w.dest_x,
                        "dest_y": w.dest_y,
                        "dest_facing": w.dest_facing,
                    }
                    for w in ws
                ]
                for (x, y), ws in sorted(graph.warp_exits.items())
            },
            "elevation_modelled": graph.elevation_modelled,
            "elevation_note": graph.elevation_note,
        }
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(f"map {graph.map_id}  {graph.width}x{graph.height}  tileset {graph.tileset_id}")
    click.echo(
        f"  {sum(graph.blocked.values())}/{graph.width * graph.height} raw-blocked cells, "
        f"{len(graph.stair_sides)} stair cell(s), {len(graph.ledge_directions)} ledge cell(s), "
        f"{sum(len(v) for v in graph.warp_exits.values())} warp exit(s)"
    )
    click.echo(f"  elevation modelled: {graph.elevation_modelled}  ({graph.elevation_note})")
    click.echo()

    legend = (
        "legend: '.'=walkable  '#'=blocked  'L'=ledge (jump only)  "
        "'<'/'>'=stair left/right side  'W'=warp"
    )
    click.echo(legend)
    for y in range(graph.height):
        row = []
        for x in range(graph.width):
            cell = (x, y)
            if cell in graph.warp_exits:
                row.append("W")
            elif graph.is_stair(cell):
                row.append("<" if graph.stair_sides[cell].value == "left" else ">")
            elif graph.is_ledge(cell):
                row.append("L")
            elif graph.blocked.get(cell, True):
                row.append("#")
            else:
                row.append(".")
        click.echo(f"  {y:>3}  {''.join(row)}")


@cli.command("path")
@_MAP_OPTION
@_MAPS_DIR_OPTION
@_TILESETS_OPTION
@_TERRAIN_TAG_OPTION
@click.option("--from", "start_str", required=True, help="Start cell, 'x,y'.")
@click.option("--to", "goal_str", required=True, help="Goal cell, 'x,y'.")
def path_cmd(
    map_id: int, maps_dir: Path, tilesets_json: Path, terrain_tag_map: Path | None,
    start_str: str, goal_str: str,
) -> None:
    """Shortest path (BFS, unweighted) between two cells on one map."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    graph = _build(map_id, maps_dir, tilesets_json, terrain_tag_map)
    start, goal = _cell(start_str), _cell(goal_str)
    path = graph.shortest_path(start, goal)
    if path is None:
        click.echo(f"UNREACHABLE: no path from {start} to {goal} on map {map_id}")
        raise SystemExit(1)
    click.echo(f"{len(path) - 1} step(s): " + " -> ".join(f"{x},{y}" for x, y in path))


@cli.command("reachable")
@_MAP_OPTION
@_MAPS_DIR_OPTION
@_TILESETS_OPTION
@_TERRAIN_TAG_OPTION
@click.option("--from", "start_str", required=True, help="Start cell, 'x,y'.")
def reachable_cmd(
    map_id: int, maps_dir: Path, tilesets_json: Path, terrain_tag_map: Path | None, start_str: str,
) -> None:
    """Reachability set size (and cell list) from one cell on one map."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    graph = _build(map_id, maps_dir, tilesets_json, terrain_tag_map)
    start = _cell(start_str)
    reach = graph.reachable_from(start)
    click.echo(f"{len(reach)} reachable cell(s) from {start} on map {map_id}")
    for cell in sorted(reach):
        click.echo(f"  {cell[0]},{cell[1]}")


if __name__ == "__main__":
    cli()
