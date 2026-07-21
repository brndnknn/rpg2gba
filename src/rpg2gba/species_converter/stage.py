"""W1 — species staging emitter.

Reuses the Phase-2 `pbs_converter.pokemon` **parsers** (never its emitters) to
pull real stats/types/abilities/learnsets/evolutions/dex-text for the six
starter-line species pinned in `species_converter.common.STARTER_SPECIES`, and
emits a set of *generated overlay* C fragments plus a machine-readable
manifest under `<out>/uranium-build/species/`.

This module does not touch anything under `engine/`. A later unit
(`assemble_pathfinder.py`) stages these files into the vendored fork behind
committed `URANIUM PATHFINDER SLICE` fenced include-hooks; see
`STARTER_SPECIES_PLAN.md` §3 for the hook mechanism and exact insertion
points.

Generated files (all under the output species dir, see `write_all`):

  uranium_species_constants.h   — SPECIES_* #defines chained off
                                   SPECIES_GLIMMORA_MEGA + URANIUM_SPECIES_LAST
                                   marker. Hooked into
                                   include/constants/species.h above the
                                   SPECIES_EGG line.
  uranium_pokedex_enum.h        — bare `NATIONAL_DEX_<NAME>,` enumerators.
                                   Hooked inside `enum NationalDexOrder { ... }`
                                   in include/constants/pokedex.h, before the
                                   closing brace.
  uranium_pokedex_count.h       — `#undef`/`#define NATIONAL_DEX_COUNT`.
                                   Hooked after the P_GEN_9_POKEMON `#elif`
                                   chain, before `POKEMON_SLOTS_NUMBER`.
  uranium_learnsets.h           — six `static const struct LevelUpMove` arrays.
                                   MUST be hooked at *file scope* in
                                   src/data/pokemon/species_info.h, near its
                                   existing top-of-file includes (line ~4,
                                   after `species_info/shared_front_pic_anims.h`)
                                   — NOT inside the `gSpeciesInfo[]` array. See
                                   "Plan correction" below.
  uranium_species_info.h        — six `[SPECIES_X] = {...}` gSpeciesInfo
                                   entries only (no #includes of its own —
                                   matches the vanilla `species_info/gen_N_
                                   families.h` convention, which also emit
                                   bare entries and rely on symbols already
                                   visible in the enclosing translation unit).
                                   Hooked into src/data/pokemon/species_info.h
                                   in the custom-species slot (~line 177),
                                   *inside* the `gSpeciesInfo[]` initializer.
  uranium_species_graphics.h    — INCGFX_* declarations. Hooked at the end of
                                   src/data/graphics/pokemon.h.
  uranium_cries_enum.h          — bare `CRY_<NAME>,` enum entries. Hooked into
                                   include/constants/cries.h before CRY_COUNT.
  uranium_cry_table_forward.inc — `cry Cry_<Ident>` rows. Hooked into
                                   `gCryTable::` in sound/cry_tables.inc.
  uranium_cry_table_reverse.inc — `cry_reverse Cry_<Ident>` rows, SAME ORDER
                                   as the forward table. Hooked into
                                   `gCryTable_Reverse::` in the same file.
  uranium_cry_sound_data.inc    — `.incbin` blocks. Hooked into
                                   sound/direct_sound_data.inc.
  species_manifest.json         — flat per-species record tying constants to
                                   asset paths; consumed by the capability
                                   gate (W5) and by other converter units.

**Plan correction (found while matching the real fork tree):** the plan's
`STARTER_SPECIES_PLAN.md` §3/§4-W1 describes `uranium_species_info.h`
`#include`-ing `uranium_learnsets.h` "at the top of file 2". That can't work:
file 2's OWN hook point is *inside* `gSpeciesInfo[]`'s designated-initializer
list (before its closing `};`), so a nested `#include` of a header that
declares new file-scope `static const` arrays would splice a declaration
into the middle of an initializer list — invalid C. The vanilla
`species_info/gen_N_families.h` files sidestep this by declaring zero
`#include`s themselves and relying on symbols (including their learnsets)
already being visible earlier in the same translation unit
(`src/pokemon.c` includes `data/pokemon/level_up_learnsets/gen_*.h` *before*
`data/pokemon/species_info.h`). This module follows that same pattern:
`uranium_species_info.h` has no `#include`s, and `uranium_learnsets.h` needs
its own file-scope hook, separate from the array-body hook. Both hook points
are documented above and in the write-up returned to the caller.

**Critical invariant (CLAUDE.md §4.2 + the plan's empty-overlay rule):** every
generated file is always emitted, and is a semantic no-op (empty guarded body)
when the selected-species list is empty. `write_all(..., selected=())`
produces a pristine-equivalent overlay set. Emitting twice with the same
inputs produces byte-identical output — no timestamps in generated content.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from rpg2gba.pbs_converter import pokemon
from rpg2gba.pbs_converter._c_emit import escape_c_string, generated_banner, wrap_header
from rpg2gba.pbs_converter._id_map import IdMap
from rpg2gba.species_converter import common
from rpg2gba.species_converter.common import STARTER_SPECIES, SpeciesSpec, gfx_ident

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.species_converter.stage"
MANIFEST_VERSION = 1

# --- Sensible defaults for fields the art converters haven't run yet --------
# The battler converter (W2) computes real bbox-derived Y offsets; until that
# manifest data exists, every staged species gets these placeholders. Callers
# may override per-species via `overrides` (keyed by internal_name) passed to
# `write_all` / `stage_species`.
DEFAULT_FRONT_PIC_Y_OFFSET = 13
DEFAULT_BACK_PIC_Y_OFFSET = 6
DEFAULT_ICON_PAL_INDEX = 0

#: `.categoryName` is `u8[13]` — 12 visible chars + NUL terminator.
CATEGORY_NAME_MAX_LEN = 12

#: Evolution method index for "Level" in `evolutions.dat` (see pokemon.py's
#: `_EVONAMES`); the only method the six starters use.
_EVO_METHOD_LEVEL = 4


@dataclass(frozen=True)
class SpeciesOverride:
    """Per-species art-derived overrides, keyed by `internal_name`."""

    front_pic_y_offset: int | None = None
    back_pic_y_offset: int | None = None
    icon_pal_index: int | None = None


@dataclass(frozen=True)
class StagedSpecies:
    """One selected species, resolved and ready to emit."""

    spec: SpeciesSpec
    fork_id: int
    record: pokemon.Species
    evolution_target_fork_id: int | None
    evolution_level: int | None
    front_pic_y_offset: int
    back_pic_y_offset: int
    icon_pal_index: int


# ===========================================================================
# Pristine-anchor reading
# ===========================================================================

_SPECIES_EGG_RE = re.compile(
    r"^#define\s+SPECIES_EGG\s+\(\s*([A-Z0-9_]+)\s*\+\s*1\s*\)\s*$", re.MULTILINE
)


def read_pristine_species_egg(engine_dir: Path) -> tuple[int, str]:
    """Read the pristine `SPECIES_EGG` value + its anchor constant name.

    Fails loud if `include/constants/species.h`'s tail doesn't match the
    expected `#define SPECIES_EGG (ANCHOR + 1)` shape this plan was verified
    against (`STARTER_SPECIES_PLAN.md` §1) — a drifted fork header is a
    silent-corruption risk, not something to paper over with a hardcoded 1573.
    """
    path = engine_dir / "include" / "constants" / "species.h"
    text = path.read_text(encoding="utf-8")
    m = _SPECIES_EGG_RE.search(text)
    if not m:
        raise ValueError(
            f"{path}: expected '#define SPECIES_EGG (ANCHOR + 1)' anchor line, not found. "
            "Fork header has drifted from the pinned shape this emitter was verified against."
        )
    anchor = m.group(1)
    # Once the committed URANIUM PATHFINDER SLICE hook is applied, SPECIES_EGG is
    # defined against the indirection macro URANIUM_SPECIES_LAST rather than a
    # numeric species constant. Follow exactly one level of aliasing, resolving
    # through the hook's `#ifndef` fallback, so this keeps reporting the PRISTINE
    # value whether or not an overlay is currently staged (the fallback always
    # names the last vanilla species). Deeper chains still fail loud.
    anchor_value: int | None = None
    resolved = anchor
    for _ in range(2):
        num = re.search(
            rf"^#define\s+{re.escape(resolved)}\s+(\d+)\s*$", text, re.MULTILINE
        )
        if num:
            anchor_value = int(num.group(1))
            break
        alias = re.search(
            rf"^#define\s+{re.escape(resolved)}\s+([A-Z0-9_]+)\s*$", text, re.MULTILINE
        )
        if not alias:
            break
        resolved = alias.group(1)
    if anchor_value is None:
        raise ValueError(
            f"{path}: anchor constant {anchor} did not resolve to a numeric #define "
            f"(stopped at {resolved}) — fork header has drifted from the pinned shape."
        )
    pristine_egg = anchor_value + 1
    if pristine_egg != common.PRISTINE_SPECIES_EGG:
        raise ValueError(
            f"{path}: pristine SPECIES_EGG read as {pristine_egg} (anchor {anchor}={anchor_value}) "
            f"but species_converter.common.PRISTINE_SPECIES_EGG={common.PRISTINE_SPECIES_EGG} — "
            "the fork header has moved; update common.py's pinned constant."
        )
    # Return the RESOLVED anchor, never the indirection macro: the generated
    # constants file chains its first species off this name and is #include-d
    # *above* the hook's `#ifndef URANIUM_SPECIES_LAST` fallback, so emitting
    # `(URANIUM_SPECIES_LAST + 1)` there would reference a macro that is still
    # undefined at that point (and that the generated file itself goes on to
    # define). Chaining off the last vanilla species is correct either way.
    return pristine_egg, resolved


def assert_fork_constants_exist(engine_dir: Path, constants: set[str], header_rel: str, prefix: str) -> None:
    """Fail loud if any of `constants` is absent from a fork header's constant set.

    Used to verify the six starters' vanilla ability constants are real,
    rather than assuming it (CLAUDE.md §4.7).
    """
    from rpg2gba.pbs_converter._naming import load_fork_constants

    known = load_fork_constants(engine_dir / header_rel, prefix)
    if not known:
        raise ValueError(f"{engine_dir / header_rel}: no {prefix}_* constants found — fork missing/unreadable")
    missing = sorted(c for c in constants if c not in known)
    if missing:
        raise ValueError(f"{header_rel}: constants not defined in fork: {missing}")


# ===========================================================================
# Parse + select
# ===========================================================================


def _reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "reference"


def load_all_species(uranium_src: Path, reference_dir: Path) -> tuple[list[pokemon.Species | None], pokemon._Resolver]:
    """Parse every species + side data via the Phase-2 parsers (no duplication)."""
    data = uranium_src / "Data"
    species = pokemon.parse_dexdata(data / "dexdata.dat")
    n = len(species) - 1
    pokemon.attach_side_data(
        species,
        level_up_moves=pokemon.parse_attacks_rs(data / "attacksRS.dat", n),
        evolutions=pokemon.parse_evolutions(data / "evolutions.dat", n),
        egg_moves=pokemon.parse_indexed_u16_list(data / "eggEmerald.dat", n),
        tutor_moves=pokemon.parse_indexed_u16_list(data / "tutor.dat", n),
        regionals_matrix=pokemon.parse_regionals(data / "regionals.dat"),
    )
    pokemon.attach_internal_names(
        species, pokemon._load_id_json(reference_dir / "uranium_data" / "species_internal_names.json")
    )
    resolver = pokemon._build_resolver(IdMap(), reference_dir)
    return species, resolver


def select_starters(
    species: list[pokemon.Species | None],
    selected: tuple[SpeciesSpec, ...] = STARTER_SPECIES,
) -> list[pokemon.Species]:
    """Pick the selected species by `uranium_id`, verifying internal names match.

    Fails loud on any mismatch — a drifted `species_internal_names.json` or a
    stale `STARTER_SPECIES` entry must not silently select the wrong record.
    """
    out: list[pokemon.Species] = []
    for spec in selected:
        rec = species[spec.uranium_id] if spec.uranium_id < len(species) else None
        if rec is None:
            raise ValueError(f"no species record at uranium_id {spec.uranium_id} ({spec.internal_name})")
        if rec.internal_name != spec.internal_name:
            raise ValueError(
                f"uranium_id {spec.uranium_id}: expected internal_name {spec.internal_name!r}, "
                f"parsed {rec.internal_name!r}"
            )
        out.append(rec)
    return out


def _pick(value: int | None, default: int) -> int:
    return default if value is None else value


def build_staged_species(
    selected_specs: tuple[SpeciesSpec, ...],
    records: list[pokemon.Species],
    pristine_species_egg: int,
    overrides: dict[str, SpeciesOverride] | None = None,
) -> list[StagedSpecies]:
    """Assign fork-append ids and resolve evolution targets within the selection.

    Fork ids are assigned by position starting at `pristine_species_egg`
    (append-only — never renumber). An evolution whose target isn't itself in
    the selection is a dangling reference and fails loud.
    """
    overrides = overrides or {}
    by_uranium_id = {spec.uranium_id: spec for spec in selected_specs}
    fork_id_by_uranium_id = {
        spec.uranium_id: pristine_species_egg + i for i, spec in enumerate(selected_specs)
    }

    staged: list[StagedSpecies] = []
    for spec, rec in zip(selected_specs, records):
        target_fork_id: int | None = None
        evo_level: int | None = None
        if rec.evolutions:
            if len(rec.evolutions) > 1:
                raise ValueError(f"{spec.internal_name}: expected at most one evolution, got {rec.evolutions}")
            method_idx, param, target_uid = rec.evolutions[0]
            if method_idx != _EVO_METHOD_LEVEL:
                raise ValueError(
                    f"{spec.internal_name}: expected EVO_LEVEL (method {_EVO_METHOD_LEVEL}), "
                    f"got method {method_idx} — W1 only handles the starters' known level evolutions"
                )
            if target_uid not in by_uranium_id:
                raise ValueError(
                    f"{spec.internal_name}: evolution targets uranium_id {target_uid}, which is not "
                    "in the selected species — dangling reference"
                )
            target_fork_id = fork_id_by_uranium_id[target_uid]
            evo_level = param

        override = overrides.get(spec.internal_name)
        staged.append(
            StagedSpecies(
                spec=spec,
                fork_id=fork_id_by_uranium_id[spec.uranium_id],
                record=rec,
                evolution_target_fork_id=target_fork_id,
                evolution_level=evo_level,
                front_pic_y_offset=_pick(override and override.front_pic_y_offset, DEFAULT_FRONT_PIC_Y_OFFSET),
                back_pic_y_offset=_pick(override and override.back_pic_y_offset, DEFAULT_BACK_PIC_Y_OFFSET),
                icon_pal_index=_pick(override and override.icon_pal_index, DEFAULT_ICON_PAL_INDEX),
            )
        )
    return staged


# ===========================================================================
# C emit helpers
# ===========================================================================


def _no_op_note() -> str:
    return "// (no Uranium species selected — this overlay is a no-op)\n"


def emit_species_constants(staged: list[StagedSpecies], anchor: str) -> str:
    """`uranium_species_constants.h`: chained #defines + URANIUM_SPECIES_LAST."""
    banner = generated_banner("dexdata.dat + STARTER_SPECIES", GENERATOR, timestamp=False)
    if not staged:
        return wrap_header("GUARD_URANIUM_SPECIES_CONSTANTS_H", _no_op_note(), banner=banner)
    lines: list[str] = []
    prev = anchor
    for s in staged:
        lines.append(f"#define {s.spec.constant} ({prev} + 1)")
        prev = s.spec.constant
    lines.append(f"#define URANIUM_SPECIES_LAST {prev}")
    return wrap_header("GUARD_URANIUM_SPECIES_CONSTANTS_H", "\n".join(lines), banner=banner)


