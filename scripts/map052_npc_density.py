#!/usr/bin/env python3
"""
Analyse Map052 (Bealbeach City Resort) NPC rendering density against the
pokeemerald OBJECT_EVENTS_COUNT=16 budget (15 NPCs + player).

Mechanical, spoiler-free analysis.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from itertools import product

MAP_PATH = Path("/home/b/repos/rpg2gba/output/uranium-build/maps/Map052.json")
SWITCHES_PATH = Path("/home/b/repos/rpg2gba/reference/uranium_switches.json")
VARIABLES_PATH = Path("/home/b/repos/rpg2gba/reference/uranium_variables.json")

WINDOW_W = 19
WINDOW_H = 16
BUDGET = 15  # slots available for NPCs (player takes 1 of 16)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

with MAP_PATH.open(encoding="utf-8") as f:
    mapdata = json.load(f)

# Load switch/variable name files just to verify IDs exist (not surfaced)
known_switches: set[int] = set()
known_variables: set[int] = set()

if SWITCHES_PATH.exists():
    with SWITCHES_PATH.open(encoding="utf-8") as f:
        sw_data = json.load(f)
    # Support dict keyed by int or str, or list
    if isinstance(sw_data, dict):
        known_switches = {int(k) for k in sw_data.keys()}
    elif isinstance(sw_data, list):
        known_switches = {int(item) if isinstance(item, (int, str)) else item.get("id", 0)
                          for item in sw_data}

if VARIABLES_PATH.exists():
    with VARIABLES_PATH.open(encoding="utf-8") as f:
        var_data = json.load(f)
    if isinstance(var_data, dict):
        known_variables = {int(k) for k in var_data.keys()}
    elif isinstance(var_data, list):
        known_variables = {int(item) if isinstance(item, (int, str)) else item.get("id", 0)
                           for item in var_data}

events = mapdata["events"]
print(f"Total events in Map052: {len(events)}")
print(f"Map size: {mapdata['width']}×{mapdata['height']}")
print()


# ---------------------------------------------------------------------------
# Helper: determine active page given a global state
# State: {switch_id: bool, ...}, {var_id: int, ...}, per-event self-switches
# ---------------------------------------------------------------------------

def active_page(pages: list, global_switches: dict[int, bool],
                global_vars: dict[int, int],
                self_switches: dict[str, bool]) -> dict | None:
    """Return the highest-indexed page whose conditions are all satisfied."""
    result = None
    for page in pages:
        cond = page["condition"]
        ok = True

        if cond.get("switch1_valid"):
            sid = cond["switch1_id"]
            if not global_switches.get(sid, False):
                ok = False

        if ok and cond.get("switch2_valid"):
            sid = cond["switch2_id"]
            if not global_switches.get(sid, False):
                ok = False

        if ok and cond.get("variable_valid"):
            vid = cond["variable_id"]
            vval = cond["variable_value"]
            if global_vars.get(vid, 0) < vval:
                ok = False

        if ok and cond.get("self_switch_valid"):
            ch = cond["self_switch_ch"]
            if not self_switches.get(ch, False):
                ok = False

        if ok:
            result = page  # keep going — we want the HIGHEST-indexed
    return result


def page_has_sprite(page: dict) -> bool:
    """Return True if this page renders a character sprite (not tile)."""
    g = page.get("graphic", {})
    return bool(g.get("character_name", ""))


def page_has_tile(page: dict) -> bool:
    g = page.get("graphic", {})
    return g.get("tile_id", 0) > 0


def event_has_command_list(event: dict) -> bool:
    """True if ANY page has a non-trivial command list (code != 0)."""
    for page in event["pages"]:
        lst = page.get("list", [])
        for cmd in lst:
            if cmd.get("code", 0) != 0:
                return True
    return False


# ---------------------------------------------------------------------------
# A. Classify events
# ---------------------------------------------------------------------------

# Collect all global switch IDs and variable IDs referenced
all_switch_ids: set[int] = set()
all_var_ids: set[int] = set()

for ev in events:
    for page in ev["pages"]:
        cond = page["condition"]
        if cond.get("switch1_valid"):
            all_switch_ids.add(cond["switch1_id"])
        if cond.get("switch2_valid"):
            all_switch_ids.add(cond["switch2_id"])
        if cond.get("variable_valid"):
            all_var_ids.add(cond["variable_id"])

print(f"Global switches referenced: {sorted(all_switch_ids)}")
print(f"Global variables referenced: {sorted(all_var_ids)}")
print()

# Verify IDs against reference files
if known_switches:
    unknown_sw = all_switch_ids - known_switches
    if unknown_sw:
        print(f"  WARNING: switch IDs not in uranium_switches.json: {sorted(unknown_sw)}")
if known_variables:
    unknown_var = all_var_ids - known_variables
    if unknown_var:
        print(f"  WARNING: variable IDs not in uranium_variables.json: {sorted(unknown_var)}")
print()


def classify_event(ev: dict) -> str:
    """
    NEVER-sprite    – no page ever has a character_name graphic
    TILE-graphic    – some page has tile_id>0, no character_name in any page
    ALWAYS-sprite   – every reachable active-page has a sprite; OR the only
                      conditions are self-switches (per semantics note 3)
    CONDITIONAL     – sprite presence depends on global switch/variable state
    """
    pages = ev["pages"]

    any_sprite = any(page_has_sprite(p) for p in pages)
    any_tile = any(page_has_tile(p) for p in pages)

    if not any_sprite and not any_tile:
        return "NEVER"
    if not any_sprite and any_tile:
        return "TILE"

    # Does any page depend on global switch or variable?
    global_gated = False
    for page in pages:
        cond = page["condition"]
        if cond.get("switch1_valid") or cond.get("switch2_valid") or cond.get("variable_valid"):
            global_gated = True
            break

    if not global_gated:
        # Only self-switch gating (or no gating) — per semantics §3, treat as ALWAYS
        return "ALWAYS"

    # At least one page is globally gated — check whether ALL outcomes still have a sprite
    # We'll do a rough check: if every page that has a graphic has one, and there's no
    # page with no graphic that could become active, it's ALWAYS; else CONDITIONAL.
    # More precisely: check if the no-condition (default first page) has a sprite.
    # If the *lowest* page (page[0]) has no sprite, there's a state where it's invisible.
    first_page_sprite = page_has_sprite(pages[0])

    if not first_page_sprite:
        # There exists a state (all globals off/0) where page[0] is active without sprite
        return "CONDITIONAL"

    # All pages have sprites — even if global state shifts, a sprite is shown
    all_pages_have_sprite = all(page_has_sprite(p) or page_has_tile(p) for p in pages)
    if all_pages_have_sprite:
        return "ALWAYS"

    return "CONDITIONAL"


classification: dict[int, str] = {}
for ev in events:
    classification[ev["id"]] = classify_event(ev)

cats = defaultdict(list)
for ev_id, cat in classification.items():
    cats[cat].append(ev_id)

print("=== A. Event Classification ===")
for cat in ["NEVER", "ALWAYS", "CONDITIONAL", "TILE"]:
    ids = cats.get(cat, [])
    print(f"  {cat:12s}: {len(ids):3d}  event IDs: {ids[:20]}{'...' if len(ids)>20 else ''}")
print()


# ---------------------------------------------------------------------------
# B. Gating structure for CONDITIONAL events
# ---------------------------------------------------------------------------

print("=== B. Gating Structure (CONDITIONAL events) ===")

# Which switches/variables affect each conditional event
switch_to_events: dict[int, list[int]] = defaultdict(list)
var_to_events: dict[int, list[int]] = defaultdict(list)

for ev in events:
    if classification[ev["id"]] != "CONDITIONAL":
        continue
    sw_seen: set[int] = set()
    var_seen: set[int] = set()
    for page in ev["pages"]:
        cond = page["condition"]
        if cond.get("switch1_valid"):
            sw_seen.add(cond["switch1_id"])
        if cond.get("switch2_valid"):
            sw_seen.add(cond["switch2_id"])
        if cond.get("variable_valid"):
            var_seen.add(cond["variable_id"])
    for sw in sw_seen:
        switch_to_events[sw].append(ev["id"])
    for v in var_seen:
        var_to_events[v].append(ev["id"])

print("  Switches gating multiple CONDITIONAL events (sorted by event count):")
for sw, evs in sorted(switch_to_events.items(), key=lambda x: -len(x[1])):
    print(f"    Switch {sw:4d}: {len(evs)} events -> {evs}")
if not switch_to_events:
    print("    (none)")
print()

print("  Variables gating CONDITIONAL events:")
for vid, evs in sorted(var_to_events.items(), key=lambda x: -len(x[1])):
    print(f"    Var {vid:4d}: {len(evs)} events -> {evs} (thresholds may vary)")
if not var_to_events:
    print("    (none)")
print()

# Collect distinct variable thresholds
var_thresholds: dict[int, set[int]] = defaultdict(set)
for ev in events:
    for page in ev["pages"]:
        cond = page["condition"]
        if cond.get("variable_valid"):
            vid = cond["variable_id"]
            vval = cond["variable_value"]
            var_thresholds[vid].add(vval)

for vid in sorted(var_thresholds):
    threshs = sorted(var_thresholds[vid])
    print(f"  Var {vid} distinct thresholds referenced: {threshs}")
print()


# ---------------------------------------------------------------------------
# C. Realistic simultaneous visible count
# ---------------------------------------------------------------------------

print("=== C. Realistic Simultaneous Visible Counts ===")

def count_visible_sprites(global_switches: dict[int, bool],
                          global_vars: dict[int, int]) -> list[dict]:
    """Return list of {id, x, y, has_commands} for visible sprite events."""
    visible = []
    for ev in events:
        pages = ev["pages"]
        # Use all-off self-switches for each event (spawn state)
        self_sw: dict[str, bool] = {}
        page = active_page(pages, global_switches, global_vars, self_sw)
        if page is None:
            continue
        if page_has_sprite(page):
            visible.append({
                "id": ev["id"],
                "x": ev["x"],
                "y": ev["y"],
                "has_commands": event_has_command_list(ev),
            })
    return visible


# Default state
default_sw = {sid: False for sid in all_switch_ids}
default_var = {vid: 0 for vid in all_var_ids}
default_visible = count_visible_sprites(default_sw, default_var)
print(f"  Default state (all OFF, all vars=0): {len(default_visible)} sprites visible")
print(f"  Positions: {[(e['x'],e['y']) for e in default_visible]}")
print()

# Identify the dominant variable (most events, widest threshold range)
dominant_var = None
if var_to_events:
    dominant_var = max(var_to_events.items(), key=lambda x: len(x[1]))[0]
    print(f"  Dominant variable: Var {dominant_var} ({len(var_to_events[dominant_var])} events gated)")

# Enumerate states to explore
states_to_try: list[tuple[dict, dict, str]] = []
states_to_try.append((default_sw, default_var, "default"))

# Sweep dominant variable across thresholds
if dominant_var is not None:
    threshs = sorted(var_thresholds[dominant_var])
    # Check just below first, at each threshold, and above last
    check_vals = [0] + threshs + [threshs[-1] + 1]
    check_vals = sorted(set(check_vals))
    for val in check_vals:
        sw = {sid: False for sid in all_switch_ids}
        vr = {vid: 0 for vid in all_var_ids}
        vr[dominant_var] = val
        states_to_try.append((sw, vr, f"Var{dominant_var}={val}"))
    # Also try with all switches ON at each threshold
    for val in check_vals:
        sw = {sid: True for sid in all_switch_ids}
        vr = {vid: 0 for vid in all_var_ids}
        vr[dominant_var] = val
        states_to_try.append((sw, vr, f"ALL_SW_ON+Var{dominant_var}={val}"))

# All switches ON / all switches OFF × var=0/max
for sw_all in [False, True]:
    sw = {sid: sw_all for sid in all_switch_ids}
    vr = {vid: 0 for vid in all_var_ids}
    tag = f"ALL_SW={'ON' if sw_all else 'OFF'},vars=0"
    states_to_try.append((sw, vr, tag))

# For each switch alone
for sid in sorted(all_switch_ids):
    sw = {s: (s == sid) for s in all_switch_ids}
    vr = {vid: 0 for vid in all_var_ids}
    states_to_try.append((sw, vr, f"SW{sid}_only_ON"))

results: list[tuple[str, int, list[dict]]] = []
for sw, vr, tag in states_to_try:
    vis = count_visible_sprites(sw, vr)
    results.append((tag, len(vis), vis))

results.sort(key=lambda x: -x[1])
max_count = results[0][1]
min_count = min(r[1] for r in results)

print(f"  MAX visible sprites across all tested states: {max_count}")
print(f"  MIN visible sprites across all tested states: {min_count}")
print()
print("  Top-5 states by sprite count:")
for tag, cnt, vis in results[:5]:
    print(f"    {cnt:3d} sprites — {tag}")
print()
print("  Bottom-3 states by sprite count:")
for tag, cnt, vis in results[-3:]:
    print(f"    {cnt:3d} sprites — {tag}")
print()


# ---------------------------------------------------------------------------
# D. Spatial: densest 19×16 window in the MAX-visible state
# ---------------------------------------------------------------------------

print("=== D. Spatial: Densest 19×16 Window ===")

max_tag, max_cnt, max_vis = results[0]
print(f"  Using state: {max_tag} ({max_cnt} sprites)")

# Get all (x,y) of visible sprites
sprite_positions = [(e["x"], e["y"]) for e in max_vis]

if sprite_positions:
    xs = [p[0] for p in sprite_positions]
    ys = [p[1] for p in sprite_positions]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    best_count = 0
    best_window = (0, 0)
    best_events_in_window: list[dict] = []

    # Slide window: camera at (cx, cy), window covers [cx-2..cx+16] × [cy..cy+15]
    # Equivalently: events with x in [cx-2, cx+16] and y in [cy, cy+15]
    # Slide cx and cy over meaningful ranges
    for cx in range(x_min - 2, x_max + 1):
        wx0, wx1 = cx - 2, cx + 16
        for cy in range(y_min, y_max + 1):
            wy0, wy1 = cy, cy + 15
            in_window = [e for e in max_vis if wx0 <= e["x"] <= wx1 and wy0 <= e["y"] <= wy1]
            if len(in_window) > best_count:
                best_count = len(in_window)
                best_window = (cx, cy)
                best_events_in_window = in_window

    print(f"  Densest window: {best_count} sprites")
    print(f"  Window position (camera x,y): {best_window}  "
          f"covers tiles x=[{best_window[0]-2}..{best_window[0]+16}] "
          f"y=[{best_window[1]}..{best_window[1]+15}]")
    print(f"  Events in window:")
    for e in sorted(best_events_in_window, key=lambda x: (x["y"], x["x"])):
        cmds = "interactable" if e["has_commands"] else "cosmetic"
        print(f"    EV{e['id']:03d} ({e['x']:2d},{e['y']:2d}) [{cmds}]")
    interactable_in_window = sum(1 for e in best_events_in_window if e["has_commands"])
    cosmetic_in_window = sum(1 for e in best_events_in_window if not e["has_commands"])
    print(f"  In-window breakdown: {interactable_in_window} interactable, "
          f"{cosmetic_in_window} cosmetic")
    excess = best_count - BUDGET
    print(f"  Budget: {BUDGET}. Excess: {excess} ({'OVER' if excess > 0 else 'UNDER'} budget)")
print()


# ---------------------------------------------------------------------------
# E. Co-located events
# ---------------------------------------------------------------------------

print("=== E. Co-located Events ===")
pos_to_events: dict[tuple, list[int]] = defaultdict(list)
for ev in events:
    pos_to_events[(ev["x"], ev["y"])].append(ev["id"])

colocated = {pos: ids for pos, ids in pos_to_events.items() if len(ids) > 1}
if colocated:
    print(f"  {len(colocated)} positions have multiple events:")
    for pos, ids in sorted(colocated.items()):
        print(f"    ({pos[0]:2d},{pos[1]:2d}): {ids}")
else:
    print("  No co-located events found.")
print()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("=== SUMMARY ===")
print(f"  Total events:        {len(events)}")
print(f"  NEVER-sprite:        {len(cats.get('NEVER', []))}")
print(f"  ALWAYS-sprite:       {len(cats.get('ALWAYS', []))}")
print(f"  CONDITIONAL-sprite:  {len(cats.get('CONDITIONAL', []))}")
print(f"  TILE-graphic:        {len(cats.get('TILE', []))}")
print()
print(f"  Default-state visible sprites:  {len(default_visible)}")
print(f"  Max across all tested states:   {max_count}")
print(f"  Min across all tested states:   {min_count}")
print(f"  Densest 19×16 window (max state): {best_count}")
print(f"  Excess over 15-NPC budget:       {best_count - BUDGET}")
print()

# Classify in-window events for final verdict
if best_events_in_window:
    print(f"  In-window interactable: {interactable_in_window}")
    print(f"  In-window cosmetic:     {cosmetic_in_window}")
