"""Convert exactly ONE Uranium event through the real pipeline (rung-3 spike).

convert-map converts a whole map's events (Map031 has 48+), which would spend far
more budget than the authorized 1-3 tiny events. This trims Map031 to event 48
(the talk-once tutorial NPC) and runs orchestrator.convert_map on the trimmed map,
so the agent is spawned for just that one event. Same path as production:
registry mint -> claude backend -> poryscript compile gate -> flush.

Usage: python scripts/convert_one_event.py [model]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from rpg2gba import pipeline
from rpg2gba.conversion_agent import orchestrator as orch

MAP_ID = 31
EVENT_ID = 48
MODEL = sys.argv[1] if len(sys.argv) > 1 else "claude-opus-4-8"

pipeline._load_dotenv()
_, out_dir = pipeline._resolve_paths()
fork = os.environ.get("RPG2GBA_POKEEMERALD")
fork_path = Path(fork) if fork and Path(fork).is_dir() else None

src = json.loads((out_dir / "maps" / f"Map{MAP_ID:03d}.json").read_text(encoding="utf-8"))
event = next(e for e in src["events"] if e["id"] == EVENT_ID)
trimmed = {"map_id": src["map_id"], "events": [event]}
tmp = Path(f"/tmp/Map{MAP_ID:03d}.json")
tmp.write_text(json.dumps(trimmed), encoding="utf-8")

registry = pipeline._phase4_registry(out_dir, clean=False, fork_path=fork_path)
backend = pipeline._phase4_backend("claude_code", MODEL)
orchestrator = orch.Orchestrator(backend, registry, out_dir)

cp = out_dir / "checkpoints" / f"Map{MAP_ID:03d}.done"
if cp.exists():
    cp.unlink()

print(f"converting Map{MAP_ID:03d} event {EVENT_ID} via {MODEL} ...", flush=True)
orchestrator.convert_map(tmp)

pory = out_dir / "scripts" / f"Map{MAP_ID:03d}.pory"
print("\n===== Map031.pory =====")
print(pory.read_text(encoding="utf-8") if pory.is_file() else "(no .pory written)")
print("===== end =====\n")
print("flags now in registry:", json.dumps(registry.to_state()["switches"], indent=2))
