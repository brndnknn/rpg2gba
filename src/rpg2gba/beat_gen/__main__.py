"""`python -m rpg2gba.beat_gen generate --chapter CHnn` (C6 Task 9).

Ties the stages together and writes, under `--out-dir` (default
`output/beats/`):

    chNN.generated.py   the module (emit.py)
    CHnn.review.md      the review doc (review.py)
    CHnn.route.json     the solved route (routing.plan.write_plan)

Output lands in `output/` by ruling (C6 plan B1): C9, not C6, owns putting
a generated module under `playtest/chapters/` and a route under
`reference/routes/`.

STATUS: wired (`assignments/C6/09_cli.md`). The boundary-warp decision
(the task file's "blocker you will hit") is still open; see the
`BOUNDARY WARP` note in `build_plan`.

The solver's argument assembly is imported from `routing/__main__.py`'s
`plan` command rather than copied: the lazy graph/overlay/occupancy views,
the world graph, the MAP_* -> id table and the trigger-overlay check are
one implementation, used by both CLIs (§4.3).
"""
from __future__ import annotations

import dataclasses
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

import click

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.beat_floor.walk import floor_for_chapter
from rpg2gba.beat_gen.adapt import archetype_kwargs, route_kwargs, warp_candidates
from rpg2gba.beat_gen.emit import emit_module
from rpg2gba.beat_gen.group import plan_beats
from rpg2gba.beat_gen.locate import locate_beats, order_beats, route_order
from rpg2gba.beat_gen.plan import (
    ARCHETYPE_TEMPLATES,
    ChapterPlan,
    PlannedBeat,
    make_kwargs,
)
from rpg2gba.beat_gen.review import render_review
from rpg2gba.beat_gen.seam import SeamCrossing, connection_for, seam_crossings
from rpg2gba.beat_gen.select import select_rows
from rpg2gba.chapter_atlas.binding import ChapterBinding, load_binding
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch, classify_manifest
from rpg2gba.chapter_manifest.schema import ManifestRow, parse_row_id
from rpg2gba.playtest.archetypes import load_chapter_rows
from rpg2gba.routing.__main__ import (
    DEFAULT_CHAPTERS_PATH,
    _build_graphs_and_overlays,
    _build_world,
    _check_trigger_overlay_or_raise,
    _LazyOccupancy,
    _load_map_ids,
)
from rpg2gba.routing.locations import (
    BeatLocationRecord,
    RowCell,
    _map_constant_for,  # the one MAP_* lookup; `cell_for_row` uses it too
    cell_for_row,
    chapter_from_locations,
)
from rpg2gba.routing.plan import write_plan
from rpg2gba.routing.solver import RouteCandidate, solve_route
from rpg2gba.story_state.model import build_chapter_stories
from rpg2gba.traversal.graph import MapGraph

logger = logging.getLogger(__name__)

BUILD_DIR = Path("output/uranium-build")
DEFAULT_OUT_DIR = Path("output/beats")


def _chain_to(binding: ChapterBinding, chapter_id: str) -> list[str]:
    """The chapter ids from the chain's root up to and including
    `chapter_id`: `build_chapter_stories` seeds each chapter from its
    predecessor's end state, so it needs the whole chain, not one id."""
    chain: list[str] = []
    current: str | None = chapter_id
    while current is not None:
        if current in chain:
            raise ValueError(f"{chapter_id}: predecessor cycle through {current}")
        chain.append(current)
        current = binding.chapter(current).predecessor
    return chain[::-1]


def _match_for(beat: PlannedBeat, matches: Sequence[ArchetypeMatch]) -> ArchetypeMatch:
    """The archetype match an archetype beat was planned from, keyed the
    way `classify_manifest` keys them: (archetype, map, event)."""
    event_id = parse_row_id(beat.rows[0]).event_id
    found = [m for m in matches
             if (m.archetype, m.map_id, m.event_id) == (beat.template, beat.map_id, event_id)]
    if len(found) != 1:
        raise ValueError(
            f"beat {beat.name!r}: expected one {beat.template} match on "
            f"map {beat.map_id} event {event_id}, found {len(found)}")
    return found[0]


