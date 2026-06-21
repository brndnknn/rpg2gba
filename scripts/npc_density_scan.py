"""How close does Uranium get to pokeemerald's overworld sprite limits?

Limits (verified in the fork):
  OBJECT_EVENTS_COUNT      = 16  (incl. player -> 15 NPCs spawnable at once)
  OBJECT_EVENT_TEMPLATES   = 64  (max events defined per map)
  spawn window             = 19 x 16 tiles (pos.x-2..+17, pos.y..+16)

For each map we count events that render a sprite (graphic.character_name set),
then find the densest 19x16 window (worst case the player can trigger).
"""
from __future__ import annotations

import json
from pathlib import Path

BUILD = Path("/home/b/repos/rpg2gba/output/uranium-build")
WIN_W, WIN_H = 19, 16
NPC_BUDGET = 15  # OBJECT_EVENTS_COUNT - player
TEMPLATE_CAP = 64


def npc_positions(map_json: dict) -> list[tuple[int, int]]:
    pts = []
    for e in map_json.get("events", []):
        # an event is a visible sprite if ANY page has a character graphic
        if any(p.get("graphic", {}).get("character_name") for p in e.get("pages", [])):
            pts.append((e["x"], e["y"]))
    return pts


def max_in_window(pts: list[tuple[int, int]]) -> int:
    if not pts:
        return 0
    xs = sorted({x for x, _ in pts})
    ys = sorted({y for _, y in pts})
    best = 0
    for lx in xs:
        for ty in ys:
            c = sum(1 for x, y in pts if lx <= x < lx + WIN_W and ty <= y < ty + WIN_H)
            best = max(best, c)
    return best


def main():
    names = json.load(open(BUILD / "map_infos.json"))
    rows = []
    for f in sorted((BUILD / "maps").glob("Map*.json")):
        d = json.load(open(f))
        mid = d["map_id"]
        pts = npc_positions(d)
        total_events = len(d.get("events", []))
        rows.append((mid, names.get(str(mid), {}).get("name", "?"),
                     total_events, len(pts), max_in_window(pts)))

    over_spawn = [r for r in rows if r[4] > NPC_BUDGET]
    over_tmpl = [r for r in rows if r[3] > TEMPLATE_CAP]  # npc_events vs 64 object-template cap

    print(f"maps scanned: {len(rows)}")
    print(f"max NPCs in any 19x16 window — distribution:")
    import collections
    dist = collections.Counter(r[4] for r in rows)
    for k in sorted(dist):
        bar = "#" * dist[k]
        flag = "  <-- OVER 15" if k > NPC_BUDGET else ""
        print(f"  {k:2d} NPCs: {dist[k]:3d} maps {bar}{flag}")

    print(f"\nmaps that exceed the 15-NPC spawn budget: {len(over_spawn)}")
    for mid, nm, tot, npc, mx in sorted(over_spawn, key=lambda r: -r[4]):
        print(f"  map {mid:3d} {nm[:34]:34s} densest={mx:2d}  (npc_events={npc}, total_events={tot})")

    print(f"\nmaps that exceed the 64 object-template cap (npc_events>64): {len(over_tmpl)}")
    for mid, nm, tot, npc, mx in sorted(over_tmpl, key=lambda r: -r[3]):
        print(f"  map {mid:3d} {nm[:34]:34s} npc_events={npc}  (total_events={tot})")

    print("\ntop 8 densest maps overall:")
    for mid, nm, tot, npc, mx in sorted(rows, key=lambda r: -r[4])[:8]:
        print(f"  map {mid:3d} {nm[:34]:34s} densest={mx:2d}  npc_events={npc}  total_events={tot}")


if __name__ == "__main__":
    main()
