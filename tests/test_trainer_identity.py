"""Tests for the shared trainer-identity extraction added to `deterministic.py`
for the debug map-viewer ("which named trainer is this NPC map event?").

Covers:
  - `_parse_trainer_battle_call` / `extract_trainer_reference` on synthetic
    events (unit-level, no repo data required).
  - `extract_trainer_reference` on a REAL sight-battle event pulled straight
    from `output/uranium-build/maps/Map033.json` (event id 9, FISHERMAN
    "Marko"), resolved against the real `trainers.json` via `load_context`,
    proving the public API works unmodified against real deserializer
    output — not just hand-built fixtures.
  - A non-trainer event from the same map returning `None`.
  - `classify_trainer_battle` / `classify_phone_rematch_trainer_battle` keep
    emitting identical Poryscript after the refactor to call the shared
    extractor (guards against behavioural drift during the refactor).
"""
from __future__ import annotations

import json
from pathlib import Path

from rpg2gba.conversion_agent import deterministic as D

# ----------------------------------------------------------------------------
# event/page builders (mirrors tests/test_deterministic.py's convention)
# ----------------------------------------------------------------------------


def _cmd(code: int, *params: object) -> dict:
    return {"code": code, "indent": 0, "parameters": list(params)}


def _page(*cmds: dict, trigger: int = 0) -> dict:
    return {"trigger": trigger, "list": list(cmds)}


def _event(*pages: dict, id: int = 1, name: str = "npc") -> dict:
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": list(pages)}


def _text(s: str) -> dict:
    return _cmd(D.SHOW_TEXT, s)


# ----------------------------------------------------------------------------
# synthetic-fixture tests
# ----------------------------------------------------------------------------

_FISHERMAN_BATTLE_ARG = (
    'pbTrainerBattle(PBTrainers::FISHERMAN,"Matt",'
    '_I("T-the ones you have are nice too..."),false,0,false,0)'
)

_FISHERMAN_PAGE1 = _page(
    _cmd(D.SCRIPT, "pbTrainerIntro(:FISHERMAN)"),
    _cmd(D.SCRIPT, "pbCallBub(2)"),
    _text("The ocean holds different species!"),
    _cmd(D.CONDITIONAL_BRANCH, 12, _FISHERMAN_BATTLE_ARG),
    _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
    _cmd(D.SCRIPT, "pbTrainerEnd"),
)
_FISHERMAN_PAGE2 = _page(_text("Y'know, the Gym Leader is tough."))
_FISHERMAN_CTX = D.Context(trainers={("TRAINER_CLASS_FISHERMAN", "Matt", 0): "TRAINER_BRANDON_16"})


def test_extract_trainer_reference_sight_resolved() -> None:
    ev = _event(_FISHERMAN_PAGE1, _FISHERMAN_PAGE2, id=5, name="Fisherman_Matt")
    ref = D.extract_trainer_reference(ev, _FISHERMAN_CTX)
    assert ref == D.TrainerReference(
        trainer_constant="TRAINER_BRANDON_16",
        trainer_class_constant="TRAINER_CLASS_FISHERMAN",
        display_name="Matt",
        party_id=0,
        kind="sight",
    )


def test_extract_trainer_reference_unresolved_lookup_returns_none_constant() -> None:
    """Unlike the classifiers, a ctx.trainers miss doesn't fail the whole
    call — trainer_constant is simply None, everything else still populated.
    """
    ev = _event(_FISHERMAN_PAGE1, _FISHERMAN_PAGE2, id=5, name="Fisherman_Matt")
    ref = D.extract_trainer_reference(ev, D.Context())
    assert ref is not None
    assert ref.trainer_constant is None
    assert ref.trainer_class_constant == "TRAINER_CLASS_FISHERMAN"
    assert ref.display_name == "Matt"
    assert ref.party_id == 0
    assert ref.kind == "sight"


def test_extract_trainer_reference_non_trainer_event_returns_none() -> None:
    ev = _event(_page(_text("Just some flavor dialogue.")), id=1, name="npc")
    assert D.extract_trainer_reference(ev, D.Context()) is None


