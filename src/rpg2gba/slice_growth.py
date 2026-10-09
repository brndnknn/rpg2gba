"""Detector for warps that were invisible when a chapter was authored and are
live now (`REDERIVATION_PLAN.md` step P2, filed as A5).

`metadata_wiring.classify_event` skips an event **wholesale** the moment any of
its `code 201` (RMXP "Transfer Player") targets falls outside the current
`SLICE_MAP_IDS` -- see its docstring and `_event_transfers` in
`tileset_converter/metadata_wiring.py`. `SLICE_MAP_IDS` only ever grows as
chapters are staged, so an event on an already-shipped chapter's map that
warps toward then-unbuilt territory was correctly invisible at authoring time
(nothing referenced the missing map) but silently becomes a *live* warp the
moment a later chapter stages that target -- the event itself never changes
and nothing re-examines it.

This has already produced two real bugs: CH03's beat B25 asserted a "clean
impassable wall" toward what was then-unbuilt Route 2, and CH04's beat B7
asserted "no warp fires" at a cave mouth that, once CH05 staged that map,
would have teleported the player through five downstream beats.

This module answers, per gated (`status: "built"`) chapter: which events on
that chapter's own maps carry a `code 201` transfer to a map that was
out-of-slice when the chapter was authored and is in-slice in the current
`SLICE_MAP_IDS`?

Transfer extraction is **not** reimplemented here -- `CLAUDE.md` §4.3, one
source of truth per concept. Everything about *what counts as a code-201
transfer* is delegated to `metadata_wiring._event_transfers` and
`metadata_wiring.classify_event`; this module only adds the historical
(authoring-time slice) dimension those functions have no reason to know
about.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from rpg2gba.map_split.spec import expand_split_ids
from rpg2gba.tileset_converter.metadata_wiring import (
    TRANSFER_CODE,
    _event_transfers,
    classify_event,
)

logger = logging.getLogger(__name__)

DEFAULT_CHAPTERS_JSON = Path("reference/chapters.json")


class SliceGrowthError(RuntimeError):
    """`reference/chapters.json` and `tileset_converter/map_set.SLICE_MAP_IDS`
    disagree about the chapter-by-chapter map roster.

    Raised instead of silently trusting one side (`CLAUDE.md` §4.5) -- this
    detector's whole premise is "the authoring-time slice for CHnn is the
    union of CH01..CHnn's map lists," so if that union doesn't reconcile with
    the current `SLICE_MAP_IDS`, every result below is suspect.
    """


@dataclass(frozen=True)
class ChapterSlice:
    """One gated chapter's own maps and its authoring-time slice (the
    cumulative union of every gated chapter's maps up to and including this
    one, in build order)."""

    chapter_id: str
    own_map_ids: tuple[int, ...]
    authoring_slice: frozenset[int]


@dataclass(frozen=True)
class SliceGrowthEvent:
    """One event, on one of a chapter's own maps, whose `code 201` transfer
    to `target_map_id` was out-of-slice when the chapter carrying the event
    was authored and is in-slice in the current `SLICE_MAP_IDS`.

    `page_indices` is every page (0-based, within the event's own `pages`
    list) that carries the specific transfer to `target_map_id` -- an event
    can have several pages, and only some may target the newly-live map.
    """

    map_id: int
    event_id: int
    event_name: str | None
    page_indices: tuple[int, ...]
    target_map_id: int
    authored_status: str  # classify_event's verdict at authoring time, e.g. "skip"


@dataclass
class ChapterSliceGrowthReport:
    """Everything found for one gated chapter."""

    chapter_id: str
    own_map_ids: tuple[int, ...]
    authored_slice_size: int
    current_slice_size: int
    events: list[SliceGrowthEvent] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.events

    def format(self) -> str:
        if not self.events:
            return f"{self.chapter_id}: clean -- no newly-live out-of-slice warps"
        rows = sorted(self.events, key=lambda e: (e.map_id, e.event_id, e.target_map_id))
        lines = [
            f"{self.chapter_id}: {len(rows)} newly-live warp(s) "
            f"(authored against {self.authored_slice_size} maps, now {self.current_slice_size}):"
        ]
        for e in rows:
            pages = ",".join(str(p) for p in e.page_indices)
            lines.append(
                f"  Map{e.map_id:03d} EV{e.event_id:03d} {e.event_name!r} "
                f"page(s) [{pages}] -> Map{e.target_map_id:03d} "
                f"(authored-time verdict: {e.authored_status!r})"
            )
        return "\n".join(lines)


def _chapter_maps_in_build_order(
    chapters_json: Path, *, only_built: bool = True, status: str | None = None
) -> list[tuple[str, tuple[int, ...]]]:
    """`(chapter_id, maps)` for every chapter in `chapters.json`, in file
    order, deduplicated to each id's first occurrence (a handful of ids like
    CH07/CH07A repeat a map roster later in the corpus; only the first,
    build-order appearance is relevant to an authoring-time union).

    `only_built` restricts to `status == "built"` -- the gated chapters this
    detector is defined over. `status`, when given, restricts to that status
    instead (and overrides `only_built`). `reference/chapters.json` is the
    §4.3 source of truth for chapter/map binding; this reads it, it does not
    hardcode a list.
    """
    wanted = status if status is not None else ("built" if only_built else None)
    data = json.loads(chapters_json.read_text(encoding="utf-8"))
    seen: set[str] = set()
    out: list[tuple[str, tuple[int, ...]]] = []
    for chapter in data["chapters"]:
        chapter_id = chapter["id"]
        if chapter_id in seen:
            continue
        seen.add(chapter_id)
        if wanted is not None and chapter.get("status") != wanted:
            continue
        out.append((chapter_id, tuple(expand_split_ids(chapter["maps"]))))
    return out


def gated_chapter_slices(
    chapters_json: Path = DEFAULT_CHAPTERS_JSON,
    *,
    current_slice_ids: list[int] | None = None,
) -> list[ChapterSlice]:
    """Every gated chapter with its own maps and its authoring-time slice.

    `current_slice_ids` defaults to `tileset_converter.map_set.SLICE_MAP_IDS`.
    Fails loud (`SliceGrowthError`) if the cumulative union of all gated
    chapters' maps disagrees with the current slice -- either in the total
    map count, in set membership, or against the specific milestones recorded
    in `map_set.py`'s comments and `REDERIVATION_PLAN.md` (CH01=8, CH02=10,
    CH03=15, CH04=16, CH05=18 maps cumulative). A disagreement means the two
    sources of truth (`chapters.json` and `SLICE_MAP_IDS`) have drifted, and
    every downstream result in this module would be built on a wrong premise.
    """
    if current_slice_ids is None:
        from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

        current_slice_ids = SLICE_MAP_IDS

    current_slice = frozenset(current_slice_ids)
    chapters = _chapter_maps_in_build_order(chapters_json, only_built=True)
    if not chapters:
        raise SliceGrowthError(f"no chapters with status=='built' found in {chapters_json}")

    # Only enforced against the real, tracked chapters.json -- these are the
    # documented milestones for *this repo's* corpus (map_set.py comments,
    # REDERIVATION_PLAN.md), not a general property callers' synthetic test
    # fixtures need to satisfy.
    _EXPECTED_MILESTONES = (
        {"CH01": 8, "CH02": 10, "CH03": 15, "CH04": 16, "CH05": 18}
        if chapters_json.resolve() == DEFAULT_CHAPTERS_JSON.resolve()
        else {}
    )

    slices: list[ChapterSlice] = []
    cumulative: set[int] = set()
    for chapter_id, own_maps in chapters:
        overlap = cumulative & set(own_maps)
        if overlap:
            raise SliceGrowthError(
                f"{chapter_id} in {chapters_json} re-introduces map id(s) "
                f"{sorted(overlap)} already claimed by an earlier built chapter -- "
                "the cumulative-union model this detector relies on assumes each "
                "map is introduced by exactly one chapter"
            )
        cumulative |= set(own_maps)
        slices.append(
            ChapterSlice(
                chapter_id=chapter_id,
                own_map_ids=own_maps,
                authoring_slice=frozenset(cumulative),
            )
        )
        expected = _EXPECTED_MILESTONES.get(chapter_id)
        if expected is not None and len(cumulative) != expected:
            raise SliceGrowthError(
                f"cumulative map count after {chapter_id} is {len(cumulative)}, but "
                f"map_set.py's SLICE_MAP_IDS comments and REDERIVATION_PLAN.md record "
                f"{expected} -- reference/chapters.json and map_set.py have drifted; "
                "reconcile them before trusting this detector's output"
            )

    # An `in_progress` chapter's maps are in SLICE_MAP_IDS (it has to build
    # before it can pass its §9 gate -- the same rule `test_chapter_atlas`
    # pins), so they count toward reconciliation. They are NOT gated: no
    # ChapterSlice is produced for them, so the detector never scans a
    # chapter whose warps are still being authored. (CH05 went planned ->
    # in_progress -> built 2026-09-04..06; this module postdates that and
    # first met an in_progress chapter with CH06.)
    in_progress = _chapter_maps_in_build_order(chapters_json, status="in_progress")
    reconcile = set(cumulative)
    for chapter_id, own_maps in in_progress:
        overlap = reconcile & set(own_maps)
        if overlap:
            raise SliceGrowthError(
                f"in-progress {chapter_id} in {chapters_json} re-introduces map id(s) "
                f"{sorted(overlap)} already claimed by an earlier chapter"
            )
        reconcile |= set(own_maps)

    if reconcile != current_slice:
        only_in_chapters = sorted(reconcile - current_slice)
        only_in_slice_ids = sorted(current_slice - reconcile)
        raise SliceGrowthError(
            "the union of every built and in-progress chapter's maps in "
            f"{chapters_json} does not equal the current SLICE_MAP_IDS.\n"
            f"  in chapters.json but not SLICE_MAP_IDS: {only_in_chapters}\n"
            f"  in SLICE_MAP_IDS but not chapters.json: {only_in_slice_ids}"
        )

    return slices


def _transfer_page_indices(event: dict, target_map_id: int) -> tuple[int, ...]:
    """Every page index (0-based) in `event` carrying a code-201 transfer to
    `target_map_id`. Bookkeeping only -- the transfer semantics themselves
    (what a code-201 command's parameters mean) come from `_event_transfers`,
    which this function does not re-derive; it re-scans the same field
    (`TRANSFER_CODE`) purely to recover which page(s) each already-identified
    target came from, since `_event_transfers` deliberately flattens pages
    away (`CLAUDE.md` §4.3 -- the classification semantics have exactly one
    owner)."""
    indices = []
    for i, page in enumerate(event["pages"]):
        for cmd in page.get("list", []):
            if cmd["code"] == TRANSFER_CODE and cmd["parameters"][1] == target_map_id:
                indices.append(i)
                break
    return tuple(indices)


def find_slice_growth_events(
    chapter: ChapterSlice, maps_dir: Path, current_slice_ids: frozenset[int]
) -> list[SliceGrowthEvent]:
    """Every event on `chapter`'s own maps carrying a `code 201` transfer to a
    map that was outside `chapter.authoring_slice` and is inside
    `current_slice_ids` now.

    A missing `Map###.json` fails loud -- a chapter's own maps are expected to
    have decoded JSON on disk (they're staged and built), so an absence is a
    build/pipeline problem, not evidence of "nothing to report."
    """
    events: list[SliceGrowthEvent] = []
    for map_id in chapter.own_map_ids:
        path = maps_dir / f"Map{map_id:03d}.json"
        if not path.is_file():
            raise SliceGrowthError(
                f"{chapter.chapter_id} claims map {map_id} but {path} does not exist -- "
                "a gated chapter's own maps must have decoded JSON on disk"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        for event in data.get("events", []):
            transfers = _event_transfers(event)
            if not transfers:
                continue
            targets = {t[0] for t in transfers}
            newly_live = {
                t for t in targets
                if t not in chapter.authoring_slice and t in current_slice_ids
            }
            if not newly_live:
                continue
            authored_status, _ = classify_event(event, chapter.authoring_slice)
            for target in sorted(newly_live):
                events.append(
                    SliceGrowthEvent(
                        map_id=map_id,
                        event_id=event["id"],
                        event_name=event.get("name"),
                        page_indices=_transfer_page_indices(event, target),
                        target_map_id=target,
                        authored_status=authored_status,
                    )
                )
    return events


def detect_slice_growth(
    chapters_json: Path = DEFAULT_CHAPTERS_JSON,
    maps_dir: Path = Path("output/uranium-build/maps"),
    *,
    current_slice_ids: list[int] | None = None,
    only_chapters: set[str] | None = None,
) -> list[ChapterSliceGrowthReport]:
    """The full detector: for every gated chapter (or the subset named in
    `only_chapters`), report every newly-live out-of-slice-then/in-slice-now
    warp on that chapter's own maps.

    This is the whole point of the module -- see the module docstring and
    `REDERIVATION_PLAN.md` step P2 (filed as A5).
    """
    if current_slice_ids is None:
        from rpg2gba.tileset_converter.map_set import SLICE_MAP_IDS

        current_slice_ids = SLICE_MAP_IDS
    current_slice = frozenset(current_slice_ids)

    slices = gated_chapter_slices(chapters_json, current_slice_ids=current_slice_ids)
    if only_chapters is not None:
        slices = [s for s in slices if s.chapter_id in only_chapters]

    reports = []
    for chapter in slices:
        events = find_slice_growth_events(chapter, maps_dir, current_slice)
        reports.append(
            ChapterSliceGrowthReport(
                chapter_id=chapter.chapter_id,
                own_map_ids=chapter.own_map_ids,
                authored_slice_size=len(chapter.authoring_slice),
                current_slice_size=len(current_slice),
                events=events,
            )
        )
    return reports


__all__ = [
    "ChapterSlice",
    "ChapterSliceGrowthReport",
    "SliceGrowthError",
    "SliceGrowthEvent",
    "detect_slice_growth",
    "find_slice_growth_events",
    "gated_chapter_slices",
]


# --- CLI ---------------------------------------------------------------------
#
# The command itself is defined once, in `pipeline.py` as `rpg2gba slice-growth`
# (§4.3 -- one definition, not two), mirroring `slice_pins.py`. This module form
# just delegates, so both invocations are the same code path.

if __name__ == "__main__":  # pragma: no cover
    from rpg2gba.pipeline import slice_growth_cmd

    raise SystemExit(slice_growth_cmd(standalone_mode=True))
