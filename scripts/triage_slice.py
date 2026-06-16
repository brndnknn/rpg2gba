"""Ad-hoc: summarize unhandled.jsonl entries for the pathfinder slice (49/48/32).

Read-only. Filters the shared queue for the slice maps, groups by map and by
reason, and prints command-code detail so we can triage what the S6 run flagged.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

SLICE = {32, 48, 49}
QUEUE = Path("output/uranium-build/unhandled.jsonl")


def main() -> None:
    rows: list[dict] = []
    for line in QUEUE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        if e.get("map_id") in SLICE:
            rows.append(e)

    print(f"=== slice queue: {len(rows)} entries across maps {sorted(SLICE)} ===\n")

    by_map: dict[int, list[dict]] = defaultdict(list)
    for e in rows:
        by_map[e["map_id"]].append(e)

    for m in sorted(by_map):
        entries = by_map[m]
        print(f"--- Map{m:03d}: {len(entries)} entries ---")
        reasons = Counter(e.get("reason", "?") for e in entries)
        for r, n in reasons.most_common():
            print(f"    reason: {r}  x{n}")
        codes = Counter(e.get("command_code") for e in entries if e.get("command_code") is not None)
        if codes:
            print("    command codes:", dict(codes.most_common()))
        # distinct events touched
        evs = sorted({(e.get("event_id"), e.get("event_name")) for e in entries})
        print(f"    distinct events: {len(evs)}")
        print()

    print("=== per-entry detail ===\n")
    for m in sorted(by_map):
        for e in by_map[m]:
            eid = e.get("event_id")
            name = e.get("event_name")
            reason = e.get("reason")
            code = e.get("command_code")
            page = e.get("page")
            desc = e.get("description")
            print(f"Map{m:03d} ev{eid} ({name!r}) | {reason}"
                  + (f" | code={code}" if code is not None else "")
                  + (f" page={page}" if page is not None else ""))
            if desc:
                print(f"        desc: {desc}")


if __name__ == "__main__":
    main()
