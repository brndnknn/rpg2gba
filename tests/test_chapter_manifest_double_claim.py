"""B1 (REDERIVATION_PLAN §16, C6): while hand and generated suites coexist,
two beats claim one row. The two checker models are scoped to ONE chapter
module each, so a hand and a generated module never meet in one index; inside
one module a double claim is tolerated unless the claims contradict."""
from __future__ import annotations

from types import ModuleType, SimpleNamespace

import pytest

from rpg2gba.chapter_manifest.beat_model import ChapterBeatModel
from rpg2gba.playtest.archetypes import ChapterArchetypeModel

ROW = "map001/ev001/p0"


def _beat(name: str, archetype: str | None) -> SimpleNamespace:
    return SimpleNamespace(name=name, rows=(ROW,), archetype_of=lambda _row: archetype)


def _chapter(*beats: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(name="CHX", beats=beats)


def test_beat_model_unions_two_claims_on_one_row():
    model = ChapterBeatModel(_chapter(_beat("B4", None), _beat("m001e001p0", None)),
                             ModuleType("chx"))
    assert model.claiming_beats(ROW) == ("B4", "m001e001p0")
    assert model.is_registered("B4") and model.is_registered("m001e001p0")


def test_archetype_model_tolerates_agreeing_double_claim():
    model = ChapterArchetypeModel(_chapter(_beat("B4", "trainer"), _beat("g", "trainer")))
    assert model.claimed_archetype(ROW) == "trainer"


def test_archetype_model_ignores_an_untyped_second_claim():
    model = ChapterArchetypeModel(_chapter(_beat("B4", "item_ball"), _beat("g", None)))
    assert model.claimed_archetype(ROW) == "item_ball"


def test_archetype_model_still_refuses_a_contradiction_inside_one_module():
    with pytest.raises(ValueError, match="claimed as both"):
        ChapterArchetypeModel(_chapter(_beat("B4", "trainer"), _beat("g", "item_ball")))


def test_models_are_built_per_module():
    # The per-module scoping IS the tolerance across suites: a hand module
    # and a generated one each get their own model, so a contradiction
    # between them can't abort either check.
    hand = ChapterArchetypeModel(_chapter(_beat("B4", "trainer")))
    generated = ChapterArchetypeModel(_chapter(_beat("m001e001_item_ball", "item_ball")))
    assert (hand.claimed_archetype(ROW), generated.claimed_archetype(ROW)) == (
        "trainer", "item_ball")
