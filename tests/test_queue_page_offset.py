"""Regression test for issue #98: the transpiler's unhandled-queue writer and
its script-block labels use two DELIBERATELY DIFFERENT page numberings, and
this test pins both so they cannot be accidentally re-conflated.

1. Script block LABELS are 1-BASED — ``_page_label(...)`` produces
   ``Map{m:03d}_EV{e:03d}_Page{n}`` where the FIRST page is ``Page1``. These
   are real emitted symbols; renumbering them would rename every block in
   the corpus.
2. The QUEUE's ``page`` field is 0-BASED — the first page is ``page: 0``,
   matching the manifest ``row_id``'s ``p0`` component
   (``schema.page_row_id`` -> ``map{m:03d}/ev{e:03d}/p{n}``).

Before the #98 fix, the queue writer emitted 1-based page numbers too, so a
page's ``unhandled`` count in ``generator.py::_load_unhandled_counts``
(which keys a Counter by the queue's raw page, then looks it up with the
0-based ``page_idx``) silently came from its neighbour. The fix was made on
the writer side so no committed ``row_id`` had to move — i.e. the label
numbering stayed 1-based and only the queue's numbering changed.

Event/page shape mirrors ``tests/test_transpiler.py``: an event is
``{id, name, x, y, pages:[...]}`` and each page is ``{trigger, list, ...}``
with ``list`` a sequence of ``{code, indent, parameters}`` commands.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from rpg2gba.conversion_agent import transpiler as T
from rpg2gba.conversion_agent.flag_registry import FlagRegistry

_SWITCHES = {
    "1": "Got Starter",
}
_VARIABLES = {
    "1": "Result Var",
}
_PRESEED_MD = """\
# Pre-seed table

| kind | index | uranium label | constant | notes |
|------|-------|---------------|----------|-------|
| flag | 999 | Preseed Only | FLAG_PRESEED_ONLY | unrelated pre-seed row so pre_seed() has content |
"""


@pytest.fixture()
def registry(tmp_path: Path) -> FlagRegistry:
    switches_path = tmp_path / "uranium_switches.json"
    variables_path = tmp_path / "uranium_variables.json"
    preseed_path = tmp_path / "essentials_to_emerald_map.md"
    switches_path.write_text(json.dumps(_SWITCHES), encoding="utf-8")
    variables_path.write_text(json.dumps(_VARIABLES), encoding="utf-8")
    preseed_path.write_text(_PRESEED_MD, encoding="utf-8")
    reg = FlagRegistry()
    reg.pre_seed(preseed_path, switches_path, variables_path)
    return reg


@pytest.fixture()
def ctx(registry: FlagRegistry) -> T.TranspileContext:
    return T.TranspileContext(registry=registry)


def cmd(code: int, params: list | None = None, indent: int = 0) -> dict:
    return {"code": code, "indent": indent, "parameters": params if params is not None else []}


def make_event(pages_cmds: list[list[dict]], id: int = 5, name: str = "npc") -> dict:
    pages = [{"trigger": 0, "list": cmds} for cmds in pages_cmds]
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": pages}


# Code 125 (Change Gold) has no named constant/dispatch in transpiler.py —
# verified by grep (see test_manifest_transpiler_divergence.py's allowlist
# comment) — so it always falls through to the generic "outside the v1
# deterministic tier" queue path. A reliable, always-unhandled command.
_UNHANDLED_CODE = 125


def test_queue_page_is_zero_based_across_pages(ctx: T.TranspileContext) -> None:
    """A command on the event's first page queues with page == 0; the same
    shape command on the second page queues with page == 1."""
    ev = make_event(
        [
            [cmd(_UNHANDLED_CODE, [1, 0, 100])],
            [cmd(_UNHANDLED_CODE, [1, 0, 100])],
        ],
        id=5,
    )
    result = T.transpile_event(49, ev, ctx)

    assert len(result.unhandled) == 2
    first, second = result.unhandled
    assert first.command_code == _UNHANDLED_CODE
    assert first.page == 0
    assert second.command_code == _UNHANDLED_CODE
    assert second.page == 1


def test_page_labels_are_one_based_in_emitted_script(ctx: T.TranspileContext) -> None:
    """The emitted script block labels for the same two-page event use
    1-based page numbers: Page1 and Page2, never Page0."""
    ev = make_event(
        [
            [cmd(_UNHANDLED_CODE, [1, 0, 100])],
            [cmd(_UNHANDLED_CODE, [1, 0, 100])],
        ],
        id=5,
    )
    result = T.transpile_event(49, ev, ctx)

    assert "Map049_EV005_Page1" in result.text
    assert "Map049_EV005_Page2" in result.text
    assert "Map049_EV005_Page0" not in result.text


def test_common_event_queue_page_is_zero(ctx: T.TranspileContext) -> None:
    """Common events have no page structure of their own; their queue
    entries fix page at 0, matching the manifest row_id's p0 component."""
    ce = {
        "id": 7,
        "name": "CE",
        "list": [cmd(_UNHANDLED_CODE, [1, 0, 100])],
    }
    result = T.transpile_common_event(ce, ctx)

    assert len(result.unhandled) == 1
    assert result.unhandled[0].command_code == _UNHANDLED_CODE
    assert result.unhandled[0].page == 0