def emit_pokedex_ids(staged: list[StagedSpecies], anchor: str) -> str:
    """`uranium_pokedex_ids.h`: chained `NATIONAL_DEX_*` #defines off `anchor`
    (the enum's real last member — NOT `NATIONAL_DEX_COUNT`, which this same
    header redefines below; chaining off a value we're about to rewrite would
    make the ids depend on macro-expansion order) plus the `NATIONAL_DEX_COUNT`
    override. `enum NationalDexOrder`'s hook site sits *outside* the enum body
    (a nested `#include` inside an enum breaks `tools/preproc`'s scanner — see
    `include/constants/pokedex.h`'s own hook comment), so these are plain
    #defines, matching `emit_species_constants`'s pattern, not bare enumerators.
    `NATIONAL_DEX_COUNT` is NOT self-sizing in the fork (an `#elif` chain
    pinned to a named entry) — skipping the override here would silently
    under-count the dex and underflow `dexSeen[]`/`dexCaught[]` on send-out."""
    banner = generated_banner("STARTER_SPECIES (regional dex is real Tandor space)", GENERATOR, timestamp=False)
    if not staged:
        return wrap_header("GUARD_URANIUM_POKEDEX_IDS_H", _no_op_note(), banner=banner)
    lines: list[str] = []
    prev = anchor
    for s in staged:
        lines.append(f"#define {s.spec.dex_constant} ({prev} + 1)")
        prev = s.spec.dex_constant
    lines.append("")
    lines.append("#undef NATIONAL_DEX_COUNT")
    lines.append(f"#define NATIONAL_DEX_COUNT {staged[-1].spec.dex_constant}")
    return wrap_header("GUARD_URANIUM_POKEDEX_IDS_H", "\n".join(lines), banner=banner)


