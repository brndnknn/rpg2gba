"""`jvNextReward` is an unknown boolean `dex_count` input, not a party_model
refusal (operator ruling 2026-10-15, 08-route-1-moki-revisit.md s9)."""
from __future__ import annotations

from rpg2gba.ruby_subset import FixedOracle, evaluate_expression, parse_expression
from rpg2gba.ruby_subset import builtins as bi
from rpg2gba.story_state.state import Variable

EV = (50, 5)


def test_jv_next_reward_is_a_dex_count_input_not_party_model():
    assert "jvNextReward" not in bi.PARTY_MODEL_CALLS
    spec = bi.INPUT_CALLS["jvNextReward"]
    assert spec.kind == "dex_count" and spec.domain == (True, False)
    assert spec.kind != bi.INPUT_CALLS["pbRockSmash"].kind  # distinct from `capability`


def test_true_arm_bumps_var_22():
    value, result = evaluate_expression(
        parse_expression("jvNextReward"),
        oracle=FixedOracle(reads={Variable(22): 3}, choices=[True]), event=EV)
    assert result.refusal is None and value is True
    assert {w.key: w.value for w in result.writes}[Variable(22)] == 4


def test_false_arm_writes_nothing():
    value, result = evaluate_expression(
        parse_expression("jvNextReward"),
        oracle=FixedOracle(reads={Variable(22): 3}, choices=[False]), event=EV)
    assert result.refusal is None and value is False
    assert not result.writes


def test_choice_source_names_dex_count():
    seen = []

    class Spy(FixedOracle):
        def choose(self, source):
            seen.append((source.kind, source.detail, source.domain))
            return True

    evaluate_expression(parse_expression("jvNextReward"), oracle=Spy(), event=EV)
    assert seen == [("dex_count", "jvNextReward", (True, False))]


def test_direct_dex_read_still_refuses():
    _, result = evaluate_expression(
        parse_expression("$Trainer.pokedexOwned >= 10"), oracle=FixedOracle(), event=EV)
    assert result.refusal is not None and result.refusal.code == "party_model"
