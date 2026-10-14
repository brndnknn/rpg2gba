"""Concrete `checker.BeatModel` over a chapter's playtest module.

`checker.py` deliberately never imports `rpg2gba.playtest` -- a `Protocol` is
the seam. This module is the thin adapter the CLI wires into
`checker.check_chapter`'s beat-model argument so the D2 rule ("every
`beat:Bn` disposition must name a beat that is actually registered") can
actually run instead of degrading to unenforced. It is the sibling of
`archetype_model.py` and `route_model.py`, which solve the same layering
problem the same way.

It joins the two halves the rule compares, which live in different places on
purpose:

- what a manifest row is **claimed as done by** comes from
  `reference/manifests/CHnn.dispositions.json`, hand-authored, e.g.
  `"disposition": "beat:B8"`;
- what beats actually got written and wired up comes from the chapter's own
  playtest module -- both the beats it registered via `@beat(...)` (visible
  through the built `Chapter`) and the beats it deliberately did NOT
  register, named in the module-level `DEFERRED_BEATS` tuple together with a
  reason.

A disposition naming a beat that is neither registered nor deferred is a
typo or a beat nobody wrote. A disposition naming a beat that is deferred is
a silent contradiction -- the manifest claims the row is covered while the
chapter module says, in writing, that it isn't yet. Both are what this
adapter exists to let the rule see.
"""
from __future__ import annotations

import logging
from types import ModuleType

from rpg2gba.playtest.chapter import Chapter, load_chapter, load_chapter_module

logger = logging.getLogger(__name__)


def _matches(beat_id: str, candidate: str) -> bool:
    """Does a registered/deferred beat named `candidate` satisfy `beat_id`?

    A disposition names a beat id like `B4`, but the D4 archetype templates
    (`src/rpg2gba/playtest/archetypes/`) register *families* of prefixed
    beats via `trainer_beats(..., beat_prefix="B4")` -- `B4_battle`,
    `B4_retalk`, and so on -- not a beat literally named `B4`. So `B4` is
    satisfied either by a beat named exactly `B4` or by any beat named
    `B4_<something>`. The match is on the literal `_` separator, not a bare
    prefix (`str.startswith`), specifically so `B4` can never be satisfied by
    a registered `B14` -- `"B14".startswith("B4")` is False already, but
    `"B4_x".startswith("B4")` and `"B40_x".startswith("B4")` would both be
    True under a naive prefix check, and only the first is a real match.
    """
    return candidate == beat_id or candidate.startswith(beat_id + "_")


class ChapterBeatModel:
    """Satisfies the checker's `BeatModel` Protocol.

    Built from a fully-composed `Chapter` (registered beats) and its source
    module (`DEFERRED_BEATS`). Both lookups are built once, at construction,
    rather than rescanned per call.
    """

    def __init__(self, chapter: Chapter, module: ModuleType) -> None:
        self._registered: tuple[str, ...] = tuple(
            beat.name for beat in chapter.beats)
        # Only the chapter's OWN beats claim rows. A replayed predecessor beat
        # is named `CHnn:<beat>` and can claim a row on this chapter's maps
        # once a chapter revisits a map (CH07: CH05's `m035e001` cave warp on
        # Route 2); that claim is the predecessor's verdict, not this one's.
        claims: dict[str, set[str]] = {}
        for beat in chapter.beats:
            if ":" in beat.name:
                continue
            for row_id in beat.rows:
                claims.setdefault(row_id, set()).add(beat.name)
        self._claims = {row_id: tuple(sorted(names)) for row_id, names in claims.items()}

        deferred: dict[str, str] = {}
        for entry in getattr(module, "DEFERRED_BEATS", ()):
            if (not isinstance(entry, (tuple, list)) or len(entry) != 3
                    or not isinstance(entry[0], str)
                    or not isinstance(entry[1], str)):
                raise TypeError(
                    f"{module.__name__}.DEFERRED_BEATS: entry {entry!r} is "
                    "not a 3-tuple (beat_id: str, reason: str, fn) -- "
                    "malformed DEFERRED_BEATS entries are not silently "
                    "skipped (CLAUDE.md §4.5)")
            beat_id, reason, _fn = entry
            deferred[beat_id] = reason
        self._deferred = deferred

    def is_registered(self, beat_id: str) -> bool:
        return any(_matches(beat_id, name) for name in self._registered)

    def deferral_reason(self, beat_id: str) -> str | None:
        for deferred_id, reason in self._deferred.items():
            if _matches(beat_id, deferred_id):
                return reason
        return None

    def claiming_beats(self, row_id: str) -> tuple[str, ...]:
        return self._claims.get(row_id, ())


def build_beat_model(chapter_id: str) -> ChapterBeatModel | None:
    """Adapter for `chapter_id`, or None when the rule cannot be enforced yet.

    Returns None -- leaving the D2 rule to degrade to its unenforced
    warning -- only when the chapter has no playtest module at all. That is
    the ordinary state of a chapter whose manifest is generated and
    dispositioned *before* its beats are written, not an error, and it is
    logged so the reason is visible in the check output.

    A module that exists but does not load is NOT that case: an
    `ImportError` from a real chapter file, a `TypeError` from a module
    missing its `CHAPTER`, or a `TypeError` from a malformed
    `DEFERRED_BEATS` entry, is a genuine fault and raises through
    (CLAUDE.md §4.5).
    """
    try:
        module = load_chapter_module(chapter_id)
    except KeyError:
        logger.info(
            "no playtest module for %s -- the beat-registration half of D2 "
            "is unenforced; it starts checking once the chapter's beats "
            "exist",
            chapter_id,
        )
        return None
    chapter = load_chapter(chapter_id)
    return ChapterBeatModel(chapter, module)
