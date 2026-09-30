"""`Emulator.face` turns without stepping (ROM run 45: the walk to the lab
heal machine's west side ended facing it, and a 3-frame "turn" press
walked the player onto the event's own cell).

Same style as `test_walk_interruption.py`: `Emulator.face` borrowed unbound
onto a bare fake, gated on mgba being importable."""
import importlib.util
from dataclasses import dataclass

import pytest

needs_mgba = pytest.mark.skipif(
    importlib.util.find_spec("mgba") is None,
    reason="needs the mgba python bindings to import emulator.py",
)


@dataclass
class _Obj:
    facing: str


class _FaceEmu:
    def __init__(self, facing: str) -> None:
        self.facing = facing
        self.taps: list[str] = []

    def resolve_constant(self, name: str) -> int:
        assert name == "LOCALID_PLAYER"
        return 255

    def object_event(self, local_id: int) -> _Obj:
        return _Obj(self.facing)

    def tap(self, key: str, hold: int = 1, release: int = 1) -> None:
        self.taps.append(key)


@needs_mgba
def test_face_is_a_no_op_when_already_facing_that_way():
    from rpg2gba.playtest.emulator import Emulator
    emu = _FaceEmu("RIGHT")
    Emulator.face(emu, "RIGHT")
    assert emu.taps == []


@needs_mgba
def test_face_taps_to_turn():
    from rpg2gba.playtest.emulator import Emulator
    emu = _FaceEmu("DOWN")
    Emulator.face(emu, "RIGHT")
    assert emu.taps == ["RIGHT"]
