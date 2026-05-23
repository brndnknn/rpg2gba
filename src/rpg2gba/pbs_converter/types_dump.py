"""Phase 2 §2.10 — dump `types.dat` to a JSON reference (no C emission, per D7).

`types.dat` is Ruby Marshal: `[pseudotypes, specialtypes, typechart]`
(Compiler.rb:2262). `typechart` is a flat `count*count` effectiveness array; per
Compiler.rb:2246-2258 the index is `attacking_type * count + defending_type`,
with values 0=immune, 1=not-very-effective, 2=normal, 4=super-effective.

Uranium has 20 types (Nuclear at index 18). This is a standalone dump — it is
**not** a pipeline converter (no `run`; `types` is absent from
`pipeline.module_order`) and touches no constant namespace. Per D7 the actual
`gTypeEffectiveness[]` C emission is Phase 6; Phase 2 only snapshots the matrix
to `reference/types_dump.json` to unblock that planning.
"""
from __future__ import annotations

import json
import logging
import math
import tempfile
from pathlib import Path

from ._marshal import dump_dat, load_json

logger = logging.getLogger(__name__)


def _load_id_json(path: Path) -> dict[int, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in raw.items()}


def _reference_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "reference"


def dump_types(uranium_src: Path, out_path: Path) -> None:
    """Read types.dat and write `out_path` as {types, matrix, nuclear_index, ...}."""
    ref = _reference_dir()
    with tempfile.TemporaryDirectory() as tmp:
        raw = load_json(dump_dat(uranium_src / "Data" / "types.dat", Path(tmp) / "types_raw.json"))
    if not (isinstance(raw, list) and len(raw) == 3):
        raise ValueError(f"types.dat: expected [pseudotypes, specialtypes, typechart], got {raw!r}")
    pseudotypes, special_types, typechart = raw

    count = math.isqrt(len(typechart))
    if count * count != len(typechart):
        raise ValueError(f"types.dat: typechart length {len(typechart)} is not a perfect square")

    names_by_id = _load_id_json(ref / "type_internal_names.json")
    if len(names_by_id) != count:
        raise ValueError(
            f"types.dat: {count} types in matrix but "
            f"type_internal_names.json has {len(names_by_id)}"
        )
    types = []
    for i in range(count):
        name = names_by_id.get(i)
        if name is None:
            raise ValueError(f"type index {i} absent from type_internal_names.json")
        types.append(name)

    # matrix[attacking][defending] = typechart[attacking * count + defending]
    matrix = [[typechart[a * count + d] for d in range(count)] for a in range(count)]

    try:
        nuclear_index = types.index("NUCLEAR")
    except ValueError:
        raise ValueError("types.dat: no NUCLEAR type found in type_internal_names.json") from None

    payload = {
        "_comment": (
            "Uranium 20-type effectiveness matrix. matrix[attacking][defending]: "
            "0=immune, 1=not-very-effective, 2=normal, 4=super-effective. "
            "C emission (gTypeEffectiveness) is Phase 6 (D7)."
        ),
        "types": types,
        "nuclear_index": nuclear_index,
        "pseudotypes": pseudotypes,
        "special_types": special_types,
        "matrix": matrix,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info(
        "dumped %d-type effectiveness matrix (Nuclear @ %d) -> %s",
        count,
        nuclear_index,
        out_path,
    )


if __name__ == "__main__":  # pragma: no cover
    import os

    from ..pipeline import _load_dotenv

    _load_dotenv()
    logging.basicConfig(level=logging.INFO)
    dump_types(Path(os.environ["RPG2GBA_URANIUM_SRC"]), _reference_dir() / "types_dump.json")
