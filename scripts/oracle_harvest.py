"""One-time differential harvest vs the frozen-Opus oracle (grill D6).

Transpiles the oracle maps in memory (write=False semantics — nothing under
output/ is touched, the registry is not saved) and diffs each map against
`reference/archive/oracle_pory/` block-by-block on normalized text. Every
divergence lands in a cluster bucket for disposition: transpiler bug (fix)
or Opus error (note, discard). After dispositions are recorded the oracle
retires.

Usage:
    python scripts/oracle_harvest.py [--maps 1,2,3,4,5,6,7] [--show LABEL]
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from rpg2gba.conversion_agent import deterministic, transpiler  # noqa: E402
from rpg2gba.conversion_agent.flag_registry import FlagRegistry  # noqa: E402
from rpg2gba.conversion_agent.transpile_driver import transpile_map  # noqa: E402

ORACLE_DIR = REPO / "reference" / "archive" / "oracle_pory"
OUT = Path("output") / "uranium-build"

_BLOCK_RE = re.compile(
    r"^(script|movement|text|mart)\s+(\w+)\s*\{", re.MULTILINE
)


def split_blocks(pory: str) -> dict[str, str]:
    """Map each top-level block label to its body text (brace-balanced)."""
    blocks: dict[str, str] = {}
    for m in _BLOCK_RE.finditer(pory):
        label = m.group(2)
        depth = 0
        start = pory.index("{", m.start())
        i = start
        while i < len(pory):
            if pory[i] == "{":
                depth += 1
            elif pory[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        blocks[label] = pory[m.start(1):i + 1]
    return blocks


def normalize(block: str) -> list[str]:
    """Normalized statement lines: comments stripped, whitespace collapsed."""
    out: list[str] = []
    for line in block.splitlines():
        line = line.split("#", 1)[0].strip()
        line = re.sub(r"\s+", " ", line)
        if line and line not in ("{", "}"):
            out.append(line)
    return out


def classify_divergence(oracle_lines: list[str], ours_lines: list[str]) -> str:
    """A coarse cluster key for a differing block."""
    o, t = set(oracle_lines), set(ours_lines)
    only_o, only_t = o - t, t - o
    keys: list[str] = []
    if any("# UNHANDLED" in ln or ln.startswith("# ") for ln in ours_lines):
        keys.append("ours-has-unhandled")
    for ln in sorted(only_o)[:3]:
        keys.append(f"oracle-extra:{ln.split('(')[0][:30]}")
    for ln in sorted(only_t)[:3]:
        keys.append(f"ours-extra:{ln.split('(')[0][:30]}")
    return " | ".join(keys) if keys else "reordered-only"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--maps", default="1,2,3,4,5,6,7")
    ap.add_argument("--show", default=None, help="print full diff for one block label")
    args = ap.parse_args()
    map_ids = [int(x) for x in args.maps.split(",")]

    registry = FlagRegistry.load(OUT / "flag_state.json")
    ctx = transpiler.TranspileContext(registry=registry)
    det_ctx = deterministic.load_context(
        reference_dir=REPO / "reference", intermediate_dir=OUT / "intermediate"
    )

    total = Counter()
    clusters: Counter[str] = Counter()
    cluster_examples: dict[str, list[str]] = {}

    for mid in map_ids:
        oracle_path = ORACLE_DIR / f"Map{mid:03d}.pory"
        if not oracle_path.is_file():
            print(f"Map{mid:03d}: no oracle file — skipped")
            continue
        map_json = json.loads(
            (OUT / "maps" / f"Map{mid:03d}.json").read_text(encoding="utf-8")
        )
        ours_text, _queue = transpile_map(mid, map_json, ctx, det_ctx)

        oracle_blocks = split_blocks(oracle_path.read_text(encoding="utf-8"))
        ours_blocks = split_blocks(ours_text)

        o_labels, t_labels = set(oracle_blocks), set(ours_blocks)

        # Pair labels across the two schemes: Opus labels often carry an
        # extra EV0NN_ id segment ("Map007_EV021_Explorer2_Page1") where the
        # transpiler uses the bare event name ("Map007_Explorer2_Page1").
        def _canon(label: str) -> str:
            # Both schemes carry the event id; drop any name segment between
            # the EV id and the Page suffix (Opus: Map002_EV010_Receptionist_
            # TRADE_Page1; transpiler: Map002_EV010_Page1).
            return re.sub(r"^(Map\d+_EV\d+)_.*_(Page\d+.*)$", r"\1_\2", label)

        remap: dict[str, str] = {}
        t_by_canon: dict[str, str] = {_canon(lb): lb for lb in t_labels - o_labels}
        for lb in o_labels - t_labels:
            match = t_by_canon.get(_canon(lb))
            if match is not None:
                remap[lb] = match

        for label in sorted(o_labels | t_labels):
            if label in remap.values():
                continue  # handled via its oracle-side name
            t_label = remap.get(label, label)
            if label not in t_labels and t_label not in t_labels:
                total["only-in-oracle"] += 1
                clusters["block-only-in-oracle"] += 1
                cluster_examples.setdefault("block-only-in-oracle", []).append(label)
                continue
            if label not in o_labels:
                total["only-in-ours"] += 1
                key = ("movement-only-in-ours" if ours_blocks[label].startswith("movement")
                       else "block-only-in-ours")
                clusters[key] += 1
                cluster_examples.setdefault(key, []).append(label)
                continue
            o_norm = normalize(oracle_blocks[label])
            t_norm = normalize(ours_blocks[t_label])
            if label != t_label:
                # neutralize the label-scheme difference inside the body too
                t_norm = [ln.replace(t_label, label) for ln in t_norm]
            if o_norm == t_norm:
                total["identical"] += 1
                continue
            total["divergent"] += 1
            key = classify_divergence(o_norm, t_norm)
            clusters[key] += 1
            cluster_examples.setdefault(key, []).append(label)
            if args.show == label:
                print(f"--- oracle {label}")
                print("\n".join(difflib.unified_diff(o_norm, t_norm, lineterm="")))

    print(f"\nblocks: {dict(total)}")
    print(f"\ndivergence clusters ({len(clusters)}):")
    for key, n in clusters.most_common():
        ex = cluster_examples[key][:4]
        print(f"  {n:4d}  {key}")
        print(f"        e.g. {', '.join(ex)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