def _merge_kwargs(beat: PlannedBeat, extra: Mapping[str, object], *, drop: tuple[str, ...] = ()
                  ) -> PlannedBeat:
    """`beat` with `extra` merged into its kwargs. A key present on both
    sides is a stage disagreement, so it raises rather than letting one
    side silently win (§4.5)."""
    base = {k: v for k, v in beat.kwargs if k not in drop}
    clash = sorted(set(base) & set(extra))
    if clash:
        raise ValueError(f"beat {beat.name!r}: kwargs {clash} set by two stages")
    return dataclasses.replace(beat, kwargs=make_kwargs(**base, **extra))


def _cell_fn(warp_rows: frozenset[str], graphs: Mapping[int, MapGraph]):  # noqa: ANN202
    """`cell_for_row`, except a warp beat's row also gets its walkable
    sides as approach candidates (`cell_for_row` puts the player ON a warp,
    which offers the solver nothing to pick; Task 5's `warp_candidates`)."""
    def cell_fn(row: ManifestRow) -> RowCell:
        cell = cell_for_row(row)
        if row.row_id not in warp_rows:
            return cell
        return dataclasses.replace(
            cell, approach_candidates=warp_candidates((cell.x, cell.y), graphs[row.map_id]))
    return cell_fn


def _seam_fn(graphs: Mapping[int, MapGraph]):  # noqa: ANN202
    def seam_fn(row: ManifestRow) -> tuple[SeamCrossing, ...]:
        return seam_crossings(row, from_graph=graphs[row.map_id],
                              to_graph=graphs[connection_for(row).to_map])
    return seam_fn


def _picks_with_fallback(records: Sequence[BeatLocationRecord], picks: Mapping[str, str]
                         ) -> dict[str, str]:
    """The solver's picks, plus the only candidate of every group that had
    exactly one. The solver records `chosen_approach` only when it had a
    choice, so a one-candidate group comes back pick-less even though its
    side is fully decided."""
    out = dict(picks)
    for record in records:
        if record.beat_id not in out and len(record.approach_candidates) == 1:
            out[record.beat_id] = record.approach_candidates[0].side
    return out


def _apply_route_kwargs(beat: PlannedBeat) -> PlannedBeat:
    """Turn the `approach_prefer` pick `order_beats` stamped on a beat into
    that template's route kwargs (for a warp: press direction and round
    trip). A warp without a pick raises: it would reach the emitter with no
    direction, which `warp_beat` can't walk."""
    side = dict(beat.kwargs).get("approach_prefer")
    if side is None:
        if beat.template == "warp":
            raise ValueError(
                f"warp beat {beat.name!r} has no approach side: the solver made no "
                f"pick and its group has more than one candidate")
        return beat
    return _merge_kwargs(beat, dict(route_kwargs(beat.template, side)),
                         drop=("approach_prefer",))


