"""Rank Phase 3 map JSONs by conversion size for the Part C smoke-test pick.

Size = total event-page command count (the real work the agent does), with
event count and page count as tie-breakers. Prints the smallest non-empty maps.
"""

from __future__ import annotations

import json
from pathlib import Path

MAPS = Path("output/uranium-build/maps")


def map_cost(path: Path) -> tuple[int, int, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data.get("events", [])
    pages = 0
    commands = 0
    for ev in events:
        ev_pages = ev.get("pages", [])
        pages += len(ev_pages)
        for pg in ev_pages:
            commands += len(pg.get("list", []))
    return commands, len(events), pages


def main() -> None:
    rows = []
    for path in sorted(MAPS.glob("Map*.json")):
        commands, n_events, n_pages = map_cost(path)
        rows.append((commands, n_events, n_pages, path.name))

    rows.sort()
    print(f"{'map':<14}{'commands':>10}{'events':>8}{'pages':>7}")
    nonempty = [r for r in rows if r[1] > 0]
    for commands, n_events, n_pages, name in nonempty[:12]:
        print(f"{name:<14}{commands:>10}{n_events:>8}{n_pages:>7}")
    empty = [r for r in rows if r[1] == 0]
    print(f"\n({len(empty)} maps have zero events; {len(nonempty)} have at least one.)")


if __name__ == "__main__":
    main()
