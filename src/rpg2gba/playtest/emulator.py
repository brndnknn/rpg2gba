"""Headless mGBA core wrapper with poll-state input primitives.

Design rule (from the feasibility study): never frame-count a scripted input
tape — poll game state (coords, field-controls lock) and act on it, with
frame-budget timeouts that fail loud with a screenshot. That keeps scenarios
robust against text-length, timing, and converter changes.
"""
import logging
from collections.abc import Sequence
from pathlib import Path

from .contact_sheet import Waypoint
from .errors import ScenarioError
from .offsets import probe_constants, probe_offsets
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

# walk_to's step-aside fallback (ROM_TEST_DEV.md C6a): per-direction grid
# deltas, and the two directions perpendicular to each axis.
_DIR_DELTA: dict[str, tuple[int, int]] = {
    "LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1), "DOWN": (0, 1),
}
_PERPENDICULAR: dict[str, tuple[str, str]] = {
    "LEFT": ("UP", "DOWN"), "RIGHT": ("UP", "DOWN"),
    "UP": ("LEFT", "RIGHT"), "DOWN": ("LEFT", "RIGHT"),
}


class Emulator:
    """One headless core for one ROM, wired to one engine build's artifacts."""

    def __init__(self, rom: Path, engine: Path,
                 screenshot_dir: Path | None = None):
        mgba.log.silence()
        self.rom = rom
        self.engine = engine
        self.screenshot_dir = screenshot_dir
        self.waypoints: list[Waypoint] = []
        self.symbols = SymbolMap(engine / "pokeemerald.map")
        self.offsets = probe_offsets(engine)
        self._constants: dict[str, int] = {}
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

    def u16(self, addr: int) -> int:
        return self.core.memory.u16[addr]

    def u32(self, addr: int) -> int:
        return self.core.memory.u32[addr]

    def write_u16(self, addr: int, value: int) -> None:
        self.core.memory.u16[addr] = value

    def read_bytes(self, addr: int, size: int) -> bytes:
        return bytes(self.core.memory.u8[addr : addr + size])

    def screenshot(self, name: str) -> Path | None:
        if self.screenshot_dir is None:
            return None
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{name}_f{self.frame}.png"
        self.screen.to_pil().convert("RGB").save(path)
        return path

    def waypoint(self, beat: str, name: str = "", note: str = "",
                 failed: bool = False) -> Waypoint | None:
        """Capture a frame for the run's contact sheet (ROM_TEST_DEV §2).

        Distinct from `screenshot`, which is failure evidence: waypoints are
        the *by-eye review surface* — the frames a human scans for the
        cosmetic defect class state assertions can't see. The runner takes
        one at every beat boundary automatically; a beat calls this itself
        when something mid-beat is worth a look (a cutscene's peak, a room
        the player only passes through).
        """
        if self.screenshot_dir is None:
            return None
        wp_dir = self.screenshot_dir / "waypoints"
        wp_dir.mkdir(parents=True, exist_ok=True)
        slug = f"{len(self.waypoints):02d}_{beat}"
        if name:
            slug += f"_{name}"
        path = wp_dir / f"{slug}.png"
        self.screen.to_pil().convert("RGB").save(path)
        wp = Waypoint(beat=beat, name=name or beat, note=note,
                      frame=self.frame, path=path, failed=failed)
        self.waypoints.append(wp)
        return wp

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

    def resolve_constant(self, name: str) -> int:
        """Resolve one `FLAG_*`/`VAR_*` (or any C macro) name to its value.

        Cache miss costs one gcc invocation; for more than one name at a
        time use `resolve_constants` so scenarios don't pay one compile per
        name.
        """
        if name not in self._constants:
            self._constants.update(probe_constants(self.engine, [name]))
        return self._constants[name]

    def resolve_constants(self, names: Sequence[str]) -> dict[str, int]:
        """Resolve several names in a single probe compile; warms the cache
        `resolve_constant` reads from."""
        missing = [n for n in names if n not in self._constants]
        if missing:
            self._constants.update(probe_constants(self.engine, missing))
        return {n: self._constants[n] for n in names}

    def flag(self, flag: str | int) -> bool:
        flag_id = self.resolve_constant(flag) if isinstance(flag, str) else flag
        byte = self.u8(self.sb1 + self.offsets["off_sb1_flags"] + flag_id // 8)
        return bool(byte >> (flag_id % 8) & 1)

    def var(self, var: str | int) -> int:
        """Read a VAR_* value, following the engine's own VarGet/GetVarPointer
        (event_data.c): ids in [VARS_START, SPECIAL_VARS_START) index
        SaveBlock1's `vars` array directly; ids below VARS_START aren't
        stored (VarGet just echoes the id back) and ids at/above
        SPECIAL_VARS_START are the dynamic "special vars" table (pointers
        resolved per-id, not a flat array) — neither is representable by a
        flat offset read, so both are a scenario error here."""
        var_id = self.resolve_constant(var) if isinstance(var, str) else var
        vars_start = self.offsets["vars_start"]
        special_vars_start = self.resolve_constant("SPECIAL_VARS_START")
        if not (vars_start <= var_id < special_vars_start):
            raise ScenarioError(
                f"var id {var_id} is outside the stored-vars range "
                f"[{vars_start}, {special_vars_start}) — special/temp vars "
                "aren't readable via a flat offset"
            )
        addr = self.sb1 + self.offsets["off_sb1_vars"] + (var_id - vars_start) * 2
        return self.core.memory.u16[addr]

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

    def _walk_step(self, direction: str, x: int, y: int) -> tuple[bool, int]:
        """Attempt one grid step in `direction` from `(x, y)`.

        Step-granular: release the key the moment the coord ticks over, so
        a burst can never overshoot onto a warp/trigger tile beyond a
        target. Returns `(moved, frames_spent)`. 40-frame cap: a
        turn-in-place (~8f) plus one walk step (~16f) fits with margin; a
        blocked direction burns the cap without moving.
        """
        for frames in range(1, 41):
            self.run(1, [direction])
            if self.player_pos() != (x, y):
                return True, frames
        return False, 40

    def walk_to(self, tx: int, ty: int, frame_budget: int = 3000,
                max_sidesteps: int = 8) -> None:
        """Greedy two-axis walk with blocked-axis fallback and step-aside
        retry.

        When both preferred directions are blocked -- typically a randomly-
        walking NPC parked on the direct line, ROM_TEST_DEV.md C6 -- this
        does not fail immediately. It steps one tile perpendicular to the
        blocked axis and re-paths toward the target from there, alternating
        which perpendicular direction it prefers and avoiding a just-tried
        sidestep tile where an alternative exists, so it can't oscillate
        between the same two tiles forever. Attempts are bounded by
        `max_sidesteps`; a genuinely impassable target still fails loud,
        with a message that reads distinctly from a plain frame-budget
        timeout. Every sidestep is a single step-granular move via
        `_walk_step` -- it can never overshoot a target the way a multi-
        frame burst could -- and map identity is re-checked after each one,
        since a sidestep landing on a warp/trigger tile would silently
        relocate the scenario.
        """
        spent = 0
        start_map = self.map_location()
        sidestep_count = 0
        visited_sidesteps: set[tuple[int, int]] = set()
        perp_toggle = 0

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
            axes = [a for a in axes if a]

            moved = False
            for d in axes:
                ok, frames = self._walk_step(d, x, y)
                spent += frames
                if ok:
                    moved = True
                    break
            if moved:
                continue

            # Both greedy directions are blocked. Step off the direct line
            # and re-path, instead of failing on what's likely a transient
            # NPC body-block.
            if sidestep_count >= max_sidesteps:
                shot = self.screenshot("walk_stuck")
                raise ScenarioError(
                    f"stuck after {sidestep_count} step-aside attempts at "
                    f"{x},{y} heading for {tx},{ty} ({shot})")

            primary = axes[0]
            perp_a, perp_b = _PERPENDICULAR[primary]
            order = [perp_a, perp_b] if perp_toggle == 0 else [perp_b, perp_a]
            perp_toggle ^= 1
            # Prefer whichever perpendicular tile wasn't just tried, so a
            # persistently-blocked pair of directions can't bounce the
            # player between the same two tiles forever.
            order.sort(key=lambda d: (x + _DIR_DELTA[d][0],
                                       y + _DIR_DELTA[d][1]) in visited_sidesteps)

            stepped = False
            for d in order:
                ok, frames = self._walk_step(d, x, y)
                spent += frames
                if ok:
                    stepped = True
                    break
            sidestep_count += 1

            if not stepped:
                # Blocked on every side, not just body-blocked — a real
                # failure, not a flake.
                shot = self.screenshot("walk_stuck")
                raise ScenarioError(
                    f"stuck after {sidestep_count} step-aside attempts at "
                    f"{x},{y} heading for {tx},{ty} ({shot})")

            visited_sidesteps.add(self.player_pos())
            here_map = self.map_location()
            if here_map != start_map:
                shot = self.screenshot("walk_map_changed")
                raise ScenarioError(
                    f"walk_to({tx},{ty}) sidestep changed map from "
                    f"{start_map} to {here_map} — aborting ({shot})")

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
