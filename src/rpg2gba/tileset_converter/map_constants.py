"""Phase 5 — MAP_* / LAYOUT_* / MAPSEC_* constant registry.

ASSIGNMENT
==========
Objective
    Be the SOURCE OF TRUTH for map names — the geometry analogue of Phase 4's
    `flag_registry`. Mint a stable, idempotent constant for every Uranium map id
    and resolve the `MAP_URANIUM_<N>` placeholders the Phase 4 warp queue is
    already emitting (Classifier 4 + the conversion agent both produce these).

The naming decision (Q2 — RESOLVED: readable names + alias header)
    Canonical names are READABLE, derived from `map_infos.json` (with
    `reference/map_name_overrides.json` consulted FIRST, CLAUDE.md §4.3): e.g.
    Uranium map 92 ("Rochfale Town") -> MAP_ROCHFALE_TOWN / LAYOUT_ROCHFALE_TOWN /
    MAPSEC_ROCHFALE_TOWN / dir "RochfaleTown". Names are sanitized to valid C
    identifiers; a collision (with vanilla or another Uranium map) fails loud and
    asks for a map_name_overrides.json entry — we do NOT silently number-suffix,
    because a meaningless MAP_PNS_HOUSE_2 is worse than a loud stop.

    The frozen Phase 4 `.pory` warps still reference `MAP_URANIUM_<N>`. Rather
    than mutate that generated output, emit an ALIAS HEADER:
        #define MAP_URANIUM_92 MAP_ROCHFALE_TOWN
    so the old symbol resolves while everything new uses the readable name.

Slice note (S4 of PATHFINDER_SLICE_ROADMAP.md)
    Maps 48 and 49 share the map_infos name "\\PN's house"; the floor labels come
    from the S1 warp topology (49 has the street door -> 1F/spawn; 48 is upstairs
    -> 2F), recorded as map_name_overrides.json entries, NOT the RMXP `order`
    field (which is just editor tree order and would mislabel them).
"""
from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from ..pbs_converter._naming import load_fork_constants, to_constant

logger = logging.getLogger(__name__)

# Q2 (RESOLVED): canonical names are READABLE, derived from the map's display name
# (see `sanitize_name`). The raw-id `MAP_URANIUM_<N>` spelling survives only as an
# alias so the frozen Phase 4 warps still resolve (`write_alias_header`).
ALIAS_CONST_FMT = "MAP_URANIUM_{n}"  # alias only -> #define'd to the readable MAP_*
MAP_CONST_FMT = "MAP_{name}"  # name = sanitized display name, e.g. ROCHFALE_TOWN
LAYOUT_CONST_FMT = "LAYOUT_{name}"
MAPSEC_CONST_FMT = "MAPSEC_{name}"

DEFAULT_STATE_PATH = Path("output/uranium-build/porymap/map_constants.json")
FORK_MAP_HEADER = Path("include/constants/map_groups.h")  # fork-relative

_ALIAS_PREFIX = "MAP_URANIUM_"


def sanitize_name(display_name: str) -> str:
    """Turn a raw map name ("Route 11", "Rochfale Town") into a constant stem
    ("ROUTE_11", "ROCHFALE_TOWN") via the shared `_naming.to_constant` rule (which
    folds diacritics). Returns the part AFTER the `MAP_` prefix; an empty stem
    (blank/junk name) is the caller's to reject — `mint` fails loud."""
    return to_constant("MAP", display_name).removeprefix("MAP_")


def _sanitize_walker_label(display_name: str, max_len: int = 18) -> str:
    """Sanitize a display name for the walker menu macro string argument.

    Strips commas and double-quotes (which would break the X(...) macro arg),
    then truncates to *max_len* characters so the label fits a menu window.
    The apostrophe is kept (valid in a C string literal)."""
    cleaned = display_name.replace(",", "").replace('"', "")
    return cleaned[:max_len]


