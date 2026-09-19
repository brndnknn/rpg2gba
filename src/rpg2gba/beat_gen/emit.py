"""Stage 6: `ChapterPlan` -> Python source for the generated chapter module
(C6 Task 6; R7).

The output is one module, headed GENERATED, that registers every beat by
calling a template in solved order, and ends `CHAPTER = <builder>.build()`.
Byte-identical on re-run is a hard requirement (§4.2), so this module is a
pure function of the plan: no clock, no dict-iteration-order luck, no
`repr` of anything whose repr isn't stable.

STATUS: stub (`assignments/C6/06_emit.md`).
"""
from __future__ import annotations

from typing import Any

from rpg2gba.beat_gen.plan import ChapterPlan, PlannedBeat

# template -> (module to import from, function, the keyword its name goes in)
TEMPLATE_CALLS: dict[str, tuple[str, str, str]] = {
    "warp": ("rpg2gba.playtest.archetypes.warp", "warp_beat", "beat_name"),
    "arrival_nudge": ("rpg2gba.playtest.archetypes.arrival_nudge",
                      "arrival_nudge_beat", "beat_name"),
    "item_ball": ("rpg2gba.playtest.archetypes.item_ball", "item_ball_beats", "beat_prefix"),
    "trainer": ("rpg2gba.playtest.archetypes.trainer", "trainer_beats", "beat_prefix"),
    "flavour_npc": ("rpg2gba.playtest.archetypes.flavour_npc",
                    "flavour_npc_beat", "beat_name"),
    "generic": ("rpg2gba.playtest.archetypes.generic", "generic_beat", "beat_name"),
    "obstacle": ("rpg2gba.playtest.archetypes.generic", "obstacle_beat", "beat_name"),
    "stair": ("rpg2gba.playtest.archetypes.generic", "stair_beat", "beat_name"),
    "seam": ("rpg2gba.playtest.archetypes.generic", "seam_beat", "beat_name"),
}

HEADER_FIRST_LINE = '"""GENERATED -- do not edit.'


def render_value(value: Any) -> str:
    """Python source for one kwarg value. Supports None, bool, int, str and
    (nested) tuples of those. Raises `TypeError` naming the type for
    anything else (a float, set, dict or object has no guaranteed stable
    rendering here)."""
    raise NotImplementedError


def render_call(chapter_var: str, chapter_id: str, beat: PlannedBeat) -> str:
    """One template call statement for one beat (see the task file for the
    exact layout). Always ends with a newline."""
    raise NotImplementedError


def emit_module(plan: ChapterPlan) -> str:
    """The whole generated module as a string, ending in exactly one
    newline."""
    raise NotImplementedError
