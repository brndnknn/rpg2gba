"""Tests for ``deterministic.classify_phone_rematch_trainer_battle`` — the
PokePod phone-rematch idiom (a sight trainer that offers phone registration
on defeat, then a phone rematch), added because Route 1's EV039 (FISHERMAN
"Brandon") and EV053 (YOUNGSTER "Richey") never battled: their 3 pages bailed
``classify_trainer_battle`` (2-page-only) and their non-canlose
``pbTrainerBattle`` call bailed ``_emit_canlose_trainer_battle_idiom``
(canlose-only) in the generic transpiler, so no ``trainerbattle_*`` call was
ever emitted for either event.

Fixtures below are a minimal, structurally-faithful transcription of
Map033 EV039 from ``output/uranium-build/maps/Map033.json`` (read directly
during development; not read at test time since ``output/`` is gitignored
and may be absent -- CLAUDE.md §4.4). Per CLAUDE.md §4.6:
  * round-trip / golden: the exact emitted Poryscript for the EV039 shape.
  * edge case: EV053's shape (different trainer/text) still resolves.
  * fail-loud: page count, ctx miss, double battle, canlose, missing
    pbNoticePlayer, wrong self-switch, wrong self-switch letter on the
    rematch/idle pages, and a missing code-115 Exit Event Processing all
    return ``None`` rather than a near-miss guess.
"""
from __future__ import annotations

import pytest

from rpg2gba.conversion_agent import deterministic as D
from rpg2gba.conversion_agent import poryscript


# ----------------------------------------------------------------------------
# fixture builders (mirrors tests/test_deterministic.py's event/page shape)
# ----------------------------------------------------------------------------


def _cmd(code: int, *params: object) -> dict:
    return {"code": code, "indent": 0, "parameters": list(params)}


def _text(s: str) -> dict:
    return _cmd(D.SHOW_TEXT, s)


def _event(*pages: dict, id: int = 1, name: str = "npc") -> dict:
    return {"id": id, "name": name, "x": 0, "y": 0, "pages": list(pages)}


def _battle_page(*, class_sym: str, name: str, battle_text: str, defeat_text: str,
                  reg_text: str, reg_maxbattles: int = 2) -> dict:
    """Page 0: the default/no-self-switch-condition sight-trainer page."""
    return {
        "trigger": 2,
        "condition": {"self_switch_valid": False},
        "list": [
            _cmd(D.COMMENT, f"Type: {class_sym}"),
            _cmd(D.COMMENT, f"Name: {name}"),
            _cmd(D.SCRIPT, f"pbTrainerIntro(:{class_sym})"),
            _cmd(D.SCRIPT, "Kernel.pbNoticePlayer(get_character(0))"),
            _cmd(D.SCRIPT, "pbCallBub(2)"),
            _text(battle_text),
            _cmd(
                D.CONDITIONAL_BRANCH, 12,
                f'pbTrainerBattle(PBTrainers::{class_sym},"{name}",'
                f'_I("{defeat_text}"),false,0,false,0)',
            ),
            _cmd(D.SCRIPT, f'pbPhoneRegisterBattle(_I("{reg_text}'),
            _cmd(
                D.SCRIPT_CONT,
                f'"),get_character(0),PBTrainers::{class_sym},"{name}",{reg_maxbattles})',
            ),
            _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
            _cmd(0),
            _cmd(D.BRANCH_END),
            _cmd(D.SCRIPT, "pbTrainerEnd"),
        ],
    }