def _learnset_symbol(spec: SpeciesSpec) -> str:
    return f"sUraniumLevelUpLearnset_{spec.internal_name}"


# Uranium signature moves (by move_id, from attacksRS.dat/moves.dat) in the
# six starter learnsets that have no vanilla pokeemerald-expansion analog
# (fork ships no custom move data — out of STARTER_SPECIES_PLAN.md scope,
# §7). Substituted with the closest existing fork move rather than dropped
# or invented; a real conversion is Phase-7 debt. User-approved substitution
# (2026-07-19): move 568 = FLAMEIMPACT (Raptorch/Archilles signature, power
# 65/physical/Fire/priority+2) -> MOVE_FIRE_FANG (power 65/physical/Fire,
# closest mechanical match modulo the priority clause).
_MOVE_SUBSTITUTIONS: dict[int, str] = {
    568: "MOVE_FIRE_FANG",  # FLAMEIMPACT
}


def emit_learnsets(staged: list[StagedSpecies], r: pokemon._Resolver) -> str:
    banner = generated_banner("attacksRS.dat", GENERATOR, timestamp=False)
    if not staged:
        return banner + _no_op_note()
    blocks: list[str] = []
    for s in staged:
        rows = [
            f"    LEVEL_UP_MOVE({lvl:>3}, {_MOVE_SUBSTITUTIONS.get(mv, r.move_constant(mv))}),"
            for lvl, mv in s.record.level_up_moves
        ]
        body = "\n".join(rows)
        blocks.append(
            f"static const struct LevelUpMove {_learnset_symbol(s.spec)}[] = {{\n"
            + (body + "\n" if body else "")
            + "    LEVEL_UP_END\n};"
        )
    return banner + "\n" + "\n\n".join(blocks) + "\n"


