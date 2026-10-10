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
    "transit": ("rpg2gba.playtest.archetypes.generic", "transit_beat", "beat_name"),
    "whiteout": ("rpg2gba.playtest.whiteout", "whiteout_fork_beat", "beat_name"),
    "escort": ("rpg2gba.playtest.archetypes.escort", "escort_beat", "beat_name"),
}

#: The generated-module marker, single source of truth (used by both the
#: docstring emitted below and `chapter_manifest.floor_model._module_is_
#: generated`, which used to hardcode a mismatched em-dash copy that could
#: never match this literal two-hyphen text -- see that module for the fix).
GENERATED_HEADER = "GENERATED -- do not edit"
HEADER_FIRST_LINE = f'"""{GENERATED_HEADER}.'


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
    if beat.template not in ARCHETYPE_TEMPLATES and beat.template != "transit":
        lines.append(f"    rows={render_value(beat.rows)},")
    for key, val in beat.kwargs:
        lines.append(f"    {key}={render_value(val)},")
    lines.append(")")
    return "\n".join(lines) + "\n"


def _never_fires_chunk(plan: ChapterPlan, *, status: str = "never_fires",
                       name: str = "NEVER_FIRES") -> str:
    """The module-level `NEVER_FIRES` dict (C9 ruling 3): every
    `plan.elsewhere` entry with `status == "never_fires"`, keyed by row id
    to its proof (`detail`). Always emitted, `{}` when empty, sorted by row
    id for determinism -- the C9 grader reads this because it can't re-run
    the generator to re-derive it. The same shape emits `EMPTY_PAGES`
    (`status="empty_page"`, 2026-09-29 operator ruling: a frozen row whose
    event is all empty pages is covered without a ROM walk)."""
    entries = sorted(
        ((e.row_id, e.detail) for e in plan.elsewhere if e.status == status),
        key=lambda kv: kv[0])
    if not entries:
        return f"{name}: dict[str, str] = {{}}"
    lines = [f"{name}: dict[str, str] = {{"]
    lines.extend(
        f"    {render_value(row_id)}: {render_value(detail)},"
        for row_id, detail in entries)
    lines.append("}")
    return "\n".join(lines)


#: `Elsewhere.status` values the `ELSEWHERE` dict records (PROJECT_TODO #124,
#: 2026-10-04 "emit + derive"). Excluded, each for a reason:
#: `never_fires`/`empty_page` -- already emitted, with the same proof, as
#: `NEVER_FIRES`/`EMPTY_PAGES` (the grader reads those; a second copy here
#: would be two sources of truth for one fact); `blocked`/`boundary` --
#: `chapter_manifest.derivation.derive_entry` already derives those from the
#: manifest (`row.requires`) and the boundary model, so recording them again
#: would let the two disagree silently.
#:
#: Except (2026-10-10): the boundary model derives only the CROSSING page,
#: which `split_outbound` keeps as an owned beat. The `boundary` entries are
#: the event's OTHER rows, which nothing else dispositions -- they belong to
#: the chapter that builds the far side, so they are written as `later`
#: (`_ELSEWHERE_AS`). First case: Nowtoch's station doors (map14000/ev052,
#: ev057), whose page 1 is the arrival nudge for coming back out of the
#: parked Metro.
ELSEWHERE_EMITTED: frozenset[str] = frozenset({
    "later", "unreachable", "unselected_arm", "stripped", "arm_gated",
    "converter_dropped"})
_ELSEWHERE_AS: dict[str, str] = {"boundary": "later"}


def _dict_chunk(name: str, entries: list[tuple[str, str]]) -> str:
    """`NAME: dict[str, str] = {...}` sorted by key, `{}` when empty."""
    if not entries:
        return f"{name}: dict[str, str] = {{}}"
    lines = [f"{name}: dict[str, str] = {{"]
    lines.extend(f"    {render_value(k)}: {render_value(v)}," for k, v in sorted(entries))
    lines.append("}")
    return "\n".join(lines)


