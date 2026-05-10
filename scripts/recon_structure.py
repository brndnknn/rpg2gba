#!/usr/bin/env python3
"""Phase 0.1 — Document Uranium source directory layout.

Usage:
    RPG2GBA_URANIUM_SRC=/path/to/uranium python scripts/recon_structure.py
"""
import os
from collections import defaultdict
from pathlib import Path

URANIUM_SRC = Path(os.environ["RPG2GBA_URANIUM_SRC"])
OUT = Path("reference/uranium_structure.md")
SKIP = {".git", "__MACOSX", ".DS_Store"}


def count_by_ext(path: Path) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for f in path.rglob("*"):
        if f.is_file():
            counts[f.suffix.lower() or "(no ext)"] += 1
    return dict(counts)


def tree(path: Path, prefix: str = "", depth: int = 0, max_depth: int = 3) -> list[str]:
    if depth >= max_depth:
        return [f"{prefix}..."]
    lines = []
    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return [f"{prefix}(permission denied)"]
    entries = [e for e in entries if e.name not in SKIP]
    for i, entry in enumerate(entries):
        last = i == len(entries) - 1
        connector = "└── " if last else "├── "
        extension = "    " if last else "│   "
        if entry.is_dir():
            counts = count_by_ext(entry)
            summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1])[:4])
            lines.append(f"{prefix}{connector}{entry.name}/  [{summary}]")
            lines.extend(tree(entry, prefix + extension, depth + 1, max_depth))
        else:
            lines.append(f"{prefix}{connector}{entry.name}")
    return lines


total = count_by_ext(URANIUM_SRC)
lines = [
    "# Uranium Source Structure",
    "",
    f"Source: `{URANIUM_SRC}`",
    "",
    "```",
    f"{URANIUM_SRC.name}/",
    *tree(URANIUM_SRC),
    "```",
    "",
    "## File type totals",
    "",
    "| Extension | Count |",
    "|---|---|",
    *[f"| `{ext}` | {n} |" for ext, n in sorted(total.items(), key=lambda x: -x[1])],
]

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Written: {OUT}")
