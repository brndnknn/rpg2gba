"""Tests for the Moki chapter scenario (`rpg2gba.playtest.chapters.moki`).

These run everywhere -- no ROM, no emulator, no engine build. They check
three things that don't need a live run:

1. `CHAPTER` loads via `load_chapter("moki")` and is well-formed.
2. The beat id / ordering matches `reference/chapters/01-moki.md`'s own
   tables (3.1 positive, 3.2 negative), parsed straight out of the doc's
   markdown so doc/scenario drift becomes a test failure.
3. No beat body reaches `emu.flag(...)` / `emu.var(...)` /
   `emu.resolve_constant(...)` with a numeric literal where a symbol name
   belongs (ROM_TEST_DEV E3c's late-binding rule).
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from rpg2gba.playtest.chapter import Chapter, load_chapter

REPO_ROOT = Path(__file__).resolve().parents[1]
CHAPTER_DOC = REPO_ROOT / "reference" / "chapters" / "01-moki.md"
CHAPTER_MODULE = (
    REPO_ROOT / "src" / "rpg2gba" / "playtest" / "chapters" / "moki.py"
)


def _parse_doc_beat_ids() -> list[str]:
    """Pull every `| B<n> | ...` / `| N<n> | ...` row's beat id out of the
    doc's two beat tables (3.1, 3.2), in file order, skipping header/
    separator rows."""
    text = CHAPTER_DOC.read_text(encoding="utf-8")
    ids: list[str] = []
    for line in text.splitlines():
        m = re.match(r"\|\s*([BN]\d+)\s*\|", line)
        if m:
            ids.append(m.group(1))
    return ids


# Doc rows the chapter deliberately does not implement. N1 (2026-07-27): the
# doc defines it as B2's companion over the same gate, and it was implemented
# as a second identical call to `_assert_house1f_exit_blocked` -- it could not
# fail unless B2 failed first. Kept as an explicit set rather than edited out
# of the doc parse, so "the chapter diverges from its doc here" stays a stated
# decision the reader can see, not a silent gap.
DROPPED_DOC_BEATS = {"N1"}


def _expected_interleaved_order() -> list[str]:
    """The doc's positive beats (B1..B15) and negative beats (N2, N3),
    interleaved per ROM_TEST_DEV Branch B2 / the task brief: N3 before B7's
    Yes answer; N2 after B8 (and, since N2 requires the player to already be
    back out in Map032, physically after B10) and before B12."""
    doc_ids = _parse_doc_beat_ids()
    positive = [b for b in doc_ids if b.startswith("B")]
    negative = [b for b in doc_ids if b.startswith("N")]
    assert set(positive) == {f"B{i}" for i in range(1, 16)}, positive
    assert set(negative) == {"N1", "N2", "N3"}, negative

    order: list[str] = []
    for beat in positive:
        if beat == "B7":
            order.append("N3")
        order.append(beat)
        if beat == "B10":
            order.append("N2")
    return [b for b in order if b not in DROPPED_DOC_BEATS]


def test_doc_beat_tables_parse_to_the_expected_shape() -> None:
    # Guards the test's own doc-parsing regex: if the doc's table format
    # ever changes shape, this fails loudly here rather than the harder-to-
    # read interleaving/order tests below silently passing on an empty list.
    doc_ids = _parse_doc_beat_ids()
    assert doc_ids, "no beat rows parsed out of the chapter doc's tables"
    assert doc_ids[:3] == ["B1", "B2", "B3"]
    assert doc_ids[-3:] == ["N1", "N2", "N3"]


def test_moki_chapter_loads() -> None:
    chapter = load_chapter("moki")
    assert isinstance(chapter, Chapter)
    assert chapter.name == "moki"
    assert chapter.doc == "reference/chapters/01-moki.md"
    # 15 positive + 3 negative doc rows, less the dropped ones.
    assert len(chapter.beats) == 18 - len(DROPPED_DOC_BEATS)


def test_moki_chapter_beat_order_matches_the_doc() -> None:
    chapter = load_chapter("moki")
    actual = [b.name for b in chapter.beats]
    assert actual == _expected_interleaved_order()


def test_moki_chapter_beat_ids_are_unique() -> None:
    chapter = load_chapter("moki")
    names = [b.name for b in chapter.beats]
    assert len(names) == len(set(names))


def test_moki_chapter_beats_have_nonempty_descriptions() -> None:
    chapter = load_chapter("moki")
    for beat in chapter.beats:
        assert beat.description.strip(), f"{beat.name} has an empty description"


def test_index_of_resolves_every_beat() -> None:
    chapter = load_chapter("moki")
    for i, beat in enumerate(chapter.beats):
        assert chapter.index_of(beat.name) == i


# -- late-binding: no hardcoded flag/var ids (ROM_TEST_DEV E3c) --------------

def _iter_late_bind_violations(tree: ast.AST) -> list[str]:
    """Walk the module AST for `emu.flag(...)`, `emu.var(...)`, and
    `emu.resolve_constant(...)` calls whose first argument is a numeric
    literal rather than a string symbol name. `emu` is a naming convention
    (every beat function's parameter is named `emu`, matching every other
    module in `playtest/`), not a type check -- adequate for a same-repo
    style guard."""
    violations: list[str] = []
    late_bind_methods = {"flag", "var", "resolve_constant"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in late_bind_methods):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "emu"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, (int, float)):
            violations.append(
                f"line {node.lineno}: emu.{func.attr}({first.value!r}, ...) "
                "-- use the symbol name, not a hardcoded id"
            )
    return violations


def test_no_hardcoded_flag_or_var_ids() -> None:
    source = CHAPTER_MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CHAPTER_MODULE))
    violations = _iter_late_bind_violations(tree)
    assert not violations, "\n".join(violations)


def test_no_hardcoded_flag_or_var_ids_via_runtime_source() -> None:
    # Belt-and-suspenders: re-derive the source from the live beat
    # functions' `inspect.getsource`, so a refactor that moves code into a
    # helper defined elsewhere in the same module is still covered (the
    # static-file check above already covers module-level helpers too, but
    # this pins the check to what actually executes as beat bodies).
    chapter = load_chapter("moki")
    for beat in chapter.beats:
        src = inspect.getsource(beat.run)
        tree = ast.parse(src)
        violations = _iter_late_bind_violations(tree)
        assert not violations, f"{beat.name}: " + "; ".join(violations)


@pytest.mark.parametrize(
    "map_const",
    [
        "MAP_MOKI_TOWN",
        "MAP_MOKI_TOWN_PLAYERS_HOUSE_1F",
        "MAP_MOKI_TOWN_PROFESSOR_LAB",
        "MAP_MOKI_TOWN_THEO_172",
    ],
)
def test_map_constants_used_are_symbol_names_not_literals(map_const: str) -> None:
    # The map-identity assertions late-bind through MAP_GROUP(...)/
    # MAP_NUM(...) macro expressions rather than emu.flag/var, so the AST
    # check above can't see them; this just confirms the chapter module's
    # source references the constant by name.
    source = CHAPTER_MODULE.read_text(encoding="utf-8")
    assert map_const in source