def _rematch_page(*, class_sym: str, name: str, rematch_text: str, defeat_text: str) -> dict:
    """Page 1 (self-switch B set): the phone rematch — verified real shape."""
    return {
        "trigger": 0,
        "condition": {"self_switch_valid": True, "self_switch_ch": "B"},
        "list": [
            _cmd(D.CONDITIONAL_BRANCH, 12, f'pbPhoneBattleCount(PBTrainers::{class_sym},"{name}")>=1'),
            _cmd(D.SCRIPT, f"pbTrainerIntro(:{class_sym})"),
            _cmd(D.SCRIPT, "pbCallBub(2)"),
            _text(rematch_text),
            _cmd(D.SCRIPT, f'trainer = createPhoneTrainer(PBTrainers::{class_sym},"{name}",0)'),
            _cmd(D.SCRIPT_CONT, f'result = customTrainerBattle(trainer, "{defeat_text}")'),
            _cmd(D.SCRIPT_CONT, "pbSet(1, result == BR_WIN ? 0 : 1)"),
            _cmd(D.CONDITIONAL_BRANCH, 12, "$game_variables[1]==0"),
            _cmd(D.SCRIPT, f'pbPhoneIncrement(PBTrainers::{class_sym},"{name}",2)'),
            _cmd(D.CONTROL_SELF_SWITCH, "A", 0),
            _cmd(D.CONTROL_SELF_SWITCH, "B", 1),
            _cmd(D.SCRIPT, "pbTrainerEnd"),
            _cmd(0),
            _cmd(D.BRANCH_END),
            _cmd(D.EXIT_EVENT_PROCESSING),
            _cmd(D.BRANCH_END),
        ],
    }


def _idle_page(*, idle_text: str) -> dict:
    """Page 2 (self-switch A set, no B): idle re-offer -- content unchecked,
    never emitted (collapsed_pages), only its page condition matters."""
    return {
        "trigger": 0,
        "condition": {"self_switch_valid": True, "self_switch_ch": "A"},
        "list": [_text(idle_text)],
    }


_BRANDON = dict(
    class_sym="FISHERMAN", name="Brandon",
    battle_text="Water Pokémon are the best.",
    rematch_text="I will prove to you that Water is the best Pokémon Type!",
    defeat_text="Erh... Other types are good as well...",
    reg_text="I need some more water Pokémon...\nHook me up on PokePod if you want to battle again!",
    idle_text="This place is perfect for fishing!",
)

_RICHEY = dict(
    class_sym="YOUNGSTER", name="Richey",
    battle_text="Don't run away from me!",
    rematch_text="Ready for a rematch? My Pokémon are raring to go!",
    defeat_text="Oh, crackers! I lost!",
    reg_text="Hey, you're pretty good! Wanna trade PokePod numbers?\nI'll win against you next time!",
    idle_text="Well, someday I'll battle you again, and then we'll see who's laughing!",
)


def _make_event(spec: dict, *, id: int, name: str = "Trainer(5)") -> dict:
    page0 = _battle_page(
        class_sym=spec["class_sym"], name=spec["name"],
        battle_text=spec["battle_text"], defeat_text=spec["defeat_text"],
        reg_text=spec["reg_text"],
    )
    page1 = _rematch_page(
        class_sym=spec["class_sym"], name=spec["name"],
        rematch_text=spec["rematch_text"], defeat_text=spec["defeat_text"],
    )
    page2 = _idle_page(idle_text=spec["idle_text"])
    return _event(page0, page1, page2, id=id, name=name)


_BRANDON_CTX = D.Context(trainers={("TRAINER_CLASS_FISHERMAN", "Brandon", 0): "TRAINER_BRANDON_16"})
_RICHEY_CTX = D.Context(trainers={("TRAINER_CLASS_YOUNGSTER", "Richey", 0): "TRAINER_RICHEY_3"})


# ----------------------------------------------------------------------------
# round-trip / golden — Map033 EV039 (Brandon)
# ----------------------------------------------------------------------------


def test_ev039_brandon_matches_and_emits_both_blocks() -> None:
    ev = _make_event(_BRANDON, id=39)
    out = D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX)
    assert out is not None
    assert "script Map033_Trainer_5_Page1 {" in out
    assert "script Map033_Trainer_5_Page1_RegisterMatchCall {" in out
    assert "script Map033_Trainer_5_Page2 {" in out
    assert (
        "trainerbattle_single(TRAINER_BRANDON_16,"
        in out
    )
    assert "Map033_Trainer_5_Page1_RegisterMatchCall)" in out
    assert "special(PlayerFaceTrainerAfterBattle)" in out
    assert "waitmovement(0)" in out
    assert "register_matchcall(TRAINER_BRANDON_16)" in out
    assert "specialvar(VAR_RESULT, IsTrainerReadyForRematch)" in out
    assert "if (var(VAR_RESULT) == FALSE) {" in out
    assert "trainerbattle_rematch(TRAINER_BRANDON_16," in out
    assert out.index("trainerbattle_single(") < out.index("register_matchcall(")
    assert out.index("specialvar(") < out.index("trainerbattle_rematch(")

    # register_matchcall must NOT be a trailing top-level command directly
    # after trainerbattle_single's own block closes -- it must live inside
    # the separate continue-script block, reached only via the 4th arg.
    page1_block = out.split("script Map033_Trainer_5_Page1 {", 1)[1].split(
        "\n}\n", 1
    )[0]
    assert "register_matchcall" not in page1_block

    # the four-argument trainerbattle_single form is used: trainer, intro,
    # defeat text, and the continue-script label as the 4th argument.
    battle_line = next(ln for ln in out.splitlines() if "trainerbattle_single(" in ln)
    assert battle_line.rstrip().endswith("Map033_Trainer_5_Page1_RegisterMatchCall)")


