"""Shared contract for the trainer-pic converter units.

Mirrors `species_converter/common.py`'s pattern (spec dataclass + path
helpers + `resolve_case`) for trainer front pics (`Graphics/Characters/
trainer<NNN>.png`) and player back pics (`Graphics/Characters/
trback<NNN>.png`). See `pics.py` for the conversion pipeline and
`STARTER_SPECIES_PLAN.md`-equivalent slice-1 selection below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: Engine target: front/back pics are square 4bpp sprites.
TRAINER_PIC_SIZE = 64
#: Index 0 is the transparent placeholder -> at most 15 opaque colours.
TRAINER_MAX_COLORS = 15
#: Player back pic is a 4-frame ball-throw animation.
BACK_PIC_FRAMES = 4

_NON_IDENT = re.compile(r"[^A-Z0-9]+")


@dataclass(frozen=True)
class TrainerPicSpec:
    """One trainer id selected for pic conversion.

    `trainer_id` is the 0-based id embedded in `trainer<NNN>.png` /
    `trback<NNN>.png` filenames. `internal_name` is Uranium's internal
    trainertype name — accepted as a passed-in field for now (this module
    does not parse PBS itself).
    """

    trainer_id: int
    internal_name: str

    @staticmethod
    def _sanitize(name: str) -> str:
        """Uppercase C identifier: apostrophes stripped, everything else
        non-alphanumeric collapsed to a single underscore."""
        stripped = name.replace("'", "").upper()
        ident = _NON_IDENT.sub("_", stripped).strip("_")
        return ident

    @property
    def pic_constant(self) -> str:
        return f"TRAINER_PIC_FRONT_URANIUM_{self._sanitize(self.internal_name)}"

    @property
    def back_pic_constant(self) -> str:
        return f"TRAINER_PIC_BACK_URANIUM_{self._sanitize(self.internal_name)}"


# --- Slice-1 selection -------------------------------------------------------
# The rest of this package is corpus-general (works for any trainer id); this
# tuple is deliberately the only place a specific id is pinned.
#
# Entries 3..9 (the seven Route-1 trainer *classes*) were appended for the
# trainer-battle slice (W6): Uranium keys its trainer-class sprites by
# trainer-TYPE id (trainertypes.dat's own `id` field), not by an NPC map
# sprite id, so `trainer_id` here is that trainer-type id — verified present
# in `trainer_types.json` and cross-checked against the real
# `Graphics/Characters/trainer<NNN>.png` files before pinning (battles.py
# staging asserts this at runtime too). `internal_name` matches the class
# identifiers `battles._CLASS_PIC_INTERNAL_NAME` maps real
# `TRAINER_CLASS_*` constants onto.
SLICE_TRAINER_PICS: tuple[TrainerPicSpec, ...] = (
    TrainerPicSpec(86, "RIVAL"),
    TrainerPicSpec(0, "PLAYER_MALE"),
    TrainerPicSpec(6, "FISHERMAN"),
    TrainerPicSpec(3, "YOUNGSTER"),
    TrainerPicSpec(12, "BUGCATCHER"),
    TrainerPicSpec(84, "SCHOOLKID"),
    TrainerPicSpec(32, "TRIATHLETE_MALERUNNER"),
    TrainerPicSpec(38, "EXPERT_FEMALE"),
    TrainerPicSpec(2, "LASS"),
)

#: internal_name values in `SLICE_TRAINER_PICS` that additionally get a player
#: BACK pic conversion (a ball-throw filmstrip), not just a front pic. Every
#: other entry (NPC trainer classes, the rival) is front-only.
PLAYER_BACK_PIC_NAMES: frozenset[str] = frozenset({"PLAYER_MALE", "PLAYER_FEMALE"})

# --- Trainer id allocation anchor --------------------------------------------
# Last vanilla trainer id (pokeemerald-expansion @ pinned rev, engine/RPG2GBA_
# VENDOR.md) before ANY Uranium/pathfinder trainer -- generated TRAINER_* battle
# ids chain off this. `battles.read_pristine_trainer_anchor` re-derives it from
# `include/constants/opponents.h` and fails loud on drift; duplicated here only
# so callers can construct fixtures without reading the fork.
PRISTINE_TRAINER_ANCHOR = "TRAINER_MAY_PLACEHOLDER"
PRISTINE_TRAINER_MAY_PLACEHOLDER = 854

# --- Trainer battle selection (W6) -------------------------------------------
# Trainer identity keys, exactly as minted by
# `pbs_converter.trainers._Resolver.trainer_constant` into
# `output/uranium-build/intermediate/trainers.json` (dict key == the desired
# final engine `TRAINER_*` constant name). Order is load-bearing: fork trainer
# ids are assigned by position off `PRISTINE_TRAINER_ANCHOR` -- append-only,
# never reorder or remove an entry. Route 1's nine trainers plus the three
# existing (currently hand-written, see `engine/include/constants/
# opponents.h` lines 862-866) Theo counter-pick entries.
SLICE_TRAINER_BATTLES: tuple[str, ...] = (
    "TRAINER_MARKO_19",
    "TRAINER_BOB_20",
    "TRAINER_FLOOD_2",
    "TRAINER_TATH_1",
    "TRAINER_BRANDON_18",
    "TRAINER_BRANDON_16",
    "TRAINER_GERTHA_17",
    "TRAINER_LYNETTE_246",
    "TRAINER_RICHEY_3",
    "TRAINER_THEO_9",
    "TRAINER_THEO_10",
    "TRAINER_THEO_11",
)


def uranium_trainer_front(uranium_src: Path, trainer_id: int) -> Path:
    """NPC front pic path (`Graphics/Characters/trainer<NNN>.png`). Uranium
    ships id 000 only as uppercase `trainer000.PNG`; resolve through
    `resolve_case`."""
    return uranium_src / "Graphics" / "Characters" / f"trainer{trainer_id:03d}.png"


def uranium_trainer_back(uranium_src: Path, trainer_id: int) -> Path:
    """Player back pic path (`Graphics/Characters/trback<NNN>.png`) — a
    horizontal 4-frame ball-throw strip. Resolve through `resolve_case`."""
    return uranium_src / "Graphics" / "Characters" / f"trback{trainer_id:03d}.png"


def resolve_case(path: Path) -> Path:
    """Return `path`, or its case-variant sibling if only that exists.

    Uranium's asset tree mixes `.png` and `.PNG` (e.g. `trainer000.PNG`).
    Fails loud when neither spelling is present — a missing asset is a bug,
    not a default.
    """
    if path.exists():
        return path
    if not path.parent.is_dir():
        raise FileNotFoundError(f"no case-variant of {path} exists (parent dir missing)")
    for sibling in path.parent.iterdir():
        if sibling.name.lower() == path.name.lower():
            return sibling
    raise FileNotFoundError(f"no case-variant of {path} exists")


__all__ = [
    "TRAINER_PIC_SIZE",
    "TRAINER_MAX_COLORS",
    "BACK_PIC_FRAMES",
    "TrainerPicSpec",
    "SLICE_TRAINER_PICS",
    "PLAYER_BACK_PIC_NAMES",
    "PRISTINE_TRAINER_ANCHOR",
    "PRISTINE_TRAINER_MAY_PLACEHOLDER",
    "SLICE_TRAINER_BATTLES",
    "uranium_trainer_front",
    "uranium_trainer_back",
    "resolve_case",
]
