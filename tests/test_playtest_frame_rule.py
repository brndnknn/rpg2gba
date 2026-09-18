"""Tests for the pure frame-rule classifier (Q7, DECIDED 2026-08-27).

No emulator import, no I/O -- these exercise `classify_claim` and
`check_frame_rule` against realistic message text only. The positive
(non-negative) messages below are drawn verbatim or near-verbatim from real
`ScenarioError(...)` call sites in `src/rpg2gba/playtest/` (assertions.py,
emulator.py, battle.py, chapters/ch03.py) so the false-positive check is
against the harness's actual prose, not a strawman.
"""

import json

import pytest

from rpg2gba.playtest.frame_rule import (
    NEGATIVE_CLAIM_PATTERNS,
    ClaimVerdict,
    FrameRuleError,
    FrameRuleResult,
    check_frame_rule,
    classify_claim,
    refusal_error,
)

# ---------------------------------------------------------------------------
# Negative-claim messages, one realistic example per pattern class.
# ---------------------------------------------------------------------------

NEGATIVE_EXAMPLES = [
    ("nothing-happened", "B4: nothing runs after the fence-row cameo trigger (shot.png)"),
    ("nothing-happened", "B9: nothing happened when the switch was flipped (shot.png)"),
    ("nothing-happened", "N2: nothing fired on re-entry (shot.png)"),
    ("script-did-not-start", "interaction did not start a script (shot.png)"),
    ("script-did-not-start", "B11: the mart counter did not open a script (shot.png)"),
    ("script-did-not-start", "B3: no script started after the tap (shot.png)"),
    ("not-rendered", "B6: the boulder is not rendered on this frame (shot.png)"),
    ("not-rendered", "B6: the sign was not drawn after the warp (shot.png)"),
    ("did-not-fire", "Map031_EV014_Page1_Joke did not fire, see module docstring (shot.png)"),
    ("did-not-fire", "B4: crossing the fence-row tile did not fire Theo's cameo (shot.png)"),
    ("did-not-appear", "B8: the trainer sprite never appeared after the walk-in (shot.png)"),
    ("did-not-appear", "B2: no object at the expected local id (shot.png)"),
    ("no-text", "B5: no text appeared in the box (shot.png)"),
    ("no-text", "B5: no dialogue after the sign interaction (shot.png)"),
    ("did-not-move", "B20: boulder (local id 4) at (12,9) did not move (shot.png)"),
    ("did-not-move", "staircase never moved the player (shot.png)"),
    ("not-present", "B7: the delivery NPC was not present at spawn (shot.png)"),
    ("not-present", "roster entry is absent from both PBS sources (shot.png)"),
]


@pytest.mark.parametrize("label, message", NEGATIVE_EXAMPLES)
def test_negative_examples_match_expected_class(label: str, message: str) -> None:
    verdict = classify_claim(message)
    assert verdict.negative, f"expected {message!r} to be classified negative"
    assert verdict.label == label
    assert verdict.matched


def test_every_pattern_class_has_at_least_one_example() -> None:
    covered = {label for label, _ in NEGATIVE_EXAMPLES}
    declared = {p.label for p in NEGATIVE_CLAIM_PATTERNS}
    assert covered == declared


# ---------------------------------------------------------------------------
# Positive (non-negative) real failure messages -- must NOT match.
# ---------------------------------------------------------------------------

POSITIVE_EXAMPLES = [
    # wrong map (assertions.py require_map)
    "B3: expected map MAP_ROUTE1 but map_location() reads group=1 num=4 (shot.png)",
    # wrong coordinate (assertions.py assert_near)
    "B6: landed at (14,22), expected near (12,20) (tolerance 1) (shot.png)",
    # wrong species / unexpected empty slot (battle.py)
    "gEnemyParty slot 0 is SPECIES_NONE within the expected roster (shot.png)",
    # walk budget exhausted (emulator.py _walk_to_once)
    "walk_to(14,22) frame budget exhausted (shot.png)",
    # flag/count mismatch, an "expected X got Y" shape (chapters/ch03.py)
    "B14: expected +1 of each free sample, got potion, antidote (shot.png)",
    # stuck walk that isn't a "nothing happened" claim -- a positive report
    # of what did happen (a wall bump), not that nothing did
    "stuck after 6 step-aside attempts at 14,22 heading for 16,22",
    # wrong facing (assertions.py assert_player_facing)
    "B9: player facing DIR_SOUTH, expected DIR_NORTH (derived live from "
    "this build's own staged warp direction) (shot.png)",
    # wrong BGM (assertions.py assert_bgm)
    "B12: gMPlayInfo_BGM is playing song id 87, expected 42 "
    "(engine/data/maps/Route1/map.json's own \"music\" key) (shot.png)",
]


@pytest.mark.parametrize("message", POSITIVE_EXAMPLES)
def test_positive_examples_do_not_match(message: str) -> None:
    verdict = classify_claim(message)
    assert not verdict.negative, f"expected {message!r} to NOT be classified negative"
    assert verdict.label == ""
    assert verdict.matched == ""


# ---------------------------------------------------------------------------
# classify_claim edge cases
# ---------------------------------------------------------------------------

