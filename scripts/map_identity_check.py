"""Read-only diagnostic: flag maps whose map_infos.json editor name disagrees with
free in-content identity signals, and identify any map missing from map_infos.json.

Free signals harvested per map:
  - BGM name  (PU-Passage Cave → "Passage Cave")
  - Sign text (\\sign[...] dialogue in events)
  - Warp-based connection neighbours (code 201)
  - map_infos parent-tree path

The script flags *candidates for human/wiki review* — it never auto-corrects.

Dup-name groups (~35 expected) are reported in full.
The Comet Cave×3 / Passage Cave×3 cross-assignment case is surfaced explicitly.

Usage:
  python scripts/map_identity_check.py
  python scripts/map_identity_check.py --output-dir /path/to/uranium-build

Output goes to stdout; nothing is written.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from rpg2gba import pipeline

# ---------------------------------------------------------------------------
# BGM signal helpers
# ---------------------------------------------------------------------------

# Canonical sub-location BGM suffixes that are *expected* to differ from the
# map's editor name (the map is a room inside the town, not the town itself).
# Matching these keeps false-positive noise low.
_BGM_SUBLOC_TOKENS: frozenset[str] = frozenset(
    {
        "pokecenter",
        "pokemart",
        "herohouse",  # player/NPC home
        "larkspurrlab",
        "bycicle",  # Bealbeach resort BGM typo
        "title",
        "punktheme",
        "nuclearevent",
        "dreamvenesi",
        "victoryroad",  # used for VR building interior
        "jungletemple",
        "nuclearlabintro",
        "theme",
    }
)

# Noise tokens that appear in both BGM names and map names but carry no
# discriminating identity information.
_NOISE: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "new",
        "old",
        "map",
        "area",
        "room",
        "hall",
        "town",
        "city",
        "route",
        "cave",
        "road",
        "road",
        "house",
        "mart",
        "center",
        "building",
        "island",
        "lake",
        "forest",
        "beach",
        "desert",
        "mountain",
        "river",
        "tower",
        "field",
        "street",
        "port",
        "other",
        "caves",
        "train",
        "station",
        "plant",
        "floor",
    }
)


def _bgm_words(bgm_name: str) -> frozenset[str]:
    """Extract meaningful lower-case tokens from a BGM name.

    Strips leading 'PU-' / 'PU ' prefix, splits on CamelCase, spaces, hyphens,
    and drops noise tokens.
    """
    stripped = re.sub(r"^PU[-\s]", "", bgm_name).strip()
    # Normalise to one long lower-case token for sub-loc check
    normalised = re.sub(r"[\s\-_().]", "", stripped).lower()
    if normalised in _BGM_SUBLOC_TOKENS or any(
        sl in normalised for sl in _BGM_SUBLOC_TOKENS
    ):
        return frozenset()
    # CamelCase split + word split
    tokens = re.findall(r"[A-Z][a-z]+|[a-z]+|[A-Z]+(?=[A-Z]|$)", stripped)
    return frozenset(t.lower() for t in tokens if len(t) >= 4) - _NOISE


def _name_words(name: str) -> frozenset[str]:
    """Extract meaningful lower-case tokens from a map_infos name."""
    tokens = re.findall(r"[A-Za-z]{4,}", name)
    return frozenset(t.lower() for t in tokens) - _NOISE


# ---------------------------------------------------------------------------
# Sign-text signal helpers
# ---------------------------------------------------------------------------

# RMXP message open / continuation codes
_MSG_CODES: frozenset[int] = frozenset({101, 401})
_SIGN_RE = re.compile(r"\\sign\[([^\]]+)\](.*)", re.DOTALL)


def _extract_sign_texts(map_data: dict) -> list[str]:
    """Return the text bodies of all \\sign[...] dialogue lines in a map."""
    results: list[str] = []
    for evt in map_data.get("events", []):
        for pg in evt.get("pages", []):
            for cmd in pg.get("list", []):
                if cmd["code"] not in _MSG_CODES:
                    continue
                params = cmd.get("parameters", [])
                if not params:
                    continue
                txt = params[0] if isinstance(params[0], str) else ""
                m = _SIGN_RE.search(txt)
                if m:
                    body = m.group(2).strip()
                    # Only keep the first non-newline segment (the headline)
                    headline = body.split("\\n")[0].split("\n")[0].strip()
                    if headline:
                        results.append(headline)
    return results


# ---------------------------------------------------------------------------
# Warp-based connection neighbour helpers
# ---------------------------------------------------------------------------

_WARP_CODE = 201  # Transfer Player


def _warp_neighbours(map_id: int, map_data: dict) -> set[int]:
    """Return the set of map ids reachable by a single warp from this map."""
    neighbours: set[int] = set()
    for evt in map_data.get("events", []):
        for pg in evt.get("pages", []):
            for cmd in pg.get("list", []):
                if cmd["code"] != _WARP_CODE:
                    continue
                params = cmd.get("parameters", [])
                # params[0]=mode (0=direct), params[1]=destination map id
                if len(params) >= 2 and params[0] == 0:
                    dest = params[1]
                    if isinstance(dest, int) and dest != map_id:
                        neighbours.add(dest)
    return neighbours


# ---------------------------------------------------------------------------
# Parent-tree path helper
# ---------------------------------------------------------------------------


def _parent_path(map_id: int, map_infos: dict[str, dict]) -> str:
    """Return a human-readable breadcrumb path from the root to map_id."""
    path: list[str] = []
    cur = str(map_id)
    seen: set[str] = set()
    while cur in map_infos and cur not in seen:
        seen.add(cur)
        entry = map_infos[cur]
        path.append(f"{cur}:{entry['name']}")
        parent = str(entry.get("parent_id", 0))
        if parent == "0" or parent not in map_infos:
            break
        cur = parent
    path.reverse()
    return " → ".join(path)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def _analyse(out_dir: Path) -> None:  # noqa: C901 — kept long for a linear report
    maps_dir = out_dir / "maps"
    info_path = out_dir / "map_infos.json"

    if not maps_dir.is_dir():
        print(f"ERROR: maps directory not found: {maps_dir}", file=sys.stderr)
        sys.exit(1)
    if not info_path.exists():
        print(f"ERROR: map_infos.json not found: {info_path}", file=sys.stderr)
        sys.exit(1)

    map_infos: dict[str, dict] = json.loads(info_path.read_text(encoding="utf-8"))

    # Collect all map file ids
    map_file_ids: set[int] = set()
    for fname in maps_dir.iterdir():
        if fname.suffix == ".json" and fname.stem.startswith("Map"):
            try:
                map_file_ids.add(int(fname.stem[3:]))
            except ValueError:
                pass

    info_ids: set[int] = {int(k) for k in map_infos}

    # ------------------------------------------------------------------
    # 1. Missing-from-map_infos report
    # ------------------------------------------------------------------
    in_files_not_infos = sorted(map_file_ids - info_ids)
    in_infos_not_files = sorted(info_ids - map_file_ids)

    print("=" * 70)
    print("MAP IDENTITY CHECK")
    print("=" * 70)
    print()
    print(f"Map files found  : {len(map_file_ids)}")
    print(f"map_infos entries: {len(info_ids)}")
    print()

    if in_files_not_infos:
        print(
            f"MISSING FROM map_infos.json ({len(in_files_not_infos)} map(s)):"
        )
        for mid in in_files_not_infos:
            mpath = maps_dir / f"Map{mid:03d}.json"
            mdata = json.loads(mpath.read_text(encoding="utf-8"))
            bgm = mdata.get("bgm", {}).get("name", "").strip()
            n_events = len(mdata.get("events", []))
            print(
                f"  Map{mid:03d}  BGM={bgm!r}  events={n_events}"
                "  (no map_infos entry — guaranteed fail-loud at mint)"
            )
    else:
        print("No maps missing from map_infos.json.")
    print()

    if in_infos_not_files:
        print(f"In map_infos but no JSON file ({len(in_infos_not_files)}):")
        for mid in in_infos_not_files:
            print(f"  Map{mid:03d}  name={map_infos[str(mid)]['name']!r}")
        print()

    # ------------------------------------------------------------------
    # 2. Duplicate-name groups
    # ------------------------------------------------------------------
    name_to_ids: dict[str, list[int]] = defaultdict(list)
    for k, v in map_infos.items():
        name_to_ids[v["name"]].append(int(k))

    dup_groups = {
        name: sorted(ids) for name, ids in name_to_ids.items() if len(ids) > 1
    }

    print("-" * 70)
    print(f"DUPLICATE-NAME GROUPS  ({len(dup_groups)} groups)")
    print("-" * 70)

    # Surface Comet Cave / Passage Cave first (the known cross-assignment risk)
    priority_names = {"Comet Cave", "Passage Cave"}
    priority_shown: set[str] = set()
    for name in sorted(dup_groups, key=lambda n: (n not in priority_names, n)):
        ids = dup_groups[name]
        tag = "  ** KNOWN CROSS-ASSIGNMENT RISK **" if name in priority_names else ""
        print(f"  {name!r} x{len(ids)}: maps {ids}{tag}")
        if name in priority_names:
            priority_shown.add(name)
            for mid in ids:
                info_entry = map_infos.get(str(mid), {})
                parent_path = _parent_path(mid, map_infos)
                mpath = maps_dir / f"Map{mid:03d}.json"
                bgm = ""
                if mpath.exists():
                    md = json.loads(mpath.read_text(encoding="utf-8"))
                    bgm = md.get("bgm", {}).get("name", "").strip()
                print(
                    f"      Map{mid:03d}  BGM={bgm!r}"
                    f"  parent_path=[{parent_path}]"
                )

    print()

    # ------------------------------------------------------------------
    # 3. Free-signal mismatch candidates
    # ------------------------------------------------------------------
    print("-" * 70)
    print("SIGNAL-VS-INFOS MISMATCH CANDIDATES")
    print("(heuristic — surface for human/wiki review; not auto-corrected)")
    print("-" * 70)

    # Build warp neighbour graph in one pass (needed for context output)
    warp_graph: dict[int, set[int]] = defaultdict(set)
    for fname in sorted(maps_dir.iterdir()):
        if fname.suffix != ".json" or not fname.stem.startswith("Map"):
            continue
        try:
            mid = int(fname.stem[3:])
        except ValueError:
            continue
        md = json.loads(fname.read_text(encoding="utf-8"))
        for nb in _warp_neighbours(mid, md):
            warp_graph[mid].add(nb)
            warp_graph[nb].add(mid)

    flagged: list[tuple[int, str, list[str]]] = []  # (map_id, info_name, reasons)

    for fname in sorted(maps_dir.iterdir()):
        if fname.suffix != ".json" or not fname.stem.startswith("Map"):
            continue
        try:
            mid = int(fname.stem[3:])
        except ValueError:
            continue

        info_entry = map_infos.get(str(mid))
        if info_entry is None:
            continue  # already reported in section 1
        info_name: str = info_entry["name"]
        info_words = _name_words(info_name)

        md = json.loads(fname.read_text(encoding="utf-8"))
        reasons: list[str] = []

        # --- BGM signal ---
        bgm_name = md.get("bgm", {}).get("name", "").strip()
        if bgm_name:
            bgm_loc_words = _bgm_words(bgm_name)
            bgm_unique = bgm_loc_words - info_words
            info_unique_vs_bgm = info_words - bgm_loc_words
            # Only flag when BOTH sides have distinctive words that contradict
            if bgm_unique and info_unique_vs_bgm:
                reasons.append(
                    f"BGM={bgm_name!r} has words {bgm_unique} absent from"
                    f" infos name (infos-unique: {info_unique_vs_bgm})"
                )

        # --- Sign-text signal ---
        sign_texts = _extract_sign_texts(md)
        for sig in sign_texts:
            sig_words = frozenset(
                w.lower() for w in re.findall(r"[A-Za-z]{4,}", sig)
            ) - _NOISE
            # Flag when the sign text contains location words that differ
            # meaningfully from the infos name
            sig_unique = sig_words - info_words
            info_unique_vs_sig = info_words - sig_words
            if sig_unique and info_unique_vs_sig:
                reasons.append(
                    f"Sign text {sig[:60]!r} has words {sig_unique}"
                    f" absent from infos name"
                )

        # --- Warp-neighbour context (informational, not a mismatch flag) ---
        # Included only for flagged maps so the reviewer has topology context.

        if reasons:
            flagged.append((mid, info_name, reasons))

    if flagged:
        print(f"\nFlagged maps ({len(flagged)}):\n")
        for mid, info_name, reasons in flagged:
            parent_path = _parent_path(mid, map_infos)
            neighbours = sorted(warp_graph[mid])
            neighbour_names = [
                f"{nb}:{map_infos[str(nb)]['name']}"
                if str(nb) in map_infos
                else str(nb)
                for nb in neighbours[:8]
            ]
            print(f"  Map{mid:03d}  infos={info_name!r}")
            print(f"    parent_path : {parent_path}")
            print(f"    neighbours  : {neighbour_names}")
            for r in reasons:
                print(f"    SIGNAL      : {r}")
            print()
    else:
        print("\nNo signal-vs-infos mismatches detected.\n")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Map files          : {len(map_file_ids)}")
    print(f"  map_infos entries  : {len(info_ids)}")
    print(f"  Missing from infos : {len(in_files_not_infos)}"
          + (f"  → map id(s): {in_files_not_infos}" if in_files_not_infos else ""))
    print(f"  Dup-name groups    : {len(dup_groups)}")
    print(f"  Flagged candidates : {len(flagged)}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--output-dir",
        metavar="DIR",
        help=(
            "Path to the uranium-build output directory. "
            "Defaults to the pipeline-resolved output path."
        ),
    )
    args = ap.parse_args()

    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        pipeline._load_dotenv()
        _, out_str = pipeline._resolve_paths()
        out_dir = Path(out_str)

    _analyse(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
