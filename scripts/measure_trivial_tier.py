"""Measure the true Sonnet-routable tier AFTER the deterministic pre-filter.

The 2026-06-03 difficulty scan (73.3% judgment / 26.7% trivial of 3,581 events)
predates the pre-filter, which was then built to claim exactly the mechanical
shapes. This script answers the option-(c) question: of the events the real
pre-filter does NOT claim (the actual Opus-spawn population), how many are
still "trivial" by the same scan's definition (mechanical text/warp/call/SE,
strippable script calls only — no branches, no vars/switches, no move routes,
no real script calls)?

    .venv/bin/python scripts/measure_trivial_tier.py
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from rpg2gba.conversion_agent import deterministic
from rpg2gba.conversion_agent.orchestrator import _event_has_commands
from rpg2gba.pipeline import _load_dotenv, _repo_root

# Judgment markers per the 2026-06-03 scan categories.
_BRANCH_CODES = {111, 411, 412}
_CHOICE_CODES = {102, 402, 403, 404, 103}
_STATE_CODES = {121, 122, 123}  # switches / variables / self-switches
_MOVE_ROUTE_CODES = {209, 210, 509}
_SCRIPT_CODES = {355, 655}

# Mechanical codes a trivial event may contain: text/comments, wait, call-CE,
# transfer, screen fx, audio.
_TRIVIAL_CODES = {
    0, 5, 6, 7,
    101, 401, 108, 408,
    106, 117, 201,
    221, 222, 223, 224,
    241, 242, 245, 246, 249, 250,
}


def _maps_dir() -> Path:
    _load_dotenv()
    out = Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
    if not out.is_absolute():
        out = _repo_root() / out
    return out / "uranium-build" / "maps"


def _commands(event: dict):
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            yield cmd


def classify_remaining(event: dict) -> tuple[str, set[str]]:
    """('trivial'|'judgment', reasons) for an event the pre-filter passed on."""
    reasons: set[str] = set()
    other: set[int] = set()
    for cmd in _commands(event):
        code = cmd.get("code", 0)
        if code in _BRANCH_CODES:
            reasons.add("branch")
        elif code in _CHOICE_CODES:
            reasons.add("choice/input")
        elif code in _STATE_CODES:
            reasons.add("switch/var/self-switch")
        elif code in _MOVE_ROUTE_CODES:
            reasons.add("move-route")
        elif code in _SCRIPT_CODES:
            p = (cmd.get("parameters") or [""])[0]
            if not (isinstance(p, str) and deterministic._DIALOGUE_STRIP_RE.match(p)):
                reasons.add("script-call")
        elif code not in _TRIVIAL_CODES:
            other.add(code)
    if other:
        reasons.add("other-code:" + ",".join(str(c) for c in sorted(other)))
    return ("judgment" if reasons else "trivial"), reasons


def main() -> None:
    maps = _maps_dir()
    map_files = sorted(maps.glob("Map*.json"))
    if not map_files:
        raise SystemExit(f"no Map*.json under {maps}")

    ctx = deterministic.load_context(
        reference_dir=_repo_root() / "reference",
        intermediate_dir=maps.parent / "intermediate",
    )

    total = claimed = 0
    trivial: list[tuple[int, int, str]] = []
    reason_counter: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()

    for mp in map_files:
        m = json.loads(mp.read_text(encoding="utf-8"))
        for event in m["events"]:
            if not _event_has_commands(event):
                continue
            total += 1
            if deterministic.try_deterministic(m["map_id"], event, ctx) is not None:
                claimed += 1
                continue
            verdict, reasons = classify_remaining(event)
            verdicts[verdict] += 1
            for r in reasons:
                reason_counter[r] += 1
            if verdict == "trivial":
                trivial.append((m["map_id"], event["id"], event.get("name", "")))

    remaining = total - claimed
    print(f"command-bearing map events:        {total}")
    print(f"claimed by deterministic filter:   {claimed}  ({100*claimed/total:.1f}%)")
    print(f"remaining (LLM-bound):             {remaining}")
    print()
    n_triv = verdicts["trivial"]
    print(f"trivial among remaining:           {n_triv}  "
          f"({100*n_triv/remaining:.1f}% of remaining, {100*n_triv/total:.1f}% of corpus)")
    print(f"judgment among remaining:          {verdicts['judgment']}")
    print()
    print("judgment reasons (events can hit several):")
    for reason, n in reason_counter.most_common(25):
        print(f"  {n:5}  {reason}")
    print()
    print(f"sample of trivial remainders (first 20 of {n_triv}):")
    for map_id, ev_id, name in trivial[:20]:
        print(f"  map {map_id:3} ev{ev_id:3}  {name!r}")


if __name__ == "__main__":
    main()
