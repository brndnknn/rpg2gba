"""Phase 2 §2.3 — convert `items.dat` into the expansion's item table.

Source (under `$RPG2GBA_URANIUM_SRC/Data/`):

  items.dat — Essentials `writeSerialRecords` format (Compiler.rb:446 +
  `pbCompileItems` at :810). Layout:
    * header: `numrec` pairs of (uint32 offset, uint32 byte_length); the very
      first uint32 is `numrec << 3` (the header's own byte size), so
      `numrec = first_dword >> 3`.
    * each record body is a sequence of self-describing TLV fields, each tagged
      by a 1-byte type: `i`=varint int, `"`=length-prefixed string, `0`=nil,
      `T`/`F`=bool (SerialRecord.encode, Compiler.rb:310).
  Each item record holds 9 fields, in this order (Compiler.rb:818-835 +
  117_PItem_Items.rb constant indices):
    0 ITEMID        int
    1 ITEMNAME      string  (display name — discarded; we use the sidecar)
    2 ITEMPOCKET    int     (Essentials pocket 1..8)
    3 ITEMPRICE     int
    4 ITEMDESC      string  (discarded; we use the sidecar)
    5 ITEMUSE       int     (field-use behavior code)
    6 ITEMBATTLEUSE int     (battle-use behavior code)
    7 ITEMTYPE      int     (special-item type code)
    8 ITEMMACHINE   int     (move id for a TM/HM, else 0)

Display name/description come from the `messages.dat` sidecars
(`reference/item_names.json`, `reference/item_descriptions.json`), which have
the mojibake already fixed; the dat's embedded strings are raw UTF-8 bytes we
read past but never decode. Internal names (the id_map key + `ITEM_*` mint
source) come from `reference/item_internal_names.json` (the `PBItems` script
section).

Item *behavior* (field use / battle use / hold effect / TM linkage) is NOT
mapped here — same call as moves §2.2 / D3. Essentials' use/battle/type codes
have no clean map to the fork's item-effect machinery; that's Phase 6 engine
work. Each item's raw codes are preserved in `intermediate/item_field_codes.json`
(the Phase 6 worklist), and the struct's behavior fields are left at their
defaults. Only deterministic, lossless fields (price, pocket, importance,
name, description) are emitted into `gItemsInfo[]`.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from ._binary import BinaryReadError, DatReader
from ._c_emit import escape_c_string, generated_banner, wrap_header
from ._id_map import IdMap
from ._naming import load_fork_constants, to_constant

logger = logging.getLogger(__name__)

GENERATOR = "rpg2gba.pbs_converter.items"

# Essentials pocket index (002__Settings.rb:166 pbPocketNames, 1-based) ->
# expansion POCKET_* (constants/item.h). The fork consolidated to 5 pockets, so
# this is a deliberately lossy remap: Medicine / Mail / Battle Items have no
# dedicated fork pocket and fold into POCKET_ITEMS. Pocket is bag-UI grouping
# only — no behavior rides on it — so the consolidation is safe.
_POCKET_BY_ESSENTIALS: dict[int, str] = {
    1: "POCKET_ITEMS",       # Items
    2: "POCKET_ITEMS",       # Medicine
    3: "POCKET_POKE_BALLS",  # Poké Balls
    4: "POCKET_TM_HM",       # TMs & HMs
    5: "POCKET_BERRIES",     # Berries
    6: "POCKET_ITEMS",       # Mail
    7: "POCKET_ITEMS",       # Battle Items
    8: "POCKET_KEY_ITEMS",   # Key Items
}
# Essentials Key Items pocket → expansion `.importance = 1` (can't be sold/tossed).
_KEY_ITEMS_POCKET = 8


@dataclass
class Item:
    """One item record. Numeric behavior fields feed the Phase 6 worklist."""

    id: int
    pocket: int          # Essentials pocket 1..8
    price: int
    item_use: int        # ITEMUSE — field-use behavior (Phase 6)
    battle_use: int      # ITEMBATTLEUSE — battle-use behavior (Phase 6)
    item_type: int       # ITEMTYPE — special-item type (Phase 6)
    machine_move: int    # ITEMMACHINE — TM/HM move id, 0 if not a machine
    internal_name: str = ""


def parse(path: Path) -> list[Item]:
    """Parse `items.dat` (SerialRecords) into Item records, keyed by ITEMID."""
    reader = DatReader(path)
    first = reader.dw()
    if first % 8 != 0:
        raise BinaryReadError(f"{path}: header size {first} is not a multiple of 8")
    numrec = first >> 3

    reader.seek(0)
    headers: list[tuple[int, int]] = [(reader.dw(), reader.dw()) for _ in range(numrec)]

    items: list[Item] = []
    for off, length in headers:
        fields = _decode_record(reader.at(off, length))
        if len(fields) != 9:
            raise BinaryReadError(
                f"{path}: item record at offset {off} has {len(fields)} fields, expected 9"
            )
        item_id, _name, pocket, price, _desc, use, battle, itype, machine = fields
        for label, value in (("ITEMID", item_id), ("ITEMPOCKET", pocket), ("ITEMPRICE", price)):
            if not isinstance(value, int):
                raise BinaryReadError(
                    f"{path}: item at offset {off} field {label} is {value!r}, expected int"
                )
        if pocket not in _POCKET_BY_ESSENTIALS:
            raise BinaryReadError(
                f"{path}: item id {item_id} has unknown Essentials pocket {pocket}"
            )
        items.append(
            Item(
                id=item_id,
                pocket=pocket,
                price=price,
                item_use=use,
                battle_use=battle,
                item_type=itype,
                machine_move=machine,
            )
        )
    return items


def _decode_record(r: DatReader) -> list[object]:
    """Decode one SerialRecord body (Compiler.rb SerialRecord.decode).

    String fields are read length-prefixed and discarded undecoded — the dat's
    strings are raw UTF-8 bytes and display text comes from the sidecars, so we
    never need to interpret them (and must not fail-loud on their encoding).
    """
    fields: list[object] = []
    while not r.eof:
        tag = r.bytes(1)
        if tag == b"i":
            fields.append(r._decode_int())
        elif tag == b'"':
            n = r._decode_int()
            r.bytes(n)  # consume and discard
            fields.append("")
        elif tag == b"0":
            fields.append(None)
        elif tag == b"T":
            fields.append(True)
        elif tag == b"F":
            fields.append(False)
        else:
            raise BinaryReadError(f"unknown SerialRecord field tag {tag!r} at offset {r.pos}")
    return fields


def attach_internal_names(items: list[Item], names_by_id: dict[int, str]) -> None:
    """Populate Item.internal_name from item_internal_names.json (fail-loud)."""
    missing: list[int] = []
    for it in items:
        name = names_by_id.get(it.id)
        if name is None:
            missing.append(it.id)
            continue
        it.internal_name = name
    if missing:
        raise ValueError(
            f"item_internal_names.json missing IDs: {missing[:10]}"
            f"{' (+more)' if len(missing) > 10 else ''}"
        )


# ===========================================================================
# C emit  (§2.3)
# ===========================================================================


def _load_id_json(path: Path) -> dict[int, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "reference"


@dataclass
class _ItemResolver:
    """Resolves Uranium item IDs to `ITEM_*` constants via the IdMap.

    The naming rule is identical to pokemon.py's `item_constant` (display name
    through `_naming.to_constant`, internal-name fallback), so a wild-held item
    referenced from a species and the same item emitted here mint the same
    constant — `IdMap.add` would otherwise fail loud on the conflict.
    """

    id_map: IdMap
    item_internal: dict[int, str]
    item_names: dict[int, str]
    item_descs: dict[int, str]
    fork_items: set[str]

    def constant(self, item_id: int) -> str:
        if item_id == 0:
            return "ITEM_NONE"
        internal = self.item_internal.get(item_id)
        if internal is None:
            raise ValueError(f"item id {item_id} absent from item_internal_names.json")
        const = to_constant("ITEM", self.item_names.get(item_id) or internal)
        needs = bool(self.fork_items) and const not in self.fork_items
        self.id_map.add("items", internal, const, needs_engine=needs)
        return const

    def name(self, item_id: int) -> str:
        return self.item_names.get(item_id, self.item_internal.get(item_id, ""))

    def desc(self, item_id: int) -> str:
        return self.item_descs.get(item_id, "")


def _build_resolver(id_map: IdMap, ref: Path) -> _ItemResolver:
    fork_env = os.environ.get("RPG2GBA_POKEEMERALD")
    fork = Path(fork_env) if fork_env else None
    fork_items = (
        load_fork_constants(fork / "include/constants/items.h", "ITEM") if fork else set()
    )
    return _ItemResolver(
        id_map=id_map,
        item_internal=_load_id_json(ref / "item_internal_names.json"),
        item_names=_load_id_json(ref / "item_names.json"),
        item_descs=_load_id_json(ref / "item_descriptions.json"),
        fork_items=fork_items,
    )


def _emit_one(it: Item, r: _ItemResolver) -> str:
    const = r.constant(it.id)
    lines: list[str] = [f"    [{const}] =", "    {"]
    lines.append(f'        .name = ITEM_NAME("{escape_c_string(r.name(it.id))}"),')
    lines.append(f"        .price = {it.price},")
    desc = r.desc(it.id)
    if desc:
        lines.append(f'        .description = COMPOUND_STRING("{escape_c_string(desc)}"),')
    lines.append(f"        .pocket = {_POCKET_BY_ESSENTIALS[it.pocket]},")
    if it.pocket == _KEY_ITEMS_POCKET:
        lines.append("        .importance = 1,")
    lines.append("    },")
    return "\n".join(lines)


def emit_items_info(items: list[Item], r: _ItemResolver) -> str:
    entries = [_emit_one(it, r) for it in items]
    banner = generated_banner(
        "items.dat (+ item_names/item_descriptions.json sidecars)", GENERATOR, timestamp=False
    )
    note = (
        "// NOTE: only deterministic fields (name, price, description, pocket,\n"
        "// importance) are emitted. Item *behavior* — field use, battle use,\n"
        "// hold effect, TM/HM linkage — is Phase 6 engine work; the raw\n"
        "// Essentials codes for every item are in intermediate/\n"
        "// item_field_codes.json. Behavior struct fields are left at default.\n"
    )
    includes = '#include "constants/items.h"\n#include "constants/item.h"\n'
    head = "const struct ItemInfo gItemsInfo[] =\n{\n"
    return banner + note + "\n" + includes + "\n" + head + "\n".join(entries) + "\n};\n"


def emit_constants(items: list[Item], r: _ItemResolver) -> str:
    lines = ["#define ITEM_NONE 0"]
    seen: dict[str, int] = {}
    for it in items:
        const = r.constant(it.id)
        prev = seen.get(const)
        if prev is not None:
            raise ValueError(
                f"item constant collision: {const} minted for both id {prev} and {it.id} "
                f"(distinct display names normalized to the same constant)"
            )
        seen[const] = it.id
        lines.append(f"#define {const} {it.id}")
    banner = generated_banner("items.dat + Constants.rxdata", GENERATOR, timestamp=False)
    note = (
        "// NOTE: these are Uranium's own item IDs. They overlap vanilla ITEM_*\n"
        "// numbering — V6 integration must reconcile them with the fork enum.\n"
    )
    return wrap_header("GUARD_URANIUM_CONSTANTS_ITEMS_H", note + "\n".join(lines), banner=banner)


def run(uranium_src: Path, out_dir: Path, id_map: IdMap) -> None:
    """Phase 2 §2.3 entry point: parse items and emit C table + worklist."""
    items = parse(uranium_src / "Data" / "items.dat")
    ref = _reference_dir()
    attach_internal_names(items, _load_id_json(ref / "item_internal_names.json"))
    r = _build_resolver(id_map, ref)

    inc = out_dir / "include" / "constants"
    data = out_dir / "src" / "data"
    inter = out_dir / "intermediate"
    for d in (inc, data, inter):
        d.mkdir(parents=True, exist_ok=True)

    (inc / "items.h").write_text(emit_constants(items, r), encoding="utf-8")
    (data / "items.h").write_text(emit_items_info(items, r), encoding="utf-8")

    # Phase 6 worklist: every item's raw Essentials behavior codes, keyed by the
    # minted ITEM_* constant. Nothing about item behavior is lost here.
    worklist = {
        r.constant(it.id): {
            "item_use": it.item_use,
            "battle_use": it.battle_use,
            "item_type": it.item_type,
            "machine_move_id": it.machine_move,
        }
        for it in items
    }
    (inter / "item_field_codes.json").write_text(
        json.dumps(dict(sorted(worklist.items())), indent=2) + "\n", encoding="utf-8"
    )

    needs = sum(1 for it in items if r.constant(it.id) in id_map.needs_engine["items"])
    logger.info(
        "emitted item data for %d items (%d Uranium-original → needs_engine; "
        "behavior deferred to Phase 6)",
        len(items),
        needs,
    )
