"""Validate deserialized map JSON (PHASE3_PLAN §3.4 / test strategy).

`.rxdata` is Marshal output and cannot be re-emitted, so Phase 2's
parse→emit→re-parse round-trip is impossible here. Fidelity is guarded instead
by two cheap, strong invariants:

1. **Conservation** — total maps/events/pages must equal the Phase 0 inventory
   oracle (`reference/map_inventory.md`). A dropped event or page shows up here,
   not as a soft-lock five phases later.
2. **Schema conformance** — every container has the keys the Phase 4 contract
   (PHASE3_PLAN §E1) promises.

Both are exposed as functions so the `phase3` pipeline command and the test
suite share one implementation. Fail-loud (CLAUDE §4.5): any deviation raises.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Inventory oracle — source: reference/map_inventory.md (Phase 0, scripts/recon_maps.rb).
# If recon_maps.rb is re-run and these change, update both this constant and the
# inventory doc (PHASE3_PLAN P3).
ORACLE = {"maps": 199, "events": 5301, "pages": 8429}

_MAP_KEYS = {"map_id", "tileset_id", "width", "height", "tiles", "events"}
_EVENT_KEYS = {"id", "name", "x", "y", "pages"}
_COMMAND_KEYS = {"code", "indent", "parameters"}


class ValidationError(RuntimeError):
    """Raised when deserialized output violates conservation or schema."""


def _check_map(path: Path) -> tuple[int, int]:
    """Schema-check one MapNNN.json; return (event_count, page_count)."""
    m = json.loads(path.read_text(encoding="utf-8"))
    missing = _MAP_KEYS - m.keys()
    if missing:
        raise ValidationError(f"{path.name}: map missing keys {sorted(missing)}")

    n_events = n_pages = 0
    for ev in m["events"]:
        if _EVENT_KEYS - ev.keys():
            raise ValidationError(
                f"{path.name}: event {ev.get('id')} missing keys "
                f"{sorted(_EVENT_KEYS - ev.keys())}"
            )
        n_events += 1
        for page in ev["pages"]:
            if "list" not in page:
                raise ValidationError(
                    f"{path.name}: event {ev['id']} page has no command list"
                )
            n_pages += 1
            for cmd in page["list"]:
                if _COMMAND_KEYS - cmd.keys():
                    raise ValidationError(
                        f"{path.name}: event {ev['id']} command missing keys "
                        f"{sorted(_COMMAND_KEYS - cmd.keys())}"
                    )
    return n_events, n_pages


def validate_output(out_dir: Path, *, oracle: bool = True) -> dict[str, int]:
    """Schema-check every map and (optionally) assert conservation against ORACLE.

    Returns the tally `{"maps", "events", "pages"}`. Raises ValidationError on
    any schema violation, or on a conservation mismatch when `oracle=True`.
    """
    out_dir = Path(out_dir)
    maps_dir = out_dir / "maps"
    map_files = sorted(maps_dir.glob("Map*.json"))
    if not map_files:
        raise ValidationError(f"no MapNNN.json under {maps_dir}")

    totals = {"maps": len(map_files), "events": 0, "pages": 0}
    for path in map_files:
        n_ev, n_pg = _check_map(path)
        totals["events"] += n_ev
        totals["pages"] += n_pg

    # The aux files must at least be present and parseable.
    for name in ("common_events.json", "system.json", "map_infos.json"):
        aux = out_dir / name
        if not aux.is_file():
            raise ValidationError(f"missing aux output: {name}")
        json.loads(aux.read_text(encoding="utf-8"))

    if oracle and totals != ORACLE:
        raise ValidationError(
            f"conservation mismatch: got {totals}, expected {ORACLE} "
            f"(reference/map_inventory.md)"
        )

    logger.info(
        "validated %d maps / %d events / %d pages",
        totals["maps"],
        totals["events"],
        totals["pages"],
    )
    return totals
