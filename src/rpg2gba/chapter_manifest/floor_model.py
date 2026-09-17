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
from pathlib import Path
from types import ModuleType

from rpg2gba.beat_floor.assertion import FloorAssertion, RowFloor
from rpg2gba.beat_floor.lookup import floor_for_row
from rpg2gba.playtest.chapter import Beat, Chapter, load_chapter, load_chapter_module

logger = logging.getLogger(__name__)

_GENERATED_HEADER = "GENERATED — do not edit"


class ChapterFloorCoverageModel:
    """Satisfies the checker's `FloorCoverageModel` Protocol.

    Built lazily: `claims`/`declared` are computed once at construction from
    `chapter.beats` (cheap, already in memory); `floor` calls
    `beat_floor.lookup.floor_for_row` per row, which is itself cached per
    `(build_dir, map_id)` -- so nothing here re-derives a map's floor twice.
    """

    def __init__(self, chapter: Chapter, *, build_dir: Path, generated: bool) -> None:
        self._build_dir = build_dir
        self._generated = generated

        claiming: dict[str, list[Beat]] = {}
        for beat in chapter.beats:
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
        return frozenset(
            a for b in declaring for a in b.assertions if a.row_id == row_id)

    def claims(self, row_id: str) -> bool:
        return row_id in self._claiming

    def is_generated(self) -> bool:
        return self._generated


def _module_is_generated(module: ModuleType) -> bool:
    """True iff `module`'s docstring/header marks it a C6-generated module
    (see `checker.FloorCoverageModel.is_generated`'s docstring). None exist
    yet -- C6 is still TODO in `REDERIVATION_PLAN.md` -- so this is
    deliberately a plain string check, not a registry: there is nothing to
    register against yet, and every real chapter module today is hand-
    written and answers False.
    """
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
        chapter, build_dir=build_dir, generated=_module_is_generated(module))
