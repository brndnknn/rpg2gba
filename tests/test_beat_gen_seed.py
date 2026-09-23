"""Tests for `rpg2gba.beat_gen.seed` (C6 seed recompute)."""
from __future__ import annotations

from pathlib import Path

import pytest

from rpg2gba.beat_gen.seed import route_winner

_MODULE = '''
from types import SimpleNamespace as _B
CHAPTER = _B(beats=(
    _B(name="CHZ:inherited", rows=("map001/ev009/p0",)),
    _B(name="a", rows=("map001/ev001/p0",)),
    _B(name="b", rows=("map001/ev002/p0", "map001/ev002/p0/b0")),
    _B(name="c", rows=("map001/ev003/p0",)),
))
'''


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    (tmp_path / "chy.generated.py").write_text(_MODULE, encoding="utf-8")
    return tmp_path


def test_last_writer_in_the_predecessor_route_wins(out_dir: Path):
    winner_for = route_winner("CHX", out_dir)
    assert winner_for("CHY", ("map001/ev003/p0", "map001/ev001/p0")) == "map001/ev003/p0"
    assert winner_for("CHY", ("map001/ev001/p0", "map001/ev002/p0/b0")) == "map001/ev002/p0/b0"


def test_the_chapter_being_generated_has_no_route_yet(out_dir: Path):
    assert route_winner("CHY", out_dir)("CHY", ("map001/ev001/p0", "map001/ev003/p0")) is None


def test_an_unwalked_writer_keeps_the_join(out_dir: Path):
    # Inherited beats (a `:` name) are not this chapter's route.
    assert route_winner("CHX", out_dir)("CHY", ("map001/ev001/p0", "map001/ev009/p0")) is None


def test_a_predecessor_never_generated_fails_loud(tmp_path: Path):
    with pytest.raises(ValueError, match="generate --chapter CHW"):
        route_winner("CHX", tmp_path)("CHW", ("map001/ev001/p0", "map001/ev003/p0"))
