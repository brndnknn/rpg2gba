"""Shared contract for the species converter units.

Everything here is *pinned* — the staging emitter, battler converter, icon
converter and cry converter all agree on these names and paths so their
outputs link up without any of them importing each other.

Fork-id assignment is append-only: the first Uranium species takes the value
`SPECIES_EGG` currently holds in the pristine fork, and `SPECIES_EGG` is
pushed up past the block. Existing species are never renumbered.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Value of SPECIES_EGG in the pristine fork (engine/ @ 21c24202). The staging
# emitter re-derives this from the header and fails loud on mismatch; it is
# duplicated here only so the art/cry units can be tested standalone.
PRISTINE_SPECIES_EGG = 1573

# `enum NationalDexOrder`'s last member in the pristine fork (engine/ @
# 21c24202) — always present regardless of P_GEN_*/P_*_FORMS config, since the
# enum lists every possible dex entry and only NATIONAL_DEX_COUNT varies by
# config. Staged dex ids chain off this as a compile-time constant (never off
# NATIONAL_DEX_COUNT, which the same generated header redefines — chaining off
# a value the header itself rewrites would make the ids depend on evaluation
# order within the translation unit).
PRISTINE_NATIONAL_DEX_ANCHOR = "NATIONAL_DEX_PECHARUNT"


@dataclass(frozen=True)
class SpeciesSpec:
    """One species selected for conversion.

    `uranium_id` is the 1-based `dexdata.dat` record index. `internal_name` is
    Uranium's internal (upper-snake) name and is the key into
    `reference/uranium_id_map.json`.
    """

    uranium_id: int
    internal_name: str

    @property
    def constant(self) -> str:
        return f"SPECIES_{self.internal_name}"

    @property
    def cry_constant(self) -> str:
        return f"CRY_{self.internal_name}"

    @property
    def dex_constant(self) -> str:
        return f"NATIONAL_DEX_{self.internal_name}"


# Originally just the six starter-line species; the name STARTER_SPECIES is
# now a misnomer (kept anyway — a rename would have to reach into
# trainer_converter, which this unit does not own; see the Route-1 comment
# below) but the *contents* are now "starters + whatever the built chapters'
# trainers and encounters need". Order is load-bearing: fork ids are
# assigned by position, so this list is append-only — never reorder or
# insert; add new species at the end.
STARTER_SPECIES: tuple[SpeciesSpec, ...] = (
    SpeciesSpec(1, "ORCHYNX"),
    SpeciesSpec(2, "METALYNX"),
    SpeciesSpec(3, "RAPTORCH"),
    SpeciesSpec(4, "ARCHILLES"),
    SpeciesSpec(5, "ELETUX"),
    SpeciesSpec(6, "ELECTRUXO"),
    # --- Route 1 trainer-party species (2026-08-05) -------------------------
    # FARTOG, BIRBIE, BAREWL, CUBBUG, CHYINMUNK, TONEMY, OWTEN are the seven
    # species Route 1's trainer parties actually use. Each one evolves
    # (single- or two-stage), and `stage.build_staged_species` fails loud on
    # a staged species whose evolution target isn't itself staged (a
    # dangling reference) — so every intermediate/final evolution stage is
    # appended alongside its pre-evolution rather than left dangling:
    #   CHYINMUNK -> KINETMUNK
    #   BIRBIE -> AVEDEN -> SPLENDIFOWL
    #   CUBBUG -> CUBBLFLY -> NIMFLORA
    #   BAREWL -> DEAREWL -> GARAREWL
    #   TONEMY -> TOFURANG
    #   FARTOG -> FOLEROG -> BLUBELROG
    #   OWTEN -> ESHOUTEN
    # All evolutions here are EVO_LEVEL (method 4), matching what
    # `build_staged_species` already handles for the starters. Verified: no
    # Nuclear-typed species in this set, and every referenced ability
    # resolves to a real fork ABILITY_* constant (no invented constants).
    SpeciesSpec(7, "CHYINMUNK"),
    SpeciesSpec(8, "KINETMUNK"),
    SpeciesSpec(9, "BIRBIE"),
    SpeciesSpec(10, "AVEDEN"),
    SpeciesSpec(11, "SPLENDIFOWL"),
    SpeciesSpec(12, "CUBBUG"),
    SpeciesSpec(13, "CUBBLFLY"),
    SpeciesSpec(14, "NIMFLORA"),
    SpeciesSpec(15, "BAREWL"),
    SpeciesSpec(16, "DEAREWL"),
    SpeciesSpec(17, "GARAREWL"),
    SpeciesSpec(20, "TONEMY"),
    SpeciesSpec(21, "TOFURANG"),
    SpeciesSpec(24, "FARTOG"),
    SpeciesSpec(25, "FOLEROG"),
    SpeciesSpec(26, "BLUBELROG"),
    SpeciesSpec(35, "OWTEN"),
    SpeciesSpec(36, "ESHOUTEN"),
)


def gfx_ident(spec: SpeciesSpec) -> str:
    """CamelCase identifier suffix used in engine graphics symbol names.

    e.g. ORCHYNX -> "Orchynx", giving `gMonFrontPic_Orchynx`. None of the
    Uranium names collide with a vanilla species; the staging emitter asserts
    this against the fork headers rather than trusting it.
    """
    return spec.internal_name.capitalize()


def asset_dir_name(spec: SpeciesSpec) -> str:
    """Directory under `graphics/pokemon/uranium/` holding this species' art."""
    return spec.internal_name.lower()


