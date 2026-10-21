"""Walk-ROM extras: own-save id, granted species, party-wide EXP Share.

`playtest walk` writes these into the embedded save's `walk` field
(`engine/include/rpg2gba_embedded_save.h`, `struct Rpg2gbaWalkExtras`) after
splicing the seed blob, so they never enter a sha-keyed seed and suite runs
never see them. Decisions: `reference/walk_qol_plan.md` §1.

- **ROM id.** Random per walk ROM. The engine copies it into SaveBlock2 on a
  blob boot, so an in-game save made on this ROM carries it, and the next boot
  of this ROM continues that save instead of the blob.
- **Granted species.** Every species catchable in the maps the suite's beats
  entered before the seed point: all wild encounter tables (every method) plus
  the story's scripted gifts (`givemon` / `giveegg`). The engine gives the ones
  the player doesn't own at the party's top level, party first then PC.
- **EXP Share.** A flag the engine sets on a blob boot.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import struct
from dataclasses import dataclass
from pathlib import Path

from ..map_split.ids import origin_of
from .archetypes import map_uranium_id
from .chapter import Chapter

logger = logging.getLogger(__name__)

ROM_BASE = 0x08000000

_ROW_MAP_RE = re.compile(r"map(\d+)")
_GIFT_RE = re.compile(r"\b(?:givemon|giveegg)\(\s*(SPECIES_\w+)")


@dataclass(frozen=True)
class WalkExtras:
    rom_id: int
    exp_share: bool
    species: tuple[str, ...]  # SPECIES_* constants, grant order


def _build_root() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"


def maps_entered(chapter: Chapter, at_beat: str | None) -> list[int]:
    """Uranium map ids the beats before `at_beat` stood on or crossed, in first-
    visit order. `at_beat=None` means the whole chapter (a chapter-complete seed).

    A beat's own locations name where it stands; its manifest rows
    (`map035/ev014/p1`, `map031/seam/N/map035`) also name the maps a seam,
    stair or warp beat crosses into."""
    beats = chapter.beats if at_beat is None else chapter.beats[:chapter.index_of(at_beat)]
    seen: dict[int, None] = {}
    for beat in beats:
        for loc in beat.locations:
            seen.setdefault(map_uranium_id(loc.map_constant))
        for row in beat.rows:
            for num in _ROW_MAP_RE.findall(row):
                seen.setdefault(int(num))
    return list(seen)


def _species_in(node: object, out: dict[str, None]) -> None:
    """Every `species` value in an encounter table, any method or nesting."""
    if isinstance(node, dict):
        species = node.get("species")
        if isinstance(species, str):
            out.setdefault(species)
        for value in node.values():
            _species_in(value, out)
    elif isinstance(node, list):
        for value in node:
            _species_in(value, out)


def catchable_species(map_ids: list[int], build_root: Path | None = None) -> list[str]:
    """SPECIES_* catchable in `map_ids`, in map order: each map's wild
    encounter tables (all methods, `uranium_extra` included), then its scripted
    gifts. A split piece reads its origin map's tables and scripts."""
    root = build_root or _build_root()
    wild_path = root / "intermediate" / "wild_encounters.json"
    if not wild_path.exists():
        raise FileNotFoundError(
            f"{wild_path} is missing; it is written by the PBS encounters "
            "converter (python -m rpg2gba.pipeline phase2)")
    wild = json.loads(wild_path.read_text(encoding="utf-8"))["maps"]
    scripts = root / "scripts"

    found: dict[str, None] = {}
    for uid in map_ids:
        ids = dict.fromkeys((uid, origin_of(uid)))
        for map_id in ids:
            _species_in(wild.get(str(map_id), {}), found)
        for map_id in ids:
            pory = scripts / f"Map{map_id:03d}.pory"
            if pory.exists():
                for species in _GIFT_RE.findall(pory.read_text(encoding="utf-8")):
                    found.setdefault(species)
    return list(found)


def plan_extras(chapter: Chapter, at_beat: str | None, *, grant: bool,
                exp_share: bool) -> WalkExtras:
    species: tuple[str, ...] = ()
    if grant:
        species = tuple(catchable_species(maps_entered(chapter, at_beat)))
    return WalkExtras(rom_id=secrets.randbits(32) or 1, exp_share=exp_share,
                      species=species)


