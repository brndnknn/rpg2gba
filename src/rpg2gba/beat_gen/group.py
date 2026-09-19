"""Stage 2: owned rows -> planned beats (C6 Task 2).

Archetypes claim first (R11: "archetypes are layered on top"), then the
row-level shapes (obstacles, stairs, seams), then the generic template takes
every page row left. Branch-arm rows ride with the beat that owns their page.

STATUS: stub (`assignments/C6/02_group.md`).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from rpg2gba.beat_floor.assertion import RowFloor
from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.chapter_manifest.archetypes import ArchetypeMatch
from rpg2gba.chapter_manifest.schema import ManifestRow


def owning_page(row: ManifestRow) -> str:
    """The page row id a row belongs to: itself for a page row, the
    enclosing page for a branch arm at any nesting depth. Raises
    `ValueError` for seam/terrain rows, which have no page."""
    raise NotImplementedError


def beat_name(template: str, rows: Sequence[ManifestRow], *, key: str = "") -> str:
    """The deterministic beat name for a beat claiming `rows` (see the
    naming table in the task file). A function of the rows (and `key`, for
    obstacle capability), never of position or a counter."""
    raise NotImplementedError


def plan_beats(
    owned: Sequence[ManifestRow],
    matches: Sequence[ArchetypeMatch],
    floors: Mapping[str, RowFloor],
) -> tuple[PlannedBeat, ...]:
    """Every owned row claimed by exactly one planned beat.

    Returns beats ordered by their first row's manifest position (the
    route solver reorders them later, Task 4). Raises `ValueError` if any
    owned row would end up unclaimed or claimed twice."""
    raise NotImplementedError
