"""Map viewer "Animated" overlay — marks cells with a multi-frame autotile.

Only the pure per-tile classifier (`_tile_is_animated`) is exercised here;
standing up a full `_ensure_loaded`/`build_map_data` map fixture (rxdata,
tilesets.json, on-disk PNGs) is disproportionate for this display-only helper.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from map_viewer_common import _tile_is_animated  # noqa: E402


def test_static_tile_id_below_autotile_range() -> None:
    assert _tile_is_animated(0, {0, 1, 2}) is False


def test_static_tile_id_above_autotile_range() -> None:
    # 384+ is the static tileset range, never animated regardless of slots set.
    assert _tile_is_animated(400, {0, 1, 2, 3, 4, 5, 6}) is False


def test_autotile_in_animated_slot() -> None:
    # tile_id 48 -> slot 48//48 - 1 == 0
    assert _tile_is_animated(48, {0}) is True


def test_autotile_not_in_animated_slot() -> None:
    # tile_id 96 -> slot 96//48 - 1 == 1, not animated
    assert _tile_is_animated(96, {0}) is False


def test_autotile_slot_boundary() -> None:
    # tile_id 383 -> slot 383//48 - 1 == 6 (last autotile slot)
    assert _tile_is_animated(383, {6}) is True