def _gfx_symbol(kind: str, spec: SpeciesSpec) -> str:
    return f"{kind}_{gfx_ident(spec)}"


def emit_species_info(staged: list[StagedSpecies], r: pokemon._Resolver) -> str:
    """Bare `[SPECIES_X] = {...},` entries only — no `#include`s.

    Matches the vanilla `species_info/gen_N_families.h` convention: this
    fragment is spliced *inside* the `gSpeciesInfo[]` initializer, so it must
    not itself contain top-level declarations or includes of headers that
    aren't already guaranteed-included earlier in the translation unit. See
    the module docstring's "Plan correction" note — `uranium_learnsets.h`
    needs a separate, file-scope hook, not an `#include` from this file.
    """
    banner = generated_banner(
        "dexdata.dat (+ attacksRS/evolutions + species_kinds/species_pokedex sidecars)",
        GENERATOR,
        timestamp=False,
    )
    if not staged:
        return banner + "\n" + _no_op_note()

    entries: list[str] = []
    for s in staged:
        rec = s.record
        spec = s.spec
        lines: list[str] = [f"    [{spec.constant}] =", "    {"]

        for fld, val in zip(pokemon._STAT_FIELDS, rec.base_stats):
            lines.append(f"        .{fld} = {val},")

        t1 = r.type_constant(rec.type1)
        t2 = r.type_constant(rec.type2)
        types = f"MON_TYPES({t1})" if t1 == t2 else f"MON_TYPES({t1}, {t2})"
        lines.append(f"        .types = {types},")

        lines.append(f"        .catchRate = {rec.rareness},")
        lines.append(f"        .expYield = {rec.base_exp},")
        for fld, val in zip(pokemon._EV_FIELDS, rec.effort_points):
            if val:
                lines.append(f"        .{fld} = {min(val, 3)},")

        gender = "MON_GENDERLESS" if rec.gender_rate == 255 else str(rec.gender_rate)
        lines.append(f"        .genderRatio = {gender},")
        lines.append(f"        .eggCycles = {round(rec.steps_to_hatch / 256)},")
        lines.append(f"        .friendship = {rec.happiness},")

        growth = pokemon._GROWTH_RATE_BY_INDEX.get(rec.growth_rate)
        if growth is None:
            raise ValueError(f"{spec.internal_name}: unknown growth rate index {rec.growth_rate}")
        lines.append(f"        .growthRate = {growth},")

        eg1 = pokemon._EGG_GROUP_BY_INDEX.get(rec.compatibility[0])
        eg2 = pokemon._EGG_GROUP_BY_INDEX.get(rec.compatibility[1])
        if eg1 is None or eg2 is None:
            raise ValueError(f"{spec.internal_name}: unknown egg group {rec.compatibility}")
        groups = f"MON_EGG_GROUPS({eg1})" if eg1 == eg2 else f"MON_EGG_GROUPS({eg1}, {eg2})"
        lines.append(f"        .eggGroups = {groups},")

        a1 = r.ability_constant(rec.abilities[0])
        a2 = r.ability_constant(rec.abilities[1])
        hidden = r.ability_constant(rec.hidden_abilities[0])
        lines.append(f"        .abilities = {{ {a1}, {a2}, {hidden} }},")
        extra_hidden = [h for h in rec.hidden_abilities[1:] if h]
        if extra_hidden:
            logger.warning(
                "%s: has %d extra hidden ability slot(s) beyond the fork's single slot "
                "(Uranium-ism, dropped): %s",
                spec.internal_name,
                len(extra_hidden),
                [r.ability_constant(h) for h in extra_hidden],
            )

        color = pokemon._BODY_COLOR_BY_INDEX.get(rec.color)
        if color is None:
            raise ValueError(f"{spec.internal_name}: unknown body color index {rec.color}")
        lines.append(f"        .bodyColor = {color},")

        lines.append(f"        .height = {rec.height_dm},")
        lines.append(f"        .weight = {rec.weight_hg},")

        lines.append(f'        .speciesName = _("{escape_c_string(r.name(rec.id))}"),')
        kind = r.kind(rec.id)
        if len(kind) > CATEGORY_NAME_MAX_LEN:
            raise ValueError(
                f"{spec.internal_name}: categoryName {kind!r} is {len(kind)} chars, "
                f"exceeds u8[13] limit of {CATEGORY_NAME_MAX_LEN}"
            )
        if kind:
            lines.append(f'        .categoryName = _("{escape_c_string(kind)}"),')
        dex = r.dex(rec.id)
        if dex:
            lines.append(f'        .description = COMPOUND_STRING("{escape_c_string(dex)}"),')

        lines.append(f"        .cryId = {spec.cry_constant},")
        lines.append(f"        .natDexNum = {spec.dex_constant},")

        lines.append(f"        .frontPic = {_gfx_symbol('gMonFrontPic', spec)},")
        lines.append(f"        .frontPicSize = MON_COORDS_SIZE({common.BATTLER_SIZE}, {common.BATTLER_SIZE}),")
        lines.append(f"        .frontPicYOffset = {s.front_pic_y_offset},")
        lines.append("        .frontAnimFrames = sAnims_SingleFramePlaceHolder,")
        lines.append(f"        .backPic = {_gfx_symbol('gMonBackPic', spec)},")
        lines.append(f"        .backPicSize = MON_COORDS_SIZE({common.BATTLER_SIZE}, {common.BATTLER_SIZE}),")
        lines.append(f"        .backPicYOffset = {s.back_pic_y_offset},")
        lines.append(f"        .palette = {_gfx_symbol('gMonPalette', spec)},")
        lines.append(f"        .shinyPalette = {_gfx_symbol('gMonShinyPalette', spec)},")
        lines.append(f"        .iconSprite = {_gfx_symbol('gMonIcon', spec)},")
        lines.append(f"        .iconPalIndex = {s.icon_pal_index},")

        lines.append(f"        .levelUpLearnset = {_learnset_symbol(spec)},")

        if s.evolution_target_fork_id is not None:
            target_const = f"SPECIES_{_internal_name_for_fork_id(staged, s.evolution_target_fork_id)}"
            lines.append(
                f"        .evolutions = EVOLUTION({{EVO_LEVEL, {s.evolution_level}, {target_const}}}),"
            )

        lines.append("    },")
        entries.append("\n".join(lines))

    return banner + "\n" + "\n".join(entries) + "\n"