def test_classify_claim_none_is_not_negative() -> None:
    verdict = classify_claim(None)
    assert verdict == ClaimVerdict(negative=False, label="", matched="")


def test_classify_claim_empty_string_is_not_negative() -> None:
    verdict = classify_claim("")
    assert not verdict.negative


def test_classify_claim_blank_string_is_not_negative() -> None:
    verdict = classify_claim("   \n  ")
    assert not verdict.negative


def test_bare_word_without_the_full_phrase_does_not_match() -> None:
    # The patterns are multi-word phrases ("nothing runs", not bare
    # "nothing") specifically so an unrelated sentence that happens to
    # contain one of the words doesn't misfire.
    verdict = classify_claim("B1: nothing to report here, values matched (shot.png)")
    assert not verdict.negative


def test_word_boundary_avoids_substring_false_positive() -> None:
    # A phrase word must not match as a substring of a longer word abutting
    # it -- "nothing" immediately followed by more word characters (as in
    # "nothingness") must not satisfy the trailing \b in "nothing runs" et al.
    verdict = classify_claim("B1: the nothingness reading was 12, expected 9 (shot.png)")
    assert not verdict.negative


# ---------------------------------------------------------------------------
# check_frame_rule branches
# ---------------------------------------------------------------------------

def test_check_frame_rule_screenshots_disabled_is_explicit_skip() -> None:
    result = check_frame_rule(
        "B4: nothing runs after the trigger (shot.png)",
        frames_marked=0,
        screenshots_enabled=False,
    )
    assert result.enforced is False
    assert result.refused is False
    assert "screenshots disabled" in result.reason


def test_check_frame_rule_non_negative_claim_always_allowed() -> None:
    result = check_frame_rule(
        "walk_to(14,22) frame budget exhausted (shot.png)",
        frames_marked=0,
        screenshots_enabled=True,
    )
    assert result.enforced is True
    assert result.refused is False
    assert not result.verdict.negative


def test_check_frame_rule_negative_claim_with_frame_is_allowed() -> None:
    result = check_frame_rule(
        "B4: nothing runs after the trigger (shot.png)",
        frames_marked=1,
        screenshots_enabled=True,
    )
    assert result.enforced is True
    assert result.refused is False
    assert result.verdict.negative
    assert result.verdict.label == "nothing-happened"


def test_check_frame_rule_negative_claim_without_frame_is_refused() -> None:
    result = check_frame_rule(
        "interaction did not start a script (shot.png)",
        frames_marked=0,
        screenshots_enabled=True,
    )
    assert result.enforced is True
    assert result.refused is True
    assert result.verdict.negative
    assert result.verdict.label == "script-did-not-start"
    assert "mark_frame()" in result.reason


def test_check_frame_rule_screenshots_disabled_beats_zero_frames_negative_claim() -> None:
    # A run with screenshots disabled never has frames marked; confirm that
    # path is the explicit skip, not a refusal, even for a negative claim.
    result = check_frame_rule(
        "no script started (shot.png)",
        frames_marked=0,
        screenshots_enabled=False,
    )
    assert result.enforced is False
    assert result.refused is False


# ---------------------------------------------------------------------------
# refusal_error / FrameRuleError
# ---------------------------------------------------------------------------

def test_refusal_error_message_names_beat_claim_and_remedy() -> None:
    claim = "interaction did not start a script (shot.png)"
    result = check_frame_rule(claim, frames_marked=0, screenshots_enabled=True)
    assert result.refused
    err = refusal_error("B11", claim, result)
    assert isinstance(err, FrameRuleError)
    assert err.beat == "B11"
    assert err.claim == claim
    assert err.verdict == result.verdict
    text = str(err)
    assert "B11" in text
    assert claim in text
    assert "mark_frame()" in text


def test_frame_rule_error_is_a_runtime_error() -> None:
    verdict = ClaimVerdict(negative=True, label="did-not-fire", matched="did not fire")
    err = FrameRuleError("B2", "the cameo did not fire (shot.png)", verdict)
    assert isinstance(err, RuntimeError)
    with pytest.raises(FrameRuleError):
        raise err


# ---------------------------------------------------------------------------
# to_dict() JSON-serialisability
# ---------------------------------------------------------------------------

def test_claim_verdict_to_dict_is_json_serialisable() -> None:
    verdict = classify_claim("B4: nothing runs after the trigger (shot.png)")
    payload = verdict.to_dict()
    json.dumps(payload)  # must not raise
    assert payload["negative"] is True
    assert payload["label"] == "nothing-happened"


def test_frame_rule_result_to_dict_is_json_serialisable() -> None:
    result = check_frame_rule(
        "interaction did not start a script (shot.png)",
        frames_marked=0,
        screenshots_enabled=True,
    )
    payload = result.to_dict()
    json.dumps(payload)  # must not raise
    assert payload["refused"] is True
    assert isinstance(payload["verdict"], dict)


def test_frame_rule_result_to_dict_non_negative_case_is_json_serialisable() -> None:
    result = check_frame_rule(
        "walk_to(14,22) frame budget exhausted (shot.png)",
        frames_marked=0,
        screenshots_enabled=True,
    )
    json.dumps(result.to_dict())  # must not raise
