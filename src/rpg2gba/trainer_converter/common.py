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
# staging asserts this at runtime too). `internal_name` is the Uranium class
# constant minus `TRAINER_CLASS_` (`battles.pic_internal_name`).
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
    # CH03 (Kevlar Town): Mawuli, TRAINER_CLASS_RICH_BOY. trainer_id 14 is
    # trainertypes.dat's own id for RICHBOY, verified against a real
    # Graphics/Characters/trainer014.png before pinning (battles.py staging
    # asserts this at runtime too).
    TrainerPicSpec(14, "RICHBOY"),
    # CH04 (Route 2): Chuck, TRAINER_CLASS_HIKER. trainer_id 4 is
    # trainertypes.dat's own id for HIKER (intermediate/trainer_types.json),
    # verified against a real Graphics/Characters/trainer004.png before
    # pinning. Timothy needs no new entry -- YOUNGSTER is already staged.
    TrainerPicSpec(4, "HIKER"),
    # Also CH04: Brent, TRAINER_CLASS_BIRD_KEEPER. trainertypes.dat id 42,
    # display name "BIRD KEEPER", real Graphics/Characters/trainer042.png.
    TrainerPicSpec(42, "BIRDKEEPER"),
    # CH05 (Passage Cave): Keichi, TRAINER_CLASS_BLACKBELT. trainertypes.dat
    # id 16 (intermediate/trainer_types.json, display name "BLACK BELT"),
    # verified against a real Graphics/Characters/trainer016.png before
    # pinning. Manny and Nunes need no new entry -- both are HIKER, already
    # staged for CH04's Chuck.
    TrainerPicSpec(16, "BLACKBELT"),
    # CH06 (Kevlar gym): Maria, TRAINER_CLASS_LEADER_ROXANNE. trainertypes.dat
    # id 71 (intermediate/trainer_types.json, display name "LEADER" ->
    # TRAINER_CLASS_LEADER), Graphics/Characters/trainer071.png.
    TrainerPicSpec(71, "LEADER_ROXANNE"),
    # CH09 (Route 3): trainertypes.dat ids from intermediate/trainer_types.json
    # (TUBER_FEMALE 19, TUBER_MALE 25, SAILOR 46, PICNICKER 60); each
    # Graphics/Characters/trainer<id>.png exists in the Uranium tree.
    TrainerPicSpec(19, "TUBER_FEMALE"),
    TrainerPicSpec(25, "TUBER_MALE"),
    TrainerPicSpec(46, "SAILOR"),
    TrainerPicSpec(60, "PICNICKER"),
    # CH10 (Burole Town). Battle pics are keyed by the trainer's own Uranium
    # class, so internal_name is the Uranium class suffix (battles.pic_internal_name):
    # LEADER_CAFF 87 (Davern; LEADER_ROXANNE above is Maria), SCHOOLKID_MALE 13
    # (Tracey; SCHOOLKID above is the female type), WORKER 22 (Martin).
    TrainerPicSpec(87, "LEADER_CAFF"),
    TrainerPicSpec(13, "SCHOOLKID_MALE"),
    TrainerPicSpec(22, "WORKER"),
    # CH11 (Route 4): PKMNRANGER_MALE 49 (Wyle), GENTLEMAN 28 (Sr. Goldkorn),
    # PSYCHIC_FEMALE 62 (Laramie), SCHOOLKID_FEMALE 63 (Marta; SCHOOLKID 84 above
    # is a different Uranium type).
    TrainerPicSpec(49, "PKMNRANGER_MALE"),
    TrainerPicSpec(28, "GENTLEMAN"),
    TrainerPicSpec(62, "PSYCHIC_FEMALE"),
    TrainerPicSpec(63, "SCHOOLKID_FEMALE"),
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
    # CH03 (Kevlar Town): Mawuli's repeatable Pokémon Center facility battle
    # (transpiler._emit_facility_trainer_battle_idiom).
    "TRAINER_MAWULI_90",
    # CH04 (Route 2): the chapter's two overworld battle trainers, in map
    # event order -- Timothy (Map035:100) then Chuck (Map035:482), both
    # `trainerbattle_single`. Order is the append rule, not a preference.
    "TRAINER_TIMOTHY_247",
    "TRAINER_CHUCK_279",
    # Also CH04: the map's two PHONE trainers, whose battles sit inside a
    # `pbTrainerBattle` conditional the transpiler had queued rather than
    # emitted -- they need staging the moment that idiom emits. Larrie is a
    # chapter beat (B2); Brent is north of the rockslide and unreachable this
    # visit, but his event still emits, so his id still has to resolve.
    "TRAINER_LARRIE_4",
    "TRAINER_BRENT_278",
    # CH05 (Passage Cave): the chapter's three overworld battle trainers, in
    # map event order -- Manny (Map036 EV004) then Keichi (Map036 EV006) then
    # Nunes (Map037 EV004), all `trainerbattle_single`. Order is the append
    # rule, not a preference.
    "TRAINER_MANNY_5",
    "TRAINER_KEICHI_248",
    "TRAINER_NUNES_128",
    # CH06 (Nowtoch City): the Gym's two trainers then the leader, in map
    # event order -- Myla (Map042 EV001) and Jack (Map042 EV002), both
    # `trainerbattle_single`, then Maria (Map042 EV003, the badge battle,
    # `trainerbattle_no_intro` via the facility idiom's LEADER_ carve-out).
    "TRAINER_MYLA_7",
    "TRAINER_JACK_8",
    "TRAINER_MARIA_15",
    # CH06 (Nowtoch City): rival Theo, starter-dependent party 1/2/3 (Map040 EV079).
    "TRAINER_THEO_12",
    "TRAINER_THEO_13",
    "TRAINER_THEO_14",
    # CH09 (Route 3): the map's eight trainers, in map event order -- Sack
    # (Map059 EV009, phone trainer), Lara (EV012), Chan (EV018), Johnny (EV027),
    # Marc (EV029), Julianna (EV031), Sophy (EV032), Shauna (EV050).
    "TRAINER_SACK_28",
    "TRAINER_LARA_21",
    "TRAINER_CHAN_27",
    "TRAINER_JOHNNY_22",
    "TRAINER_MARC_41",
    "TRAINER_JULIANNA_250",
    "TRAINER_SOPHY_42",
    "TRAINER_SHAUNA_249",
    # CH10 (Burole Town): Gym 2 (Map066) then the school (Map029) -- chapters.json
    # roster order [60, 66, 2, 4, 29, 85, 90], events in map event order within
    # each. Gym: Tod (EV001), Jang (EV002), Martin (EV003), then leader Davern
    # (EV004). School: Diana (EV002), Rich (EV009), Tracey (EV010), James (EV011).
    "TRAINER_TOD_30",
    "TRAINER_JANG_31",
    "TRAINER_MARTIN_32",
    "TRAINER_DAVERN_29",
    "TRAINER_DIANA_43",
    "TRAINER_RICH_44",
    "TRAINER_TRACEY_45",
    "TRAINER_JAMES_46",
    # CH11 (Route 4): Map076's eight trainers in map event order -- Carlton (EV002),
    # Wyle (EV009, Strength pocket: unreachable this visit, but his event emits),
    # Marta (EV010), Ogilvy (EV043), Laramie (EV044), Nelson (EV058), William
    # (EV059), Sr. Goldkorn (EV071, phone trainer).
    "TRAINER_CARLTON_34",
    "TRAINER_WYLE_117",
    "TRAINER_MARTA_33",
    "TRAINER_OGILVY_253",
    "TRAINER_LARAMIE_254",
    "TRAINER_NELSON_40",
    "TRAINER_WILLIAM_35",
    "TRAINER_SR_GOLDKORN_36",
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
