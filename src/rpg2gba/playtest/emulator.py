"""Headless mGBA core wrapper with poll-state input primitives.

Design rule (from the feasibility study): never frame-count a scripted input
tape — poll game state (coords, field-controls lock) and act on it, with
frame-budget timeouts that fail loud with a screenshot. That keeps scenarios
robust against text-length, timing, and converter changes.
"""
import logging
from pathlib import Path

from .errors import ScenarioError
from .offsets import probe_offsets
from .symbols import SymbolMap, static_addr_via_accessor

try:
    import mgba.core
    import mgba.image
    import mgba.log
    from mgba.gba import GBA
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "mGBA python bindings not installed — run scripts/fetch_libmgba.py"
    ) from exc

logger = logging.getLogger(__name__)

KEYS = {
    "A": GBA.KEY_A, "B": GBA.KEY_B, "SELECT": GBA.KEY_SELECT,
    "START": GBA.KEY_START, "RIGHT": GBA.KEY_RIGHT, "LEFT": GBA.KEY_LEFT,
    "UP": GBA.KEY_UP, "DOWN": GBA.KEY_DOWN, "R": GBA.KEY_R, "L": GBA.KEY_L,
}


class Emulator:
    """One headless core for one ROM, wired to one engine build's artifacts."""

    def __init__(self, rom: Path, engine: Path,
                 screenshot_dir: Path | None = None):
        mgba.log.silence()
        self.rom = rom
        self.engine = engine
        self.screenshot_dir = screenshot_dir
        self.symbols = SymbolMap(engine / "pokeemerald.map")
        self.offsets = probe_offsets(engine)
        self._lock_addr = static_addr_via_accessor(
            engine / "pokeemerald.elf",
            self.symbols["ArePlayerFieldControlsLocked"],
        )
        self.core = mgba.core.load_path(str(rom))
        if self.core is None:
            raise ScenarioError(f"could not load ROM {rom}")
        self.screen = mgba.image.Image(*self.core.desired_video_dimensions())
        self.core.set_video_buffer(self.screen)
        if not self.core.autoload_save():
            # Without this, in-game saves are silently discarded (spike 3).
            raise ScenarioError(f"could not attach save file for {rom}")
        self.core.reset()
        self.frame = 0

    # -- raw access ---------------------------------------------------------

    def run(self, frames: int, keys: list[str] | None = None) -> None:
        mask = 0
        for k in keys or []:
            mask |= 1 << KEYS[k]
        self.core._core.setKeys(self.core._core, mask)
        for _ in range(frames):
            self.core.run_frame()
        self.frame += frames
        self.core._core.setKeys(self.core._core, 0)

    def u8(self, addr: int) -> int:
        return self.core.memory.u8[addr]

    def u32(self, addr: int) -> int:
        return self.core.memory.u32[addr]

    def read_bytes(self, addr: int, size: int) -> bytes:
        return bytes(self.core.memory.u8[addr : addr + size])

    def screenshot(self, name: str) -> Path | None:
        if self.screenshot_dir is None:
            return None
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{name}_f{self.frame}.png"
        self.screen.to_pil().convert("RGB").save(path)
        return path

    # -- game state ---------------------------------------------------------

    @property
    def sb1(self) -> int:
        return self.u32(self.symbols["gSaveBlock1Ptr"])

    def player_pos(self) -> tuple[int, int]:
        base = self.sb1 + self.offsets["off_sb1_pos"]
        return self.core.memory.u16[base], self.core.memory.u16[base + 2]

    def map_location(self) -> tuple[int, int]:
        base = self.sb1 + self.offsets["off_sb1_location"]
        return self.u8(base), self.u8(base + 1)

    def flag(self, flag_id: int) -> bool:
        byte = self.u8(self.sb1 + self.offsets["off_sb1_flags"] + flag_id // 8)
        return bool(byte >> (flag_id % 8) & 1)

    def field_locked(self) -> bool:
        """True while a script/dialogue holds the overworld controls."""
        return self.u8(self._lock_addr) != 0

    # -- primitives ---------------------------------------------------------

    def tap(self, key: str, hold: int = 6, release: int = 6) -> None:
        self.run(hold, [key])
        self.run(release)

    def face(self, direction: str) -> None:
        # A sub-step press turns in place without moving.
        self.tap(direction, hold=3, release=8)

    def walk_to(self, tx: int, ty: int, frame_budget: int = 3000) -> None:
        """Greedy two-axis walk with blocked-axis fallback."""
        spent = 0
        while spent < frame_budget:
            if self.field_locked():
                # A script owns the player (scene auto-walk, dialogue we
                # bumped into). Don't fight it — wait, then re-path from
                # wherever it leaves us.
                self.run(30)
                spent += 30
                continue
            x, y = self.player_pos()
            if (x, y) == (tx, ty):
                # The coord ticks before the step animation finishes; settle
                # so a follow-up face/interact isn't eaten by the motion.
                self.run(16)
                return
            dx, dy = tx - x, ty - y
            axes = [("RIGHT" if dx > 0 else "LEFT") if dx else None,
                    ("DOWN" if dy > 0 else "UP") if dy else None]
            if abs(dy) > abs(dx):
                axes.reverse()
            for d in (a for a in axes if a):
                # Step-granular: release the key the moment the coord ticks
                # over, so a burst can never overshoot onto a warp/trigger
                # tile beyond the target.
                # 40-frame cap: a turn-in-place (~8f) plus one walk step
                # (~16f) fits with margin; a blocked direction burns the
                # cap and falls through to the other axis.
                moved = False
                for _ in range(40):
                    self.run(1, [d])
                    spent += 1
                    if self.player_pos() != (x, y):
                        moved = True
                        break
                if moved:
                    break
            else:
                shot = self.screenshot("walk_stuck")
                raise ScenarioError(
                    f"stuck at {x},{y} heading for {tx},{ty} ({shot})")
        shot = self.screenshot("walk_budget")
        raise ScenarioError(f"walk_to({tx},{ty}) frame budget exhausted ({shot})")

    def interact(self) -> None:
        """Press A; fail if no script picks up the field controls."""
        self.tap("A")
        self.run(30)
        if not self.field_locked():
            shot = self.screenshot("interact_noop")
            raise ScenarioError(f"interaction did not start a script ({shot})")

    def advance_dialog(self, max_taps: int = 1500) -> int:
        taps = 0
        while self.field_locked():
            if taps >= max_taps:
                shot = self.screenshot("dialog_stuck")
                raise ScenarioError(
                    f"dialogue never released field controls ({shot})")
            self.tap("A")
            taps += 1
        return taps
