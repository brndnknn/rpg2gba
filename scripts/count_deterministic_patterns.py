"""Count events matching candidate deterministic patterns.

For each pattern, reports total matches and a few examples. These are
upper-bound estimates — some matches will have edge cases that fall
through to Opus, but this shows the potential savings ceiling.

Patterns checked:
  A) Pure dialogue      — only text/lock/release/pbCallBub commands
  B) Item ball          — contains pbItemBall / Kernel.pbItemBall
  C) Trainer battle     — contains pbTrainerBattle (any variant)
  D) Simple warp        — contains Transfer Player (201) and nothing else
                          non-trivial (fadescreen + warp + end, no dialogue,
                          no script calls beyond audio)
"""
import json
import re
from pathlib import Path

MAP_DIR = Path("output/uranium-build/maps")

_SAFE_CODES = {0, 5, 6, 7, 101, 401}
_SCRIPT_CODES = {355, 655}

_PBCALLBUB_RE     = re.compile(r"^\s*pbCallBub\b")
_ITEM_BALL_RE     = re.compile(r"^\s*(Kernel\.)?pbItemBall\b")
_TRAINER_RE       = re.compile(r"^\s*(Kernel\.)?pbTrainerBattle\b")
_RECEIVE_ITEM_RE  = re.compile(r"^\s*(Kernel\.)?pbReceiveItem\b")


def _script_params(event: dict) -> list[str]:
    """All script-call parameter strings across every page of the event."""
    out = []
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            if cmd.get("code") in _SCRIPT_CODES:
                params = cmd.get("parameters", [])
                if params and isinstance(params[0], str):
                    out.append(params[0])
    return out


def _all_codes(event: dict) -> set[int]:
    codes: set[int] = set()
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            codes.add(cmd.get("code", 0))
    return codes


def _is_pbcallbub(s: str) -> bool:
    return bool(_PBCALLBUB_RE.match(s))


def _page_is_pure_dialogue(page: dict) -> bool:
    for cmd in page.get("list", []):
        code = cmd.get("code", 0)
        if code in _SAFE_CODES:
            continue
        if code in _SCRIPT_CODES:
            params = cmd.get("parameters", [])
            if params and isinstance(params[0], str) and _is_pbcallbub(params[0]):
                continue
            return False
        return False
    return True


def _is_pure_dialogue(event: dict) -> bool:
    pages = event.get("pages", [])
    return bool(pages) and all(_page_is_pure_dialogue(p) for p in pages)


def _contains_script(event: dict, pattern: re.Pattern) -> bool:
    return any(pattern.match(s) for s in _script_params(event))


def _is_item_ball(event: dict) -> bool:
    return _contains_script(event, _ITEM_BALL_RE)


def _is_trainer(event: dict) -> bool:
    return _contains_script(event, _TRAINER_RE)


def _is_simple_warp(event: dict) -> bool:
    """Single-page, only warp (201), fade (223/224), wait (106), lock/release,
    end markers. No dialogue, no script calls beyond audio."""
    pages = event.get("pages", [])
    if len(pages) != 1:
        return False
    _WARP_SAFE = {0, 5, 6, 7, 106, 201, 221, 222, 223, 224, 249, 250}
    codes = _all_codes(event)
    non_safe = codes - _WARP_SAFE
    # Allow script calls only if they're audio (pbSEPlay / pbPlayCry / XInput)
    _AUDIO_RE = re.compile(r"^\s*(pbSEPlay|pbPlayCry|XInput\.vibrate)\b")
    if non_safe == {355} or non_safe == {655} or non_safe == {355, 655}:
        return all(_AUDIO_RE.match(s) for s in _script_params(event))
    return not non_safe


def _event_has_commands(event: dict) -> bool:
    for page in event.get("pages", []):
        for cmd in page.get("list", []):
            if cmd.get("code", 0) != 0:
                return True
    return False


def _label(m: dict, event: dict) -> str:
    return f"map{m['map_id']:03d} ev{event['id']:03d} ({event.get('name','')}) — {len(event.get('pages',[]))}p"


def main() -> None:
    total = 0
    counts = {"dialogue": 0, "item_ball": 0, "trainer": 0, "simple_warp": 0}
    examples = {k: [] for k in counts}
    overlap: dict[frozenset, int] = {}

    for path in sorted(MAP_DIR.glob("Map*.json")):
        m = json.loads(path.read_text(encoding="utf-8"))
        for event in m["events"]:
            if not _event_has_commands(event):
                continue
            total += 1
            matched = set()
            if _is_pure_dialogue(event):
                counts["dialogue"] += 1
                matched.add("dialogue")
                if len(examples["dialogue"]) < 4:
                    examples["dialogue"].append(_label(m, event))
            if _is_item_ball(event):
                counts["item_ball"] += 1
                matched.add("item_ball")
                if len(examples["item_ball"]) < 4:
                    examples["item_ball"].append(_label(m, event))
            if _is_trainer(event):
                counts["trainer"] += 1
                matched.add("trainer")
                if len(examples["trainer"]) < 4:
                    examples["trainer"].append(_label(m, event))
            if _is_simple_warp(event):
                counts["simple_warp"] += 1
                matched.add("simple_warp")
                if len(examples["simple_warp"]) < 4:
                    examples["simple_warp"].append(_label(m, event))

    total_covered = sum(counts.values())
    print(f"Command-bearing map events:  {total}")
    print()
    for k, n in counts.items():
        print(f"  {k:<16} {n:>4}  ({n/total*100:.1f}%)")
        for ex in examples[k]:
            print(f"               {ex}")
        print()
    print(f"Total pattern matches:       {total_covered}  (sum, not deduplicated)")
    # rough deduplicated estimate — assume minimal overlap
    unique_covered = len({
        (path.stem, event["id"])
        for path in sorted(MAP_DIR.glob("Map*.json"))
        for event in json.loads(path.read_text(encoding="utf-8"))["events"]
        if _event_has_commands(event) and (
            _is_pure_dialogue(event) or _is_item_ball(event)
            or _is_trainer(event) or _is_simple_warp(event)
        )
    })
    print(f"Unique events covered:       {unique_covered}  ({unique_covered/total*100:.1f}%)")
    print(f"Remaining for Opus:          {total - unique_covered}")


if __name__ == "__main__":
    main()
