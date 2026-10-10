"""CLI for the offline chapter route solver.

    python -m rpg2gba.routing plan --chapter CH05
    python -m rpg2gba.routing plan --chapter CH05 --dry-run
    python -m rpg2gba.routing show --chapter CH05

`--chapter` is the atlas chapter id (`reference/chapters.json`), which keys
the manifest and route files. `--module` is the playtest chapter module that
registers the beats (`rpg2gba.playtest.chapters.<module>`, see
`playtest.chapter.load_chapter`). They are two different names for one
chapter. Since 2026-09-01 (CH05_DECISIONS E1) the module is *named for* the
chapter id -- `CH04` -> `chapters/ch04.py` -- so `--module` defaults to the
chapter id and only has to be passed when a chapter's beats deliberately live
in some other module. The two remain separate fields rather than one, because
the plan records the module as `RoutePlan.chapter_module` so every consumer
(notably `chapter_manifest.route_model`) can rediscover it from the artifact
rather than guessing. The chapter id
used for the manifest/route file naming convention:

    reference/manifests/<chapter>.manifest.json   (chapter_manifest.generator output)
    reference/routes/<chapter>.route.json          (this module's `plan` output)

with `--manifest`/`--out`/`--route` overrides for pointing at a scratch copy,
mirroring `chapter_manifest.__main__`'s option conventions.
"""
from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path

import click

from rpg2gba.map_split.spec import expand_split_ids
from ..chapter_manifest.__main__ import load_manifest
from ..chapter_manifest.checker import (
    Finding,
    TriggerOverlayModel,
    check_trigger_overlay,
)
from ..chapter_manifest.dispositions import disposition_path, load_dispositions
from ..chapter_manifest.schema import Disposition, ManifestRow
from ..playtest.chapter import load_chapter
from ..tileset_converter.map_constants import DEFAULT_STATE_PATH, MapConstantRegistry
from ..traversal.graph import MapGraph, build_map_graph
from ..traversal.triggers import (
    DEFAULT_ENGINE_MAPS_DIR,
    TriggerKind,
    TriggerOverlay,
    build_trigger_overlay,
)
from ..traversal.world import (
    DEFAULT_CONNECTIONS_JSON,
    DEFAULT_MAP_INFOS_JSON,
    DEFAULT_SEAM_WARPS_PATH,
    WorldGraph,
    build_world_graph,
)
from .locations import (
    chapter_from_locations,
    derive_locations,
    load_locations,
    locations_path,
    write_locations,
)
from .occupancy import MapOccupancy, build_occupancy
from .plan import RoutePlan, load_plan, plan_to_dict, route_path, write_plan
from .solver import RouteCandidate, RouteSolverError, solve_route

logger = logging.getLogger(__name__)

MANIFESTS_DIR = Path("reference") / "manifests"
DEFAULT_BUILD_DIR = Path("output") / "uranium-build"
DEFAULT_CHAPTERS_PATH = Path("reference") / "chapters.json"

# Sentinel for `--locations` used with no value: fall back to the
# reference/routes/<chapter>.locations.json convention.
_LOCATIONS_DEFAULT = "@default"


def _manifest_path(chapter: str) -> Path:
    return MANIFESTS_DIR / f"{chapter}.manifest.json"


def _load_chapter_maps(chapter_id: str, chapters_path: Path) -> list[int]:
    """The map ids bound to `chapter_id` in `chapters_path`, mirroring
    `chapter_manifest.generator._load_chapter_maps`'s simple lookup (kept as
    a separate small helper here rather than importing that private
    function -- CLAUDE.md §4.3's chain-binding source of truth is the file
    on disk, not either module's loader)."""
    data = json.loads(chapters_path.read_text(encoding="utf-8"))
    for entry in data.get("chapters", []):
        if entry.get("id") == chapter_id:
            return expand_split_ids(entry.get("maps", []))
    raise click.ClickException(f"no chapter {chapter_id!r} in {chapters_path}")


