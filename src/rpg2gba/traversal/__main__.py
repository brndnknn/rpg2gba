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
from .capabilities import (
    VERIFIED_CAPABILITIES,
    Capability,
    build_capability_map,
)
from .graph import Cell, MapGraph, build_map_graph
from .ledges import DEFAULT_TERRAIN_TAG_MAP
from .reachability import derive_blocked_verdict, derive_blocked_verdict_for_event
from .triggers import (
    DEFAULT_ENGINE_MAPS_DIR,
    DEFAULT_MAP_CONSTANTS_JSON,
    build_trigger_overlay,
)
from .world import (
    DEFAULT_CONNECTIONS_JSON,
    DEFAULT_MAP_INFOS_JSON,
    DEFAULT_SEAM_WARPS_PATH,
    DEFAULT_START_MAP_ID,
    WorldEdge,
    build_world_graph,
)

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


@cli.command("triggers")
@_MAP_OPTION
@_MAPS_DIR_OPTION
@_TILESETS_OPTION
@_TERRAIN_TAG_OPTION
@click.option(
    "--map-constants-json", type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_MAP_CONSTANTS_JSON,
    help="Decoded map-constants oracle (default: output/uranium-build/porymap/map_constants.json)",
)
@click.option(
    "--engine-maps-dir", type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_ENGINE_MAPS_DIR,
    help="Emitted pokeemerald maps directory (default: engine/data/maps)",
)
@click.option(
    "--json", "as_json", is_flag=True, help="Emit machine-readable JSON instead of a table.",
)
def triggers_cmd(
    map_id: int, maps_dir: Path, tilesets_json: Path, terrain_tag_map: Path | None,
    map_constants_json: Path, engine_maps_dir: Path, as_json: bool,
) -> None:
    """Dump one map's trigger overlay: which tiles fire which event, and how certainly."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    graph = _build(map_id, maps_dir, tilesets_json, terrain_tag_map)
    overlay = build_trigger_overlay(
        map_id, graph=graph, map_constants_json=map_constants_json, engine_maps_dir=engine_maps_dir,
    )

    if as_json:
        payload = {
            "map_id": overlay.map_id,
            "tiles": {
                f"{x},{y}": [
                    {
                        "kind": ref.kind.value,
                        "script": ref.script,
                        "certainty": ref.certainty.value,
                        "owner_xy": f"{ref.owner_xy[0]},{ref.owner_xy[1]}" if ref.owner_xy else None,
                        "detail": ref.detail,
                    }
                    for ref in refs
                ]
                for (x, y), refs in sorted(overlay.tiles.items())
            },
        }
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(
        f"map {overlay.map_id}  {len(overlay.tiles)} trigger tile(s)  "
        f"({len(overlay.certain_tiles())} certain, {len(overlay.possible_tiles())} possible)"
    )
    click.echo()
    for (x, y), refs in sorted(overlay.tiles.items()):
        for ref in refs:
            owner = f"  owner={ref.owner_xy[0]},{ref.owner_xy[1]}" if ref.owner_xy else ""
            click.echo(
                f"  {x},{y}  {ref.kind.value:<13} {ref.certainty.value:<8} "
                f"{ref.script}{owner}  ({ref.detail})"
            )


@cli.command("capabilities")
@_MAP_OPTION
@_MAPS_DIR_OPTION
@_TILESETS_OPTION
@click.option(
    "--capability", "capability_names", multiple=True,
    type=click.Choice(sorted(c.value for c in VERIFIED_CAPABILITIES)),
    help="Restrict to these capabilities (default: all verified capabilities).",
)
@click.option(
    "--json", "as_json", is_flag=True, help="Emit machine-readable JSON instead of a table.",
)
def capabilities_cmd(
    map_id: int, maps_dir: Path, tilesets_json: Path, capability_names: tuple[str, ...],
    as_json: bool,
) -> None:
    """Dump one map's capability-tagged obstacle cells (rocks, boulders, water, waterfalls)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    capabilities = (
        frozenset(Capability(name) for name in capability_names) if capability_names else None
    )
    cap_map = build_capability_map(
        map_id, maps_dir=maps_dir, tilesets_json=tilesets_json, capabilities=capabilities,
    )

    if as_json:
        payload = {
            "map_id": cap_map.map_id,
            "obstacles": {
                f"{x},{y}": {
                    "capability": obstacle.capability.value,
                    "source": obstacle.source,
                    "detail": obstacle.detail,
                    "event_id": obstacle.event_id,
                }
                for (x, y), obstacle in sorted(cap_map.obstacles.items())
            },
        }
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(f"map {cap_map.map_id}  {len(cap_map.obstacles)} obstacle cell(s)")
    for cap in sorted(cap_map.capabilities_present(), key=lambda c: c.value):
        click.echo(f"  {cap.value}: {len(cap_map.cells_for(cap))} cell(s)")
    click.echo()
    for (x, y), obstacle in sorted(cap_map.obstacles.items()):
        click.echo(
            f"  {x},{y}  {obstacle.capability.value:<10} {obstacle.source:<8} {obstacle.detail}"
        )