def encode_extras(extras: WalkExtras, offsets: dict[str, int],
                  species_ids: dict[str, int]) -> bytes:
    """`struct Rpg2gbaWalkExtras` bytes, laid out by the probed offsets."""
    limit = offsets["val_walk_grant_max"]
    if len(extras.species) > limit:
        raise ValueError(
            f"{len(extras.species)} species to grant, but the engine holds "
            f"{limit} (RPG2GBA_WALK_GRANT_MAX in rpg2gba_embedded_save.h)")
    buf = bytearray(offsets["sizeof_walk"])
    struct.pack_into("<I", buf, offsets["off_walk_romid"], extras.rom_id)
    buf[offsets["off_walk_expshare"]] = 1 if extras.exp_share else 0
    struct.pack_into("<H", buf, offsets["off_walk_grantcount"], len(extras.species))
    for i, name in enumerate(extras.species):
        struct.pack_into("<H", buf, offsets["off_walk_grants"] + 2 * i, species_ids[name])
    return bytes(buf)


def patch_extras(rom: Path, engine: Path, extras: WalkExtras) -> None:
    """Write `extras` into the stamped ROM at `rom`, in place. The blob must
    already be stamped (non-zero magic), or the engine would ignore it."""
    from .offsets import probe_constants, probe_offsets
    from .symbols import SymbolMap

    offsets = probe_offsets(engine)
    species_ids = probe_constants(engine, list(extras.species)) if extras.species else {}
    blob_off = SymbolMap(engine / "pokeemerald.map")["gRpg2gbaEmbeddedSave"] - ROM_BASE
    data = bytearray(rom.read_bytes())
    magic = struct.unpack_from("<I", data, blob_off)[0]
    if magic != offsets["embedded_save_magic"]:
        raise ValueError(f"{rom}: no stamped embedded save to add walk extras to")
    payload = encode_extras(extras, offsets, species_ids)
    start = blob_off + offsets["off_es_walk"]
    data[start:start + len(payload)] = payload
    rom.write_bytes(bytes(data))
    logger.info("walk extras: rom id %08x, EXP Share %s, %d species to grant",
                extras.rom_id, "on" if extras.exp_share else "off",
                len(extras.species))


#: Money written before the in-game save in `verify_extras`; any value the
#: seed is unlikely to hold already.
_SAVE_SENTINEL_MONEY = 424242


def verify_extras(rom: Path, engine: Path, extras: WalkExtras, *,
                  boot_frames: int) -> None:
    """Prove the extras work on the built ROM, with no .sav paired:

    1. A blob boot sets the EXP Share flag iff it was asked for, and the party
       still reads cleanly after the grant.
    2. An in-game save made on this ROM is what the next boot of the same ROM
       continues (money set to a sentinel before saving survives the reboot),
       not the blob.

    The foreign-.sav check (`stamp.verify_stamped_rom`) covers the other half:
    a save from any other ROM still loses to the blob.
    """
    import shutil

    from .assertions import read_party_species
    from .emulator import Emulator
    from .scenarios import save_in_game

    work = rom.parent / f".{rom.stem}.extras.gba"
    sav = work.with_suffix(".sav")
    try:
        shutil.copy(rom, work)
        sav.unlink(missing_ok=True)
        emu = Emulator(work, engine)
        emu.run(boot_frames)
        flag_on = emu.flag("FLAG_RPG2GBA_EXP_SHARE")
        if flag_on != extras.exp_share:
            raise ValueError(
                f"walk ROM booted with EXP Share {'on' if flag_on else 'off'}, "
                f"expected {'on' if extras.exp_share else 'off'}")
        party = read_party_species(emu)
        if not party:
            raise ValueError("walk ROM booted with an empty party after the grant")
        emu.set_money(_SAVE_SENTINEL_MONEY)
        save_in_game(emu)
        del emu

        emu = Emulator(work, engine)
        emu.run(boot_frames)
        if emu.money() != _SAVE_SENTINEL_MONEY:
            raise ValueError(
                "an in-game save made on this walk ROM did not load on the next "
                f"boot (money {emu.money()}, saved {_SAVE_SENTINEL_MONEY}): the "
                "blob shadowed the player's own save (rom id check in "
                "engine/src/rpg2gba_embedded_save.c)")
    finally:
        work.unlink(missing_ok=True)
        sav.unlink(missing_ok=True)
    logger.info("verified: %s party %s; own in-game save reloads on reboot",
                rom, party)
