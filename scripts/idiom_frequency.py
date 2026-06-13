"""Corpus idiom-frequency analyzer (zero LLM).

Scans the deserialized map corpus and reports, for every event Opus would
currently handle (i.e. the deterministic pre-filter does NOT claim it), what
command-idiom is blocking it and how often that idiom recurs. The point is to
rank what to make deterministic next — a new classifier, a STRIP entry, or a
Phase-6 engine feature — so Opus is spent only on the irreducible long tail.

Pure static analysis: reads output/uranium-build/maps/*.json and the same
deterministic.try_deterministic the real run uses. No network, no Opus, seconds.

Run:  PYTHONPATH=src python3 scripts/idiom_frequency.py [MAPS_DIR]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from rpg2gba.conversion_agent import deterministic as det
from rpg2gba.conversion_agent.lane import in_lane, real_commands

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MAPS = REPO / "output" / "uranium-build" / "maps"
CMD_TABLE = REPO / "reference" / "rgss_event_commands.md"

SCRIPT_CODES = {355, 655}
# Continuation codes folded into the run they continue (not their own idiom token).
CONTINUATION = {401, 408, 655}

# RMXP 201 transfer param decode: [mode, map_id, x, y, dir, fade].
TRANSFER = 201


def load_code_meta() -> dict[int, tuple[str, str]]:
    """Parse the reference table → {code: (name, disposition)}.

    Disposition column is one of Direct / Adaptable / Strip / NeedsC — a ready
    hint for whether a blocking code is cheap (Direct/Strip) or needs C (NeedsC).
    """
    meta: dict[int, tuple[str, str]] = {}
    row = re.compile(r"^\|\s*(\d{2,3})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")
    for line in CMD_TABLE.read_text(encoding="utf-8").splitlines():
        m = row.match(line)
        if m:
            meta[int(m.group(1))] = (m.group(2).strip(), m.group(3).strip())
    return meta


_HEAD_RE = re.compile(
    r"^\s*(?:Kernel\.|\$[A-Za-z_][A-Za-z0-9_]*\.)?([A-Za-z_][A-Za-z0-9_]*)"
)


def script_head(call: str) -> str:
    """Leading identifier of a 355/655 Script string (``pbCaveExit(...)`` → ``pbCaveExit``)."""
    m = _HEAD_RE.match(call or "")
    return m.group(1) if m else "<expr>"


def already_strip(head: str) -> bool:
    """True if this script-call head is already STRIP-listed in deterministic.py."""
    return bool(det._DIALOGUE_STRIP_RE.match(head))


def event_tokens(event: dict, meta: dict[int, tuple[str, str]]) -> list[str]:
    """Distinct idiom tokens for an event: code names, script-calls by head.

    Continuation codes are folded out; a Script run is one token named for its
    call head so ``pbCaveExit`` and ``setTempSwitchOn`` don't collapse together.
    """
    toks: list[str] = []
    warps = 0
    for c in real_commands(event):
        code = c.get("code", 0)
        if code in CONTINUATION:
            continue
        if code in SCRIPT_CODES:
            p = c.get("parameters") or [""]
            toks.append(f"script:{script_head(p[0] if p else '')}")
            continue
        if code == TRANSFER:
            warps += 1
            continue
        name = meta.get(code, (f"code{code}", "?"))[0]
        toks.append(f"{code} {name}")
    if warps == 1:
        toks.append("201 Transfer")
    elif warps >= 2:
        toks.append(f"201 Transfer x{warps}")
    # distinct, stable order
    seen: dict[str, None] = {}
    for t in toks:
        seen.setdefault(t, None)
    return list(seen)


def main() -> None:
    maps_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MAPS
    meta = load_code_meta()
    ctx = det.load_context(
        reference_dir=REPO / "reference",
        intermediate_dir=maps_dir.parent / "intermediate",
    )

    total = free = opus = 0
    lane_count = 0
    sig_counter: Counter[tuple[str, ...]] = Counter()
    sig_example: dict[tuple[str, ...], str] = {}
    call_events: Counter[str] = Counter()  # events (Opus-bound) containing each call
    block_code_events: Counter[str] = Counter()  # Opus-bound events blocked by each code

    import json

    for mp in sorted(maps_dir.glob("Map*.json")):
        d = json.loads(mp.read_text(encoding="utf-8"))
        mid = d.get("map_id")
        for ev in d.get("events", []):
            if not real_commands(ev):
                continue
            total += 1
            if det.try_deterministic(mid, ev, ctx) is not None:
                free += 1
                continue
            opus += 1
            if in_lane(ev):
                lane_count += 1
            toks = event_tokens(ev, meta)
            sig = tuple(sorted(toks))
            sig_counter[sig] += 1
            sig_example.setdefault(sig, f"Map{mid:03d} {ev.get('name')}")
            for t in toks:
                if t.startswith("script:"):
                    call_events[t[len("script:"):]] += 1
                else:
                    block_code_events[t] += 1

    print(f"corpus: {total} non-empty events")
    print(f"  deterministic now (free): {free}  ({free*100//max(total,1)}%)")
    print(f"  fall to Opus:             {opus}  ({opus*100//max(total,1)}%)")
    print(f"    of those, in human lane: {lane_count}")

    print("\n== top Opus-bound idiom signatures (distinct command sets) ==")
    for sig, n in sig_counter.most_common(25):
        print(f"{n:4}  {sig_example[sig]:22}  {{{', '.join(sig)}}}")

    print("\n== script-calls in Opus-bound events (by #events; * = already STRIP) ==")
    for head, n in call_events.most_common(30):
        flag = " *" if already_strip(head) else ""
        print(f"{n:4}  {head}{flag}")

    print("\n== command codes blocking Opus-bound events (by #events; disposition) ==")
    for tok, n in block_code_events.most_common(25):
        code = int(tok.split()[0].split("x")[0]) if tok[0].isdigit() else None
        disp = meta.get(code, ("", "?"))[1] if code in meta else "?"
        print(f"{n:4}  {tok:28}  {disp}")


if __name__ == "__main__":
    main()
