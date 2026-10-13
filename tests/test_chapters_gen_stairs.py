"""No committed generated suite may refuse a staircase.

A refused stair row is a staircase nothing ever crosses on ROM. CH02's Route 1
and CH06's Nowtoch park staircases both sat in `REFUSED` through approved
reviews, and the Nowtoch one was broken on device (multi-step stairs,
`tileset_converter.stairs.lane_cells`). Read statically: importing a module
builds its whole chapter.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_GEN_DIR = Path(__file__).resolve().parent.parent / "src" / "rpg2gba" / "playtest" / "chapters_gen"


def _refused_keys(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "REFUSED":
            assert isinstance(node.value, ast.Dict)
            return [ast.literal_eval(k) for k in node.value.keys if k is not None]
    return []


@pytest.mark.parametrize("path", sorted(_GEN_DIR.glob("ch[0-9][0-9].py")), ids=lambda p: p.stem)
def test_no_stair_row_is_refused(path: Path) -> None:
    stairs = [key for key in _refused_keys(path) if "/terrain/stairs/" in key]
    assert not stairs, f"{path.name} refuses staircase rows: {stairs}"
