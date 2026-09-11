"""Per-chapter event manifest: the approval artifact for playtest authoring.

A chapter's beat list used to be prose, reconciled against the map data by hand.
Every failure class in `PLAYTEST_AUTHORING_IMPROVEMENT.md` was an omission that
no artifact made visible, so the manifest replaces the prose table with two
files joined by a stable row id:

* **generated, never hand-edited** — one row per event page on the chapter's
  maps, plus one per overland seam touching them, derived from
  ``output/uranium-build/`` (see `generator`).
* **authored, committed, hand-edited** — a disposition per row
  (``beat:Bn`` / ``blocked:<capability set>`` / ``cosmetic`` / ``unreachable:<reason>``),
  which the generator joins at build time and never writes to (see `schema`).
  `blocked:` answers exactly one question -- what unblocks this row -- and
  takes one or more minimal capability sets ("+" joins tokens required
  together, "|" separates alternative sets, either of which suffices; e.g.
  `blocked:rock_smash|strength+surf`), or a `blocked:tooling:<primitive>`
  form for a row gated on missing tooling, not an in-game capability; a separate
  `assertable`/`negative_beat` pair on the `Disposition` records whether a
  negative beat can be written today. `unreachable` is narrowed to content no
  chapter will ever reach.

The generator is emphatically driven from the **RMXP** side, never the compiled
Poryscript: an event the transpiler silently dropped would otherwise be absent
from both the manifest and the ROM, which is exactly the shape of CH03's three
dead ``giveitem`` grants.
"""
from __future__ import annotations

from rpg2gba.chapter_manifest.schema import (
    COSMETIC_SAFE_TAGS,
    EFFECT_TAGS,
    STATE_WRITING_TAGS,
    Disposition,
    DispositionError,
    ManifestRow,
    PageCondition,
    SeamRef,
    Verdict,
    content_hash,
    page_row_id,
    row_from_dict,
    row_to_dict,
    seam_row_id,
)

__all__ = [
    "COSMETIC_SAFE_TAGS",
    "EFFECT_TAGS",
    "STATE_WRITING_TAGS",
    "Disposition",
    "DispositionError",
    "ManifestRow",
    "PageCondition",
    "SeamRef",
    "Verdict",
    "content_hash",
    "page_row_id",
    "row_from_dict",
    "row_to_dict",
    "seam_row_id",
]
