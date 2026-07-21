"""Uranium species → pokeemerald-expansion custom species.

Converts a small, explicitly-listed set of Uranium species into real engine
species: data entries, battler art, icons, and cries, emitted as *generated
overlays* that the assembler stages into `$RPG2GBA_POKEEMERALD` behind
committed `URANIUM PATHFINDER SLICE` fenced include-hooks.

This package reuses the **parsers** from `rpg2gba.pbs_converter.pokemon`; it
never reuses that module's Phase-2 emitters (which are full-replacement and
Uranium-numbered). See `STARTER_SPECIES_PLAN.md`.
"""

from rpg2gba.species_converter.common import (
    STARTER_SPECIES,
    SpeciesSpec,
    asset_dir_name,
    gfx_ident,
)

__all__ = ["STARTER_SPECIES", "SpeciesSpec", "asset_dir_name", "gfx_ident"]
