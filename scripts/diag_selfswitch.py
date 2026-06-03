"""Diagnostic: how do Uranium events actually express the talk-once idiom?"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

MAPS = Path("output/uranium-build/maps")

multi = 0
has_ss_cond = 0
base_trigger = Counter()
set_via_123 = 0
set_via_script = 0
gated_has_text = 0
total_events = 0

for path in sorted(MAPS.glob("Map*.json")):
    data = json.loads(path.read_text(encoding="utf-8"))
    for ev in data.get("events", []):
        total_events += 1
        pages = ev.get("pages", [])
        if len(pages) < 2:
            continue
        multi += 1
        # any page gated on a self switch?
        gated = [p for p in pages if p.get("condition", {}).get("self_switch_valid")]
        if gated:
            has_ss_cond += 1
            base_trigger[pages[0].get("trigger")] += 1
            # does ANY page set a self switch via 123?
            for p in pages:
                for c in p.get("list", []):
                    if c.get("code") == 123:
                        set_via_123 += 1
                        break
                else:
                    continue
                break
            # via pbSetSelfSwitch script call?
            found_script = False
            for p in pages:
                for c in p.get("list", []):
                    if c.get("code") in (355, 655):
                        pr = c.get("parameters", [])
                        if pr and isinstance(pr[0], str) and "etSelfSwitch" in pr[0]:
                            found_script = True
            if found_script:
                set_via_script += 1
            # gated page has text?
            for g in gated:
                if any(c.get("code") in (101, 401) for c in g.get("list", [])):
                    gated_has_text += 1
                    break

print(f"total events:                 {total_events}")
print(f"multi-page events (>=2):      {multi}")
print(f"  with a self-switch-gated page: {has_ss_cond}")
print(f"    base(page0) trigger dist:    {dict(base_trigger)}")
print(f"    set self-switch via 123:     {set_via_123}")
print(f"    set self-switch via script:  {set_via_script}")
print(f"    gated page has text:         {gated_has_text}")
