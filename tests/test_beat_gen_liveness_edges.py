"""Killer and threshold edges (`beat_gen/liveness_edges.py`, solver
`killed_before` / `threshold_enabled_by`)."""
from __future__ import annotations

import logging
from types import SimpleNamespace

from rpg2gba.beat_gen.liveness_edges import WriteModel, killed_before, split_threshold_enablers
from rpg2gba.beat_gen.plan import PlannedBeat
from rpg2gba.routing.solver import (
    PrecedenceEdge,
    _acyclic_story_edges,
    _derive_killer_precedence,
)
from rpg2gba.story_state.state import Adjust, Assign, Test, Variable

V = Variable(101)
EV = "map032/ev009"
P0, P1, P2 = f"{EV}/p0", f"{EV}/p1", f"{EV}/p2"
PAGES = (P0, P1, P2)


def _row(row_id, *, tests=(), writes=(), pages=PAGES, havoc=()):
    return SimpleNamespace(row_id=row_id, parent_row_id=None, page_tests=tuple(tests),
                           page_refusals=(), arm_guard=None, writes=tuple(writes),
                           havoc_keys=tuple(havoc), event_page_row_ids=pages)


def _assign(v):
    return Assign(V, frozenset({v}), False, "t")


def _model(states):
    return WriteModel(states.get, lambda _p: {"list": []})


def _beat(name, rows, group=None):
    return PlannedBeat(name=name, template="generic", map_id=32, rows=tuple(rows),
                       group=group or name)


def _states():
    return {
        P0: _row(P0),
        P1: _row(P1, tests=[Test(V, ">=", 2)]),
        P2: _row(P2, tests=[Test(V, ">=", 4)], writes=[_assign(4)]),
        "map172/ev004/p0": _row("map172/ev004/p0", pages=("map172/ev004/p0",),
                                writes=[_assign(2)]),
        "map172/ev004/p1": _row("map172/ev004/p1", pages=("map172/ev004/p1",),
                                writes=[_assign(1)]),
    }


def test_killer_orders_lower_page_before_enabling_write():
    st = _states()
    beats = [_beat("b0", [P0]), _beat("theo", ["map172/ev004/p0"])]
    out = killed_before(beats, wm=_model(st), seed={}, claimed_rows={P0, "map172/ev004/p0"})
    # setvar 2 satisfies p1 (>= 2): p0 must fire before it.
    assert out == {P0: ("map172/ev004/p0",)}
    edges = _derive_killer_precedence(out, {P0: "b0", "map172/ev004/p0": "theo"})
    assert edges == (PrecedenceEdge(before="b0", after="theo",
                                    reason=f"killer:map172/ev004/p0->{P0}"),)


def test_several_killers_page_precedes_all():
    st = _states()
    beats = [_beat("b0", [P0]), _beat("theo", ["map172/ev004/p0"]), _beat("moki", [P2])]
    out = killed_before(beats, wm=_model(st), seed={},
                        claimed_rows={P0, "map172/ev004/p0", P2})
    assert out[P0] == tuple(sorted((P2, "map172/ev004/p0")))
    edges = _derive_killer_precedence(out, {P0: "b0", "map172/ev004/p0": "theo", P2: "moki"})
    assert {(e.before, e.after) for e in edges} == {("b0", "theo"), ("b0", "moki")}


def test_same_group_and_own_page_writers_are_exempt():
    st = _states()
    # theo's write lands in p0's own group: no killer, no edge.
    beats = [_beat("b0", [P0, "map172/ev004/p0"], group="g")]
    assert killed_before(beats, wm=_model(st), seed={},
                         claimed_rows={P0, "map172/ev004/p0"}) == {}
    # a write on p0's own page never kills p0.
    st[P0] = _row(P0, writes=[_assign(2)])
    assert killed_before([_beat("b0", [P0])], wm=_model(st), seed={}, claimed_rows={P0}) == {}
    assert _derive_killer_precedence({P0: ("x",)}, {P0: "g", "x": "g"}) == ()


def test_threshold_enabler_drops_writer_too_small():
    st = _states()
    st["map050/ev019/p0"] = _row("map050/ev019/p0", pages=("map050/ev019/p0",),
                                 havoc=[V])
    st["map032/ev002/p1"] = _row("map032/ev002/p1", tests=[Test(V, ">=", 4)],
                                 pages=("map032/ev002/p1",))
    enabled = {"map032/ev002/p1": (("map032/ev009/p2", "map050/ev019/p0"),),
               P1: (("map172/ev004/p0", P2),)}
    wm = WriteModel(st.get, lambda _p: {"list": [
        {"code": 122, "parameters": [101, 101, 1, 0, 1]}]})
    kept, shrunk = split_threshold_enablers(
        enabled, wm=wm, seed={}, claimed_rows={"map172/ev004/p0", P2, "map050/ev019/p0"})
    # +1 on {0, 2, 4} never takes a failing value across >= 4; only p2 qualifies.
    assert shrunk == {"map032/ev002/p1": (("map032/ev009/p2",),)}
    # both writers of >= 2 qualify: the group is unchanged.
    assert kept == {P1: (("map172/ev004/p0", P2),)}


def test_threshold_adjust_that_can_reach_is_kept():
    st = _states()
    st["a"] = _row("a", pages=("a",), writes=[Adjust(V, "+", 2, False, "t")])
    st["t"] = _row("t", tests=[Test(V, ">=", 2)], pages=("t",))
    kept, shrunk = split_threshold_enablers(
        {"t": (("a", P2),)}, wm=_model(st), seed={}, claimed_rows={"a", P2})
    assert shrunk == {} and kept == {"t": (("a", P2),)}


def test_cycle_closing_killer_is_dropped_with_warning(caplog):
    hard = (PrecedenceEdge(before="theo", after="b0", reason="warp"),)
    killer = _derive_killer_precedence({P0: ("map172/ev004/p0",)},
                                       {P0: "b0", "map172/ev004/p0": "theo"})
    with caplog.at_level(logging.WARNING):
        kept = _acyclic_story_edges(hard, killer, level=logging.WARNING)
    assert kept == ()
    assert any(r.levelno == logging.WARNING and "killer:" in r.message for r in caplog.records)
