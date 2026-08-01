"""Unit tests for sprite_pass.py — the gfx-map-driven sheet selection and the
JSON-vs-art consistency gates that keep `reference/npc_gfx_map.json` (the §4.3
source of truth the transpiler reads) honest about what the sprite pass will
actually put in the ROM."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from rpg2gba.tileset_converter.graphics.sprites import (
    LARGE_PROP_FRAME_PX,
    LARGE_PROP_IDLE_STATE,
    ConvertedSprite,
)
from rpg2gba.tileset_converter.sprite_pass import _check_declared_states


def _prop(name: str, states: tuple[tuple[int, int], ...]) -> ConvertedSprite:
    frame = np.zeros((LARGE_PROP_FRAME_PX, LARGE_PROP_FRAME_PX, 4), dtype=np.uint8)
    frame[0, 0] = (1, 2, 3, 255)
    return ConvertedSprite(
        name=name, frames=[frame.copy() for _ in states], cycle="large_prop",
        asymmetry=0.0, content_size=(1, 1), frame_px=LARGE_PROP_FRAME_PX,
        states=states,
    )


def _map_file(tmp_path: Path, entry: dict) -> Path:
    path = tmp_path / "npc_gfx_map.json"
    path.write_text(json.dumps({"PU-PokeballMachine": entry}), encoding="utf-8")
    return path


def test_declared_states_matching_the_art_pass(tmp_path: Path) -> None:
    path = _map_file(tmp_path, {
        "gfx": "OBJ_EVENT_GFX_URANIUM_PU_POKEBALLMACHINE",
        "states": {
            "2,0": "OBJ_EVENT_GFX_URANIUM_PU_POKEBALLMACHINE",
            "2,1": "OBJ_EVENT_GFX_URANIUM_PU_POKEBALLMACHINE_D2P1",
        },
    })
    _check_declared_states(path, [_prop("PU-PokeballMachine", (LARGE_PROP_IDLE_STATE, (2, 1)))])


def test_state_in_the_art_but_not_declared_fails_loud(tmp_path: Path) -> None:
    """An emitted state the JSON never declares is one the transpiler can never
    reach — the swap would queue while the frame sat unused in the ROM."""
    path = _map_file(tmp_path, {
        "gfx": "OBJ_EVENT_GFX_URANIUM_PU_POKEBALLMACHINE",
        "states": {"2,0": "OBJ_EVENT_GFX_URANIUM_PU_POKEBALLMACHINE"},
    })
    with pytest.raises(ValueError, match=r"missing: \[\(2, 1\)\]"):
        _check_declared_states(
            path, [_prop("PU-PokeballMachine", (LARGE_PROP_IDLE_STATE, (2, 1)))]
        )


def test_declared_state_the_art_lacks_fails_loud(tmp_path: Path) -> None:
    """A declared state with no cell behind it would pass the fork gate (the
    constant is in the map) and then show nothing."""
    path = _map_file(tmp_path, {
        "gfx": "OBJ_EVENT_GFX_URANIUM_PU_POKEBALLMACHINE",
        "states": {
            "2,0": "OBJ_EVENT_GFX_URANIUM_PU_POKEBALLMACHINE",
            "8,3": "OBJ_EVENT_GFX_URANIUM_PU_POKEBALLMACHINE_D8P3",
        },
    })
    with pytest.raises(ValueError, match=r"stale: \[\(8, 3\)\]"):
        _check_declared_states(path, [_prop("PU-PokeballMachine", (LARGE_PROP_IDLE_STATE,))])


def test_sheet_with_no_states_either_side_passes(tmp_path: Path) -> None:
    path = _map_file(tmp_path, {"gfx": "OBJ_EVENT_GFX_URANIUM_PU_POKEBALLMACHINE"})
    frame = np.zeros((32, 32, 4), dtype=np.uint8)
    walker = ConvertedSprite(
        name="HGSS_000", frames=[frame.copy() for _ in range(9)],
        cycle="neutral02", asymmetry=0.0, content_size=(1, 1),
    )
    _check_declared_states(path, [walker])