class _LazyGraphs(Mapping):
    """`MapGraph` per map id, built on first access and cached.

    Eagerly building only the chapter's own declared maps is not enough: a
    route legitimately leaves them. Solving CH04 (Route 2) walks through map
    31 (Kevlar Town) because the world graph's shortest hop between two of
    CH04's own points runs through it, and an eager roster raised a bare
    `KeyError: 31` out of `pathing.plan_segment`.

    Lazy is also the cheaper shape. `traversal` has no caching of its own --
    every `build_map_graph` re-parses the whole corpus-wide `tilesets.json`
    -- so building on demand and holding the result avoids both the maps a
    route never visits and the repeat builds a solver's pairwise-cost sweep
    would otherwise trigger.
    """

    def __init__(self, build_dir: Path) -> None:
        self._maps_dir = build_dir / "maps"
        self._tilesets_json = build_dir / "tilesets.json"
        self._cache: dict[int, MapGraph] = {}

    def __getitem__(self, map_id: int) -> MapGraph:
        if map_id not in self._cache:
            self._cache[map_id] = build_map_graph(
                map_id, maps_dir=self._maps_dir, tilesets_json=self._tilesets_json)
        return self._cache[map_id]

    def __iter__(self):  # noqa: ANN204 - Mapping protocol
        return iter(self._cache)

    def __len__(self) -> int:
        return len(self._cache)


class _LazyOverlays(Mapping):
    """`TriggerOverlay` per map id, built on first access and cached.

    Same reasoning as `_LazyGraphs`, plus one of its own: an overlay is built
    from the *emitted* pokeemerald map JSON, and only part of the corpus has
    been emitted. Building eagerly would fail on any unemitted map the route
    never actually touches.
    """

    def __init__(self, build_dir: Path, graphs: Mapping[int, MapGraph]) -> None:
        self._map_constants_json = build_dir / "porymap" / "map_constants.json"
        self._graphs = graphs
        self._cache: dict[int, TriggerOverlay] = {}
        self._unemitted: set[int] = set()

    def __contains__(self, map_id: object) -> bool:
        """Is `map_id` emitted (has an overlay)? `pathing`'s detour asks this
        before hopping: a detour through a map the ROM doesn't carry is not
        a route (the parked Metro station, map 44, sits one door off
        Nowtoch's main piece). Indexing an unemitted map still fails loud."""
        if not isinstance(map_id, int) or map_id in self._unemitted:
            return False
        try:
            self[map_id]
        except click.ClickException:
            self._unemitted.add(map_id)
            return False
        return True

    def __getitem__(self, map_id: int) -> TriggerOverlay:
        if map_id not in self._cache:
            try:
                self._cache[map_id] = build_trigger_overlay(
                    map_id, graph=self._graphs[map_id],
                    map_constants_json=self._map_constants_json,
                    engine_maps_dir=DEFAULT_ENGINE_MAPS_DIR,
                )
            except FileNotFoundError as exc:
                raise click.ClickException(
                    f"map {map_id} lies on this chapter's route but has no emitted "
                    f"map data to build a trigger overlay from ({exc}). Convert that "
                    f"map before routing this chapter -- routing it blind would plan "
                    f"a walk across triggers nothing can see."
                ) from exc
        return self._cache[map_id]

    def __iter__(self):  # noqa: ANN204 - Mapping protocol
        return iter(self._cache)

    def __len__(self) -> int:
        return len(self._cache)