def _pascal_dir(display_name: str) -> str:
    """PascalCase directory stem ("Moki Town Player's House 1F" ->
    "MokiTownPlayersHouse1F"): fold diacritics, drop apostrophes/periods, split on
    non-alnum, upper-case each word's first letter (keeping "1F" intact)."""
    decomposed = unicodedata.normalize("NFKD", display_name)
    ascii_name = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    ascii_name = ascii_name.replace("'", "").replace(".", "")
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", ascii_name) if w)


@dataclass(frozen=True)
class MapConstants:
    """The full set of generated names for one Uranium map (Q2: readable canonical)."""

    uranium_id: int
    map_const: str  # canonical, e.g. MAP_ROCHFALE_TOWN
    alias_const: str  # MAP_URANIUM_<N> -> #define'd to map_const for frozen .pory warps
    layout_const: str  # LAYOUT_ROCHFALE_TOWN
    mapsec_const: str  # MAPSEC_ROCHFALE_TOWN
    dir_name: str  # data/maps/<dir>, e.g. RochfaleTown
    display_name: str  # raw human name (override-corrected) for show_map_name


class MapConstantRegistry:
    """Mints + persists map constants; resolves Phase 4 `MAP_URANIUM_<N>` placeholders.

    Like flag_registry: deterministic, idempotent, and the ONLY thing that creates
    map names. Everything else reads from it."""

    def __init__(
        self,
        state_path: Path = DEFAULT_STATE_PATH,
        vanilla_consts: set[str] | None = None,
    ) -> None:
        self.state_path = state_path
        self._vanilla = vanilla_consts or set()
        self._by_id: dict[int, MapConstants] = {}

    def mint(
        self, uranium_id: int, display_name: str, *, auto_disambiguate: bool = False
    ) -> MapConstants:
        """Return the (stable) constants for a map id, creating them on first sight.

        Idempotent: a second call for the same id returns the same object. Fails
        loud if the sanitized name is empty or collides with a vanilla MAP_* or an
        already-minted Uranium map (the signal to add a map_name_overrides.json
        entry — see Q2).

        `auto_disambiguate` (Map Walker only): instead of failing loud on a
        collision, suffix this map's INTERNAL constant/dir with its id
        (``MAP_COMET_CAVE`` -> ``MAP_COMET_CAVE_10``, dir ``CometCave`` ->
        ``CometCave10``). The ``display_name`` is left untouched, so the HUD/menu
        still read the real name. The full corpus has ~32 duplicate-name groups
        (multi-floor caves, "(Metro)" variants, ...) — proper identity for those is
        a Phase-5/7 fidelity job, not a prerequisite for a warps-only debug walker.
        The strict default is kept for the real pipeline."""
        existing = self._by_id.get(uranium_id)
        if existing is not None:
            return existing

        stem = sanitize_name(display_name)
        if not stem:
            raise ValueError(
                f"map {uranium_id}: display name {display_name!r} yields an empty "
                f"constant stem; add a reference/map_name_overrides.json entry"
            )
        map_const = MAP_CONST_FMT.format(name=stem)
        dir_name = _pascal_dir(display_name)

        # Walker: resolve a collision deterministically by suffixing with the id
        # (maps are minted in sorted-id order, so the lowest id keeps the base name).
        if auto_disambiguate and self._const_taken(map_const):
            stem = f"{stem}_{uranium_id}"
            map_const = MAP_CONST_FMT.format(name=stem)
            dir_name = f"{dir_name}{uranium_id}"

        if map_const in self._vanilla:
            raise ValueError(
                f"map {uranium_id} ({display_name!r}) -> {map_const} collides with a "
                f"vanilla pokeemerald MAP_*; add a map_name_overrides.json entry"
            )
        clash = next((uid for uid, m in self._by_id.items() if m.map_const == map_const), None)
        if clash is not None:
            raise ValueError(
                f"map {uranium_id} ({display_name!r}) -> {map_const} collides with "
                f"already-minted map {clash}; add a map_name_overrides.json entry"
            )

        constants = MapConstants(
            uranium_id=uranium_id,
            map_const=map_const,
            alias_const=ALIAS_CONST_FMT.format(n=uranium_id),
            layout_const=LAYOUT_CONST_FMT.format(name=stem),
            mapsec_const=MAPSEC_CONST_FMT.format(name=stem),
            dir_name=dir_name,
            display_name=display_name,
        )
        self._by_id[uranium_id] = constants
        logger.info("minted map %d -> %s (dir %s)", uranium_id, map_const, constants.dir_name)
        return constants

    def _const_taken(self, map_const: str) -> bool:
        """Whether `map_const` already collides with a vanilla or minted map."""
        return map_const in self._vanilla or any(
            m.map_const == map_const for m in self._by_id.values()
        )

    def get(self, uranium_id: int) -> MapConstants:
        """The minted constants for an id (KeyError if not minted)."""
        return self._by_id[uranium_id]

    def resolve_placeholder(self, placeholder: str) -> str:
        """Map a Phase 4 warp's `MAP_URANIUM_<N>` alias to the canonical `MAP_<NAME>`.

        Fails loud if N names a map that wasn't minted, so a dangling warp is caught
        here, not at fork assembly (Phase 7)."""
        if not placeholder.startswith(_ALIAS_PREFIX):
            raise ValueError(f"not a Uranium map placeholder: {placeholder!r}")
        try:
            n = int(placeholder[len(_ALIAS_PREFIX):])
        except ValueError:
            raise ValueError(f"malformed placeholder {placeholder!r}") from None
        constants = self._by_id.get(n)
        if constants is None:
            raise KeyError(
                f"unresolved warp placeholder {placeholder}: Uranium map {n} not "
                f"minted (dangling warp — strip it or include the map in the slice)"
            )
        return constants.map_const

    def write_alias_header(self, out_path: Path) -> None:
        """Emit `#define MAP_URANIUM_<N> MAP_<NAME>` for every minted map so the
        frozen Phase 4 `.pory` warps resolve without rewriting generated output (Q2)."""
        lines = [
            "// Auto-generated by tileset_converter/map_constants.py — DO NOT EDIT.",
            "// Resolves frozen Phase-4 .pory MAP_URANIUM_<N> warp placeholders to the",
            "// canonical readable MAP_<NAME> (Q2 alias header).",
            "#ifndef GUARD_URANIUM_MAP_ALIASES_H",
            "#define GUARD_URANIUM_MAP_ALIASES_H",
            "",
        ]
        lines += [
            f"#define {self._by_id[uid].alias_const} {self._by_id[uid].map_const}"
            for uid in sorted(self._by_id)
        ]
        lines += ["", "#endif // GUARD_URANIUM_MAP_ALIASES_H", ""]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")

    def write_walker_maps_header(self, slice_map_ids: list[int], out_path: Path) -> None:
        """Emit the Map Walker menu macros for the debug jump-menu.

        Generates two macros to ``engine/include/uranium_walker_maps.h``:
        - ``URANIUM_WALKER_MAP_COUNT`` — number of maps in *slice_map_ids*.
        - ``URANIUM_WALKER_MAP_LIST(X)`` — X-macro iterating the slice maps in
          *slice_map_ids* order; each entry is
          ``X(MAP_CONSTANT, COMPOUND_STRING("Label"))``.

        The C agent's ``uranium_map_walker.c`` ``#include``s this header.
        All maps in *slice_map_ids* must already be minted; fails loud otherwise.
        Idempotent: same inputs produce byte-identical output."""
        count = len(slice_map_ids)
        x_lines: list[str] = []
        for uid in slice_map_ids:
            consts = self._by_id[uid]
            # Prefix the Uranium map id so labels are unique even when two display
            # names truncate to the same text (e.g. the player's-house floors). The
            # id is also the handle the slice is navigated by (SLICE_MAP_IDS) and,
            # being leftmost, is never clipped by the menu window.
            label = f"{uid} {_sanitize_walker_label(consts.display_name, max_len=24)}"
            # COMPOUND_STRING (not bare _()) — the label is consumed as a `const u8 *`
            # struct field; _() alone expands to a braced byte list (only valid for a
            # `const u8 name[]`), COMPOUND_STRING wraps it in a compound literal.
            x_lines.append(f'    X({consts.map_const}, COMPOUND_STRING("{label}"))')

        lines: list[str] = [
            "// GENERATED by rpg2gba assembler from SLICE_MAP_IDS"
            " (src/rpg2gba/tileset_converter/map_set.py). DO NOT EDIT.",
            f"#define URANIUM_WALKER_MAP_COUNT {count}",
            "#define URANIUM_WALKER_MAP_LIST(X) \\",
        ]
        for i, x_line in enumerate(x_lines):
            if i < count - 1:
                lines.append(x_line + " \\")
            else:
                lines.append(x_line)
        lines.append("")  # trailing newline after the last X-line
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="utf-8")

    def load(self) -> None:
        """Load persisted state (idempotent re-runs). No-op if the file is absent."""
        if not self.state_path.exists():
            return
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        self._by_id = {int(uid): MapConstants(**rec) for uid, rec in raw.items()}

    def save(self) -> None:
        """Persist state with encoding='utf-8' (sorted by id for stable diffs)."""
        state = {str(uid): asdict(self._by_id[uid]) for uid in sorted(self._by_id)}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    def write_map_groups(
        self,
        out_path: Path,
        group_order: list[str] | None = None,
        group_name: str = "gMapGroup_Uranium",
    ) -> None:
        """Emit map_groups.json membership (a flat single group for v1; grouping
        proper ties into 5.4/connections). Members are the minted dir names, id-sorted."""
        members = [self._by_id[uid].dir_name for uid in sorted(self._by_id)]
        doc = {"group_order": group_order or [group_name], group_name: members}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