def _internal_name_for_fork_id(staged: list[StagedSpecies], fork_id: int) -> str:
    for s in staged:
        if s.fork_id == fork_id:
            return s.spec.internal_name
    raise ValueError(f"no staged species with fork_id {fork_id}")


def emit_graphics(staged: list[StagedSpecies]) -> str:
    banner = generated_banner("STARTER_SPECIES asset layout (common.py)", GENERATOR, timestamp=False)
    if not staged:
        return banner + _no_op_note()
    lines: list[str] = []
    for s in staged:
        spec = s.spec
        ident = gfx_ident(spec)
        d = f"{common.ENGINE_GFX_ROOT.as_posix()}/{common.asset_dir_name(spec)}"
        lines.append(
            f'const u32 gMonFrontPic_{ident}[] = INCGFX_U32("{d}/{common.FRONT_PNG}", ".4bpp.smol");'
        )
        lines.append(
            f'const u16 gMonPalette_{ident}[] = INCGFX_U16("{d}/{common.NORMAL_PAL}", ".gbapal");'
        )
        lines.append(
            f'const u32 gMonBackPic_{ident}[] = INCGFX_U32("{d}/{common.BACK_PNG}", ".4bpp.smol");'
        )
        lines.append(
            f'const u16 gMonShinyPalette_{ident}[] = INCGFX_U16("{d}/{common.SHINY_PAL}", ".gbapal");'
        )
        lines.append(f'const u8 gMonIcon_{ident}[] = INCGFX_U8("{d}/{common.ICON_PNG}", ".4bpp");')
        lines.append("")
    return banner + "\n" + "\n".join(lines).rstrip() + "\n"


