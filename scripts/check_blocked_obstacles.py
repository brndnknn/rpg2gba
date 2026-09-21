"""ONE-OFF (C7 Task 3, R5): cross-check `blocked_obstacle` floor assertions
against the `blocked:<cap>` dispositions in reference/manifests/CHnn.dispositions.json.

For CH01-CH05: every row dispositioned `blocked:<cap>` is reported as MATCH
(its floor carries a `blocked_obstacle` with that capability) or NONE (no
assertion -- expected only for rows behind an obstacle, or a rock's erased
follow-up page). Also lists floor obstacles with no `blocked:` disposition.
Needs output/uranium-build/ populated; fails loud if not.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rpg2gba.beat_floor.walk import floor_for_chapter

BUILD_DIR = Path("output/uranium-build")
CHAPTERS = ["CH01", "CH02", "CH03", "CH04", "CH05"]


def main() -> int:
    if not (BUILD_DIR / "maps").is_dir():
        print(f"ERROR: {BUILD_DIR}/maps missing or empty; build first", file=sys.stderr)
        return 2
    rc = 0
    for ch in CHAPTERS:
        floors = floor_for_chapter(ch, build_dir=BUILD_DIR)
        disp = json.loads(Path(f"reference/manifests/{ch}.dispositions.json").read_text(encoding="utf-8"))
        obstacles = {
            rid: dict(a.params)
            for rid, f in floors.items() for a in f.assertions if a.kind == "blocked_obstacle"
        }
        blocked = {rid: d["disposition"].split(":", 1)[1]
                   for rid, d in disp.items() if d["disposition"].startswith("blocked:")}
        matched = [r for r, cap in blocked.items() if obstacles.get(r, {}).get("capability") == cap]
        mismatch = [r for r, cap in blocked.items()
                    if r in obstacles and obstacles[r]["capability"] != cap]
        missing = [r for r in blocked if r not in obstacles]
        extra = [r for r in obstacles if r not in blocked]
        print(f"{ch}: blocked rows={len(blocked)} match={len(matched)} "
              f"cap-mismatch={len(mismatch)} no-assertion={len(missing)} "
              f"floor-obstacles-not-blocked={len(extra)}")
        for r in mismatch:
            rc = 1
            print(f"  MISMATCH {r}: disp={blocked[r]} floor={obstacles[r]}")
        for r in missing:
            print(f"  NONE     {r}: blocked:{blocked[r]}")
        for r in extra:
            print(f"  EXTRA    {r}: {obstacles[r]}")
        for r in ("map032/ev014/p0",):
            if r in obstacles:
                print(f"  anchor {r}: {obstacles[r]}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
