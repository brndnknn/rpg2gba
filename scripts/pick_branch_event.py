"""Find the cleanest 2-page self-switch 'talk-once' NPC for the rung-3 (Step C) proof.

The canonical Uranium talk-once idiom:
  - Page 0 (base, no self-switch condition, trigger=action): shows text A, then
    Control Self Switch (123) 'A' ON.
  - Page 1 (condition: self-switch A is ON): shows text B.

system.md maps self-switch A -> FLAG_MAP{id}_EVENT{id}_SSA (setflag), one script
block per page; the page dispatcher (goto_if_set that flag) is hand-wired. That
exercises the full flag spine (mint -> header -> setflag -> check -> save).

We rank by total command count, prefer ASCII-clean dialogue (charmap-safe), no
warps (201), and script calls limited to STRIP-tagged cosmetics (pbCallBub).

Run: python scripts/pick_branch_event.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

MAPS = Path("output/uranium-build/maps")
TEXT_CODES = {101, 401}
SIG_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.]*)")


def is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def page_texts(page: dict) -> list[str]:
    out = []
    for cmd in page.get("list", []):
        if cmd.get("code") in TEXT_CODES:
            p = cmd.get("parameters", [])
            if p and isinstance(p[0], str):
                out.append(p[0])
    return out


def script_sigs(page: dict) -> set[str]:
    sigs = set()
    for cmd in page.get("list", []):
        if cmd.get("code") in (355, 655):
            p = cmd.get("parameters", [])
            if p and isinstance(p[0], str):
                m = SIG_RE.match(p[0])
                sigs.add(m.group(1) if m else "(non-id)")
    return sigs


def codes_of(page: dict) -> set[int]:
    return {c.get("code") for c in page.get("list", [])}


def sets_self_switch(page: dict) -> set[str]:
    """Self-switch letters this page turns ON via code 123 (param[1]==0)."""
    out = set()
    for cmd in page.get("list", []):
        if cmd.get("code") == 123:
            p = cmd.get("parameters", [])
            if len(p) >= 2 and p[1] == 0 and isinstance(p[0], str):
                out.add(p[0])
    return out


def analyze_event(ev: dict) -> dict | None:
    pages = ev.get("pages", [])
    if len(pages) < 2:
        return None

    base = pages[0]
    if base.get("condition", {}).get("self_switch_valid"):
        return None  # page 0 should be the unconditional base
    if base.get("trigger") != 0:  # RMXP trigger 0 == Action Button (talk)
        return None

    base_set = sets_self_switch(base)
    if not base_set:
        return None

    # find a later page gated on a self-switch the base sets
    gated = None
    for pg in pages[1:]:
        cond = pg.get("condition", {})
        if cond.get("self_switch_valid") and cond.get("self_switch_ch") in base_set:
            gated = pg
            break
    if gated is None:
        return None

    base_txt = page_texts(base)
    gated_txt = page_texts(gated)
    if not base_txt or not gated_txt:
        return None  # need different text on each page

    sigs = script_sigs(base) | script_sigs(gated)
    codes = codes_of(base) | codes_of(gated)
    n = len([c for pg in (base, gated) for c in
             (x.get("code") for x in pg.get("list", [])) if c != 0])
    ascii_clean = all(is_ascii(t) for t in base_txt + gated_txt)

    return {
        "n_commands": n,
        "ss": sorted(base_set),
        "codes": sorted(codes),
        "sigs": sorted(sigs),
        "ascii_clean": ascii_clean,
        "has_warp": 201 in codes,
        "base_text": base_txt[0][:70],
        "gated_text": gated_txt[0][:70],
    }


def main() -> None:
    rows = []
    for path in sorted(MAPS.glob("Map*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for ev in data.get("events", []):
            info = analyze_event(ev)
            if info is None:
                continue
            # only-cosmetic script calls
            clean_sigs = all(s in {"pbCallBub", "(non-id)"} for s in info["sigs"])
            rows.append((
                info["n_commands"],
                info["has_warp"],
                not info["ascii_clean"],
                not clean_sigs,
                path.name, ev.get("id"), ev.get("name", ""), info,
            ))

    rows.sort(key=lambda r: (r[1], r[3], r[2], r[0]))
    print(f"Found {len(rows)} two-page self-switch talk NPCs.\n")
    for n, warp, non_ascii, dirty, mapname, evid, evname, info in rows[:25]:
        print(f"{mapname} ev{evid} '{evname}' cmds={info['n_commands']} ss={info['ss']} "
              f"ascii={info['ascii_clean']} warp={info['has_warp']} sigs={info['sigs']}")
        print(f"    codes={info['codes']}")
        print(f"    A: {info['base_text']!r}")
        print(f"    B: {info['gated_text']!r}")


if __name__ == "__main__":
    main()
