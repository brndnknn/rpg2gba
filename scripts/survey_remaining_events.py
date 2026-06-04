"""Survey the events that don't match any current deterministic pattern.

Shows the most common script-call signatures and command-code profiles
among the ~2,767 events that would still go to Opus, to reveal candidate
patterns we haven't considered yet.
"""
import json
import re
from collections import Counter
from pathlib import Path

MAP_DIR = Path("output/uranium-build/maps")

# --- pattern detection (mirrors count_deterministic_patterns.py) ---

_SAFE_CODES      = {0, 5, 6, 7, 101, 401}
_SCRIPT_CODES    = {355, 655}
_PBCALLBUB_RE    = re.compile(r"^\s*pbCallBub\b")
_ITEM_BALL_RE    = re.compile(r"^\s*(Kernel\.)?pbItemBall\b")
_TRAINER_RE      = re.compile(r"pbTrainerBattle\b")
_AUDIO_RE        = re.compile(r"^\s*(pbSEPlay|pbPlayCry|XInput\.vibrate)\b")
_WARP_SAFE_CODES = {0, 5, 6, 7, 106, 201, 221, 222, 223, 224, 249, 250}


def _event_has_commands(ev):
    return any(
        cmd.get("code", 0) != 0
        for page in ev.get("pages", [])
        for cmd in page.get("list", [])
    )


def _script_params(ev):
    return [
        cmd["parameters"][0]
        for page in ev.get("pages", [])
        for cmd in page.get("list", [])
        if cmd.get("code") in _SCRIPT_CODES
        and cmd.get("parameters")
        and isinstance(cmd["parameters"][0], str)
    ]


def _all_codes(ev):
    return {cmd.get("code", 0) for page in ev.get("pages", []) for cmd in page.get("list", [])}


def _page_is_pure_dialogue(page):
    for cmd in page.get("list", []):
        code = cmd.get("code", 0)
        if code in _SAFE_CODES:
            continue
        if code in _SCRIPT_CODES:
            p = cmd.get("parameters", [""])[0]
            if isinstance(p, str) and _PBCALLBUB_RE.match(p):
                continue
        return False
    return True


def _is_pure_dialogue(ev):
    pages = ev.get("pages", [])
    return bool(pages) and all(_page_is_pure_dialogue(p) for p in pages)


def _is_item_ball(ev):
    return any(_ITEM_BALL_RE.match(p) for p in _script_params(ev))


def _is_trainer(ev):
    return any(
        _TRAINER_RE.search(str(p))
        for page in ev.get("pages", [])
        for cmd in page.get("list", [])
        for p in cmd.get("parameters", [])
        if isinstance(p, str)
    )


def _is_simple_warp(ev):
    if len(ev.get("pages", [])) != 1:
        return False
    codes = _all_codes(ev) - {0}
    non_safe = codes - _WARP_SAFE_CODES
    if not non_safe:
        return True
    if non_safe <= _SCRIPT_CODES:
        return all(_AUDIO_RE.match(p) for p in _script_params(ev))
    return False


def _is_any_pattern(ev):
    return _is_pure_dialogue(ev) or _is_simple_warp(ev) or _is_item_ball(ev) or _is_trainer(ev)


# --- leading script-call signature (first identifier path) ---
_SIG_RE = re.compile(r"^[\s\(]*([A-Za-z_$][A-Za-z0-9_.$]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)")

def _sig(s):
    m = _SIG_RE.match(s)
    return m.group(1) if m else s.strip()[:40]


def main():
    remaining = []

    for path in sorted(MAP_DIR.glob("Map*.json")):
        m = json.load(open(path))
        for ev in m["events"]:
            if not _event_has_commands(ev):
                continue
            if not _is_any_pattern(ev):
                remaining.append((m["map_id"], ev))

    print(f"Events not matching any current pattern: {len(remaining)}\n")

    # --- top script-call signatures ---
    sig_counter: Counter = Counter()
    for _, ev in remaining:
        for p in _script_params(ev):
            sig_counter[_sig(p)] += 1

    print("Top 40 script-call signatures in remaining events:")
    for sig, n in sig_counter.most_common(40):
        print(f"  {n:5}  {sig}")

    # --- dominant non-trivial code profiles ---
    print("\nTop 20 command-code profiles (non-zero, non-text codes):")
    profile_counter: Counter = Counter()
    _TEXT_CODES = {0, 5, 6, 7, 101, 108, 401, 408}
    for _, ev in remaining:
        codes = _all_codes(ev) - _TEXT_CODES - {355, 655}
        profile = tuple(sorted(codes))
        profile_counter[profile] += 1

    for profile, n in profile_counter.most_common(20):
        print(f"  {n:5}  {profile}")


if __name__ == "__main__":
    main()
