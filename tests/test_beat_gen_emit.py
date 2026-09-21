"""Tests for `rpg2gba.beat_gen.emit` (C6 Task 6).

All synthetic: a `ChapterPlan` is plain data, so the emitter is testable
without any map data. Importing the emitted module for real is Task 9's
job (it needs Task 7's templates).

STATUS: implemented, skipped. DELETE the `pytestmark` line to start Task 6.
"""
from __future__ import annotations

import ast

import pytest

from rpg2gba.beat_gen import emit
from rpg2gba.beat_gen.plan import ChapterPlan, PlannedBeat, make_kwargs

TRAINER = PlannedBeat(name="m036e004_trainer", template="trainer", map_id=36,
                      rows=("map036/ev004/p0", "map036/ev004/p1"), group="m036e004_trainer",
                      kwargs=make_kwargs(map_id=36, event_id=4, rider=False))
ARMS = PlannedBeat(name="m036e004_trainer_arms", template="generic", map_id=36,
                   rows=("map036/ev004/p0/b0", "map036/ev004/p0/b1"),
                   group="m036e004_trainer", kwargs=make_kwargs(skip_claimed=True))
STAIR = PlannedBeat(name="m037stair11x9", template="stair", map_id=37,
                    rows=("map037/terrain/stairs/11,9",), group="m037stair11x9")


def _plan(*beats, predecessor="CH04"):
    return ChapterPlan(chapter_id="CH05", predecessor=predecessor, beats=beats)


# --- render_value ---------------------------------------------------------------

@pytest.mark.parametrize("value, text", [
    (None, "None"), (True, "True"), (False, "False"), (0, "0"), (-3, "-3"),
    ("a", "'a'"), ("it's", repr("it's")),
    ((), "()"), (("a",), "('a',)"), ((1, 2), "(1, 2)"), ((("x", 1),), "(('x', 1),)"),
])
def test_render_value(value, text):
    assert emit.render_value(value) == text


@pytest.mark.parametrize("value", [1.5, {1}, {"a": 1}, [1], object()])
def test_render_value_rejects_unstable_types(value):
    with pytest.raises(TypeError, match=type(value).__name__):
        emit.render_value(value)


def test_render_value_roundtrips_through_literal_eval():
    value = (("a", 1), None, True, ("nested", ("deep",)))
    assert ast.literal_eval(emit.render_value(value)) == value


# --- render_call ----------------------------------------------------------------

def test_render_call_exact_layout():
    assert emit.render_call("ch05", "CH05", TRAINER) == (
        "trainer_beats(\n"
        "    ch05,\n"
        "    chapter_id='CH05',\n"
        "    beat_prefix='m036e004_trainer',\n"
        "    group='m036e004_trainer',\n"
        "    event_id=4,\n"
        "    map_id=36,\n"
        "    rider=False,\n"
        ")\n"
    )


def test_non_archetype_templates_get_rows():
    text = emit.render_call("ch05", "CH05", ARMS)
    assert "    rows=('map036/ev004/p0/b0', 'map036/ev004/p0/b1'),\n" in text
    assert text.index("group=") < text.index("rows=") < text.index("skip_claimed=")


def test_archetype_templates_do_not_get_rows():
    assert "rows=" not in emit.render_call("ch05", "CH05", TRAINER)


def test_reserved_kwarg_fails_loud():
    bad = PlannedBeat(name="x", template="generic", map_id=1, rows=("map001/ev001/p0",),
                      group="x", kwargs=make_kwargs(group="sneaky"))
    with pytest.raises(ValueError, match="group"):
        emit.render_call("ch05", "CH05", bad)


# --- emit_module ----------------------------------------------------------------

def test_module_header_and_tail():
    src = emit.emit_module(_plan(TRAINER, ARMS))
    assert src.startswith(emit.HEADER_FIRST_LINE)
    assert src.endswith("\nCHAPTER = ch05.build()\n")
    assert not src.endswith("\n\n")


def test_module_compiles():
    compile(emit.emit_module(_plan(TRAINER, ARMS, STAIR)), "ch05.generated.py", "exec")


def _imports(src: str) -> list[tuple[str, list[str]]]:
    tree = ast.parse(src)
    return [(n.module, [a.name for a in n.names]) for n in tree.body
            if isinstance(n, ast.ImportFrom) and n.module != "__future__"]


def test_imports_only_what_is_used_grouped_and_sorted():
    src = emit.emit_module(_plan(STAIR, TRAINER, ARMS))
    assert _imports(src) == [
        ("rpg2gba.playtest.archetypes.generic", ["generic_beat", "stair_beat"]),
        ("rpg2gba.playtest.archetypes.trainer", ["trainer_beats"]),
        ("rpg2gba.playtest.chapter", ["ChapterBuilder"]),
    ]


def _calls(src: str) -> list[ast.Call]:
    return [n.value for n in ast.parse(src).body
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]


def test_calls_in_plan_order():
    src = emit.emit_module(_plan(STAIR, TRAINER, ARMS))
    assert [c.func.id for c in _calls(src)] == ["stair_beat", "trainer_beats", "generic_beat"]


def test_builder_line():
    tree = ast.parse(emit.emit_module(_plan(TRAINER)))
    (assign,) = [n for n in tree.body if isinstance(n, ast.Assign)
                 and isinstance(n.value, ast.Call)
                 and getattr(n.value.func, "id", "") == "ChapterBuilder"]
    assert assign.targets[0].id == "ch05"
    assert [ast.literal_eval(a) for a in assign.value.args] == ["CH05"]
    kw = {k.arg: ast.literal_eval(k.value) for k in assign.value.keywords}
    assert kw["predecessor"] == "CH04"
    assert "doc" in kw


def test_no_predecessor_is_omitted_not_none():
    src = emit.emit_module(_plan(TRAINER, predecessor=None))
    assert "predecessor" not in src


def test_byte_identical_on_rerun():
    plan = _plan(TRAINER, ARMS, STAIR)
    assert emit.emit_module(plan) == emit.emit_module(plan)


def test_empty_plan_fails_loud():
    with pytest.raises(ValueError, match="CH05"):
        emit.emit_module(_plan())
