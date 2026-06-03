"""Dump one event's full JSON. Usage: python scripts/dump_event.py MAP_ID EVENT_ID"""
from __future__ import annotations

import json
import sys
from pathlib import Path

map_id, ev_id = int(sys.argv[1]), int(sys.argv[2])
path = Path(f"output/uranium-build/maps/Map{map_id:03d}.json")
data = json.loads(path.read_text(encoding="utf-8"))
for ev in data["events"]:
    if ev["id"] == ev_id:
        print(json.dumps(ev, indent=2, ensure_ascii=False))
        break
else:
    print(f"event {ev_id} not found in {path.name}")