def emit_cries_enum(staged: list[StagedSpecies]) -> str:
    banner = generated_banner("STARTER_SPECIES", GENERATOR, timestamp=False)
    if not staged:
        return banner + _no_op_note()
    lines = [f"    {s.spec.cry_constant}," for s in staged]
    return banner + "\n" + "\n".join(lines) + "\n"


def emit_cry_table_forward(staged: list[StagedSpecies]) -> str:
    banner = generated_banner("STARTER_SPECIES", GENERATOR, timestamp=False)
    if not staged:
        return banner + _no_op_note()
    lines = [f"\tcry Cry_{gfx_ident(s.spec)}" for s in staged]
    return banner + "\n" + "\n".join(lines) + "\n"


def emit_cry_table_reverse(staged: list[StagedSpecies]) -> str:
    banner = generated_banner("STARTER_SPECIES", GENERATOR, timestamp=False)
    if not staged:
        return banner + _no_op_note()
    lines = [f"\tcry_reverse Cry_{gfx_ident(s.spec)}" for s in staged]
    return banner + "\n" + "\n".join(lines) + "\n"


def emit_cry_sound_data(staged: list[StagedSpecies]) -> str:
    banner = generated_banner("STARTER_SPECIES", GENERATOR, timestamp=False)
    if not staged:
        return banner + _no_op_note()
    blocks: list[str] = []
    for s in staged:
        ident = gfx_ident(s.spec)
        name = common.asset_dir_name(s.spec)
        blocks.append(
            "\t.align 2\n"
            f"Cry_{ident}::\n"
            ".if TESTING == FALSE\n"
            f'\t.incbin "{common.ENGINE_CRY_ROOT.as_posix()}/{name}.bin"\n'
            ".endif"
        )
    return banner + "\n" + "\n\n".join(blocks) + "\n"