def test_extract_trainer_reference_malformed_event_returns_none() -> None:
    """Safe to call on garbage/unrelated event dicts — never raises."""
    assert D.extract_trainer_reference({}, D.Context()) is None
    assert D.extract_trainer_reference({"pages": None}, D.Context()) is None
    assert D.extract_trainer_reference({"pages": []}, D.Context()) is None
    assert D.extract_trainer_reference({"pages": [{"list": "not-a-list"}]}, D.Context()) is None
    assert D.extract_trainer_reference({"pages": [{"list": [{"code": 111}]}]}, D.Context()) is None


def test_extract_trainer_reference_double_battle_not_claimed() -> None:
    page1 = _page(
        _cmd(D.SCRIPT, "pbTrainerIntro(:FISHERMAN)"),
        _text("Two vs two!"),
        _cmd(
            D.CONDITIONAL_BRANCH,
            12,
            'pbDoubleTrainerBattle(PBTrainers::FISHERMAN,"Matt",_I("Ugh!"),false,0)',
        ),
        _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
        _cmd(D.SCRIPT, "pbTrainerEnd"),
    )
    page2 = _page(_text("Good match."))
    ev = _event(page1, page2, id=5, name="Fisherman_Matt")
    assert D.extract_trainer_reference(ev, _FISHERMAN_CTX) is None


# ----------------------------------------------------------------------------
# real repo data — output/uranium-build/maps/Map033.json
# ----------------------------------------------------------------------------

_BUILD = Path("output/uranium-build")
_MAP033 = _BUILD / "maps" / "Map033.json"


def _load_map033_events() -> list[dict]:
    data = json.loads(_MAP033.read_text(encoding="utf-8"))
    return data["events"]


def _load_real_ctx() -> "D.Context":
    return D.load_context(reference_dir=Path("reference"), intermediate_dir=_BUILD / "intermediate")


def test_extract_trainer_reference_real_sight_event_map033() -> None:
    """Event id 9 ("Trainer(3)") is a real 2-page sight battle — FISHERMAN
    "Marko" — verified directly against Map033.json and trainers.json."""
    events = {e["id"]: e for e in _load_map033_events()}
    ev9 = events[9]
    ctx = _load_real_ctx()

    ref = D.extract_trainer_reference(ev9, ctx)
    assert ref is not None
    assert ref.kind == "sight"
    assert ref.trainer_class_constant == "TRAINER_CLASS_FISHERMAN"
    assert ref.display_name == "Marko"
    assert ref.party_id == 0
    assert ref.trainer_constant == "TRAINER_MARKO_19"

    # Must agree with the strict classifier's own resolution.
    out = D.classify_trainer_battle(33, ev9, ctx)
    assert out is not None
    assert f"trainerbattle_single({ref.trainer_constant}," in out


def test_extract_trainer_reference_real_non_trainer_event_map033() -> None:
    """Event id 2 in Map033 is not a trainer battle at all."""
    events = {e["id"]: e for e in _load_map033_events()}
    ev2 = events[2]
    ctx = _load_real_ctx()
    assert D.extract_trainer_reference(ev2, ctx) is None


# ----------------------------------------------------------------------------
# refactor-safety: classifiers must emit byte-identical output after now
# routing through the shared extractor.
# ----------------------------------------------------------------------------


def test_classify_trainer_battle_output_unchanged_by_refactor() -> None:
    ev = _event(_FISHERMAN_PAGE1, _FISHERMAN_PAGE2, id=5, name="Fisherman_Matt")
    out = D.classify_trainer_battle(8, ev, _FISHERMAN_CTX)
    assert out == (
        "script Map008_Fisherman_Matt_Page1 {\n"
        '    trainerbattle_single(TRAINER_BRANDON_16, format("The ocean holds different species!"), '
        'format("T-the ones you have are nice too..."))\n'
        '    msgbox(format("Y\'know, the Gym Leader is tough."))\n'
        "    release\n"
        "    end\n"
        "}"
    )
