"""The "human lane" — which events the hand-conversion pass owns vs. which go to Opus.

Single source of truth shared by `scripts/run_human.py` (what to OFFER the operator) and
`orchestrator` (what `run_bulk --skip-lane` SKIPS). Keeping one definition guarantees the
two passes partition the corpus cleanly: an event Opus skips is exactly one run_human can
offer, so there is no gap and no overlap.

An event is "in lane" when every one of its real commands is a code the operator can
translate without a global-flag/var naming call or Phase-5 coupling. Excluded (held for
Opus): 121/122 (global switch/var — needs a registry name proposal), warps (201),
move-routes (209/210/509), and Uranium script-calls (355/655).

Note: `in_lane` is necessary but not sufficient for an event to reach the operator —
run_human additionally drops events the deterministic pre-filter claims for free and ones
already in the memo. The orchestrator's skip is placed AFTER those same two checks, so the
skipped set matches run_human's queue exactly (in_lane AND not deterministic AND not memoized).
"""
from __future__ import annotations

# Command codes the operator can hand-translate. Dialogue (101/401), choices
# (102/402/403/404), conditional branches (111/411/412), self-switch (123), call common
# event (117), wait (106), comment (108/408), and the no-op fillers (0/5/6/7).
LANE_CODES: set[int] = {
    0, 5, 6, 7, 101, 401, 102, 402, 403, 404, 111, 411, 412, 123, 106, 108, 408, 117,
}


def real_commands(event: dict) -> list[dict]:
    """Every non-empty command across all of an event's pages (code != 0)."""
    return [
        c
        for page in event.get("pages", [])
        for c in page.get("list", [])
        if c.get("code", 0) != 0
    ]


def in_lane(event: dict) -> bool:
    """True if the event has commands and all of them are lane codes (operator-handleable)."""
    cmds = real_commands(event)
    if not cmds:
        return False
    return all(c.get("code", 0) in LANE_CODES for c in cmds)
