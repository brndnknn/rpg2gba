"""Invisible walls: the one place that decides which RMXP events are one.

RMXP blocks the player on any event page whose graphic has a non-empty
`character_name` and `through == false`, regardless of opacity. Uranium uses
that for invisible walls: an opacity-0, non-through, named page with no script
(Burole Town Gym "Pillar2", map 66 EV046/EV047, which the gym puzzle later
`removeobject`s). The converter used to treat every opacity-0 page as "not
visible", so such an event never spawned and never blocked.

An event is an **invisible wall** only when (1) EVERY page is either an
invisible-wall page or a blank-graphic page, and (2) nothing on the same map
can reveal it: no event's Set Move Route (code 209) targets it and no script
line (code 355/655) names it as `events[N]` / `get_character(N)`. Uranium
cutscene actors are opacity-0 until another event's route changes their
opacity, so (2) keeps them out. Wall-ness is therefore a MAP-level decision:
`invisible_wall_ids(events)` is the one definition (CLAUDE.md §4.3), and the
visibility readers (`metadata_wiring`, `hidden_actor_bracket`) take their
answer from it. `is_invisible_wall_event` is only the per-event page test.

The wall is emitted as a real object_event wearing `INVISIBLE_GFX`, a fully
transparent sprite the sprite emitter generates (`graphics/sprite_emit.py`).
"""
from __future__ import annotations

import re

# Engine-mechanism constant (CLAUDE.md §5: mechanism names are RPG2GBA_*).
# Minted by `sprite_emit.emit_sprites` into rpg2gba_event_objects.gen.h.
INVISIBLE_GFX = "OBJ_EVENT_GFX_RPG2GBA_INVISIBLE"

TRIGGER_ACTION = 0


def is_invisible_wall_page(page: dict) -> bool:
    """A page that blocks like a sprite but draws nothing and does nothing:
    named graphic, opacity 0, not `through`, action-button trigger, and a
    command list holding only the terminator."""
    graphic = page.get("graphic", {})
    return (
        bool(graphic.get("character_name"))
        and graphic.get("opacity", 255) <= 0
        and not page.get("through", False)
        and page.get("trigger") == TRIGGER_ACTION
        and all(cmd.get("code") == 0 for cmd in page.get("list", []))
    )


def _is_blank_page(page: dict) -> bool:
    graphic = page.get("graphic", {})
    return not graphic.get("character_name") and not graphic.get("tile_id", 0)


def is_invisible_wall_event(pages: list[dict]) -> bool:
    """True when at least one page is an invisible-wall page and every page is
    an invisible-wall page or a blank-graphic page."""
    if not pages:
        return False
    if not any(is_invisible_wall_page(p) for p in pages):
        return False
    return all(is_invisible_wall_page(p) or _is_blank_page(p) for p in pages)


_SCRIPT_TARGET_RES = (
    re.compile(r"events\s*\[\s*(\d+)\s*\]"),
    re.compile(r"get_character\s*\(\s*(\d+)\s*\)"),
)


def revealed_event_ids(events: list[dict]) -> set[int]:
    """Event ids some command on this map can act on as a character: the
    first parameter of a code-209 Set Move Route (0 = the host event itself,
    -1 = the player, ignored) or an `events[N]` / `get_character(N)` mention in
    a code-355/655 script line."""
    targeted: set[int] = set()
    for event in events:
        if not event:
            continue
        for page in event.get("pages", []):
            for cmd in page.get("list", []):
                code = cmd.get("code")
                params = cmd.get("parameters") or []
                if code == 209 and params and isinstance(params[0], int):
                    target = event["id"] if params[0] == 0 else params[0]
                    if target > 0:
                        targeted.add(target)
                elif code in (355, 655):
                    text = str(params)
                    for rx in _SCRIPT_TARGET_RES:
                        targeted.update(int(m) for m in rx.findall(text))
    return targeted


def invisible_wall_ids(events: list[dict]) -> set[int]:
    """Ids of the invisible-wall events among one map's `events`."""
    revealed = revealed_event_ids(events)
    return {
        ev["id"]
        for ev in events
        if ev and ev["id"] not in revealed and is_invisible_wall_event(ev.get("pages", []))
    }
