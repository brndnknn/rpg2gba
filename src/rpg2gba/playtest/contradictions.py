"""Q8's carried contradiction ledger.

A *contradiction* is a disagreement between the model (the offline
traversal graph derived from decoded data) and a measurement (what the
running ROM reported). `PLAYTEST_AUTHORING_IMPROVEMENT_V2.md` Q8 settles
what to do with one, and the answer is deliberately not "stop":

1. **A measurement/model contradiction is a recorded finding, not a
   blocking one.** Work continues on a stated assumption; the
   contradiction is carried forward in the artifact until explicitly
   closed.
2. **Not blocking, deliberately.** `CH02:B14`'s RNG-timed facing check
   was indistinguishable from "not yet fired" and truncated two full CH04
   debug runs. A blocking rule halts work on genuine noise. The CH04
   failure was never that work continued -- it was that the disagreement
   *vanished*, with nothing carrying it.
3. **Resolution is against an independent oracle** (Q7): the offline
   graph, or a captured frame -- never against another inference.

Q13.1 folds into this rather than adding a second mechanism: a walked
path that leaves the approved route without touching a trigger tile is
precisely evidence that the offline graph is wrong about the engine
(sideways-stairs collision, sight-cone semantics, the object spawn
window, the hardware-unverified ledge derivation), and that class of
error will essentially never land on a trigger tile. So it is recorded
here and carried, not failed. Slice 4 builds one thing, not two.

**Why a ledger object and not a `logger.warning`.** `_plan_route` already
detected the graph-vs-live-collision disagreement and logged it at
WARNING. A warning in a run log is exactly the shape of "carried by
someone remembering to read it" that §1.5 of the source document
disqualifies: it does not reach the artifact, the viewer, or the gate
stamp, so it goes invisible the moment the run scrolls past. The ledger
puts the same finding in `observed_beats/<chapter>.json`, where the
viewer draws it and the next run's diff can see it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

Cell = tuple[int, int]

#: Model/measurement disagreement about whether one tile is walkable.
#: Raised by `Emulator._plan_route`, which consults the offline graph for
#: static walkability and the live collision grid for the same cell.
KIND_WALKABILITY = "graph_vs_live_collision"

#: The walk left the approved route on a tile that fires no foreign
#: trigger (Q13.1). Not a failure -- see the module docstring.
KIND_OFF_PLAN = "walk_off_plan"

#: A walked tile whose live `(map_group, map_num)` resolves to no minted
#: Uranium map, so nothing could be compared for it. Recorded rather than
#: dropped: a silently uncompared tile is indistinguishable from a
#: compared-and-clean one, which is the failure mode §4.5 forbids.
KIND_UNRESOLVED_MAP = "unresolved_map"

#: An INHERITED beat whose leg could not be planned and was walked greedily
#: on the bare target instead, with none of the planner's avoid-set.
#:
#: CH01-CH04 were authored while `_route_waypoints` degraded to exactly this
#: walk on every planning failure, so their coordinates were never held to a
#: strict planner; the degrade was removed in f705b642 and CH05's replay is
#: the first run to feel it. `_walk_to_once` restores it for inherited beats
#: only, as scaffolding until those chapters are re-derived -- see its
#: docstring for the scope and the expiry.
#:
#: It is recorded because of what it costs. This is the walk that crossed
#: Timothy's event-touch tile in CH04's B3, fought the wrong trainer, and
#: passed both guards -- read as a converter bug for three sessions. A run
#: that leaned on it is not the same evidence as a run that did not, and the
#: difference has to be visible in the artifact rather than in a log nobody
#: reads. §4.5 forbids the silence, not the walk.
KIND_REPLAY_FALLBACK = "replay_route_fallback"

_KINDS = frozenset({KIND_WALKABILITY, KIND_OFF_PLAN, KIND_UNRESOLVED_MAP,
                    KIND_REPLAY_FALLBACK})


@dataclass(frozen=True)
class Contradiction:
    """One carried finding.

    `model` and `measurement` are short verdict strings written from the
    two sides' own point of view ("walkable" / "blocked"), never a
    pre-resolved conclusion: the whole point of Q8 is that the ledger
    records the disagreement instead of picking a winner. `assumption`
    states which side the run proceeded on, so a reader can tell what the
    output was built against -- decision 1's "work continues on a stated
    assumption".
    """

    kind: str
    beat: str
    detail: str
    model: str = ""
    measurement: str = ""
    assumption: str = ""
    map_id: int | None = None
    cell: Cell | None = None
    count: int = 1

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError(
                f"unknown contradiction kind {self.kind!r}; add it to "
                f"contradictions.py rather than passing a free-form string "
                f"(known: {sorted(_KINDS)})")

    @property
    def key(self) -> tuple[str, str, int | None, Cell | None]:
        """Identity for de-duplication within one run.

        A stuck-and-replanning walk consults the same disputed cell dozens
        of times per beat; each consultation is the same finding, not a
        new one. Collapsing on (kind, beat, map, cell) keeps a `count`
        instead, so the ledger stays readable without losing how loud the
        disagreement was.
        """
        return (self.kind, self.beat, self.map_id, self.cell)

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "beat": self.beat,
            "detail": self.detail,
            "model": self.model,
            "measurement": self.measurement,
            "assumption": self.assumption,
            "map_id": self.map_id,
            "cell": list(self.cell) if self.cell is not None else None,
            "count": self.count,
            # Every entry is carried, never closed by the run that found
            # it: closure is against an independent oracle (Q7), which is
            # a human reading a frame or a re-derivation, not this run.
            "status": "carried",
        }


@dataclass
class ContradictionLedger:
    """The run's carried findings, in first-seen order.

    Deliberately append-only and non-blocking: nothing in this class can
    fail a beat, and no caller should branch on its contents. It is an
    evidence trail.
    """

    entries: list[Contradiction] = field(default_factory=list)
    _index: dict[tuple[str, str, int | None, Cell | None], int] = field(
        default_factory=dict, repr=False)

    def record(self, item: Contradiction) -> None:
        seen = self._index.get(item.key)
        if seen is None:
            self._index[item.key] = len(self.entries)
            self.entries.append(item)
            logger.warning(
                "contradiction recorded (%s, beat %s): %s -- carried, not "
                "blocking (Q8)", item.kind, item.beat or "-", item.detail)
            return
        prior = self.entries[seen]
        self.entries[seen] = Contradiction(
            kind=prior.kind, beat=prior.beat, detail=prior.detail,
            model=prior.model, measurement=prior.measurement,
            assumption=prior.assumption, map_id=prior.map_id,
            cell=prior.cell, count=prior.count + item.count)

    def extend(self, items: Iterable[Contradiction]) -> None:
        for item in items:
            self.record(item)

    def rebeat(self, beat: str) -> None:
        """Attribute every entry recorded with no beat name to `beat`.

        `_plan_route` runs deep inside a beat and has no idea which one it
        is in; the runner does. Rather than thread a beat name through the
        whole walk stack, the runner stamps the unattributed entries at
        each beat boundary. Entries already carrying a beat are left
        alone.
        """
        for i, item in enumerate(self.entries):
            if item.beat:
                continue
            stamped = Contradiction(
                kind=item.kind, beat=beat, detail=item.detail,
                model=item.model, measurement=item.measurement,
                assumption=item.assumption, map_id=item.map_id,
                cell=item.cell, count=item.count)
            self.entries[i] = stamped
            self._index.pop(item.key, None)
            self._index[stamped.key] = i

    def drain_into(self, other: "ContradictionLedger", *, beat: str) -> None:
        """Move every entry into `other`, stamping unattributed ones with
        `beat`, and empty this ledger.

        The emulator collects findings as it walks and the runner owns the
        run-level ledger; this is the handoff at each beat boundary, which
        is also the first point where the beat's name is known.
        """
        self.rebeat(beat)
        other.extend(self.entries)
        self.entries.clear()
        self._index.clear()

    def to_list(self) -> list[dict[str, object]]:
        return [item.to_dict() for item in self.entries]

    def conformance(self) -> dict[str, object]:
        """Q7's conformance summary, from the same evidence.

        Q7 decision 2 folds the conformance suite into Q13's divergence
        check "using the offline graph as its oracle -- one mechanism, not
        two", and the grill finding behind it is why: a suite whose
        expected values come from the harness goes green when the harness
        lies, because the lying primitive and the lying oracle agree.
        `interact()`'s stale sample would have passed a suite whose
        expectations `interact()` recorded. So there is no separate
        expectation table here. The conformance number IS the count of
        places the harness's live reads disagreed with offline-derived
        truth over the run that actually happened.
        """
        by_map: dict[str, int] = {}
        walkability = 0
        for item in self.entries:
            if item.kind != KIND_WALKABILITY:
                continue
            walkability += item.count
            key = str(item.map_id)
            by_map[key] = by_map.get(key, 0) + item.count
        return {
            "oracle": "offline_graph",
            "walkability_disagreements": walkability,
            "distinct_cells": sum(
                1 for e in self.entries if e.kind == KIND_WALKABILITY),
            "by_map": by_map,
        }
