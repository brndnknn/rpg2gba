"""Step 1 — tileset source resolution (image pipeline)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from rpg2gba.tileset_converter.graphics import sources as src


def _png(path: Path, size: tuple[int, int] = (8, 8)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (1, 2, 3, 255)).save(path)


def _write_tilesets(path: Path, entries: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


def _fixture(tmp_path: Path, *, autotile_names: list[str]) -> tuple[Path, Path]:
    """A graphics dir + tilesets.json for one tileset id 19."""
    gfx = tmp_path / "Graphics"
    _png(gfx / "Tilesets" / "Indoor(1).png")
    for name in autotile_names:
        if name:
            _png(gfx / "Autotiles" / f"{name}.png")
    tj = tmp_path / "tilesets.json"
    _write_tilesets(
        tj,
        {
            "19": {
                "id": 19,
                "name": "Inner (REV)",
                "tileset_name": "Indoor(1)",
                "autotile_names": autotile_names,
            }
        },
    )
    return gfx, tj


def test_slot_base_roundtrip() -> None:
    for slot in range(7):
        base = src.base_for_slot(slot)
        assert src.slot_for_base(base) == slot
    assert src.base_for_slot(0) == 48
    assert src.base_for_slot(6) == 336
    assert src.slot_for_base(144) == 2


def test_resolves_tileset_and_autotiles(tmp_path: Path) -> None:
    names = ["Black", "", "", "", "", "", "Flowers"]
    gfx, tj = _fixture(tmp_path, autotile_names=names)
    s = src.load_tileset_sources(19, tilesets_json=tj, graphics_dir=gfx)

    assert s.tileset_id == 19
    assert s.tileset_png.name == "Indoor(1).png"
    assert len(s.autotiles) == 7
    assert s.autotiles[0] is not None and s.autotiles[0].name == "Black.png"
    assert s.autotiles[1] is None  # empty slot
    assert s.autotile_for_base(48).name == "Black.png"
    assert s.autotile_for_base(96) is None
    assert s.autotile_for_tile(50).name == "Black.png"  # 50 // 48 == slot 0
    assert s.autotile_for_tile(370) is not None  # slot 6 -> Flowers


def test_missing_autotile_png_fails_loud_on_access(tmp_path: Path) -> None:
    """A named-but-absent autotile is fail-loud — but lazily, only when its slot
    is actually accessed. Naming an asset no map paints (a dead reference like
    OverWorld 'City') must not abort the tileset at load time."""
    names = ["Ghost", "", "", "", "", "", ""]  # named slot 0, but no file written
    gfx = tmp_path / "Graphics"
    _png(gfx / "Tilesets" / "Indoor(1).png")
    tj = tmp_path / "tilesets.json"
    _write_tilesets(
        tj,
        {"19": {"id": 19, "tileset_name": "Indoor(1)", "autotile_names": names}},
    )
    # Load no longer resolves autotiles eagerly: the missing PNG doesn't abort here.
    s = src.load_tileset_sources(19, tilesets_json=tj, graphics_dir=gfx)
    assert s.autotiles[1] is None  # an unused slot resolves to None, no error
    # Accessing the named-but-missing slot is where it fails loud.
    with pytest.raises(FileNotFoundError, match="Ghost"):
        _ = s.autotiles[0]


def test_missing_tileset_id_fails_loud(tmp_path: Path) -> None:
    gfx, tj = _fixture(tmp_path, autotile_names=[""] * 7)
    with pytest.raises(KeyError, match="22"):
        src.load_tileset_sources(22, tilesets_json=tj, graphics_dir=gfx)


def test_wrong_autotile_name_count_fails_loud(tmp_path: Path) -> None:
    gfx = tmp_path / "Graphics"
    _png(gfx / "Tilesets" / "Indoor(1).png")
    tj = tmp_path / "tilesets.json"
    _write_tilesets(
        tj, {"19": {"id": 19, "tileset_name": "Indoor(1)", "autotile_names": ["a", "b"]}}
    )
    with pytest.raises(ValueError, match="autotile_names"):
        src.load_tileset_sources(19, tilesets_json=tj, graphics_dir=gfx)


def test_case_folded_resolution(tmp_path: Path) -> None:
    gfx = tmp_path / "Graphics"
    _png(gfx / "Tilesets" / "indoor(1).png")  # lowercase on disk
    tj = tmp_path / "tilesets.json"
    _write_tilesets(
        tj, {"19": {"id": 19, "tileset_name": "Indoor(1)", "autotile_names": [""] * 7}}
    )
    s = src.load_tileset_sources(19, tilesets_json=tj, graphics_dir=gfx)
    assert s.tileset_png.name == "indoor(1).png"