# --- module helpers (input loading + the slice driver) -----------------------

def load_display_names(
    map_infos_path: Path, overrides_path: Path | None = None
) -> dict[int, str]:
    """Merge `map_infos.json` names with `map_name_overrides.json` (overrides win,
    CLAUDE.md §4.3). Returns {uranium_id: display_name}."""
    infos = json.loads(Path(map_infos_path).read_text(encoding="utf-8"))
    names = {
        int(k): v["name"]
        for k, v in infos.items()
        if isinstance(v, dict) and v.get("name")
    }
    if overrides_path is not None and Path(overrides_path).exists():
        raw = json.loads(Path(overrides_path).read_text(encoding="utf-8"))
        for k, v in raw.get("overrides", {}).items():
            names[int(k)] = v["display_name"]
    return names


def load_vanilla_map_consts(fork_path: Path | None = None) -> set[str]:
    """The fork's vanilla MAP_* set (the collision oracle). Resolves the fork from
    `$RPG2GBA_POKEEMERALD` if `fork_path` is omitted; empty set if unreachable."""
    if fork_path is None:
        env = os.environ.get("RPG2GBA_POKEEMERALD")
        fork_path = Path(env) if env else None
    if fork_path is None:
        return set()
    return load_fork_constants(Path(fork_path) / FORK_MAP_HEADER, "MAP")