class _OverlayTrainerSightModel(TriggerOverlayModel):
    """The concrete `TriggerOverlayModel` adapter `plan_cmd` wires into
    `chapter_manifest.checker.check_trigger_overlay` (RULE_TRIGGER_OVERLAY_
    VACUOUS/_MODEL_UNENFORCED, PROJECT_TODO #75) -- wraps the SAME
    `_LazyOverlays` mapping this module already builds for `solve_route`
    itself, so "does map N have a TRAINER_SIGHT tile" is answered from the
    identical overlay the solver's own CROSSING accounting reads, not a
    second, possibly-diverging build.
    """

    def __init__(self, overlays: Mapping[int, TriggerOverlay]) -> None:
        self._overlays = overlays

    def has_trainer_sight_tiles(self, map_id: int) -> bool:
        overlay = self._overlays[map_id]
        return any(
            ref.kind is TriggerKind.TRAINER_SIGHT
            for refs in overlay.tiles.values()
            for ref in refs
        )


def _check_trigger_overlay_or_raise(
    rows: list[ManifestRow],
    chapter: str,
    overlays: Mapping[int, TriggerOverlay],
) -> None:
    """Runs `check_trigger_overlay` at the ROUTE step itself -- see
    `TriggerOverlayModel`'s docstring for why zero `CROSSING` lines must not
    be allowed to read as "checked and clean" when it could instead mean
    "the overlay measured nothing" (PROJECT_TODO #75, the CH05 incident).

    Dispositions are loaded here, independently of `rows`, from the same
    default path `chapter_manifest.__main__`'s `check` command reads
    (`reference/manifests/<chapter>.dispositions.json`) -- if that file does
    not exist yet, there is nothing to classify as a "dispositioned trainer
    row" and the check is silently skipped. A chapter with no dispositions
    file at all is a different, already-covered failure (`chapter_manifest
    check`'s own `RULE_UNDISPOSITIONED`), not the vacuous-overlay problem
    this rule exists to catch.
    Raises `click.ClickException` on any ERROR-severity finding; logs any
    WARNING-severity finding (e.g. `RULE_TRIGGER_OVERLAY_MODEL_UNENFORCED`,
    which cannot fire here since this always supplies a model, but stays
    generically handled for parity with `chapter_manifest check`'s own
    reporting).
    """
    disp_file = disposition_path(chapter)
    if not disp_file.exists():
        logger.warning(
            "%s: no dispositions file found -- skipping the trigger-overlay "
            "vacuousness check (RULE_TRIGGER_OVERLAY_VACUOUS unenforced for "
            "this solve)",
            disp_file,
        )
        return

    dispositions: dict[str, Disposition] = load_dispositions(disp_file)
    findings: list[Finding] = check_trigger_overlay(
        rows, dispositions, trigger_overlay=_OverlayTrainerSightModel(overlays),
    )

    errors = [f for f in findings if f.severity == "error"]
    for f in findings:
        if f.severity == "warning":
            logger.warning("%s: %s: %s", f.rule, f.row_id, f.message)
    if errors:
        detail = "\n".join(f"  {f.row_id} ({f.rule}): {f.message}" for f in errors)
        raise click.ClickException(
            f"trigger overlay looks vacuous on {len(errors)} map(s) with a "
            f"dispositioned trainer row -- a zero-CROSSING route across "
            f"them would be unproven, not clean:\n{detail}"
        )


class _LazyOccupancy(Mapping):
    """`MapOccupancy` per map id, built on first access and cached.

    Reads the SAME `map_constants.json`/`engine/data/maps` source
    `_LazyOverlays` does, and for the same reason `occupancy.py`'s module
    docstring gives: occupancy and trigger sight cones must be present or
    absent together for a given map, or a chapter could get one without the
    other. Degrades identically to `_LazyOverlays` on a not-yet-emitted map.
    """

    def __init__(self, build_dir: Path) -> None:
        self._map_constants_json = build_dir / "porymap" / "map_constants.json"
        self._cache: dict[int, MapOccupancy] = {}

    def __getitem__(self, map_id: int) -> MapOccupancy:
        if map_id not in self._cache:
            try:
                self._cache[map_id] = build_occupancy(
                    map_id,
                    map_constants_json=self._map_constants_json,
                    engine_maps_dir=DEFAULT_ENGINE_MAPS_DIR,
                )
            except FileNotFoundError as exc:
                raise click.ClickException(
                    f"map {map_id} lies on this chapter's route but has no emitted "
                    f"map data to build an occupancy overlay from ({exc}). Convert "
                    f"that map before routing this chapter -- routing it blind "
                    f"would plan a walk straight through its NPCs."
                ) from exc
        return self._cache[map_id]

    def __iter__(self):  # noqa: ANN204 - Mapping protocol
        return iter(self._cache)

    def __len__(self) -> int:
        return len(self._cache)


