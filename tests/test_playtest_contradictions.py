"""Q8's carried contradiction ledger (`playtest/contradictions.py`).

What these protect is a posture, not an algorithm: a model/measurement
disagreement is *recorded and carried*, never blocking and never
auto-resolved. The CH04 failure this exists to prevent was not that
someone picked the wrong side of a disagreement -- dismissing Larrie's
(18,39) reading was defensible, given the harness genuinely was lying
elsewhere that day -- but that the disagreement was closed without being
resolved, recorded as a conclusion rather than as an open question, and
so vanished until it was rediscovered a day later.
"""
import json

import pytest

from rpg2gba.playtest.contradictions import (
    KIND_OFF_PLAN,
    KIND_UNRESOLVED_MAP,
    KIND_WALKABILITY,
    Contradiction,
    ContradictionLedger,
)


def _walkability(beat: str = "B1", cell=(3, 4), map_id: int = 35) -> Contradiction:
    return Contradiction(
        kind=KIND_WALKABILITY, beat=beat,
        detail=f"map {map_id} cell {cell}", model="walkable=True",
        measurement="walkable=False", assumption="graph's verdict used",
        map_id=map_id, cell=cell)


def test_unknown_kind_is_refused_rather_than_stored() -> None:
    """A free-form kind string would let the ledger accumulate categories
    nothing can aggregate, which is how a findings list becomes prose
    (CLAUDE.md §4.5)."""
    with pytest.raises(ValueError, match="unknown contradiction kind"):
        Contradiction(kind="vibes", beat="B1", detail="x")


def test_every_entry_is_carried_never_closed() -> None:
    """Closure is against an independent oracle -- the offline graph or a
    captured frame -- never against the run that found the disagreement
    (Q8 decision 3). No code path may mark one resolved."""
    ledger = ContradictionLedger()
    ledger.record(_walkability())
    assert [e["status"] for e in ledger.to_list()] == ["carried"]


def test_repeat_findings_collapse_to_one_row_with_a_count() -> None:
    """A stuck-and-replanning walk consults the same disputed cell dozens
    of times; each consultation is the same finding, not a new one."""
    ledger = ContradictionLedger()
    for _ in range(5):
        ledger.record(_walkability())
    assert len(ledger.entries) == 1
    assert ledger.entries[0].count == 5


def test_different_cells_and_beats_stay_separate() -> None:
    ledger = ContradictionLedger()
    ledger.record(_walkability(cell=(3, 4)))
    ledger.record(_walkability(cell=(9, 9)))
    ledger.record(_walkability(beat="B2", cell=(3, 4)))
    assert len(ledger.entries) == 3


def test_rebeat_stamps_only_unattributed_entries() -> None:
    """`_plan_route` runs deep inside the walk stack and has no idea which
    beat it is in; the runner stamps its findings at the boundary. An entry
    that already names a beat must not be re-attributed to a later one."""
    ledger = ContradictionLedger()
    ledger.record(_walkability(beat=""))
    ledger.record(_walkability(beat="B7", cell=(1, 1)))
    ledger.rebeat("B3")
    beats = [e.beat for e in ledger.entries]
    assert beats == ["B3", "B7"]


def test_rebeat_keeps_dedup_working_afterwards() -> None:
    """Re-keying on stamp must not orphan the dedup index, or the same
    finding would start producing a fresh row per occurrence."""
    ledger = ContradictionLedger()
    ledger.record(_walkability(beat=""))
    ledger.rebeat("B3")
    ledger.record(_walkability(beat="B3"))
    assert len(ledger.entries) == 1
    assert ledger.entries[0].count == 2


def test_drain_into_moves_and_empties() -> None:
    source, sink = ContradictionLedger(), ContradictionLedger()
    source.record(_walkability(beat=""))
    source.drain_into(sink, beat="B4")
    assert source.entries == []
    assert [e.beat for e in sink.entries] == ["B4"]


def test_conformance_counts_only_walkability_disagreements() -> None:
    """Q7's number is specifically "the harness's live read disagreed with
    the offline graph". An off-plan walk or an unresolvable map is a
    carried finding too, but neither is a harness-vs-oracle conformance
    result, and folding them in would inflate the one number the report
    exists to make trustworthy."""
    ledger = ContradictionLedger()
    ledger.record(_walkability(cell=(1, 1), map_id=35))
    ledger.record(_walkability(cell=(1, 1), map_id=35))  # same cell, x2
    ledger.record(_walkability(cell=(2, 2), map_id=35))
    ledger.record(_walkability(cell=(5, 5), map_id=37))
    ledger.record(Contradiction(kind=KIND_OFF_PLAN, beat="B1", detail="off"))
    ledger.record(Contradiction(kind=KIND_UNRESOLVED_MAP, beat="B1", detail="?"))

    conf = ledger.conformance()
    assert conf["oracle"] == "offline_graph"
    assert conf["walkability_disagreements"] == 4  # 2 + 1 + 1
    assert conf["distinct_cells"] == 3
    assert conf["by_map"] == {"35": 3, "37": 1}


def test_conformance_over_a_clean_run_is_zero_not_absent() -> None:
    """A clean run must report zero rather than omitting the section: an
    absent number reads as "not measured", which is exactly the ambiguity
    a conformance report exists to remove."""
    conf = ContradictionLedger().conformance()
    assert conf["walkability_disagreements"] == 0
    assert conf["by_map"] == {}


def test_to_list_is_json_serialisable() -> None:
    ledger = ContradictionLedger()
    ledger.record(_walkability())
    ledger.record(Contradiction(kind=KIND_UNRESOLVED_MAP, beat="B1",
                                 detail="group=9 num=2 is unminted"))
    round_tripped = json.loads(json.dumps(ledger.to_list()))
    assert round_tripped[0]["cell"] == [3, 4]
    assert round_tripped[1]["cell"] is None
    assert round_tripped[1]["map_id"] is None
