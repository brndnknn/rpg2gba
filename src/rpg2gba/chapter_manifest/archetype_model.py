"""Concrete `checker.ArchetypeModel` over a chapter's playtest module.

`checker.py` deliberately never imports `playtest` -- a `Protocol` is the
seam. This module is the thin adapter the CLI wires into
`checker.check_chapter`'s `archetype_model=` argument so
`RULE_ARCHETYPE_CONFORMANCE`'s beat-claim half can actually run instead of
degrading to `RULE_ARCHETYPE_MODEL_UNENFORCED`. It is the sibling of
`route_model.py`, which solves the same layering problem the same way.

It joins the two halves the rule compares, which live in different places on
purpose:

- what a row **is** comes from `archetypes.classify_manifest`, a pure
  function of generated `ManifestRow` data -- nobody types it;
- what a row is **claimed as** comes from the chapter's own playtest module,
  where an author called an archetype template that registered beats
  carrying `archetype=` and `rows=`.

Without this adapter the rule can still catch a row nobody dispositioned,
but not a row dispositioned `beat:` whose beat was never actually written
against the archetype -- which is the half that closes the set.

**One model per chapter module (B1, C6).** While a hand module and a
generated module both claim a chapter's rows, each is checked through its own
model; they are never merged into one index. Inside one module two claims on
a row are fine when they agree and fail loud when they contradict
(`tests/test_chapter_manifest_double_claim.py`).
"""
from __future__ import annotations

import logging

from rpg2gba.playtest.archetypes import ChapterArchetypeModel
from rpg2gba.playtest.chapter import load_chapter

logger = logging.getLogger(__name__)


def build_archetype_model(chapter_id: str) -> ChapterArchetypeModel | None:
    """Adapter for `chapter_id`, or None when the rule cannot be enforced yet.

    Returns None -- leaving the beat-claim half to degrade to its
    `*_unenforced` warning -- only when the chapter has no playtest module.
    That is the ordinary state of a chapter whose beats have not been
    written yet (the manifest is generated and dispositioned *before* the
    beats, per `BUILD_PLAN.md`'s step order), not an error, and it is logged
    so the reason is visible in the check output.

    A module that exists but does not load is NOT that case: an
    `ImportError` from a real chapter file, or a `ValueError` from two beats
    claiming one row under different archetypes, is a genuine fault and
    raises through (CLAUDE.md §4.5).
    """
    try:
        chapter = load_chapter(chapter_id.lower())
    except KeyError:
        logger.info(
            "no playtest module for %s -- the archetype beat-claim half is "
            "unenforced; it starts checking once the chapter's beats exist",
            chapter_id,
        )
        return None
    return ChapterArchetypeModel(chapter)