# --- Layout of the generated overlay tree (under $RPG2GBA_OUTPUT) -----------

SPECIES_OUT_SUBDIR = Path("species")
MANIFEST_NAME = "species_manifest.json"

#: Engine-relative destination for each species' art directory.
ENGINE_GFX_ROOT = Path("graphics/pokemon/uranium")
#: Engine-relative destination for cry sample wavs.
ENGINE_CRY_ROOT = Path("sound/direct_sound_samples/cries")

# Art filenames inside a species' asset directory. `anim_front.png` matches the
# vanilla convention even though these are single-frame (the engine pairs it
# with `sAnims_SingleFramePlaceHolder`).
FRONT_PNG = "anim_front.png"
BACK_PNG = "back.png"
NORMAL_PAL = "normal.pal"
SHINY_PAL = "shiny.pal"
ICON_PNG = "icon.png"

# --- Engine-side invariants the converters must hit ------------------------

#: Battler sprites are 64x64, 4bpp, 15 colors + transparent.
BATTLER_SIZE = 64
BATTLER_MAX_COLORS = 15

#: Engine mon icons are 32x64 = two vertically-stacked 32x32 frames.
ICON_WIDTH = 32
ICON_HEIGHT = 64
#: Number of shared icon palettes (graphics/pokemon/icon_palettes/pal0..pal5).
ICON_PALETTE_COUNT = 6

#: Vanilla cry house norm, measured from the fork's own cry wavs:
#: mono, 10512 Hz, 8-bit unsigned PCM.
CRY_SAMPLE_RATE = 10512
CRY_CHANNELS = 1
CRY_SAMPLE_WIDTH = 1


def uranium_battler_front(uranium_src: Path, spec: SpeciesSpec, *, shiny: bool) -> Path:
    """Front battler filmstrip for a species.

    Uranium ships some of these with an uppercase `.PNG` extension, so callers
    must resolve case-insensitively; this returns the lowercase spelling and
    `resolve_case` does the fallback.
    """
    stem = f"{spec.uranium_id:03d}{'s' if shiny else ''}"
    return uranium_src / "Graphics" / "Battlers" / f"{stem}.png"


def uranium_battler_back(uranium_src: Path, spec: SpeciesSpec, *, shiny: bool) -> Path:
    stem = f"{spec.uranium_id:03d}{'s' if shiny else ''}b"
    return uranium_src / "Graphics" / "Battlers" / f"{stem}.png"


def uranium_icon(uranium_src: Path, spec: SpeciesSpec) -> Path:
    return uranium_src / "Graphics" / "Icons" / f"icon{spec.uranium_id:03d}.png"


def uranium_cry(uranium_src: Path, spec: SpeciesSpec) -> Path:
    return uranium_src / "Audio" / "SE" / f"{spec.uranium_id:03d}Cry.wav"


def resolve_case(path: Path) -> Path:
    """Return `path`, or its case-variant sibling if only that exists.

    Uranium's asset tree mixes `.png` and `.PNG` (e.g. `002b.PNG`). Fails loud
    when neither spelling is present — a missing asset is a bug, not a default.
    """
    if path.exists():
        return path
    for sibling in path.parent.iterdir():
        if sibling.name.lower() == path.name.lower():
            return sibling
    raise FileNotFoundError(f"no case-variant of {path} exists")
