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


def _register_call_cmds(
    *, class_sym: str, name: str, reg_text: str, reg_maxbattles: int, split: bool
) -> list[dict]:
    """The ``pbPhoneRegisterBattle(...)`` call, in either of its two verified
    on-disk forms: a single code-355 command (Map035 Larrie/Brent -- the
    ``_I("...")`` literal fits on one RGSS line), or split across a
    code-355 + code-655 continuation (Map033 Brandon/Richey -- the literal
    spans the line boundary). Both must classify identically once joined."""
    call = f'pbPhoneRegisterBattle(_I("{reg_text}"),get_character(0),PBTrainers::{class_sym},"{name}",{reg_maxbattles})'
    if not split:
        return [_cmd(D.SCRIPT, call)]
    # Split the literal itself across the 355/655 boundary, mirroring the
    # real Map033 corpus data (the split happens mid-string, not at a call
    # boundary).
    mid = len(reg_text) // 2
    head, tail = reg_text[:mid], reg_text[mid:]
    return [
        _cmd(D.SCRIPT, f'pbPhoneRegisterBattle(_I("{head}'),
        _cmd(
            D.SCRIPT_CONT,
            f'{tail}"),get_character(0),PBTrainers::{class_sym},"{name}",{reg_maxbattles})',
        ),
    ]


