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

import io
import json
import logging
import os
import re
import subprocess
import tarfile
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

        Idempotent: a second call with the SAME resulting identity returns the
        existing object untouched, no log. Fails loud if the sanitized name is
        empty or collides with a vanilla MAP_* or an already-minted Uranium map
        (the signal to add a map_name_overrides.json entry — see Q2).

        DRIFT: if this id already has persisted state but `display_name` now
        implies a different identity (typically a map_name_overrides.json edit
        landing after the id was first minted, e.g. by the Map Walker's
        auto_disambiguate run), the id is RE-MINTED from the current
        display_name — replacing the stale entry, freeing the old constant for
        reuse, and logging at WARNING (CLAUDE.md §4.3: overrides are the source
        of truth, not whatever got persisted first). The re-mint is
        collision-checked exactly like a fresh mint.

        `auto_disambiguate` (Map Walker only): instead of failing loud on a
        collision, suffix this map's INTERNAL constant/dir with its id
        (``MAP_COMET_CAVE`` -> ``MAP_COMET_CAVE_10``, dir ``CometCave`` ->
        ``CometCave10``). The ``display_name`` is left untouched, so the HUD/menu
        still read the real name. The full corpus has ~32 duplicate-name groups
        (multi-floor caves, "(Metro)" variants, ...) — proper identity for those is
        a Phase-5/7 fidelity job, not a prerequisite for a warps-only debug walker.
        The strict default is kept for the real pipeline. A walker-suffixed
        identity is NOT drift on its own — re-deriving the same suffix from the
        same display_name is the idempotent no-op path below."""
        existing = self._by_id.get(uranium_id)

        stem = sanitize_name(display_name)
        if not stem:
            raise ValueError(
                f"map {uranium_id}: display name {display_name!r} yields an empty "
                f"constant stem; add a reference/map_name_overrides.json entry"
            )
        candidate_const = MAP_CONST_FMT.format(name=stem)
        candidate_dir = _pascal_dir(display_name)

        # Walker: resolve a collision deterministically by suffixing with the id
        # (maps are minted in sorted-id order, so the lowest id keeps the base
        # name). `exclude_id` so this id's OWN prior entry never blocks its own
        # re-derivation (that's not a collision, it's the same map).
        if auto_disambiguate and self._const_taken(candidate_const, exclude_id=uranium_id):
            stem = f"{stem}_{uranium_id}"
            candidate_const = MAP_CONST_FMT.format(name=stem)
            candidate_dir = f"{candidate_dir}{uranium_id}"

        if (
            existing is not None
            and existing.map_const == candidate_const
            and existing.dir_name == candidate_dir
        ):
            return existing  # identity unchanged -> idempotent no-op, no log

        if candidate_const in self._vanilla:
            raise ValueError(
                f"map {uranium_id} ({display_name!r}) -> {candidate_const} collides "
                f"with a vanilla pokeemerald MAP_*; add a map_name_overrides.json entry"
            )
        clash = next(
            (
                uid
                for uid, m in self._by_id.items()
                if uid != uranium_id and m.map_const == candidate_const
            ),
            None,
        )
        if clash is not None:
            raise ValueError(
                f"map {uranium_id} ({display_name!r}) -> {candidate_const} collides "
                f"with already-minted map {clash}; add a map_name_overrides.json entry"
            )

        constants = MapConstants(
            uranium_id=uranium_id,
            map_const=candidate_const,
            alias_const=ALIAS_CONST_FMT.format(n=uranium_id),
            layout_const=LAYOUT_CONST_FMT.format(name=stem),
            mapsec_const=MAPSEC_CONST_FMT.format(name=stem),
            dir_name=candidate_dir,
            display_name=display_name,
        )
        self._by_id[uranium_id] = constants
        if existing is not None:
            logger.warning(
                "map %d identity drift: %s (dir %s) -> %s (dir %s); display name "
                "now %r (was %r) — re-minted from current display name "
                "(likely a map_name_overrides.json edit)",
                uranium_id,
                existing.map_const,
                existing.dir_name,
                constants.map_const,
                constants.dir_name,
                display_name,
                existing.display_name,
            )
        else:
            logger.info(
                "minted map %d -> %s (dir %s)", uranium_id, candidate_const, candidate_dir
            )
        return constants

    def _const_taken(self, map_const: str, *, exclude_id: int | None = None) -> bool:
        """Whether `map_const` already collides with a vanilla or minted map
        (other than `exclude_id` itself, when re-deriving that id's own identity)."""
        return map_const in self._vanilla or any(
            uid != exclude_id and m.map_const == map_const for uid, m in self._by_id.items()
        )

    def get(self, uranium_id: int) -> MapConstants:
        """The minted constants for an id (KeyError if not minted)."""
        return self._by_id[uranium_id]

    def minted_ids(self) -> list[int]:
        """Every minted Uranium map id, ascending.

        The public way to enumerate state; consumers must not walk `_by_id`.
        """
        return sorted(self._by_id)

    def map_const_to_uranium_id(self) -> dict[str, int]:
        """Reverse index: `MAP_*` constant -> Uranium map id.

        Minting is one-directional (id -> constants), but two consumers need
        the reverse and this class is the one source of truth for map names
        (CLAUDE.md 4.3), so the reverse index belongs here rather than being
        re-derived. Both callers previously forked it -- the playtest beat
        framework hand-parsed the persisted JSON and the emulator's map-id
        bridge reached into `_by_id` -- which is the promote-on-second-use
        case Q6 decided must become a parameterized shared helper rather
        than two implementations.

        Fails loud on a collision instead of silently keeping one winner: two
        ids sharing a constant means minting is broken, and `mint` already
        guards against it, so reaching here is a real invariant violation.
        """
        by_const: dict[str, int] = {}
        for uid in sorted(self._by_id):
            map_const = self._by_id[uid].map_const
            if map_const in by_const:
                raise ValueError(
                    f"map constant {map_const!r} is claimed by both Uranium "
                    f"map {by_const[map_const]} and map {uid} -- the minted "
                    f"state at {self.state_path} is not a bijection")
            by_const[map_const] = uid
        return by_const

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
    # Split pieces are named by reference/split_maps.json (rpg2gba.map_split).
    from rpg2gba.map_split.spec import split_specs

    for spec in split_specs().values():
        for piece in spec.pieces:
            names[piece.uid(spec.origin)] = piece.name
    return names


def _git_toplevel(path: Path) -> Path | None:
    """The git work tree containing `path`, or None if it isn't inside one
    (git missing, not a repo, etc.) — callers treat None as "can't use git"."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    return Path(result.stdout.strip())


def _load_vanilla_map_ids_pristine(fork_path: Path) -> set[str] | None:
    """The real vanilla MAP_* set, read from git HEAD, never the working tree.

    `include/constants/map_groups.h` — what `load_fork_constants` would read —
    is itself gitignored/build-generated in pokeemerald-expansion, upstream
    convention (`engine/include/constants/.gitignore`): it's never a committed
    file, so there's no pristine version of it to fall back to. Once
    `fork_path` is a slice-assembled working tree, the generated header also
    carries OUR OWN injected Uranium `MAP_*` constants (e.g. `MAP_MOKI_TOWN`),
    which then misreport as vanilla collisions (CLAUDE.md §4.7 spirit: verify
    against real fork state, not a contaminated one — mirrors how
    `conversion_agent.fork_index` reads specials/macros from git HEAD instead
    of the working tree for the same reason).

    Reconstructs the same information from what IS committed: every
    `data/maps/<Dir>/map.json`'s `"id"` field, read in one `git archive HEAD`
    of the fork's `data/maps/` tree (~900 vanilla map dirs; a per-file `git
    show` loop would be hundreds of subprocess calls). Uranium map dirs are
    excluded by construction — `data/maps/*/` is gitignored repo-root-side so
    pipeline-generated map dirs were never committed; only the originally
    vendored vanilla dirs are tracked.

    Returns None (caller falls back to the working-tree header read) if
    `fork_path` isn't inside a git work tree, or its `data/maps/` isn't
    tracked at HEAD there (e.g. an external, non-vendored fork checkout)."""
    toplevel = _git_toplevel(fork_path)
    if toplevel is None:
        return None
    try:
        rel_fork = fork_path.resolve().relative_to(toplevel.resolve())
    except ValueError:
        return None
    maps_dir = (rel_fork / "data" / "maps").as_posix()
    try:
        result = subprocess.run(
            ["git", "-C", str(toplevel), "archive", "HEAD", "--", maps_dir],
            capture_output=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    if not result.stdout:
        return None
    ids: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tf:
        for member in tf.getmembers():
            if not member.isfile() or not member.name.endswith("/map.json"):
                continue
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            try:
                data = json.loads(extracted.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            map_id = data.get("id")
            if isinstance(map_id, str):
                ids.add(map_id)
    return ids or None


def load_vanilla_map_consts(fork_path: Path | None = None) -> set[str]:
    """The fork's vanilla MAP_* set (the collision oracle). Resolves the fork from
    `$RPG2GBA_POKEEMERALD` if `fork_path` is omitted; empty set if unreachable.

    Prefers `_load_vanilla_map_ids_pristine` (git HEAD, immune to a built
    tree's own injected Uranium constants); falls back to a plain working-tree
    header read (`load_fork_constants`) only when git isn't usable — e.g. an
    external fork checkout with no `.git`, or (best-effort) a repo where
    `data/maps/` isn't tracked."""
    if fork_path is None:
        env = os.environ.get("RPG2GBA_POKEEMERALD")
        fork_path = Path(env) if env else None
    if fork_path is None:
        return set()
    fork_path = Path(fork_path)
    pristine = _load_vanilla_map_ids_pristine(fork_path)
    if pristine is not None:
        return pristine
    return load_fork_constants(fork_path / FORK_MAP_HEADER, "MAP")


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
    # A split origin is replaced by its pieces (rpg2gba.map_split): it no longer
    # builds, and its main piece inherits its name — retire its old identity.
    from rpg2gba.map_split.ids import is_piece, origin_of

    for origin in sorted({origin_of(u) for u in map_ids if is_piece(u)}):
        if origin in registry._by_id:
            logger.info("map %d is split; retiring %s", origin, registry._by_id[origin].map_const)
            del registry._by_id[origin]
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
