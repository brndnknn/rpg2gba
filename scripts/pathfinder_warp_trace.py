#!/usr/bin/env python3
"""S1 (pathfinder) — trace every warp in the slice maps 49/48/32.

Read-only analysis. Walks each Phase-3 MapNNN.json events->pages->list and reports
every map transfer:
  - code 201 (Transfer Player): params = [method, map_id, x, y, direction, fade]
    (method 1 = variable designation -> map/x/y are VARIABLE ids, not literals)
  - code 355/655 (Script) lines naming pbTransferPlayer / pbCaveEntrance / pbCaveExit

Output is the input to PATHFINDER_FINDINGS.md (keep / wall / stub decisions).
Run:  PYTHONPATH=src python3 scripts/pathfinder_warp_trace.py
"""
from __future__ import annotations

import json
from pathlib import Path

MAPS_DIR = Path("output/uranium-build/maps")
SLICE = [49, 48, 32]
DIRS = {0: "retain", 2: "down", 4: "left", 6: "right", 8: "up"}
SCRIPT_CODES = {355, 655}
WARP_TOKENS = ("pbTransferPlayer", "TransferPlayer", "pbCaveEntrance", "pbCaveExit")


def _script_text(params: list) -> str:
    return " ".join(str(p) for p in params if isinstance(p, str))


def trace_map(map_id: int) -> dict:
    data = json.loads((MAPS_DIR / f"Map{map_id:03d}.json").read_text(encoding="utf-8"))
    name = data.get("map_id"), data.get("tileset_id")
    warps: list[dict] = []
    scripts: list[dict] = []
    for ev in data.get("events", []):
        ev_name = ev.get("name", "?")
        ev_xy = (ev.get("x"), ev.get("y"))
        for pi, page in enumerate(ev.get("pages", [])):
            for cmd in page.get("list", []):
                code = cmd.get("code")
                params = cmd.get("parameters", [])
                if code == 201:
                    method = params[0] if params else None
                    warps.append({
                        "event": ev_name, "event_xy": ev_xy, "page": pi,
                        "method": method,
                        "target_map": params[1] if len(params) > 1 else None,
                        "dest_xy": (params[2], params[3]) if len(params) > 3 else None,
                        "dir": DIRS.get(params[4], params[4]) if len(params) > 4 else None,
                        "by_variable": method == 1,
                    })
                elif code in SCRIPT_CODES:
                    txt = _script_text(params)
                    if any(tok in txt for tok in WARP_TOKENS):
                        scripts.append({"event": ev_name, "event_xy": ev_xy,
                                        "page": pi, "code": code, "text": txt.strip()})
    return {"tileset_id": data.get("tileset_id"), "width": data.get("width"),
            "height": data.get("height"), "n_events": len(data.get("events", [])),
            "warps": warps, "scripts": scripts}


def main() -> None:
    all_targets: set[int] = set()
    for mid in SLICE:
        r = trace_map(mid)
        print(f"\n=== Map{mid:03d}  tileset={r['tileset_id']}  "
              f"{r['width']}x{r['height']}  events={r['n_events']} ===")
        if not r["warps"]:
            print("  (no code-201 warps)")
        for w in r["warps"]:
            tgt = w["target_map"]
            if not w["by_variable"] and isinstance(tgt, int):
                all_targets.add(tgt)
            tgt_s = f"VAR#{tgt}" if w["by_variable"] else f"Map{tgt:03d}" if isinstance(tgt, int) else str(tgt)
            print(f"  201  ev='{w['event']}'@{w['event_xy']} p{w['page']}  "
                  f"-> {tgt_s} @ {w['dest_xy']} dir={w['dir']}"
                  + ("  [VARIABLE-DESIGNATED]" if w["by_variable"] else ""))
        for s in r["scripts"]:
            print(f"  {s['code']}  ev='{s['event']}'@{s['event_xy']} p{s['page']}  {s['text']}")

    print("\n=== distinct literal target maps referenced by the slice ===")
    for t in sorted(all_targets):
        in_slice = " (IN SLICE)" if t in SLICE else ""
        print(f"  Map{t:03d}{in_slice}")


if __name__ == "__main__":
    main()