def build_plan(chapter_id: str, *, build_dir: Path = BUILD_DIR) -> ChapterPlan:
    """Run stages 1-4 for one chapter and return the fully decided plan."""
    # 1. Load.
    binding = load_binding(DEFAULT_CHAPTERS_PATH)
    predecessor = binding.chapter(chapter_id).predecessor
    rows = load_chapter_rows(chapter_id)
    rows_by_id = {r.row_id: r for r in rows}
    stories = build_chapter_stories(_chain_to(binding, chapter_id), build_dir=build_dir,
                                    chapters_path=DEFAULT_CHAPTERS_PATH)
    story = stories[chapter_id]
    verdicts = {v.row_id: v for v in story.rows}
    floors: dict[str, RowFloor] = floor_for_chapter(chapter_id, build_dir=build_dir)
    matches = classify_manifest(rows)

    # 2. Select and group.
    selection = select_rows(rows, verdicts, floors)
    beats = plan_beats(selection.owned, matches, floors)

    # 3. Adapt, source half.
    beats = tuple(
        _merge_kwargs(b, dict(archetype_kwargs(b, _match_for(b, matches), floors,
                                               map_constant_fn=_map_constant_for)))
        if b.template in ARCHETYPE_TEMPLATES else b
        for b in beats
    )

    # 4. Locate. Graphs are lazy: a seam or a route may touch maps outside
    #    the chapter's own list (`routing.__main__._LazyGraphs`).
    graphs, overlays = _build_graphs_and_overlays(list(binding.chapter(chapter_id).maps),
                                                  build_dir)
    warp_rows = frozenset(r for b in beats if b.template == "warp" for r in b.rows)
    records, cell_refusals = locate_beats(
        beats, rows_by_id,
        cell_fn=_cell_fn(warp_rows, graphs), seam_fn=_seam_fn(graphs),
        map_constant_fn=_map_constant_for)
    # A refused group has no record, so the solver can't visit it; its
    # beats leave the plan and survive only as refusals in the review doc.
    located = {r.beat_id for r in records}
    beats = tuple(b for b in beats if b.group in located)

    # 5. Solve, with the same argument assembly as `routing plan`.
    _check_trigger_overlay_or_raise(list(rows), chapter_id, overlays)
    candidates = {
        r.beat_id: tuple(RouteCandidate(x=c.x, y=c.y, side=c.side, resolver=c.resolver)
                         for c in r.approach_candidates)
        for r in records if r.approach_candidates
    }
    route = solve_route(
        chapter_from_locations(chapter_id, records), chapter_id,
        manifest_rows=rows, graphs=graphs, overlays=overlays,
        world=_build_world(build_dir), map_ids=_load_map_ids(build_dir),
        occupancy=_LazyOccupancy(build_dir), candidates=candidates,
    )

    # 6. Order, then adapt's route half.
    # BOUNDARY WARP (09_cli.md, "The blocker you will hit"): every warp that
    # reaches here becomes a round trip, including one whose destination is
    # the next chapter's unstaged map. Which stage marks a warp as a chapter
    # boundary, and what its beat does instead, is the open design call.
    group_order, picks = route_order(route.nodes)
    beats = order_beats(beats, group_order, _picks_with_fallback(records, picks))
    beats = tuple(_apply_route_kwargs(b) for b in beats)

    return ChapterPlan(
        chapter_id=chapter_id,
        predecessor=predecessor,
        beats=beats,
        refusals=selection.refusals + tuple(cell_refusals),
        elsewhere=selection.elsewhere,
        order_dependent=story.order_dependent,
        route=route,
    )


def write_outputs(plan: ChapterPlan, out_dir: Path, *, build_dir: Path = BUILD_DIR) -> list[Path]:
    """Write the three artifacts; return their paths in a fixed order
    (module, review, route). Overwrites; must be byte-identical on re-run."""
    if plan.route is None:
        raise ValueError(f"{plan.chapter_id}: plan has no solved route to write")
    out_dir.mkdir(parents=True, exist_ok=True)
    module_path = out_dir / f"{plan.chapter_id.lower()}.generated.py"
    review_path = out_dir / f"{plan.chapter_id}.review.md"
    route_path = out_dir / f"{plan.chapter_id}.route.json"

    module_path.write_text(emit_module(plan), encoding="utf-8")
    review_path.write_text(
        render_review(plan, floor_lookup=lambda row_id: floor_for_row(row_id, build_dir=build_dir)),
        encoding="utf-8")
    write_plan(plan.route, route_path)
    return [module_path, review_path, route_path]


@click.group()
def cli() -> None:
    """The C6 beat generator."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@cli.command()
@click.option("--chapter", "chapter_id", required=True, help="e.g. CH05")
@click.option("--out-dir", type=click.Path(path_type=Path), default=DEFAULT_OUT_DIR,
              show_default=True)
def generate(chapter_id: str, out_dir: Path) -> None:
    """Generate one chapter's module, review doc and route."""
    plan = build_plan(chapter_id)
    for path in write_outputs(plan, out_dir):
        logger.info("wrote %s", path)
    if plan.refusals:
        logger.warning("%s: %d rows refused -- see the review doc",
                       chapter_id, len(plan.refusals))


if __name__ == "__main__":
    cli()
