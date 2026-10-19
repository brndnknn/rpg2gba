"""Which items to generate, and how each one behaves."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rpg2gba.pbs_converter import items as pbs_items

REFERENCE = Path(__file__).resolve().parents[3] / "reference"
ID_MAP_PATH = REFERENCE / "uranium_id_map.json"
RULINGS_PATH = REFERENCE / "item_rulings.json"

Kind = Literal["key", "inert", "held", "berry", "heal", "blocked"]
_KINDS: frozenset[str] = frozenset({"key", "inert", "held", "berry", "heal", "blocked"})
_KEY_POCKET = 8  # Essentials Key Items


@dataclass(frozen=True)
class GenItem:
    uranium_id: int
    internal: str          # Uranium internal name (rulings / id-map key)
    constant: str          # ITEM_*
    name: str              # display name (after any ruling override)
    description: str       # Uranium's description, unwrapped
    price: int
    essentials_pocket: int
    kind: Kind
    analog: str | None = None      # stock ITEM_* cloned by berry/heal kinds
    heal_hp: int = 0
    cure_status: bool = False

    @property
    def ident(self) -> str:
        """CamelCase symbol suffix: ITEM_ACAI_BERRY -> AcaiBerry."""
        return "".join(p.capitalize() for p in self.constant.removeprefix("ITEM_").split("_"))


@dataclass(frozen=True)
class Catalog:
    berries: tuple[GenItem, ...]   # continue the stock berry run, Uranium-id order
    tail: tuple[GenItem, ...]      # follow the last stock item, Uranium-id order
    blocked: tuple[GenItem, ...]   # not generated

    @property
    def generated(self) -> tuple[GenItem, ...]:
        return self.berries + self.tail


def generated_constants(*, id_map_path: Path = ID_MAP_PATH,
                        rulings_path: Path = RULINGS_PATH) -> frozenset[str]:
    """The `ITEM_*` constants the item pass generates into the engine.

    Derived from the two reference files alone (no Uranium tree), so the
    conversion-time gate and transpiler can accept them before the assembler
    has ever run. Matches `build_catalog`'s generated set: every missing item
    except the blocked ones."""
    id_map = json.loads(Path(id_map_path).read_text(encoding="utf-8"))
    rulings = json.loads(Path(rulings_path).read_text(encoding="utf-8"))["items"]
    internal_by_const = {c: i for i, c in id_map["items"].items()}
    return frozenset(
        c for c in id_map["needs_engine"]["items"]
        if rulings.get(internal_by_const[c], {}).get("kind") != "blocked"
    )


def _load_ids(path: Path) -> dict[int, str]:
    return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def build_catalog(uranium_src: Path, *, id_map_path: Path = ID_MAP_PATH,
                  rulings_path: Path = RULINGS_PATH,
                  reference_dir: Path = REFERENCE) -> Catalog:
    """Every item in `needs_engine.items`, classified by the rulings file.

    Fails loud on an item the rulings don't cover (outside the key pocket), on
    a ruling for an item that isn't missing, and on an unknown kind."""
    id_map = json.loads(Path(id_map_path).read_text(encoding="utf-8"))
    rulings = json.loads(Path(rulings_path).read_text(encoding="utf-8"))["items"]
    data = Path(reference_dir) / "uranium_data"
    internal_by_id = _load_ids(data / "item_internal_names.json")
    names = _load_ids(data / "item_names.json")
    descs = _load_ids(data / "item_descriptions.json")
    id_by_internal = {v: k for k, v in internal_by_id.items()}
    records = {it.id: it for it in pbs_items.parse(Path(uranium_src) / "Data" / "items.dat")}
    internal_by_const = {c: i for i, c in id_map["items"].items()}

    missing = sorted(id_map["needs_engine"]["items"])
    missing_internals = {internal_by_const[c] for c in missing}
    stray = sorted(set(rulings) - missing_internals)
    if stray:
        raise ValueError(f"item_rulings.json rules items the engine already has: {stray}")

    out: list[GenItem] = []
    for const in missing:
        internal = internal_by_const[const]
        uid = id_by_internal[internal]
        rec = records[uid]
        ruling = rulings.get(internal)
        if ruling is None:
            if rec.pocket != _KEY_POCKET:
                raise ValueError(
                    f"{internal} ({const}) is in Essentials pocket {rec.pocket} and has no "
                    "ruling in item_rulings.json; decide how it is generated"
                )
            ruling = {"kind": "key"}
        kind = ruling["kind"]
        if kind not in _KINDS:
            raise ValueError(f"{internal}: unknown kind {kind!r}")
        if kind in ("berry", "heal") and not ruling.get("analog"):
            raise ValueError(f"{internal}: kind {kind!r} needs an analog stock item")
        out.append(GenItem(
            uranium_id=uid,
            internal=internal,
            constant=const,
            name=ruling.get("display_name") or names.get(uid) or internal,
            description=descs.get(uid, ""),
            price=rec.price,
            essentials_pocket=rec.pocket,
            kind=kind,
            analog=ruling.get("analog"),
            heal_hp=int(ruling.get("heal_hp", 0)),
            cure_status=bool(ruling.get("cure_status", False)),
        ))
    out.sort(key=lambda g: g.uranium_id)
    return Catalog(
        berries=tuple(g for g in out if g.kind == "berry"),
        tail=tuple(g for g in out if g.kind not in ("berry", "blocked")),
        blocked=tuple(g for g in out if g.kind == "blocked"),
    )
