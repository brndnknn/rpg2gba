"""OQ-3 Step 1 — move-route coverage census (zero LLM).

Implements Step 1 of OQ3_EMPIRICAL_PLAN.md: the structural census that answers
whether the RMXP move-command -> pokeemerald `MOVEMENT_ACTION_*` mapping is
deterministic (vocabulary determinism), separately from target resolution
(player/self/other local-id wiring, already Track-B-gated).

For every `209` (Set Move Route) command in the corpus it:

  * enumerates the inner RMXP move-command codes (1..45) actually used, with a
    histogram by occurrence and by number of events touched;
  * applies a hand-authored CANDIDATE map (the determinism hypothesis under
    test) bucketing each code A / B / C:
      A = direct macro      -> a fixed MOVEMENT_ACTION_*, no judgement
      B = parameterized-det -> a fixed function of the command's parameters
      C = no static analog / context-dependent / needs judgement
  * classifies each 209-bearing event: FULLY-DETERMINISTIC iff every inner
    command is in A or B (code 0 terminator ignored);
  * crosses determinism with the target class (player -1 / self 0 / other >0)
    to produce the Step-3 three-way partition:
      1. fully-det + player-only   -> reclaim now (no local-id dependency)
      2. fully-det + self/other    -> reclaimable after Track-B local-ids
      3. contains a bucket-C cmd    -> Opus tail (Group 5);
  * dumps the exact bucket-C commands that break each non-deterministic event,
    so we can see whether the residue is one or two recurring (rule-fixable)
    commands or genuinely scattered (judgement).

Pure static analysis over output/uranium-build/maps/*.json. No network, seconds.
The CANDIDATE table below is the single thing to edit when re-bucketing.

Run:  PYTHONPATH=src python3 scripts/moveroute_coverage.py [MAPS_DIR]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from rpg2gba.conversion_agent.lane import real_commands

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MAPS = REPO / "output" / "uranium-build" / "maps"

SET_MOVE_ROUTE = 209  # event command carrying an inline RPG::MoveRoute
# Related move-route event codes, tallied for scope visibility only.
WAIT_FOR_COMPLETION = 210
MOVE_ROUTE_CONT = 509  # move-command continuation, if the deserializer emits it

A, B, C = "A", "B", "C"

# RMXP inner move-command code -> (bucket, candidate MOVEMENT_ACTION_* / rule, note).
# Codes per RMXP RPG::MoveCommand: 1-8 move dirs, 9 random, 10/11 toward/away
# player, 12/13 step fwd/back, 14 jump, 15 wait, 16-26 turns, 27/28 switch,
# 29 speed, 30 freq, 31-40 anim/dirfix/through/on-top toggles, 41 graphic,
# 42 opacity, 43 blending, 44 SE, 45 script. Code 0 = route terminator.
CANDIDATE: dict[int, tuple[str, str, str]] = {
    1:  (A, "WALK_NORMAL_DOWN", ""),
    2:  (A, "WALK_NORMAL_LEFT", ""),
    3:  (A, "WALK_NORMAL_RIGHT", ""),
    4:  (A, "WALK_NORMAL_UP", ""),
    5:  (C, "-", "diagonal: no GBA walk action"),
    6:  (C, "-", "diagonal: no GBA walk action"),
    7:  (C, "-", "diagonal: no GBA walk action"),
    8:  (C, "-", "diagonal: no GBA walk action"),
    9:  (C, "-", "move at random (nondeterministic)"),
    10: (C, "-", "move toward player (no walk-to-player action)"),
    11: (C, "-", "move away from player (no walk-away action)"),
    12: (C, "-", "step forward (facing-relative)"),
    13: (C, "-", "step backward (facing-relative)"),
    14: (B, "JUMP_* by (dx,dy)", "cardinal <=2 tiles -> JUMP macro; else C (see params)"),
    15: (B, "DELAY_* by frames", "frame count -> nearest DELAY_*"),
    16: (A, "FACE_DOWN", ""),
    17: (A, "FACE_LEFT", ""),
    18: (A, "FACE_RIGHT", ""),
    19: (A, "FACE_UP", ""),
    20: (C, "-", "turn 90 right (facing-relative)"),
    21: (C, "-", "turn 90 left (facing-relative)"),
    22: (C, "-", "turn 180 (facing-relative)"),
    23: (C, "-", "turn 90 right-or-left (random)"),
    24: (C, "-", "turn at random"),
    25: (A, "FACE_PLAYER", ""),
    26: (A, "FACE_AWAY_PLAYER", ""),
    27: (C, "-", "switch ON (side-effect; hoist setflag)"),
    28: (C, "-", "switch OFF (side-effect; hoist clearflag)"),
    29: (B, "WALK_{SLOW,NORMAL,FAST,FASTER}", "speed param sets following steps' speed"),
    30: (C, "-", "change frequency (no analog; timing only)"),
    31: (C, "-", "move-animation ON (toggle)"),
    32: (C, "-", "move-animation OFF (toggle)"),
    33: (C, "-", "stop-animation ON (toggle)"),
    34: (C, "-", "stop-animation OFF (toggle)"),
    35: (A, "LOCK_FACING_DIRECTION", "dirfix-on; confirm semantics at Step 2"),
    36: (A, "UNLOCK_FACING_DIRECTION", "dirfix-off; confirm semantics at Step 2"),
    37: (C, "-", "through ON (object property, no movement action)"),
    38: (C, "-", "through OFF (object property, no movement action)"),
    39: (C, "-", "always-on-top ON (approx SET_FIXED_PRIORITY)"),
    40: (C, "-", "always-on-top OFF (approx CLEAR_FIXED_PRIORITY)"),
    41: (C, "-", "change graphic (hoist sprite swap)"),
    42: (C, "-", "change opacity (approx -> binary visible/invisible)"),
    43: (C, "-", "change blending (no analog)"),
    44: (C, "-", "play SE (hoist playse)"),
    45: (C, "-", "script (judgement)"),
}

CODE_NAME: dict[int, str] = {
    1: "Move Down", 2: "Move Left", 3: "Move Right", 4: "Move Up",
    5: "Move LL", 6: "Move LR", 7: "Move UL", 8: "Move UR",
    9: "Move Random", 10: "Move toward Player", 11: "Move away Player",
    12: "Step Forward", 13: "Step Backward", 14: "Jump", 15: "Wait",
    16: "Turn Down", 17: "Turn Left", 18: "Turn Right", 19: "Turn Up",
    20: "Turn 90R", 21: "Turn 90L", 22: "Turn 180", 23: "Turn 90R/L",
    24: "Turn Random", 25: "Turn toward Player", 26: "Turn away Player",
    27: "Switch ON", 28: "Switch OFF", 29: "Change Speed", 30: "Change Freq",
    31: "MoveAnim ON", 32: "MoveAnim OFF", 33: "StopAnim ON", 34: "StopAnim OFF",
    35: "DirFix ON", 36: "DirFix OFF", 37: "Through ON", 38: "Through OFF",
    39: "OnTop ON", 40: "OnTop OFF", 41: "Change Graphic", 42: "Change Opacity",
    43: "Change Blending", 44: "Play SE", 45: "Script",
}


# Within bucket C, the "soft" codes are side-effect / property / cosmetic toggles
# whose §5.5 lean is a fixed rule (drop / hoist-as-side-effect / approximate) — NOT
# judgement. If Step-2 calibration validates those rules they stop breaking events.
# Everything else in C is "hard": no possible static analog or genuine judgement
# (diagonals, random, toward/away-player moves, facing-relative steps & turns, script).
SOFT_C: set[int] = {27, 28, 30, 31, 32, 33, 34, 37, 38, 39, 40, 41, 42, 43, 44}

# Inner-jump offsets pokeemerald can express (cardinal 1-2 tiles, or in-place 0,0).
JUMP_OK = {(0, 0), (0, 1), (1, 0), (0, 2), (2, 0)}


def bucket_of(code: int) -> str:
    """Bucket for an inner move-command code; unknown codes fail to C (conservative)."""
    return CANDIDATE.get(code, (C, "-", "UNKNOWN code"))[0]


def is_hard_c(code: int) -> bool:
    """True if `code` is a bucket-C command with no rule-based fix (genuine judgement)."""
    return bucket_of(code) == C and code not in SOFT_C


def target_class(tid: int) -> str:
    if tid == -1:
        return "player"
    if tid == 0:
        return "self"
    return "other"


def iter_routes(maps_dir: Path):
    """Yield (map_id, event, route_target_id, move_commands) for every 209 command."""
    for mp in sorted(maps_dir.glob("Map*.json")):
        d = json.loads(mp.read_text(encoding="utf-8"))
        mid = d.get("map_id")
        for ev in d.get("events", []):
            for c in real_commands(ev):
                if c.get("code") != SET_MOVE_ROUTE:
                    continue
                params = c.get("parameters") or []
                tid = params[0] if params else 0
                route = params[1] if len(params) > 1 else {}
                cmds = route.get("list", []) if isinstance(route, dict) else []
                yield mid, ev, tid, cmds


def main() -> None:
    maps_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MAPS

    n_routes = 0
    code_occ: Counter[int] = Counter()        # inner code -> total occurrences
    code_events: Counter[int] = Counter()     # inner code -> distinct events
    bucketC_occ: Counter[int] = Counter()     # C code -> occurrences
    bucketC_events: Counter[int] = Counter()  # C code -> distinct events broken
    jump_offsets: Counter[tuple[int, int]] = Counter()
    wait_frames: Counter[int] = Counter()
    speed_vals: Counter[int] = Counter()

    # Per-event aggregation keyed by (map_id, event_id).
    ev_codes: dict[tuple[int, int], set[int]] = {}
    ev_targets: dict[tuple[int, int], set[str]] = {}
    ev_name: dict[tuple[int, int], str] = {}

    sibling_210 = sibling_509 = 0
    anomalies = 0

    for mid, ev, tid, cmds in iter_routes(maps_dir):
        n_routes += 1
        key = (mid, ev.get("id"))
        ev_name.setdefault(key, f"Map{mid:03d} {ev.get('name')}")
        ev_targets.setdefault(key, set()).add(target_class(tid))
        codes_here: set[int] = set()
        for mc in cmds:
            if not isinstance(mc, dict):
                anomalies += 1
                continue
            code = mc.get("code", 0)
            if code == 0:  # route terminator
                continue
            code_occ[code] += 1
            codes_here.add(code)
            if bucket_of(code) == C:
                bucketC_occ[code] += 1
            mparams = mc.get("parameters") or []
            if code == 14 and len(mparams) >= 2:
                jump_offsets[(mparams[0], mparams[1])] += 1
            elif code == 15 and mparams:
                wait_frames[mparams[0]] += 1
            elif code == 29 and mparams:
                speed_vals[mparams[0]] += 1
        for code in codes_here:
            code_events[code] += 1
            if bucket_of(code) == C:
                bucketC_events[code] += 1
        ev_codes.setdefault(key, set()).update(codes_here)

    # Sibling move-route codes, for scope visibility.
    for mp in sorted(maps_dir.glob("Map*.json")):
        d = json.loads(mp.read_text(encoding="utf-8"))
        for ev in d.get("events", []):
            for c in real_commands(ev):
                if c.get("code") == WAIT_FOR_COMPLETION:
                    sibling_210 += 1
                elif c.get("code") == MOVE_ROUTE_CONT:
                    sibling_509 += 1

    # Per-event determinism + Step-3 partition.
    # Conservative: A/B only. Potential: A/B + SOFT-C (after Step-2 rules validate).
    reclaim_now = track_b = opus_tail = 0
    pot_reclaim = pot_track_b = hard_tail = 0
    tail_examples: list[str] = []
    for key, codes in ev_codes.items():
        targets = ev_targets[key]
        player_only = targets == {"player"}
        fully_det = all(bucket_of(c) in (A, B) for c in codes)
        if not fully_det:
            opus_tail += 1
            if len(tail_examples) < 15:
                breakers = sorted(c for c in codes if bucket_of(c) == C)
                names = ", ".join(f"{c} {CODE_NAME.get(c, '?')}" for c in breakers)
                tail_examples.append(f"{ev_name[key]:30}  breaks on: {names}")
        elif player_only:
            reclaim_now += 1
        else:
            track_b += 1
        # Potential partition: only HARD-C commands count as breakers.
        if any(is_hard_c(c) for c in codes):
            hard_tail += 1
        elif player_only:
            pot_reclaim += 1
        else:
            pot_track_b += 1

    n_events = len(ev_codes)

    print(f"corpus: {maps_dir}")
    print(f"209 (Set Move Route) commands : {n_routes}")
    print(f"events containing >=1 209     : {n_events}")
    print(f"sibling 210 (wait-for-move)   : {sibling_210}")
    print(f"sibling 509 (route cont)      : {sibling_509}")
    if anomalies:
        print(f"!! malformed inner commands    : {anomalies}")

    print("\n== inner move-command codes (by occurrence) ==")
    print(f"{'code':>4}  {'name':22} {'bkt':3} {'occ':>6} {'events':>7}  candidate")
    for code, occ in code_occ.most_common():
        bkt, action, _ = CANDIDATE.get(code, (C, "-", ""))
        print(f"{code:>4}  {CODE_NAME.get(code, '?'):22} {bkt:3} {occ:>6} "
              f"{code_events[code]:>7}  {action}")

    a_occ = sum(n for c, n in code_occ.items() if bucket_of(c) == A)
    b_occ = sum(n for c, n in code_occ.items() if bucket_of(c) == B)
    c_occ = sum(n for c, n in code_occ.items() if bucket_of(c) == C)
    tot = max(a_occ + b_occ + c_occ, 1)
    print(f"\ncommand-level buckets: A {a_occ} ({a_occ*100//tot}%)  "
          f"B {b_occ} ({b_occ*100//tot}%)  C {c_occ} ({c_occ*100//tot}%)")

    print("\n== bucket-C breakers (the determinism killers; by #events broken) ==")
    for code, n in bucketC_events.most_common():
        _, _, note = CANDIDATE.get(code, (C, "-", "UNKNOWN"))
        print(f"{n:5} ev  {code:>3} {CODE_NAME.get(code, '?'):22}  "
              f"{bucketC_occ[code]:>6} occ  {note}")

    print("\n== bucket-B parameter caveats (deterministic only if these stay simple) ==")
    diag_far = sum(n for (dx, dy), n in jump_offsets.items()
                   if (abs(dx), abs(dy)) not in {(0, 0), (0, 1), (1, 0), (0, 2), (2, 0)})
    print(f"  jump (14): {sum(jump_offsets.values())} occ; "
          f"{diag_far} are diagonal or >2 tiles (true bucket-C; (0,0)=jump-in-place is OK)")
    if jump_offsets:
        top = ", ".join(f"({dx},{dy})x{n}" for (dx, dy), n in jump_offsets.most_common(6))
        print(f"    top offsets: {top}")
    if speed_vals:
        print(f"  speed (29) values: {dict(sorted(speed_vals.items()))}")
    if wait_frames:
        print(f"  wait  (15) frames: {dict(sorted(wait_frames.most_common(8)))}")

    print("\n== target class crosstab (events; player-only is local-id-free) ==")
    tc = Counter(frozenset(t) for t in ev_targets.values())
    for ts, n in tc.most_common():
        print(f"{n:5}  {{{', '.join(sorted(ts))}}}")

    print("\n== OQ-3 ANSWER (conservative: only A/B macros count as deterministic) ==")
    print(f"  fully-deterministic + player-only  (reclaim NOW)      : {reclaim_now}")
    print(f"  fully-deterministic + self/other   (after Track-B)    : {track_b}")
    print(f"  contains ANY bucket-C command      (Opus tail/Grp 5)  : {opus_tail}")
    det_total = reclaim_now + track_b
    print(f"  --> vocabulary-deterministic events: {det_total}/{n_events} "
          f"({det_total*100//max(n_events,1)}%)")

    print("\n== OQ-3 POTENTIAL (if Step-2 validates the SOFT-C drop/hoist/approx rules) ==")
    print(f"  deterministic + player-only        (reclaim after S2)  : {pot_reclaim}")
    print(f"  deterministic + self/other         (after S2+Track-B)  : {pot_track_b}")
    print(f"  contains a HARD-C command          (irreducible tail)  : {hard_tail}")
    pot_total = pot_reclaim + pot_track_b
    print(f"  --> potential deterministic events : {pot_total}/{n_events} "
          f"({pot_total*100//max(n_events,1)}%)")
    print("  SOFT-C (rule-fixable at Step 2): through 37/38, opacity 42, SE 44,")
    print("    graphic 41, on-top 39/40, freq 30, anim 31-34, blend 43, switch 27/28.")

    print("\n== sample Opus-tail events (what their bucket-C breakers are) ==")
    for line in tail_examples:
        print(f"  {line}")


if __name__ == "__main__":
    main()
