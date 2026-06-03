"""Summarize a map's events (count = conversion spawns, plus what each does).

Usage: python scripts/summarize_map.py MAP_ID
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

mid = int(sys.argv[1])
data = json.loads(
    Path(f"output/uranium-build/maps/Map{mid:03d}.json").read_text(encoding="utf-8")
)
events = data.get("events", [])
print(f"Map{mid:03d}: {len(events)} events\n")
for ev in events:
    pages = ev.get("pages", [])
    cmds = sum(len(p.get("list", [])) for p in pages)
    codes = sorted({c.get("code") for p in pages for c in p.get("list", [])})
    sigs: set[str] = set()
    for p in pages:
        for c in p.get("list", []):
            if c.get("code") in (355, 655):
                par = c.get("parameters", [])
                if par and isinstance(par[0], str):
                    sigs.add(par[0].split("(")[0].strip()[:32])
    print(f"  ev{ev.get('id')} '{ev.get('name')}' pages={len(pages)} cmds={cmds}")
    print(f"      codes={codes}")
    if sigs:
        print(f"      script-calls: {sorted(sigs)}")