def _battle_page(*, class_sym: str, name: str, battle_text: str, defeat_text: str,
                  reg_text: str, reg_maxbattles: int = 2, split_register: bool = True) -> dict:
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
            *_register_call_cmds(
                class_sym=class_sym, name=name, reg_text=reg_text,
                reg_maxbattles=reg_maxbattles, split=split_register,
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


def _idle_page(*, class_sym: str, name: str, idle_text: str, reg_text: str,
                reg_maxbattles: int = 2, split_register: bool = True) -> dict:
    """Page 2 (self-switch A set, no B): idle re-offer -- verified real shape
    (Map033 EV039/EV053, Map035 events 3/23): a code-111 gate on
    ``pbPhoneBattleCount(...)>=1`` around [optional pbCallBub, the idle
    Show-Text, ``pbPhoneRegisterBattle(...)``, EXIT_EVENT_PROCESSING], a
    BRANCH_END with no else, then the exact same three commands again
    unconditionally (the corpus's own -- structurally unreachable in
    practice, since self-switch A implies the count check -- fallback)."""

    def _branch_body() -> list[dict]:
        return [
            _cmd(D.SCRIPT, "pbCallBub(2)"),
            _text(idle_text),
            *_register_call_cmds(
                class_sym=class_sym, name=name, reg_text=reg_text,
                reg_maxbattles=reg_maxbattles, split=split_register,
            ),
        ]

    return {
        "trigger": 0,
        "condition": {"self_switch_valid": True, "self_switch_ch": "A"},
        "list": [
            _cmd(D.CONDITIONAL_BRANCH, 12, f'pbPhoneBattleCount(PBTrainers::{class_sym},"{name}")>=1'),
            *_branch_body(),
            _cmd(D.EXIT_EVENT_PROCESSING),
            _cmd(0),
            _cmd(D.BRANCH_END),
            *_branch_body(),
        ],
    }


_BRANDON = dict(
    class_sym="FISHERMAN", name="Brandon",
    battle_text="Water Pokémon are the best.",
    rematch_text="I will prove to you that Water is the best Pokémon Type!",
    defeat_text="Erh... Other types are good as well...",
    reg_text="I need some more water Pokémon...\nHook me up on PokePod if you want to battle again!",
    idle_text="This place is perfect for fishing!",
    split_register=True,  # verified real shape: Map033 splits 355+655
)

_RICHEY = dict(
    class_sym="YOUNGSTER", name="Richey",
    battle_text="Don't run away from me!",
    rematch_text="Ready for a rematch? My Pokémon are raring to go!",
    defeat_text="Oh, crackers! I lost!",
    reg_text="Hey, you're pretty good! Wanna trade PokePod numbers?\nI'll win against you next time!",
    idle_text="Well, someday I'll battle you again, and then we'll see who's laughing!",
    split_register=True,
)

# Map035 CH04 -- HIKER Larrie (event 3) and BIRDKEEPER Brent (event 23):
# a single code-355 ``pbPhoneRegisterBattle(...)`` command (the ``_I("...")``
# literal fits on one RGSS line), not the split 355+655 form Map033 uses.
# This is the exact shape that used to bail the classifier entirely.
_LARRIE = dict(
    class_sym="HIKER", name="Larrie",
    battle_text="Hey, kid! Are you tough enough to make it through this cave?",
    rematch_text="So you have returned for a rematch? Let me show you my moves!",
    defeat_text="Looks like you're tough all right.",
    reg_text="Hmm, you're pretty good it seems. Trade PokePod numbers with me, "
              "and I'll call you whenever I find a rare Pokémon.",
    idle_text="Watch your step! In caves, Pokémon can jump out from anywhere!",
    split_register=False,  # verified real shape: Map035 is a single 355
)

_BRENT = dict(
    class_sym="BIRDKEEPER", name="Brent",
    battle_text="Fly to the sky, my beautiful Bird Pokémon!",
    rematch_text="Behold! My birds are bolder than before!",
    defeat_text="You clipped our wings...",
    reg_text="I can tell you have a soaring spirit. Want to trade PokéPod numbers?",
    idle_text="Is Owten a bird? I can't tell...",
    split_register=False,
)


def _make_event(spec: dict, *, id: int, name: str = "Trainer(5)") -> dict:
    page0 = _battle_page(
        class_sym=spec["class_sym"], name=spec["name"],
        battle_text=spec["battle_text"], defeat_text=spec["defeat_text"],
        reg_text=spec["reg_text"], split_register=spec["split_register"],
    )
    page1 = _rematch_page(
        class_sym=spec["class_sym"], name=spec["name"],
        rematch_text=spec["rematch_text"], defeat_text=spec["defeat_text"],
    )
    page2 = _idle_page(
        class_sym=spec["class_sym"], name=spec["name"],
        idle_text=spec["idle_text"], reg_text=spec["reg_text"],
        split_register=spec["split_register"],
    )
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
    assert "setflag(FLAG_MAP033_EVENT039_SSA)" in out
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
    # #141: the registration question, asked as a yes/no (its literal's line break is a space).
    question = 'format("I need some more water Pokémon... Hook me up on PokePod if you want to battle again!")'
    expected = (
        "script Map033_Trainer_5_Page1 {\n"
        '    trainerbattle_single(TRAINER_BRANDON_16, format("Water Pokémon are the best."), '
        'format("Erh... Other types are good as well..."), '
        "Map033_Trainer_5_Page1_RegisterMatchCall)\n"
        "    goto(Map033_Trainer_5_Page2)\n"
        "}\n\n"
        "script Map033_Trainer_5_Page1_RegisterMatchCall {\n"
        "    special(PlayerFaceTrainerAfterBattle)\n"
        "    waitmovement(0)\n"
        "    if (flag(FLAG_SYS_POKENAV_GET)) {\n"
        f"        msgbox({question}, MSGBOX_YESNO)\n"
        "        if (var(VAR_RESULT) == YES) {\n"
        "            register_matchcall(TRAINER_BRANDON_16)\n"
        "        }\n"
        "    }\n"
        "    setflag(FLAG_MAP033_EVENT039_SSA)\n"
        "    release\n"
        "    end\n"
        "}\n\n"
        "script Map033_Trainer_5_Page2 {\n"
        "    setvar(VAR_0x8004, TRAINER_BRANDON_16)\n"
        "    specialvar(VAR_RESULT, IsTrainerRegistered)\n"
        "    if (var(VAR_RESULT) == FALSE) {\n"
        '        msgbox(format("This place is perfect for fishing!"))\n'
        "        if (flag(FLAG_SYS_POKENAV_GET)) {\n"
        f"            msgbox({question}, MSGBOX_YESNO)\n"
        "            if (var(VAR_RESULT) == YES) {\n"
        "                register_matchcall(TRAINER_BRANDON_16)\n"
        "            }\n"
        "        }\n"
        "        release\n"
        "        end\n"
        "    }\n"
        "    specialvar(VAR_RESULT, IsTrainerReadyForRematch)\n"
        "    if (var(VAR_RESULT) == FALSE) {\n"
        '        msgbox(format("This place is perfect for fishing!"))\n'
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
# re-talk routing — Map035 EV003 (Larrie): the fix for the silent-NPC bug
# (B11), WITHOUT a dispatcher (a dispatcher would break sight-trainer
# detection -- GetTrainerFlagFromScriptPointer reads the object_event's raw
# script bytes as a trainerbattle opcode; see the comment on `battle_block`
# in deterministic.py).
# ----------------------------------------------------------------------------


def test_larrie_page1_falls_through_to_page2_after_trainerbattle() -> None:
    """The re-talk route to Page2 must be Page1's FALL-THROUGH -- the command
    immediately after `trainerbattle_single` -- not the four-argument
    continue-script.

    On a re-talk the engine's own scaffolding
    (`EventScript_TryDoNormalTrainerBattle`, engine/data/scripts/
    trainer_battle.inc:9-21) locks, faceplayers, sees the trainer flag set and
    runs `gotopostbattlescript`, which resolves to `sTrainerBattleEndScript` --
    set by `TrainerBattleLoadArgs` (engine/src/battle_setup.c:1058) to the byte
    after the packed trainerbattle command, i.e. Page1's next line. The
    four-argument script is a different pointer (`battleScriptRetAddrA`),
    reached only by `gotobeatenscript` once, on the return from a won battle.

    Putting the branch in the four-argument script (065e9c04) therefore left
    Page2 unreachable in every state, and Larrie and Richey turned to face the
    player and said nothing, permanently. Keep the goto here."""
    ev = _make_event(_LARRIE, id=3)
    out = D.classify_phone_rematch_trainer_battle(35, ev, D.Context(
        trainers={("TRAINER_CLASS_HIKER", "Larrie", 0): "TRAINER_LARRIE_4"}
    ))
    assert out is not None
    assert "script Map035_Trainer_5_Page1 {" in out
    assert "trainerbattle_single(TRAINER_LARRIE_4," in out
    # the goto is the very next line after trainerbattle_single, and Page1
    # has no silent release/end exit for a re-talk to land on.
    page1 = out.split("}\n\n", 1)[0]
    assert page1.rstrip().endswith("    goto(Map035_Trainer_5_Page2)")
    assert "release" not in page1
    # the one-shot post-victory script registers unconditionally: it can only
    # ever run with the self-switch clear, so a flag check there is dead code.
    assert (
        "script Map035_Trainer_5_Page1_RegisterMatchCall {\n"
        "    special(PlayerFaceTrainerAfterBattle)"
    ) in out
    # the self-switch still advances -- metadata_wiring reads it for page
    # conditions.
    assert "setflag(FLAG_MAP035_EVENT003_SSA)" in out
    # no dispatcher block, and Page1's own script pointer is untouched --
    # the object_event must keep pointing straight at trainerbattle_single.
    assert "Dispatch" not in out


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
