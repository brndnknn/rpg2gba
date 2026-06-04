"""Count how many real map events the deterministic pre-filter claims (plan §10.1).

Runs each classifier against every command-bearing map event in the Phase-3 corpus
and reports, per classifier, how many events it would translate without an LLM
spawn. No `claude` spawns; pass --compile to also gate each claim through the real
poryscript binary (slower, the true count) instead of just the classifier claim.

    .venv/bin/python scripts/count_deterministic_actual.py [--compile] [--examples N]
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

from rpg2gba.conversion_agent import deterministic, poryscript
from rpg2gba.conversion_agent.orchestrator import _event_has_commands
from rpg2gba.pipeline import _load_dotenv, _repo_root


def _maps_dir() -> Path:
    """Phase-3 map JSON dir, anchored to the repo root so cwd doesn't matter.

    Loads .env-paths first (for RPG2GBA_PORYSCRIPT, used by --compile) and resolves
    a relative RPG2GBA_OUTPUT against the repo root rather than the current dir —
    running from anywhere finds the same corpus.
    """
    _load_dotenv()
    out = Path(os.environ.get("RPG2GBA_OUTPUT", "output"))
    if not out.is_absolute():
        out = _repo_root() / out
    return out / "uranium-build" / "maps"


def claim(map_id: int, event: dict, ctx: deterministic.Context) -> tuple[str | None, str | None]:
    """(classifier_name, script) for the first classifier that claims the event."""
    for fn in deterministic._CLASSIFIERS:
        try:
            out = fn(map_id, event, ctx)
        except Exception:
            out = None
        if out is not None:
            script = out.script if isinstance(out, deterministic.DetResult) else out
            return fn.__name__, script
    return None, None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compile", action="store_true", help="gate each claim through poryscript")
    ap.add_argument(
        "--examples", type=int, default=0, help="print N example outputs per classifier"
    )
    args = ap.parse_args()

    maps = _maps_dir()
    map_files = sorted(maps.glob("Map*.json"))
    if not map_files:
        raise SystemExit(
            f"no Map*.json under {maps} — run `phase3` first (or set RPG2GBA_OUTPUT)."
        )

    ctx = deterministic.load_context(
        reference_dir=_repo_root() / "reference", intermediate_dir=maps.parent / "intermediate"
    )
    claimed: Counter[str] = Counter()
    compiled_ok: Counter[str] = Counter()
    compile_fail: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    total_with_cmds = 0

    for mp in map_files:
        m = json.loads(mp.read_text(encoding="utf-8"))
        for event in m["events"]:
            if not _event_has_commands(event):
                continue
            total_with_cmds += 1
            name, script = claim(m["map_id"], event, ctx)
            if name is None:
                continue
            claimed[name] += 1
            if args.examples and len(examples.setdefault(name, [])) < args.examples:
                tag = f"# map {m['map_id']} ev{event['id']} {event.get('name')!r}"
                examples[name].append(f"{tag}\n{script}")
            if args.compile:
                if poryscript.compile_script(script).ok:
                    compiled_ok[name] += 1
                else:
                    compile_fail[name] += 1

    print(f"command-bearing map events: {total_with_cmds}\n")
    header = f"{'classifier':<28} {'claimed':>8}"
    if args.compile:
        header += f" {'compiles':>9} {'fails':>6}"
    print(header)
    print("-" * len(header))
    for fn in deterministic._CLASSIFIERS:
        n = fn.__name__
        row = f"{n:<28} {claimed[n]:>8}"
        if args.compile:
            row += f" {compiled_ok[n]:>9} {compile_fail[n]:>6}"
        print(row)
    total = sum(claimed.values())
    print("-" * len(header))
    print(f"{'TOTAL claimed':<28} {total:>8}  ({100 * total / total_with_cmds:.1f}%)")
    if args.compile:
        ok = sum(compiled_ok.values())
        print(f"{'TOTAL compiles':<28} {ok:>8}  ({100 * ok / total_with_cmds:.1f}%)")

    for n, exs in examples.items():
        print(f"\n===== examples: {n} =====")
        for e in exs:
            print(e + "\n")


if __name__ == "__main__":
    main()
