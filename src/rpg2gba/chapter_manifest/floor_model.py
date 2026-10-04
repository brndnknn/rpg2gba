"""Concrete `checker.FloorCoverageModel` over a chapter's playtest module and
the generic beat floor (REDERIVATION_PLAN.md §16.3 C5, R11).

`checker.py` deliberately never imports `rpg2gba.playtest` -- a `Protocol` is
the seam. This module is the thin adapter the CLI wires into
`checker.check_chapter`'s `floor_coverage=` argument so
`RULE_FLOOR_UNCOVERED`/`RULE_FLOOR_UNDECLARED`/`RULE_FLOOR_MISSING` can
actually run instead of degrading to `RULE_FLOOR_MODEL_UNENFORCED`. It is the
sibling of `beat_model.py`/`archetype_model.py`, which solve the same
layering problem the same way.

It joins the two halves the rule compares, which live in different places on
purpose:

- what a row's floor demands comes from `beat_floor.lookup.floor_for_row`,
  the generic per-command extractor built from RMXP source (`beat_floor/`,
  C4);
- what a row's claiming beat(s) actually check comes from the chapter's own
  (already predecessor-composed) `playtest.chapter.load_chapter(...).beats`
  -- `Beat.rows` for the claim, `Beat.assertions` for the declaration.

Predecessor beats count as claims here exactly like `beat_model.py`'s
`ChapterBeatModel` and `playtest.archetypes.ChapterArchetypeModel` treat
them: both walk `chapter.beats` (already fully composed -- `Chapter`'s own
docstring: "beats is already fully composed: if this chapter has a
predecessor, ... you never need to know a predecessor was involved") with no
predecessor filter at all. A predecessor's inherited beat still claims and
declares its own rows under this chapter's own `check_chapter` call, and
that is deliberate: the same beat body runs when this chapter replays it, so
whatever it declares is still true here.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor
from rpg2gba.beat_floor.coverage import inherited_page_trigger, is_boundary_claim
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.beat_gen.emit import GENERATED_HEADER as _GENERATED_HEADER
from rpg2gba.playtest.chapter import Beat, Chapter, load_chapter, load_chapter_module

logger = logging.getLogger(__name__)


class ChapterFloorCoverageModel:
    """Satisfies the checker's `FloorCoverageModel` Protocol.

    Built lazily: `claims`/`declared` are computed once at construction from
    `chapter.beats` (cheap, already in memory); `floor` calls
    `beat_floor.lookup.floor_for_row` per row, which is itself cached per
    `(build_dir, map_id)` -- so nothing here re-derives a map's floor twice.
    """

    def __init__(
        self, chapter: Chapter, *, build_dir: Path, generated: bool,
        walk_checked: Mapping[str, str] = {},
    ) -> None:
        self._build_dir = build_dir
        self._generated = generated
        self._walk_checked = walk_checked

        # Own beats only (`:` marks an inherited `<OWNER>:` beat), as the C9
        # grader does -- an inherited beat's rows are graded in its owner.
        claiming: dict[str, list[Beat]] = {}
        for beat in chapter.beats:
            if ":" in beat.name:
                continue
            for row_id in beat.rows:
                claiming.setdefault(row_id, []).append(beat)
        self._claiming = claiming

    def floor(self, row_id: str) -> RowFloor:
        return floor_for_row(row_id, build_dir=self._build_dir)

    def declared(self, row_id: str) -> frozenset[FloorAssertion] | None:
        beats = self._claiming.get(row_id, ())
        declaring = [b for b in beats if b.assertions is not None]
        if not declaring:
            return None
        page_beats = self._claiming.get(row_id.rpartition("/")[0], ())
        return frozenset(
            a for b in declaring for a in b.assertions if a.row_id == row_id
        ) | inherited_page_trigger(row_id, page_beats)

    def claims(self, row_id: str) -> bool:
        return row_id in self._claiming

    def is_generated(self) -> bool:
        return self._generated

    def exempt(self, row_id: str) -> bool:
        """Rows the grader never holds to the floor here: a random arm the
        module lists in `WALK_CHECKED` (ruling 19), or a row claimed only by
        a boundary warp, whose crossing is the successor's (ruling 9)."""
        if row_id in self._walk_checked:
            return True
        beats = self._claiming.get(row_id, ())
        return bool(beats) and is_boundary_claim(row_id, beats)


def _module_is_generated(module: ModuleType) -> bool:
    """True iff `module`'s docstring/header marks it a C6/C9-generated
    module (see `checker.FloorCoverageModel.is_generated`'s docstring). This
    is deliberately a plain string check against `beat_gen.emit.
    GENERATED_HEADER` (the emitter's own single source of truth for the
    marker), not a registry -- a generated module's docstring always starts
    with it (`emit.HEADER_FIRST_LINE`), and every hand-written chapter
    module answers False."""
    doc = getattr(module, "__doc__", None) or ""
    return doc.strip().startswith(_GENERATED_HEADER)


def build_floor_coverage_model(
    chapter_id: str, *, build_dir: Path,
) -> ChapterFloorCoverageModel | None:
    """Adapter for `chapter_id`, or None when the rule cannot be enforced yet.

    Returns None -- leaving the ⊇-floor rule to degrade to its
    `RULE_FLOOR_MODEL_UNENFORCED` warning -- only when the chapter has no
    playtest module. That is the ordinary state of a chapter whose beats
    have not been written yet (the manifest is generated and dispositioned
    *before* the beats, per `BUILD_PLAN.md`'s step order), not an error, and
    it is logged so the reason is visible in the check output. Same
    reasoning and the same exception shape as `build_beat_model`/
    `build_archetype_model`.

    A module that exists but does not load is NOT that case: an
    `ImportError` from a real chapter file is a genuine fault and raises
    through (CLAUDE.md §4.5).
    """
    try:
        chapter = load_chapter(chapter_id.lower())
    except KeyError:
        logger.info(
            "no playtest module for %s -- the floor-coverage rule is "
            "unenforced; it starts checking once the chapter's beats exist",
            chapter_id,
        )
        return None
    module = load_chapter_module(chapter_id)
    return ChapterFloorCoverageModel(
        chapter, build_dir=build_dir, generated=_module_is_generated(module),
        walk_checked=getattr(module, "WALK_CHECKED", {}))