def _build_graphs_and_overlays(
    map_ids: list[int], build_dir: Path,
) -> tuple[Mapping[int, MapGraph], Mapping[int, TriggerOverlay]]:
    """Lazy graph/overlay views. `map_ids` is retained for the caller's own
    reporting; neither view is limited to it (see `_LazyGraphs`)."""
    graphs = _LazyGraphs(build_dir)
    return graphs, _LazyOverlays(build_dir, graphs)


def _build_world(build_dir: Path) -> WorldGraph:
    return build_world_graph(
        maps_dir=build_dir / "maps",
        map_infos=build_dir / "map_infos.json" if (build_dir / "map_infos.json").exists()
        else DEFAULT_MAP_INFOS_JSON,
        connections_json=build_dir / "connections.json"
        if (build_dir / "connections.json").exists() else DEFAULT_CONNECTIONS_JSON,
        seam_warps=DEFAULT_SEAM_WARPS_PATH,
    )


def _load_map_ids(build_dir: Path) -> dict[str, int]:
    state_path = build_dir / "porymap" / "map_constants.json"
    registry = MapConstantRegistry(state_path=state_path if state_path.exists() else DEFAULT_STATE_PATH)
    registry.load()
    return registry.map_const_to_uranium_id()


def _summary(plan: RoutePlan) -> str:
    lines = [
        f"chapter {plan.chapter_id} ({plan.chapter_module}) -- solver: {plan.solver_method}",
        f"{len(plan.nodes)} node(s), {plan.tile_cost} tile(s) total",
        "",
        "nodes:",
    ]
    for node in plan.nodes:
        if node.kind == "group":
            approach = ""
            if node.chosen_approach is not None:
                approach = (f" approach={node.chosen_approach.side} "
                            f"({node.chosen_approach.resolver})")
            lines.append(
                f"  [{node.index}] group {node.group!r} beats={list(node.beats)} "
                f"map={node.map_id} cell={node.cell}{approach}"
            )
        else:
            lines.append(f"  [{node.index}] {node.kind} map={node.map_id} cell={node.cell}")

    lines += ["", "segments:"]
    any_crossings = False
    for segment in plan.segments:
        lines.append(f"  {segment.from_index} -> {segment.to_index}: {segment.tile_count} tile(s)")
        for crossing in segment.crossed_foreign_triggers:
            any_crossings = True
            lines.append(
                f"    CROSSING map={crossing.map_id} cell={crossing.cell} "
                f"script={crossing.script} certainty={crossing.certainty}"
            )
    if any_crossings:
        lines.append("WARNING: this plan crosses one or more foreign trigger tiles (see above)")

    lines += ["", "precedence:"]
    if not plan.precedence:
        lines.append("  (none)")
    for edge in plan.precedence:
        lines.append(f"  {edge.before} -> {edge.after}: {edge.reason}")

    return "\n".join(lines)


@click.group()
def cli() -> None:
    """rpg2gba offline chapter route solver (see routing/solver.py)."""


@cli.command("plan")
@click.option("--chapter", required=True, help="Chapter id, e.g. CH05.")
@click.option("--out", type=click.Path(path_type=Path), default=None,
              help="Route plan output path (default: reference/routes/<chapter>.route.json)")
@click.option("--manifest", type=click.Path(exists=True, path_type=Path), default=None,
              help="Manifest JSON path (default: reference/manifests/<chapter>.manifest.json)")
