"""rpg2gba conversion tutor — a hands-on walkthrough, vimtutor-style.

Walks you through a few REAL events that have already been translated, easiest
first. For each: you read the source event, type your own Poryscript attempt (or
just press Enter to skip ahead), then see the reference translation the pipeline
actually produced, with notes on every rule applied. No usage is spent and nothing
is written — it's pure practice for `scripts/run_human.py`.

    python scripts/run_tutor.py

Press Enter at any "type your attempt" prompt to reveal the answer without typing.
Ctrl-D / Ctrl-C exits.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from rpg2gba import pipeline
from rpg2gba.conversion_agent.backends.human import _render_event, _wrap

_BLOCK_RE = re.compile(r"^(script|mart|movement|text|raw)\s+(\S+)")


# Each lesson points at one already-translated event. `answer_prefix` selects which
# emitted block(s) are the reference answer (a page label, or the whole-event prefix).
LESSONS = [
    {
        "title": "1. A sign / plain line of text",
        "map": 7, "event": 4, "answer_prefix": "Map007_EV004_",
        "teach": (
            "The simplest event: show one line of text. One `101 text` command -> one "
            "`msgbox`, wrapped in the skeleton `lock` / `msgbox(...)` / `release` / "
            "`end`. (`faceplayer` is only for NPCs you turn toward — a sign doesn't "
            "need it.) Watch for Uranium text codes like `\\sign[..]`, `\\c[..]`, "
            "`\\wt[..]` — strip them, they have no GBA equivalent."
        ),
        "notes": (
            "• `101 text` -> `msgbox(\"...\")`.\n"
            "• The `\\sign[sign1]` control code was stripped.\n"
            "• No `faceplayer` — it's a sign, not a turn-to NPC.\n"
            "• `lock`/`release`/`end` are the idiom, not source commands.\n"
            "• Label `Map{map}_EV{event}_Page1` — the run_human UI hands you this "
            "prefix; you never compute it."
        ),
    },
    {
        "title": "2. A receptionist (calls a common event)",
        "map": 2, "event": 9, "answer_prefix": "Map002_EV009_",
        "teach": (
            "Some NPCs run shared logic stored in a Common Event. In the source that's "
            "command 117 (Call Common Event N). You don't re-translate the shared logic "
            "— you call it by label: `call CommonEvent_<NNN>` (id zero-padded to 3)."
        ),
        "notes": (
            "• `117 call common event: [5]` -> `call CommonEvent_005`.\n"
            "• Do NOT queue it as unhandled — the common event is translated "
            "separately under that label.\n"
            "• Wrapped in the usual lock/faceplayer/release skeleton."
        ),
    },
    {
        "title": "3. A ground item + self-switch (2 pages)",
        "map": 7, "event": 6, "answer_prefix": "Map007_EV006_",
        "teach": (
            "A Poké Ball lying on the ground. Two patterns here:\n"
            "1) `pbItemBall(ITEM)` is Uranium's give-a-ground-item idiom -> "
            "`giveitem(ITEM, 1)`. The `if` wrapper around it just disappears.\n"
            "2) Code 123 sets self-switch A -> `setflag(<the SSA flag the UI shows "
            "you>)`, so the ball is gone next time. Page 2 is gated on that switch and "
            "is EMPTY (already taken) -> it translates to just `end`."
        ),
        "notes": (
            "• `giveitem(ITEM_HP_UP, 1)` is the pickup (`pbItemBall` idiom).\n"
            "• `setflag(FLAG_MAP007_EVENT006_SSA)` hides the ball — that self-switch "
            "name is handed to you by run_human; you never invent it.\n"
            "• Page 2 = the empty 'already taken' state -> `end`.\n"
            "• Heads-up: ground items this tidy are usually auto-converted by the "
            "pipeline, so your real run_human queue will be slightly chewier versions "
            "of these same patterns."
        ),
    },
]


def _extract_blocks(pory_text: str, prefix: str) -> str:
    """Pull the emitted block(s) whose label starts with `prefix` from a .pory file.

    Poryscript top-level blocks (`script`/`mart`/`movement`/…) close with a `}` alone
    on a line, so we capture from the opening keyword line to that brace."""
    out: list[str] = []
    cur: list[str] | None = None
    for line in pory_text.split("\n"):
        if cur is None:
            m = _BLOCK_RE.match(line)
            if m and m.group(2).startswith(prefix):
                cur = [line]
        else:
            cur.append(line)
            if line.strip() == "}":
                out.append("\n".join(cur))
                cur = None
    return "\n\n".join(out)


def _load_source(maps_dir: Path, map_id: int, event_id: int) -> dict | None:
    path = maps_dir / f"Map{map_id:03d}.json"
    if not path.is_file():
        return None
    m = json.loads(path.read_text(encoding="utf-8"))
    for ev in m["events"]:
        if ev["id"] == event_id:
            return {"map_id": map_id, **ev}
    return None


def _read_attempt() -> str | None:
    """Read the operator's attempt (ended by a line `EOF`), or None if they just
    pressed Enter to reveal the answer."""
    first = True
    lines: list[str] = []
    while True:
        line = input()
        if first and line.strip() == "":
            return None
        first = False
        if line.strip() == "EOF":
            break
        lines.append(line)
    return "\n".join(lines)


def main() -> int:
    pipeline._load_dotenv()
    _, out_dir = pipeline._resolve_paths()
    out_dir = Path(out_dir)
    maps_dir = out_dir / "maps"
    scripts_dir = out_dir / "scripts"
    if not maps_dir.is_dir() or not scripts_dir.is_dir():
        print("Need converted output (maps/ + scripts/). Run phase3 + a bulk round first.")
        return 2

    print(_wrap(
        "Welcome to the rpg2gba conversion tutor. We'll walk through "
        f"{len(LESSONS)} real, already-translated events. For each one: read the "
        "source, optionally type your own version (end with a line `EOF`), then see "
        "the answer with notes. Press Enter to skip typing. Ctrl-C to quit.\n"
    ))
    input("Press Enter to begin… ")

    try:
        for lesson in LESSONS:
            source = _load_source(maps_dir, lesson["map"], lesson["event"])
            answer = _extract_blocks(
                (scripts_dir / f"Map{lesson['map']:03d}.pory").read_text(encoding="utf-8"),
                lesson["answer_prefix"],
            )
            if source is None or not answer:
                print(f"(skipping {lesson['title']} — not in this build)")
                continue

            print("\n" + "═" * 45)
            print(lesson["title"])
            print("═" * 45)
            print(_wrap(lesson["teach"]) + "\n")
            print(_render_event(source))
            print(_wrap("\nYour turn — type a translation (end with `EOF`), "
                        "or press Enter to reveal:"))
            attempt = _read_attempt()
            if attempt:
                print(_wrap("\n— your attempt —"))
                print(attempt)
            print("\n" + "─" * 45)
            print(" reference translation")
            print("─" * 45)
            print(answer)
            print("\n" + _wrap(lesson["notes"]))
            input("\nPress Enter for the next lesson… ")
    except (EOFError, KeyboardInterrupt):
        print("\nLeaving the tutor. Run `scripts/run_human.py` for the real thing.")
        return 0

    print(_wrap("\nThat's the tour. The real queue is `scripts/run_human.py` — "
                "same render, easiest events first. Good luck!"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
