"""Uranium trainer art -> pokeemerald-expansion trainer pic converter.

Converts NPC front pics (`Graphics/Characters/trainer<NNN>.png`) and player
back-pic strips (`Graphics/Characters/trback<NNN>.png`) into the engine's
64x64 front / 64x256 (4-frame) back 4bpp indexed sprites. Architecturally
mirrors `rpg2gba.species_converter.battlers` (see `pics.py` for why the
pipeline is new rather than reused).
"""

from rpg2gba.trainer_converter.common import (
    BACK_PIC_FRAMES,
    SLICE_TRAINER_PICS,
    TRAINER_MAX_COLORS,
    TRAINER_PIC_SIZE,
    TrainerPicSpec,
)

__all__ = [
    "BACK_PIC_FRAMES",
    "SLICE_TRAINER_PICS",
    "TRAINER_MAX_COLORS",
    "TRAINER_PIC_SIZE",
    "TrainerPicSpec",
]