def test_ev039_golden_output() -> None:
    ev = _make_event(_BRANDON, id=39)
    out = D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX)
    expected = (
        "script Map033_Trainer_5_Page1 {\n"
        '    trainerbattle_single(TRAINER_BRANDON_16, format("Water Pokémon are the best."), '
        'format("Erh... Other types are good as well..."), '
        "Map033_Trainer_5_Page1_RegisterMatchCall)\n"
        "    release\n"
        "    end\n"
        "}\n\n"
        "script Map033_Trainer_5_Page1_RegisterMatchCall {\n"
        "    special(PlayerFaceTrainerAfterBattle)\n"
        "    waitmovement(0)\n"
        "    register_matchcall(TRAINER_BRANDON_16)\n"
        "    release\n"
        "    end\n"
        "}\n\n"
        "script Map033_Trainer_5_Page2 {\n"
        "    specialvar(VAR_RESULT, IsTrainerReadyForRematch)\n"
        "    if (var(VAR_RESULT) == FALSE) {\n"
        "        release\n"
        "        end\n"
        "    }\n"
        '    trainerbattle_rematch(TRAINER_BRANDON_16, '
        'format("I will prove to you that Water is the best Pokémon Type!"), '
        'format("Erh... Other types are good as well..."))\n'
        "    release\n"
        "    end\n"
        "}"
    )
    assert out == expected


# ----------------------------------------------------------------------------
# edge case — Map033 EV053 (Richey), a different trainer/text combination
# ----------------------------------------------------------------------------


def test_ev053_richey_also_resolves() -> None:
    ev = _make_event(_RICHEY, id=53)
    out = D.classify_phone_rematch_trainer_battle(33, ev, _RICHEY_CTX)
    assert out is not None
    assert "trainerbattle_single(TRAINER_RICHEY_3," in out
    assert "register_matchcall(TRAINER_RICHEY_3)" in out
    assert "trainerbattle_rematch(TRAINER_RICHEY_3," in out


@pytest.mark.phase4
@pytest.mark.skipif(not poryscript.is_available(), reason="poryscript binary not installed")
def test_output_compiles() -> None:
    ev = _make_event(_BRANDON, id=39)
    out = D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX)
    assert out is not None
    result = poryscript.compile_script(out)
    assert result.ok, result.stderr


# ----------------------------------------------------------------------------
# fail-loud: structural deviations return None, never a near-miss guess
# ----------------------------------------------------------------------------


def test_two_pages_returns_none() -> None:
    """classify_trainer_battle's own turf — must not overlap."""
    ev = _make_event(_BRANDON, id=39)
    ev["pages"] = ev["pages"][:2]
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_unknown_trainer_returns_none() -> None:
    ev = _make_event(_BRANDON, id=39)
    assert D.classify_phone_rematch_trainer_battle(33, ev, D.Context()) is None


def test_no_context_returns_none() -> None:
    ev = _make_event(_BRANDON, id=39)
    assert D.classify_phone_rematch_trainer_battle(33, ev, None) is None


def _find_branch(page: dict) -> dict:
    for cmd in page["list"]:
        if cmd.get("code") == D.CONDITIONAL_BRANCH:
            return cmd
    raise AssertionError("no code-111 branch found")


def _first_param(cmd: dict) -> object:
    params = cmd.get("parameters") or [None]
    return params[0]