def elsewhere_value(status: str, owner: str | None, detail: str) -> str:
    """`"<status>"` or `"<status>: <detail>"` -- `detail` if the entry has
    one, else the owning chapter (`later`), else the bare status."""
    extra = detail or owner
    return f"{status}: {extra}" if extra else status


def refused_value(blocker: str, reason: str, detail: str) -> str:
    """`"<blocker>: <reason>"`, then the detail -- folded in when it already
    starts with the reason id (story refusals: `unmodelled_outcome:...`),
    appended after ` -- ` otherwise."""
    if not detail or detail == reason:
        return f"{blocker}: {reason}"
    if detail.startswith(reason):
        return f"{blocker}: {detail}"
    return f"{blocker}: {reason} -- {detail}"


def _elsewhere_chunk(plan: ChapterPlan) -> str:
    """The module-level `ELSEWHERE` dict: row id -> `elsewhere_value(...)`
    for every `plan.elsewhere` entry whose status is in `ELSEWHERE_EMITTED`.
    Read by `chapter_manifest.generator_status`, never by the grader. A row
    listed twice with different values is a generator bug and fails loud."""
    out: dict[str, str] = {}
    for e in plan.elsewhere:
        status = _ELSEWHERE_AS.get(e.status, e.status)
        if status not in ELSEWHERE_EMITTED:
            continue
        value = elsewhere_value(status, e.owner, e.detail)
        if out.setdefault(e.row_id, value) != value:
            raise ValueError(
                f"{plan.chapter_id}: {e.row_id} is Elsewhere twice "
                f"({out[e.row_id]!r} vs {value!r})")
    return _dict_chunk("ELSEWHERE", list(out.items()))


def _refused_chunk(plan: ChapterPlan) -> str:
    """The module-level `REFUSED` dict: row id -> `refused_value(...)` for
    every `plan.refusals` entry. Same duplicate rule as `ELSEWHERE`."""
    out: dict[str, str] = {}
    for r in plan.refusals:
        value = refused_value(r.blocker, r.reason, r.detail)
        if out.setdefault(r.row_id, value) != value:
            raise ValueError(
                f"{plan.chapter_id}: {r.row_id} is refused twice "
                f"({out[r.row_id]!r} vs {value!r})")
    return _dict_chunk("REFUSED", list(out.items()))


def _walk_checked_chunk(plan: ChapterPlan) -> str:
    """The module-level `WALK_CHECKED` dict (ruling 19): arms a beat claims
    but doesn't declare, keyed by row id to the reason. Always emitted, `{}`
    when empty; the grader exempts these rows from rule (b)."""
    from rpg2gba.beat_gen.arms import walk_checked

    entries = sorted(walk_checked(plan.beats).items())
    if not entries:
        return "WALK_CHECKED: dict[str, str] = {}"
    lines = ["WALK_CHECKED: dict[str, str] = {"]
    lines.extend(f"    {render_value(r)}: {render_value(d)}," for r, d in entries)
    lines.append("}")
    return "\n".join(lines)


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
    builder_kwargs.append(f"suite={render_value('gen')}")
    builder_args = ", ".join([render_value(plan.chapter_id), *builder_kwargs])
    chunks.append(f"{chapter_var} = ChapterBuilder({builder_args})")

    for beat in plan.beats:
        chunks.append(render_call(chapter_var, plan.chapter_id, beat).rstrip("\n"))

    chunks.append(_never_fires_chunk(plan))
    chunks.append(_never_fires_chunk(plan, status="empty_page", name="EMPTY_PAGES"))
    chunks.append(_walk_checked_chunk(plan))
    chunks.append(_elsewhere_chunk(plan))
    chunks.append(_refused_chunk(plan))

    chunks.append(f"CHAPTER = {chapter_var}.build()")

    return "\n\n".join(chunks) + "\n"