@cli.command("blocked")
@_MAP_OPTION
@_MAPS_DIR_OPTION
@_TILESETS_OPTION
@_TERRAIN_TAG_OPTION
@click.option("--from", "start_str", required=True, help="Start cell, 'x,y'.")
@click.option(
    "--to", "goal_strs", multiple=True,
    help="Target cell, 'x,y' -- goal is the cell itself. Repeatable.",
)
@click.option(
    "--event", "event_ids", type=int, multiple=True,
    help="Target event id -- goal is any cell orthogonally adjacent to the event's spawn "
    "tile (an event is interacted with, never stood on). Repeatable.",
)
@click.option(
    "--capability", "capability_names", multiple=True,
    type=click.Choice(sorted(c.value for c in VERIFIED_CAPABILITIES)),
    help="Restrict candidate capabilities considered (default: all verified capabilities).",
)
@click.option(
    "--require-clearing", is_flag=True,
    help="For --event targets, ask the CLEARING question (must the obstacle itself be "
    "cleared -- e.g. rock_smash for a rock) instead of the default APPROACH question "
    "(can the player merely stand next to it). No effect on --to targets, which have "
    "no event of their own to clear. See reachability.derive_blocked_verdict_for_event's "
    "docstring for the two-question distinction (backlog #95).",
)
@click.option(
    "--json", "as_json", is_flag=True, help="Emit machine-readable JSON instead of one line per target.",
)
def blocked_cmd(
    map_id: int, maps_dir: Path, tilesets_json: Path, terrain_tag_map: Path | None,
    start_str: str, goal_strs: tuple[str, ...], event_ids: tuple[int, ...],
    capability_names: tuple[str, ...], require_clearing: bool, as_json: bool,
) -> None:
    """Derive the blocked:<capability set> verdict for one or more targets on a map.

    By default --event targets ask the APPROACH question (can the player
    reach a tile next to the event); pass --require-clearing to ask whether
    the event's own obstacle (if any) is additionally cleared -- see
    --require-clearing's help text."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not goal_strs and not event_ids:
        raise click.UsageError("at least one --to or --event is required")

    graph = _build(map_id, maps_dir, tilesets_json, terrain_tag_map)
    capability_map = build_capability_map(map_id, maps_dir=maps_dir, tilesets_json=tilesets_json)
    start = _cell(start_str)
    candidates = frozenset(Capability(name) for name in capability_names) if capability_names else None

    targets: list[tuple[str, Cell, bool]] = []
    for goal_str in goal_strs:
        targets.append((goal_str, _cell(goal_str), False))
    if event_ids:
        map_json = collision.load_map_json(map_id, maps_dir)
        events_by_id = {e["id"]: e for e in map_json.get("events", [])}
        for event_id in event_ids:
            event = events_by_id.get(event_id)
            if event is None:
                raise click.BadParameter(
                    f"map {map_id} has no event id {event_id}", param_hint="--event",
                )
            targets.append((f"event {event_id}", (event["x"], event["y"]), True))

    any_unreachable = False
    results = []
    for label, cell, is_event in targets:
        verdict = (
            derive_blocked_verdict_for_event(
                graph, capability_map, start, cell,
                require_clearing=require_clearing, candidates=candidates,
            )
            if is_event
            else derive_blocked_verdict(graph, capability_map, start, cell, candidates=candidates)
        )
        results.append((label, cell, verdict))
        if verdict.as_disposition() == "unreachable:geography":
            any_unreachable = True

    if as_json:
        payload = {
            "map_id": map_id,
            "start": f"{start[0]},{start[1]}",
            "results": [
                {
                    "target": label,
                    "cell": f"{cell[0]},{cell[1]}",
                    "reachable_now": verdict.reachable_now,
                    "disposition": verdict.as_disposition(),
                    "minimal_sets": [sorted(c.value for c in s) for s in verdict.minimal_sets],
                }
                for label, cell, verdict in results
            ],
        }
        click.echo(json.dumps(payload, indent=2))
    else:
        for label, cell, verdict in results:
            disposition = verdict.as_disposition() or "reachable"
            click.echo(f"  {label} ({cell[0]},{cell[1]}): {disposition}")

    if any_unreachable:
        raise SystemExit(1)


def _edge_json(e: WorldEdge) -> dict:
    return {
        "src_map": e.src_map,
        "dst_map": e.dst_map,
        "kind": e.kind,
        "src_cell": f"{e.src_cell[0]},{e.src_cell[1]}" if e.src_cell else None,
        "dst_cell": f"{e.dst_cell[0]},{e.dst_cell[1]}" if e.dst_cell else None,
        "event_id": e.event_id,
    }


@cli.command("world")
@click.option(
    "--maps-dir", type=click.Path(exists=True, path_type=Path),
    default=collision.DEFAULT_MAPS_DIR,
    help="Decoded maps directory (default: output/uranium-build/maps)",
)
@click.option(
    "--map-infos-json", type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_MAP_INFOS_JSON,
    help="Decoded map_infos oracle (default: output/uranium-build/map_infos.json)",
)
@click.option(
    "--connections-json", type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_CONNECTIONS_JSON,
    help="Decoded connections oracle (default: output/uranium-build/connections.json)",
)
@click.option(
    "--seam-warps-json", type=click.Path(exists=True, path_type=Path),
    default=DEFAULT_SEAM_WARPS_PATH,
    help="Seam-warp declarations (default: reference/seam_warps.json)",
)
@click.option(
    "--start-map", type=int, default=DEFAULT_START_MAP_ID,
    help=f"Game start map id, for the summary's unreachable-from-start report "
    f"(default: {DEFAULT_START_MAP_ID}, CH01's outdoor map).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit a full machine-readable JSON dump.")
@click.option(
    "--from", "from_map", type=int, default=None,
    help="Report every map reachable from this map id, with hop distance.",
)
@click.option(
    "--between", "between_maps", type=int, nargs=2, default=None,
    help="Shortest map-to-map path between two map ids, edge kinds annotated.",
)
def world_cmd(
    maps_dir: Path,
    map_infos_json: Path,
    connections_json: Path,
    seam_warps_json: Path,
    start_map: int,
    as_json: bool,
    from_map: int | None,
    between_maps: tuple[int, int] | None,
) -> None:
    """Corpus-wide map-to-map adjacency: warps + connections + seam warps."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    graph = build_world_graph(
        maps_dir=maps_dir,
        map_infos=map_infos_json,
        connections_json=connections_json,
        seam_warps=seam_warps_json,
    )

    def name(mid: int) -> str:
        return graph.names.get(mid, f"Map{mid:03d}")

    if between_maps:
        a, b = between_maps
        path = graph.shortest_path(a, b)
        if path is None:
            click.echo(f"UNREACHABLE: no map-to-map path from {a} ({name(a)}) to {b} ({name(b)})")
            raise SystemExit(1)
        if not path:
            click.echo(f"{a} ({name(a)}) is the same map as {b} ({name(b)})")
            return
        click.echo(f"{len(path)} hop(s): {a} ({name(a)})")
        for e in path:
            click.echo(f"  --[{e.kind}]--> {e.dst_map} ({name(e.dst_map)})")
        return

    if from_map is not None:
        dist = graph.hop_distances_from(from_map)
        click.echo(f"{len(dist)} map(s) reachable from {from_map} ({name(from_map)}):")
        for mid in sorted(dist, key=lambda m: (dist[m], m)):
            click.echo(f"  {dist[mid]:>3}  {mid} ({name(mid)})")
        return

    if as_json:
        payload = {
            "maps": sorted(graph.map_ids),
            "names": {str(mid): n for mid, n in sorted(graph.names.items())},
            "edges": [_edge_json(e) for e in graph.edges],
            "maps_without_info": sorted(graph.maps_without_info),
            "infos_without_map": sorted(graph.infos_without_map),
            "variable_warp_count": graph.variable_warp_count,
            "variable_warp_maps": {str(k): v for k, v in sorted(graph.variable_warp_maps.items())},
            "one_way_pairs": [
                {"src": a, "dst": b} for a, b in graph.one_way_pairs()
            ],
            "connected_components": [
                sorted(c) for c in sorted(graph.connected_components(), key=lambda c: (-len(c), min(c)))
            ],
            "orphan_maps": graph.orphan_maps(),
        }
        click.echo(json.dumps(payload, indent=2))
        return

    # Human-readable summary.
    edges_by_kind: dict[str, int] = {}
    for e in graph.edges:
        edges_by_kind[e.kind] = edges_by_kind.get(e.kind, 0) + 1

    components = sorted(graph.connected_components(), key=lambda c: (-len(c), min(c)))
    one_way = graph.one_way_pairs()
    orphans = graph.orphan_maps()

    if start_map in graph.map_ids:
        reachable = graph.reachable_from(start_map)
        unreachable = sorted(graph.map_ids - reachable)
    else:
        unreachable = None

    click.echo(f"{len(graph.map_ids)} map(s), {len(graph.edges)} edge(s)")
    for kind in ("warp", "connection", "seam_warp"):
        click.echo(f"  {kind}: {edges_by_kind.get(kind, 0)}")
    click.echo()

    click.echo(f"{len(one_way)} one-way (non-reciprocal) map pair(s):")
    for a, b in one_way:
        click.echo(f"  {a} ({name(a)}) -> {b} ({name(b)}), no edge back")
    click.echo()

    click.echo(f"{len(components)} connected component(s) (direction-ignored)")
    largest = components[0] if components else set()
    click.echo(f"  largest: {len(largest)} map(s)")
    for comp in components[1:]:
        click.echo(f"  component ({len(comp)} map(s)): {sorted(comp)}")
    click.echo()

    if unreachable is None:
        click.echo(f"start map {start_map} not present in the corpus -- cannot report unreachable maps")
    else:
        click.echo(f"{len(unreachable)} map(s) unreachable from start map {start_map} ({name(start_map)}):")
        for mid in unreachable:
            click.echo(f"  {mid} ({name(mid)})")
    click.echo()

    click.echo(f"{len(orphans)} orphan map(s) (no in-edges and no out-edges):")
    for mid in orphans:
        click.echo(f"  {mid} ({name(mid)})")
    click.echo()

    click.echo(
        f"{graph.variable_warp_count} variable-driven warp(s) (destination chosen at "
        f"runtime -- not represented as edges) across {len(graph.variable_warp_maps)} map(s):"
    )
    for mid, count in sorted(graph.variable_warp_maps.items()):
        click.echo(f"  {mid} ({name(mid)}): {count}")

    if graph.maps_without_info or graph.infos_without_map:
        click.echo()
        if graph.maps_without_info:
            click.echo(f"{len(graph.maps_without_info)} map file(s) with no map_infos.json entry: "
                       f"{sorted(graph.maps_without_info)}")
        if graph.infos_without_map:
            click.echo(f"{len(graph.infos_without_map)} map_infos.json entry(ies) with no map file: "
                       f"{sorted(graph.infos_without_map)}")


if __name__ == "__main__":
    cli()