def test_double_battle_returns_none() -> None:
    ev = _make_event(_BRANDON, id=39)
    branch = _find_branch(ev["pages"][0])
    branch["parameters"][1] = branch["parameters"][1].replace(
        "pbTrainerBattle(", "pbDoubleTrainerBattle("
    )
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_canlose_true_returns_none() -> None:
    """canlose=true is _emit_canlose_trainer_battle_idiom's turf, not this one's."""
    ev = _make_event(_BRANDON, id=39)
    branch = _find_branch(ev["pages"][0])
    branch["parameters"][1] = branch["parameters"][1].replace(
        ",false,0,false,0)", ",false,0,true,0)"
    )
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_missing_notice_player_returns_none() -> None:
    ev = _make_event(_BRANDON, id=39)
    page0 = ev["pages"][0]
    page0["list"] = [
        c for c in page0["list"]
        if _first_param(c) != "Kernel.pbNoticePlayer(get_character(0))"
    ]
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_page0_self_switch_wrong_value_returns_none() -> None:
    """The then-branch self-switch write must be A ON (value 0), not a clear."""
    ev = _make_event(_BRANDON, id=39)
    for cmd in ev["pages"][0]["list"]:
        if cmd.get("code") == D.CONTROL_SELF_SWITCH:
            cmd["parameters"][1] = 1
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_rematch_page_wrong_self_switch_letter_returns_none() -> None:
    """Verified real-data deviation check: the rematch page's condition must be
    self-switch B (not A) -- the corpus data disagrees with an earlier prose
    description of this idiom that said the rematch page checked self-switch A.
    Coding to that wrong description would silently misclassify the idle page
    as the rematch page (or vice versa); this test pins the correct letter and
    proves a swap is caught, not guessed past."""
    ev = _make_event(_BRANDON, id=39)
    ev["pages"][1]["condition"]["self_switch_ch"] = "A"
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_idle_page_wrong_self_switch_letter_returns_none() -> None:
    ev = _make_event(_BRANDON, id=39)
    ev["pages"][2]["condition"]["self_switch_ch"] = "B"
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_missing_exit_event_processing_returns_none() -> None:
    """A real structural landmark of this idiom -- the unconditional code-115
    after the inner win-branch closes. Dropping it (e.g. a hand-edited or
    slightly different Uranium event) must not be silently accepted."""
    ev = _make_event(_BRANDON, id=39)
    page1 = ev["pages"][1]
    page1["list"] = [c for c in page1["list"] if c.get("code") != D.EXIT_EVENT_PROCESSING]
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_page0_default_condition_checks_self_switch_returns_none() -> None:
    """Page 0 must be the unconditional default page -- if it actually checks
    a self-switch, this isn't the verified idiom shape."""
    ev = _make_event(_BRANDON, id=39)
    ev["pages"][0]["condition"] = {"self_switch_valid": True, "self_switch_ch": "C"}
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_page0_wrong_trigger_returns_none() -> None:
    ev = _make_event(_BRANDON, id=39)
    ev["pages"][0]["trigger"] = 0
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_mismatched_trainer_class_between_calls_returns_none() -> None:
    """pbPhoneRegisterBattle naming a different class than pbTrainerIntro/
    pbTrainerBattle is a deviation, not something to guess past."""
    ev = _make_event(_BRANDON, id=39)
    page0 = ev["pages"][0]
    for cmd in page0["list"]:
        if cmd.get("code") == D.SCRIPT_CONT and "PBTrainers::FISHERMAN" in str(_first_param(cmd)):
            cmd["parameters"][0] = cmd["parameters"][0].replace(
                "PBTrainers::FISHERMAN", "PBTrainers::YOUNGSTER"
            )
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_trailing_junk_on_page0_returns_none() -> None:
    ev = _make_event(_BRANDON, id=39)
    ev["pages"][0]["list"].append(_cmd(D.SCRIPT, "pbSomethingUnexpected()"))
    assert D.classify_phone_rematch_trainer_battle(33, ev, _BRANDON_CTX) is None


def test_deepcopy_independence_sanity() -> None:
    """The shared spec dicts (_BRANDON/_RICHEY) must not be mutated by a
    fixture-mangling test above -- guards against cross-test pollution."""
    ev_a = _make_event(_BRANDON, id=39)
    ev_b = _make_event(_BRANDON, id=39)
    assert ev_a == ev_b
    out = D.classify_phone_rematch_trainer_battle(33, ev_b, _BRANDON_CTX)
    assert out is not None