def build_map_constants(
    map_ids: list[int],
    *,
    map_infos_path: Path,
    overrides_path: Path | None = None,
    fork_path: Path | None = None,
    state_path: Path = DEFAULT_STATE_PATH,
    alias_header_path: Path | None = None,
    map_groups_path: Path | None = None,
    auto_disambiguate: bool = False,
) -> MapConstantRegistry:
    """Mint constants for `map_ids` (sorted, deterministic), persist state, and
    optionally emit the alias header + map_groups.json. Used by S8 assembly and the
    slice test.

    `auto_disambiguate` (Map Walker) suffixes duplicate-name maps' internal
    constants with their id instead of failing loud — see `MapConstantRegistry.mint`."""
    names = load_display_names(map_infos_path, overrides_path)
    registry = MapConstantRegistry(state_path, load_vanilla_map_consts(fork_path))
    registry.load()  # idempotent: reuse already-minted constants
    for uid in sorted(map_ids):
        if uid not in names:
            raise KeyError(f"map {uid} has no name in map_infos/overrides")
        registry.mint(uid, names[uid], auto_disambiguate=auto_disambiguate)
    registry.save()
    if alias_header_path is not None:
        registry.write_alias_header(alias_header_path)
    if map_groups_path is not None:
        registry.write_map_groups(map_groups_path)
    return registry
