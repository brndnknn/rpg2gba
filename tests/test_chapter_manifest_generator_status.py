"""Tests for `chapter_manifest.generator_status` -- reading the beat
generator's per-row status record back out of a generated module
(PROJECT_TODO #124, 2026-10-04)."""
from __future__ import annotations

import logging
from types import ModuleType
from typing import get_args, get_type_hints

import pytest

from rpg2gba.beat_gen import emit
from rpg2gba.beat_gen.plan import BLOCKERS, ChapterPlan, Elsewhere, PlannedBeat, Refusal
from rpg2gba.chapter_manifest.generator_status import (
    UNREACHABLE_DEFAULT_REASON,
    status_from_module,
)
from rpg2gba.chapter_manifest.schema import ELSEWHERE_STATUSES, REFUSAL_BLOCKERS, Disposition


def _module(**attrs: object) -> ModuleType:
    mod = ModuleType("fake_chapter")
    for name, value in attrs.items():
        setattr(mod, name, value)
    return mod


def test_maps_each_dict_to_its_head():
    status = status_from_module(_module(
        ELSEWHERE={"a/p0": "later: CH07", "b/p0": "unreachable", "c/p0": "unreachable: cut",
                   "d/p0": "stripped: strip_list.json map_events (Luz)"},
        REFUSED={"e/p0": "story-state: unmodelled_outcome:x"},
        NEVER_FIRES={"f/p0": "no warp lands"},
        EMPTY_PAGES={"g/p0": "every page empty"},
    ))
    assert dict(status.specs) == {
        "a/p0": "elsewhere:later: CH07",
        "b/p0": f"unreachable:{UNREACHABLE_DEFAULT_REASON}",
        "c/p0": "unreachable:cut",
        "d/p0": "elsewhere:stripped: strip_list.json map_events (Luz)",
        "e/p0": "refused:story-state: unmodelled_outcome:x",
        "f/p0": "elsewhere:never_fires: no warp lands",
        "g/p0": "elsewhere:empty_page: every page empty",
    }
    for row_id, spec in status.specs.items():
        Disposition.parse(row_id, spec)
    assert status.spec_for("zzz") is None


def test_module_predating_the_record_reads_as_empty_and_logs_info(caplog):
    with caplog.at_level(logging.INFO, logger="rpg2gba.chapter_manifest.generator_status"):
        status = status_from_module(_module(NEVER_FIRES={"f/p0": "proof"}, EMPTY_PAGES={}))
    assert dict(status.specs) == {"f/p0": "elsewhere:never_fires: proof"}
    assert any("ELSEWHERE/REFUSED" in r.getMessage() for r in caplog.records)


def test_bare_module_is_empty():
    assert dict(status_from_module(_module()).specs) == {}


def test_row_in_two_dicts_fails_loud():
    with pytest.raises(ValueError, match="exactly one bucket"):
        status_from_module(_module(ELSEWHERE={"a/p0": "later"}, REFUSED={"a/p0": "C8: x"}))


def test_malformed_record_fails_loud():
    with pytest.raises(TypeError, match="dict\\[str, str\\]"):
        status_from_module(_module(ELSEWHERE={"a/p0": 3}))
    with pytest.raises(Exception, match="must start with one of"):
        status_from_module(_module(ELSEWHERE={"a/p0": "blocked: rock_smash"}))
    with pytest.raises(Exception, match="must start with one of"):
        status_from_module(_module(REFUSED={"a/p0": "nonsense: x"}))


def test_grammar_sets_agree_with_the_generator():
    statuses = set(get_args(get_type_hints(Elsewhere)["status"]))
    assert ELSEWHERE_STATUSES == statuses - {"unreachable", "blocked", "boundary"}
    assert REFUSAL_BLOCKERS == BLOCKERS
    # everything emit writes into ELSEWHERE, plus the two NEVER_FIRES/EMPTY_PAGES
    # carry, is spelled either elsewhere: or unreachable:
    assert emit.ELSEWHERE_EMITTED | {"never_fires", "empty_page"} == (
        ELSEWHERE_STATUSES | {"unreachable"})


def test_emitted_module_round_trips_through_the_reader():
    beat = PlannedBeat(name="m001stair1x1", template="stair", map_id=1,
                       rows=("map001/terrain/stairs/1,1",), group="g")
    plan = ChapterPlan(
        chapter_id="CH09", predecessor=None, beats=(beat,),
        refusals=(Refusal("map001/ev002/p0", "story-state", "unmodelled_outcome",
                          "unmodelled_outcome:badge"),),
        elsewhere=(Elsewhere("map001/ev003/p0", "later", "CH10"),
                   Elsewhere("map001/ev004/p0", "unreachable"),
                   Elsewhere("map001/ev005/p0", "never_fires", detail="no warp"),
                   Elsewhere("map001/ev006/p0", "blocked", requires=("surf",))))
    src = emit.emit_module(plan)
    namespace: dict[str, object] = {}
    # only the dict assignments: executing the whole module would build a chapter
    for chunk in src.split("\n\n"):
        if chunk.split(":", 1)[0] in ("ELSEWHERE", "REFUSED", "NEVER_FIRES", "EMPTY_PAGES"):
            exec(chunk, namespace)  # noqa: S102
    status = status_from_module(_module(**{k: v for k, v in namespace.items()
                                           if not k.startswith("__")}))
    assert dict(status.specs) == {
        "map001/ev002/p0": "refused:story-state: unmodelled_outcome:badge",
        "map001/ev003/p0": "elsewhere:later: CH10",
        "map001/ev004/p0": f"unreachable:{UNREACHABLE_DEFAULT_REASON}",
        "map001/ev005/p0": "elsewhere:never_fires: no warp",
    }