@click.option("--build-dir", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_BUILD_DIR,
              help="Converted-map build directory (default: output/uranium-build)")
@click.option("--chapters", "chapters_path", type=click.Path(exists=True, path_type=Path),
              default=DEFAULT_CHAPTERS_PATH,
              help="Chapter/map chain JSON (default: reference/chapters.json)")
@click.option("--module", "module", default=None,
              help="Playtest chapter module registering the beats "
                   "(default: the chapter id, e.g. CH04 -> chapters/ch04.py).")
@click.option("--locations", "locations_opt", type=str,
              default=None, is_flag=False, flag_value=_LOCATIONS_DEFAULT,
              help="Solve against a derived locations file instead of importing the playtest chapter module (default path: reference/routes/<chapter>.locations.json). This is the step-6 path: it lets an ORDER be approved before the beats are authored.")
@click.option("--dry-run", is_flag=True, help="Solve and print a summary; write nothing.")
def plan_cmd(
    chapter: str, out: Path | None, manifest: Path | None, build_dir: Path,
    chapters_path: Path, module: str | None, locations_opt: str | None,
    dry_run: bool,
) -> None:
    """Solve a chapter's route plan and write it (or, with --dry-run, just show it)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    manifest_file = manifest or _manifest_path(chapter)
    if not manifest_file.exists():
        raise click.ClickException(f"manifest not found: {manifest_file}")

    rows = load_manifest(manifest_file)

    # group id -> its candidate approach sides, when the beat behind it
    # carries more than one (derived-locations path only -- an authored
    # module's `BeatLocation` has no side-candidate field, so this stays
    # empty on that path and `solve_route` reproduces today's single-cell
    # behaviour, per its own docstring).
    route_candidates: dict[str, tuple[RouteCandidate, ...]] = {}

    if locations_opt is not None:
        if module is not None:
            raise click.ClickException(
                "--locations and --module are mutually exclusive: the first "
                "solves against derived coordinates (before the beats exist), "
                "the second against the authored module")
        loc_file = (locations_path(chapter) if locations_opt == _LOCATIONS_DEFAULT
                    else Path(locations_opt))
        if not loc_file.exists():
            raise click.ClickException(
                f"locations file not found: {loc_file} -- run "
                f"`python -m rpg2gba.routing locations --chapter {chapter}` first")
        loc_chapter, records = load_locations(loc_file)
        if loc_chapter != chapter:
            raise click.ClickException(
                f"{loc_file} is for chapter {loc_chapter!r}, not {chapter!r}")
        chapter_obj = chapter_from_locations(chapter, records)
        logger.info("solving against %d derived location(s) from %s",
                    len(records), loc_file)
        # `chapter_from_locations` gives every derived beat its own singleton
        # group, named after the beat -- so `record.beat_id` IS the group id
        # `solve_route` will see (see `playtest.chapter.Chapter.groups`).
        for record in records:
            if record.approach_candidates:
                route_candidates[record.beat_id] = tuple(
                    RouteCandidate(x=c.x, y=c.y, side=c.side, resolver=c.resolver)
                    for c in record.approach_candidates
                )
    else:
        module = module or chapter
        try:
            chapter_obj = load_chapter(module)
        except KeyError as exc:
            raise click.ClickException(str(exc)) from exc
    map_ids_for_chapter = _load_chapter_maps(chapter, chapters_path)
    graphs, overlays = _build_graphs_and_overlays(map_ids_for_chapter, build_dir)
    occupancy = _LazyOccupancy(build_dir)
    world = _build_world(build_dir)
    map_const_to_id = _load_map_ids(build_dir)

    # RULE_TRIGGER_OVERLAY_VACUOUS (PROJECT_TODO #75): before trusting
    # whatever CROSSING count the solve below produces, confirm the overlay
    # it will read actually saw a TRAINER_SIGHT tile on every map this
    # chapter has a dispositioned trainer row on -- see
    # `_check_trigger_overlay_or_raise`/`TriggerOverlayModel` for why this
    # must happen here, at the ROUTE step, not later.
    _check_trigger_overlay_or_raise(rows, chapter, overlays)

    try:
        route = solve_route(
            chapter_obj, chapter,
            manifest_rows=rows, graphs=graphs, overlays=overlays, world=world,
            map_ids=map_const_to_id, occupancy=occupancy,
            candidates=route_candidates,
        )
    except RouteSolverError as exc:
        raise click.ClickException(str(exc)) from exc

    if dry_run:
        click.echo(_summary(route))
        sys.exit(0)

    out_path = out or route_path(chapter)
    write_plan(route, out_path)
    click.echo(f"wrote {out_path}: {len(route.nodes)} node(s), {route.tile_cost} tile(s)")
    sys.exit(0)


@cli.command("locations")
@click.option("--chapter", required=True, help="Chapter id, e.g. CH05.")
@click.option("--manifest", type=click.Path(exists=True, path_type=Path), default=None,
              help="Manifest path (default: reference/manifests/<chapter>.manifest.json)")
@click.option("--dispositions", "dispositions_opt",
              type=click.Path(exists=True, path_type=Path), default=None,
              help="Dispositions path (default: reference/manifests/<chapter>.dispositions.json)")
@click.option("--out", type=click.Path(path_type=Path), default=None,
              help="Output path (default: reference/routes/<chapter>.locations.json)")
@click.option("--dry-run", is_flag=True, help="Derive and print; write nothing.")
def locations_cmd(chapter: str, manifest: Path | None, dispositions_opt: Path | None,
                  out: Path | None, dry_run: bool) -> None:
    """Derive each dispositioned beat's routing point from the manifest.

    Runs BEFORE the chapter's playtest module exists, which is what lets
    step 6 approve an order rather than grade one. Emits where each beat is,
    never what happens there.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    manifest_file = manifest or _manifest_path(chapter)
    if not manifest_file.exists():
        raise click.ClickException(f"manifest not found: {manifest_file}")
    disp_file = dispositions_opt or (MANIFESTS_DIR / f"{chapter}.dispositions.json")
    if not disp_file.exists():
        raise click.ClickException(f"dispositions not found: {disp_file}")

    rows = load_manifest(manifest_file)
    try:
        records = derive_locations(chapter, rows, disp_file)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    for record in records:
        extra = ""
        if len({(c.map_constant, c.x, c.y) for c in record.candidates}) > 1:
            extra = "  [multi-cell: routed on terminal row]"
        if len(record.approach_candidates) > 1:
            sides = "/".join(a.side for a in record.approach_candidates)
            extra += f"  [approach sides: {sides}]"
        click.echo(f"{record.beat_id:<5} {record.map_constant} "
                   f"({record.x},{record.y})  {record.resolver}"
                   f"  rows={','.join(record.rows)}{extra}")

    if dry_run:
        return
    out_path = out or locations_path(chapter)
    write_locations(chapter, records, out_path)
    click.echo(f"wrote {out_path}: {len(records)} beat(s)")


@cli.command("show")
@click.option("--chapter", required=True, help="Chapter id, e.g. CH05.")
@click.option("--route", "route_path_opt", type=click.Path(exists=True, path_type=Path),
              default=None,
              help="Route plan path (default: reference/routes/<chapter>.route.json)")
@click.option("--json", "as_json", is_flag=True, help="Emit the raw plan JSON instead of a summary.")
def show_cmd(chapter: str, route_path_opt: Path | None, as_json: bool) -> None:
    """Print a readable summary (or --json dump) of an already-solved route plan."""
    route_file = route_path_opt or route_path(chapter)
    if not route_file.exists():
        raise click.ClickException(f"route plan not found: {route_file}")

    plan = load_plan(route_file)

    if as_json:
        click.echo(json.dumps(plan_to_dict(plan), indent=2))
        return

    click.echo(_summary(plan))


if __name__ == "__main__":
    cli()
