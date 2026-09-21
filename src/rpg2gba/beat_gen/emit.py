"""Stage 6: `ChapterPlan` -> Python source for the generated chapter module
(C6 Task 6; R7).

The output is one module, headed GENERATED, that registers every beat by
calling a template in solved order, and ends `CHAPTER = <builder>.build()`.
Byte-identical on re-run is a hard requirement (§4.2), so this module is a
pure function of the plan: no clock, no dict-iteration-order luck, no
`repr` of anything whose repr isn't stable.

String assembly with a fixed layout, never `ast.unparse`: its formatting
changes between Python versions, which would diff every generated module
on an interpreter upgrade (`assignments/C6/06_emit.md`).
"""
from __future__ import annotations

from typing import Any

from rpg2gba.beat_gen.plan import ARCHETYPE_TEMPLATES, ChapterPlan, PlannedBeat

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
    if value is None:
        return "None"
    if isinstance(value, bool):  # must precede the int check: bool is an int
        return repr(value)
    if isinstance(value, (int, str)):
        return repr(value)
    if isinstance(value, tuple):
        if not value:
            return "()"
        inner = ", ".join(render_value(item) for item in value)
        if len(value) == 1:
            return f"({inner},)"
        return f"({inner})"
    raise TypeError(
        f"render_value: cannot stably render a {type(value).__name__} "
        f"({value!r}); only None/bool/int/str and tuples of those are supported")


# kwargs the emitter itself supplies for every call; a PlannedBeat.kwargs
# entry using one of these names is a contract violation (plan.py says
# kwargs excludes the builder, chapter_id and the name keyword -- group and
# rows are emitter-owned too).
_RESERVED_KWARGS = {"chapter_id", "group", "rows"}


def render_call(chapter_var: str, chapter_id: str, beat: PlannedBeat) -> str:
    """One template call statement for one beat (see the task file for the
    exact layout). Always ends with a newline."""
    module, func, name_kw = TEMPLATE_CALLS[beat.template]
    reserved = _RESERVED_KWARGS | {name_kw}
    bad = sorted({k for k, _ in beat.kwargs} & reserved)
    if bad:
        raise ValueError(
            f"beat {beat.name!r}: kwargs.{bad[0]} collides with an "
            f"emitter-supplied keyword {bad}")

    lines = [
        f"{func}(",
        f"    {chapter_var},",
        f"    chapter_id={render_value(chapter_id)},",
        f"    {name_kw}={render_value(beat.name)},",
        f"    group={render_value(beat.group)},",
    ]
    if beat.template not in ARCHETYPE_TEMPLATES:
        lines.append(f"    rows={render_value(beat.rows)},")
    for key, val in beat.kwargs:
        lines.append(f"    {key}={render_value(val)},")
    lines.append(")")
    return "\n".join(lines) + "\n"


def _imports(plan: ChapterPlan) -> list[str]:
    """`from <module> import <names>` lines, one per module, both levels
    sorted, for the templates the plan actually uses. Always includes
    `ChapterBuilder`."""
    modules: dict[str, set[str]] = {}
    for beat in plan.beats:
        module, func, _ = TEMPLATE_CALLS[beat.template]
        modules.setdefault(module, set()).add(func)
    modules.setdefault("rpg2gba.playtest.chapter", set()).add("ChapterBuilder")
    lines = []
    for module in sorted(modules):
        names = ", ".join(sorted(modules[module]))
        lines.append(f"from {module} import {names}")
    return lines


def emit_module(plan: ChapterPlan) -> str:
    """The whole generated module as a string, ending in exactly one
    newline."""
    if not plan.beats:
        raise ValueError(f"{plan.chapter_id}: empty plan has no beats to emit")

    chapter_var = plan.chapter_id.lower()

    chunks: list[str] = []

    chunks.append(
        f"{HEADER_FIRST_LINE}\n"
        f"\n"
        f"Chapter {plan.chapter_id}. Regenerate with "
        f"`python -m rpg2gba.beat_gen generate --chapter {plan.chapter_id}`.\n"
        f'"""'
    )

    chunks.append("from __future__ import annotations")

    chunks.append("\n".join(_imports(plan)))

    doc = f"beat_gen-generated module for {plan.chapter_id}"
    builder_kwargs = [f"doc={render_value(doc)}"]
    if plan.predecessor is not None:
        builder_kwargs.append(f"predecessor={render_value(plan.predecessor)}")
    builder_args = ", ".join([render_value(plan.chapter_id), *builder_kwargs])
    chunks.append(f"{chapter_var} = ChapterBuilder({builder_args})")

    for beat in plan.beats:
        chunks.append(render_call(chapter_var, plan.chapter_id, beat).rstrip("\n"))

    chunks.append(f"CHAPTER = {chapter_var}.build()")

    return "\n\n".join(chunks) + "\n"
