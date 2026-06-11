"""Phase 5 — MAP_* / LAYOUT_* / MAPSEC_* constant registry.

ASSIGNMENT
==========
Objective
    Be the SOURCE OF TRUTH for map names — the geometry analogue of Phase 4's
    `flag_registry`. Mint a stable, idempotent constant for every Uranium map id
    and resolve the `MAP_URANIUM_<N>` placeholders the Phase 4 warp queue is
    already emitting (Classifier 4 + the conversion agent both produce these).

The naming decision (Q2 — RESOLVED: readable names + alias header)
    Canonical names are READABLE, derived from `map_infos.json`: e.g. Uranium map
    92 ("Rochfale Town") -> MAP_ROCHFALE_TOWN / LAYOUT_ROCHFALE_TOWN /
    MAPSEC_ROCHFALE_TOWN / dir "RochfaleTown". Names are sanitized to valid C
    identifiers and de-duplicated (suffix or parent-context); fail loud if a
    unique name can't be produced.

    The frozen Phase 4 `.pory` warps still reference `MAP_URANIUM_<N>`. Rather
    than mutate that generated output, emit an ALIAS HEADER:
        #define MAP_URANIUM_92 MAP_ROCHFALE_TOWN
    so the old symbol resolves while everything new uses the readable name.
    `ALIAS_CONST_FMT` is the alias spelling; `write_alias_header()` emits them.

Inputs
    the list of Uranium map ids (the 199 MapNNN.json files), map_infos.json (names).
Outputs
    a persisted registry state (idempotent across runs) + map_groups.json
    membership + the resolution map proving every warp placeholder has a home.

Constraints
    - Idempotent + persisted: same map id -> same constant on every run.
    - Names are valid C identifiers; no collision with vanilla pokeemerald MAP_*
      (check against the fork's map_groups.json / generated constants — fail loud).

Acceptance
    [ ] same map id -> same constant across runs (persisted state)
    [ ] every MAP_URANIUM_<N> the Phase 4 queue emitted resolves
    [ ] no collision with a vanilla MAP_*; all names are valid identifiers
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Q2 (RESOLVED): canonical names are READABLE, derived from the map's display name
# (see `sanitize_name`). The raw-id `MAP_URANIUM_<N>` spelling survives only as an
# alias so the frozen Phase 4 warps still resolve (`write_alias_header`).
ALIAS_CONST_FMT = "MAP_URANIUM_{n}"  # alias only -> #define'd to the readable MAP_*
MAP_CONST_FMT = "MAP_{name}"  # name = sanitized display name, e.g. ROCHFALE_TOWN
LAYOUT_CONST_FMT = "LAYOUT_{name}"
MAPSEC_CONST_FMT = "MAPSEC_{name}"
MAP_DIR_FMT = "{dir}"  # PascalCase dir derived from the display name, e.g. RochfaleTown

DEFAULT_STATE_PATH = Path("output/uranium-build/porymap/map_constants.json")


def sanitize_name(display_name: str) -> str:
    """Turn a raw map name ("Route 11", "Rochfale Town") into a constant stem
    ("ROUTE_11", "ROCHFALE_TOWN"): fold diacritics, upper-case, non-alnum -> '_',
    collapse repeats, strip edges, prefix if it starts with a digit. Reuse
    `pbs_converter._naming.to_constant` (already does diacritic folding) rather
    than re-rolling this. Blank/junk names ("", "GAME") must be handled by the
    caller's dedup, not silently — fail loud there if a unique name can't form."""
    raise NotImplementedError("sanitize display_name -> C-identifier stem (reuse _naming)")


@dataclass(frozen=True)
class MapConstants:
    """The full set of generated names for one Uranium map (Q2: readable canonical)."""

    uranium_id: int
    map_const: str  # canonical, e.g. MAP_ROCHFALE_TOWN
    alias_const: str  # MAP_URANIUM_<N> -> #define'd to map_const for frozen .pory warps
    layout_const: str  # LAYOUT_ROCHFALE_TOWN
    mapsec_const: str  # MAPSEC_ROCHFALE_TOWN
    dir_name: str  # data/maps/<dir>, e.g. RochfaleTown
    display_name: str  # raw human name from map_infos.json (for show_map_name)


class MapConstantRegistry:
    """Mints + persists map constants; resolves Phase 4 `MAP_URANIUM_<N>` placeholders.

    Like flag_registry: deterministic, idempotent, and the ONLY thing that creates
    map names. Everything else reads from it."""

    def __init__(self, state_path: Path = DEFAULT_STATE_PATH) -> None:
        self.state_path = state_path
        self._by_id: dict[int, MapConstants] = {}

    def mint(self, uranium_id: int, display_name: str) -> MapConstants:
        """Return the (stable) constants for a map id, creating them on first sight.

        Canonical names derive from `sanitize_name(display_name)` (Q2); the alias is
        `ALIAS_CONST_FMT.format(n=uranium_id)`. De-duplicate against already-minted
        names (suffix/parent-context); fail loud if a unique name can't be formed.
        Idempotent: a second call for the same id returns the same object."""
        raise NotImplementedError("mint: readable MapConstants from display_name + dedup, record")

    def resolve_placeholder(self, placeholder: str) -> str:
        """Map a Phase 4 warp's `MAP_URANIUM_<N>` alias to the canonical `MAP_<NAME>`.

        MUST fail loud if N names a map that doesn't exist in the corpus, so a
        dangling warp is caught here, not at fork assembly (Phase 7)."""
        raise NotImplementedError("resolve_placeholder: validate N exists, return canonical name")

    def write_alias_header(self, out_path: Path) -> None:
        """Emit `#define MAP_URANIUM_<N> MAP_<NAME>` for every minted map so the
        frozen Phase 4 `.pory` warps resolve without rewriting generated output (Q2)."""
        raise NotImplementedError("emit the MAP_URANIUM_<N> -> canonical alias header")

    def load(self) -> None:
        """Load persisted state (idempotent re-runs). No-op if the file is absent."""
        raise NotImplementedError("load persisted map_constants.json")

    def save(self) -> None:
        """Persist state with encoding='utf-8'."""
        raise NotImplementedError("save map_constants.json")

    def write_map_groups(self, out_path: Path, group_order: list[str] | None = None) -> None:
        """Emit map_groups.json (group_order + each group's member dir names).

        Grouping (which maps belong to which gMapGroup_*) ties into 5.4/connections;
        a flat single-group first pass is acceptable to get maps building."""
        raise NotImplementedError("emit map_groups.json membership")
