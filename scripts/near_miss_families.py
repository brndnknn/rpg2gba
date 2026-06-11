"""Cluster the 133 trivial-but-unclaimed events into implementable families.

Follow-up to measure_trivial_tier.py: for each event the pre-filter passes on but the
06-03 scan calls trivial, summarize WHY the classifiers rejected it (the wrinkle)
and group by shape, so we can judge effort-vs-savings per family. Also reports:
  - how many sit on maps already checkpointed (savings already lost)
  - how many have a memo entry (savings already covered by dedup C)

    .venv/bin/python scripts/near_miss_families.py
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from measure_trivial_tier import classify_remaining  # same trivial definition

from rpg2gba.conversion_agent import deterministic
from rpg2gba.conversion_agent.orchestrator import _event_has_commands, _memo_key
from rpg2gba.pipeline import _load_dotenv, _repo_root

_load_dotenv()
OUT = Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
if not OUT.is_absolute():
    OUT = _repo_root() / OUT
BUILD = OUT / "uranium-build"
MAPS = BUILD / "maps"


def shape(event: dict) -> str:
    """Coarse family signature: page count + the non-zero codes + script-call heads."""
    pages = event.get("pages", [])
    codes: Counter[int] = Counter()
    sigs: set[str] = set()
    for p in pages:
        for cmd in p.get("list", []):
            c = cmd.get("code", 0)
            if c == 0:
                continue
            codes[c] += 1
            if c in (355, 655):
                arg = (cmd.get("parameters") or [""])[0]
                if isinstance(arg, str):
                    head = arg.split("(")[0].split(".")[0].strip()[:30]
                    sigs.add(head or "?")
    code_part = ",".join(f"{c}" for c in sorted(codes))
    sig_part = "+".join(sorted(sigs)) if sigs else "-"
    return f"pages={len(pages)} codes=[{code_part}] sigs={sig_part}"


def main() -> None:
    ctx = deterministic.load_context(
        reference_dir=_repo_root() / "reference",
        intermediate_dir=BUILD / "intermediate",
    )
    memo = {}
    mm = BUILD / "memo_manifest.json"
    if mm.is_file():
        memo = json.loads(mm.read_text(encoding="utf-8")).get("entries", {})
    done_maps = {
        int(p.stem[3:]) for p in (BUILD / "checkpoints").glob("Map*.done")
    }

    fams: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    n_done = n_memo = 0
    for mp in sorted(MAPS.glob("Map*.json")):
        m = json.loads(mp.read_text(encoding="utf-8"))
        for event in m["events"]:
            if not _event_has_commands(event):
                continue
            if deterministic.try_deterministic(m["map_id"], event, ctx) is not None:
                continue
            verdict, _ = classify_remaining(event)
            if verdict != "trivial":
                continue
            if m["map_id"] in done_maps:
                n_done += 1
            if _memo_key({"map_id": m["map_id"], **event}) in memo:
                n_memo += 1
            fams[shape(event)].append((m["map_id"], event["id"], event.get("name", "")))

    total = sum(len(v) for v in fams.values())
    print(f"trivial near-misses: {total}")
    print(f"  on already-checkpointed maps (savings gone): {n_done}")
    print(f"  already covered by a memo entry:             {n_memo}")
    print()
    print(f"families ({len(fams)}), largest first:")
    for sig, evs in sorted(fams.items(), key=lambda kv: -len(kv[1])):
        names = Counter(n for _, _, n in evs)
        top = ", ".join(f"{n!r}x{c}" for n, c in names.most_common(3))
        print(f"  {len(evs):4}  {sig}")
        print(f"        e.g. {top}   first={evs[0][:2]}")


if __name__ == "__main__":
    main()
