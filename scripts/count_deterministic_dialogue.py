"""Count events that qualify for deterministic dialogue handling.

A "pure dialogue" event has every page containing only:
  - 0   end marker
  - 5   lock
  - 6   face player
  - 7   release
  - 101 show text (message start)
  - 401 show text (continuation)
  - 355/655 script call — ONLY if the call is pbCallBub (STRIP)

No branches (111), no self-switch sets (123), no warps (201), no other
script calls. All pages must qualify; a mixed event falls through to Opus.
"""
import json
import re
from pathlib import Path

MAP_DIR = Path("output/uranium-build/maps")

_SAFE_CODES = {0, 5, 6, 7, 101, 401}
_SCRIPT_CODES = {355, 655}
_PBCALLBUB_RE = re.compile(r"^\s*pbCallBub\b")


def _is_pbcallbub(cmd: dict) -> bool:
    params = cmd.get("parameters", [])
    return bool(params and isinstance(params[0], str) and _PBCALLBUB_RE.match(params[0]))


def _page_is_pure_dialogue(page: dict) -> bool:
    for cmd in page.get("list", []):
        code = cmd.get("code", 0)
        if code in _SAFE_CODES:
            continue
        if code in _SCRIPT_CODES:
            if _is_pbcallbub(cmd):
                continue
            return False
        return False
    return True


def _event_is_pure_dialogue(event: dict) -> bool:
    pages = event.get("pages", [])
    if not pages:
        return False
    return all(_page_is_pure_dialogue(p) for p in pages)


def _event_has_commands(event: dict) -> bool:
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            if cmd.get("code", 0) != 0:
                return True
    return False


def main() -> None:
    total_with_cmds = 0
    pure_dialogue = 0
    single_page = 0
    multi_page = 0
    examples: list[str] = []

    for path in sorted(MAP_DIR.glob("Map*.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        for event in m["events"]:
            if not _event_has_commands(event):
                continue
            total_with_cmds += 1
            if _event_is_pure_dialogue(event):
                pure_dialogue += 1
                n_pages = len(event.get("pages", []))
                if n_pages == 1:
                    single_page += 1
                else:
                    multi_page += 1
                if len(examples) < 8:
                    examples.append(
                        f"  map{m['map_id']:03d} ev{event['id']:03d} "
                        f"({event.get('name','')}) — {n_pages} page(s)"
                    )

    print(f"Command-bearing map events:  {total_with_cmds}")
    print(f"Pure-dialogue matches:        {pure_dialogue}  ({pure_dialogue/total_with_cmds*100:.1f}%)")
    print(f"  Single-page:               {single_page}")
    print(f"  Multi-page (all pages OK): {multi_page}")
    print()
    print("Examples:")
    for e in examples:
        print(e)


if __name__ == "__main__":
    main()