# ===========================================================================
# Manifest
# ===========================================================================


def build_manifest(
    staged: list[StagedSpecies],
    pristine_species_egg: int,
) -> dict:
    new_egg = pristine_species_egg + len(staged)
    records = []
    for s in staged:
        spec = s.spec
        ident = gfx_ident(spec)
        asset_dir = f"{common.ENGINE_GFX_ROOT.as_posix()}/{common.asset_dir_name(spec)}"
        target_name = (
            _internal_name_for_fork_id(staged, s.evolution_target_fork_id)
            if s.evolution_target_fork_id is not None
            else None
        )
        records.append(
            {
                "uranium_id": spec.uranium_id,
                "internal_name": spec.internal_name,
                "fork_species_id": s.fork_id,
                "species_constant": spec.constant,
                "national_dex_constant": spec.dex_constant,
                "cry_constant": spec.cry_constant,
                "gfx_ident": ident,
                "asset_dir": asset_dir,
                "art_files": {
                    "front": f"{asset_dir}/{common.FRONT_PNG}",
                    "back": f"{asset_dir}/{common.BACK_PNG}",
                    "normal_pal": f"{asset_dir}/{common.NORMAL_PAL}",
                    "shiny_pal": f"{asset_dir}/{common.SHINY_PAL}",
                    "icon": f"{asset_dir}/{common.ICON_PNG}",
                },
                "cry_wav_relpath": f"{common.ENGINE_CRY_ROOT.as_posix()}/{common.asset_dir_name(spec)}.wav",
                "front_pic_y_offset": s.front_pic_y_offset,
                "back_pic_y_offset": s.back_pic_y_offset,
                "icon_pal_index": s.icon_pal_index,
                "evolves_to_species_constant": f"SPECIES_{target_name}" if target_name else None,
                "evolution_level": s.evolution_level,
            }
        )
    return {
        "version": MANIFEST_VERSION,
        "generator": GENERATOR,
        "pristine_species_egg": pristine_species_egg,
        "new_species_egg": new_egg,
        "species": records,
    }


# ===========================================================================
# Top-level entry point
# ===========================================================================

# Vanilla ability constants the six starters must resolve to; verified
# against the fork rather than assumed (CLAUDE.md §4.7).
_EXPECTED_ABILITIES = {
    "ABILITY_BATTLE_ARMOR",
    "ABILITY_OVERGROW",
    "ABILITY_FLAME_BODY",
    "ABILITY_BLAZE",
    "ABILITY_STATIC",
    "ABILITY_TORRENT",
}


def write_all(
    *,
    uranium_src: Path,
    engine_dir: Path,
    out_dir: Path,
    selected: tuple[SpeciesSpec, ...] = STARTER_SPECIES,
    overrides: dict[str, SpeciesOverride] | None = None,
) -> dict:
    """Parse, select, and emit the full overlay set + manifest.

    `out_dir` is the species staging directory itself (typically
    `$RPG2GBA_OUTPUT/uranium-build/species`); this function writes directly
    into it (creating it if needed) rather than nesting another `species/`
    level, so callers control the exact path per `common.SPECIES_OUT_SUBDIR`.

    Returns the manifest dict (also written to `species_manifest.json`).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pristine_egg, anchor = read_pristine_species_egg(engine_dir)

    if selected:
        reference_dir = _reference_dir()
        species, resolver = load_all_species(uranium_src, reference_dir)
        records = select_starters(species, selected)
        assert_fork_constants_exist(
            engine_dir, _EXPECTED_ABILITIES, "include/constants/abilities.h", "ABILITY"
        )
        assert_fork_constants_exist(
            engine_dir,
            {common.PRISTINE_NATIONAL_DEX_ANCHOR},
            "include/constants/pokedex.h",
            "NATIONAL_DEX",
        )
        staged = build_staged_species(selected, records, pristine_egg, overrides)
        assert_no_gfx_symbol_collisions(engine_dir, staged)
    else:
        resolver = None
        staged = []

    _write(out_dir / "uranium_species_constants.h", emit_species_constants(staged, anchor))
    _write(
        out_dir / "uranium_pokedex_ids.h",
        emit_pokedex_ids(staged, common.PRISTINE_NATIONAL_DEX_ANCHOR),
    )
    _write(out_dir / "uranium_learnsets.h", emit_learnsets(staged, resolver))
    _write(out_dir / "uranium_species_info.h", emit_species_info(staged, resolver))
    _write(out_dir / "uranium_species_graphics.h", emit_graphics(staged))
    _write(out_dir / "uranium_cries_enum.h", emit_cries_enum(staged))
    _write(out_dir / "uranium_cry_table_forward.inc", emit_cry_table_forward(staged))
    _write(out_dir / "uranium_cry_table_reverse.inc", emit_cry_table_reverse(staged))
    _write(out_dir / "uranium_cry_sound_data.inc", emit_cry_sound_data(staged))

    manifest = build_manifest(staged, pristine_egg)
    (out_dir / common.MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    logger.info("staged %d Uranium species (fork ids %d..%d)", len(staged), pristine_egg, pristine_egg + len(staged) - 1)
    return manifest


def assert_no_gfx_symbol_collisions(engine_dir: Path, staged: list[StagedSpecies]) -> None:
    """Fail loud if any generated gfx symbol name collides with an existing one."""
    path = engine_dir / "src" / "data" / "graphics" / "pokemon.h"
    text = path.read_text(encoding="utf-8")
    existing = set(re.findall(r"\bg(?:MonFrontPic|MonBackPic|MonPalette|MonShinyPalette|MonIcon)_(\w+)\b", text))
    collisions = [gfx_ident(s.spec) for s in staged if gfx_ident(s.spec) in existing]
    if collisions:
        raise ValueError(f"{path}: gfx symbol identifier(s) already used by an existing species: {collisions}")


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
