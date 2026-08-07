"""Headless mGBA core wrapper with poll-state input primitives.

Design rule (from the feasibility study): never frame-count a scripted input
tape — poll game state (coords, field-controls lock) and act on it, with
frame-budget timeouts that fail loud with a screenshot. That keeps scenarios
robust against text-length, timing, and converter changes.
"""
import logging
import struct
from collections import deque
from collections.abc import Callable, Sequence
from pathlib import Path

from .contact_sheet import Waypoint
from .errors import ScenarioError
from .offsets import probe_constants, probe_offsets
from .symbols import (
    SymbolMap,
    static_addr_via_accessor,
    static_fn_via_literal_pool,
    static_ptr_via_accessor,
)

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

# A waypoint frame captured during a palette fade or a battle transition is
# solid black — useless as the by-eye review surface the contact sheet exists
# to be (5 of 19 frames in the 2026-07-27 moki sheet were blank). A frame is
# "unreviewable" when it is essentially one flat colour, or so dark nothing in
# it can be judged; `waypoint` waits out that state before capturing.
_BLANK_COLOR_CAP = 8  # a fade/wipe frame holds a handful of colours at most
_BLANK_DOMINANCE = 0.98  # ...and one of them covers nearly every pixel
_DARK_LUMA = 24  # mean luma (0-255) below which a frame shows nothing usable
_SETTLE_BUDGET = 240  # 4s: longer than any fade, short enough to give up on
_SETTLE_STEP = 4

# How many times walk_to re-plans its route after a leg gets locally stuck
# (a randomly-walking NPC parked in a doorway is the normal cause, and it
# moves on its own within a second or two).
_MAX_REPLANS = 4
_REPLAN_WAIT = 60


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
        # `sFieldMessageBoxMode` (field_message_box.c): FIELD_MESSAGE_BOX_HIDDEN
        # (0) while no field message box is up, NORMAL/AUTO_SCROLL while one is.
        # Recovered through the same global-accessor trick as the lock above —
        # `IsFieldMessageBoxHidden` and `GetFieldMessageBoxMode` both compile to
        # the ldr-literal + ldrb shape and resolve to the same static.
        self._msgbox_addr = static_addr_via_accessor(
            engine / "pokeemerald.elf",
            self.symbols["IsFieldMessageBoxHidden"],
        )
        self._printer_list = static_ptr_via_accessor(
            engine / "pokeemerald.elf",
            self.symbols["IsTextPrinterActiveOnWindow"],
        )
        # `Task_HandleYesNoInput` (script_menu.c): the task `ScriptMenu_YesNo`
        # creates alongside the menu and which lives exactly as long as the
        # prompt is on screen. Static, so it is not in the link map — but
        # `ScriptMenu_YesNo` must load its address as a literal to pass it to
        # `FuncIsActiveTask`/`CreateTask`, so the pool carries it.
        self._yesno_task_fn = static_fn_via_literal_pool(
            engine / "pokeemerald.elf",
            self.symbols["ScriptMenu_YesNo"],
        )
        self._text_frame: "object | None" = None
        self._text_was_drawing = False
        self._frame_pinned = False
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

    def run(self, frames: int, keys: list[str] | None = None,
            on_frame: Callable[[], None] | None = None) -> None:
        """Advance `frames` frames with `keys` held for all of them.

        `on_frame` is called after each individual frame, for observations that
        must not miss a short-lived state (see `tap`). It must not advance the
        core itself. The keys stay held across the whole call either way —
        re-pressing per frame would turn one press into `frames` presses, and
        the engine's `JOY_NEW` checks would see every one of them.
        """
        mask = 0
        for k in keys or []:
            mask |= 1 << KEYS[k]
        self.core._core.setKeys(self.core._core, mask)
        for _ in range(frames):
            self.core.run_frame()
            self.frame += 1
            if on_frame is not None:
                on_frame()
        self.core._core.setKeys(self.core._core, 0)

    def u8(self, addr: int) -> int:
        return self.core.memory.u8[addr]

    def u16(self, addr: int) -> int:
        return self.core.memory.u16[addr]

    def u32(self, addr: int) -> int:
        return self.core.memory.u32[addr]

    def write_u16(self, addr: int, value: int) -> None:
        # Not `memory.u16[addr] = value`: that path in the mgba bindings
        # (site-packages/mgba/memory.py:60) calls `rawWrite16` without the
        # `segment` argument the C signature requires and dies with a cffi
        # arity TypeError. `raw_write` (:68) passes segment=-1 properly.
        self.core.memory.u16.raw_write(addr, value)

    def read_bytes(self, addr: int, size: int) -> bytes:
        return bytes(self.core.memory.u8[addr : addr + size])

    def snapshot_state(self) -> bytes:
        """Serialize the whole core (CPU, RAM, PPU, ...) for a later
        `restore_state`.

        Exists so a caller can run the engine's own routines (e.g. an
        in-game save, see `stamp.dump_save_blocks`) mid-scenario and then
        rewind, without the caller's live emulator ending up perturbed by
        it. Cost is a full-state copy (~400KB), not a ROM reboot.
        """
        raw = self.core.save_raw_state()
        if raw is None:
            raise ScenarioError("core.save_raw_state() returned no state")
        return bytes(raw)

    def restore_state(self, state: bytes) -> None:
        """Rewind the core to a `snapshot_state()` capture."""
        if not self.core.load_raw_state(state):
            raise ScenarioError(
                "core.load_raw_state() failed to restore a snapshot "
                f"({len(state)} bytes)")

    def screenshot(self, name: str) -> Path | None:
        if self.screenshot_dir is None:
            return None
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{name}_f{self.frame}.png"
        self.screen.to_pil().convert("RGB").save(path)
        return path

    def _frame_unreviewable(self) -> bool:
        """True while the screen shows nothing worth a human's eye — a fade to
        or from black, a transition wipe, a battle intro's blank stretch."""
        img = self.screen.to_pil().convert("RGB")
        pixels = img.size[0] * img.size[1]
        counts = img.getcolors(maxcolors=_BLANK_COLOR_CAP)  # None if more
        if counts is not None and max(n for n, _ in counts) >= pixels * _BLANK_DOMINANCE:
            return True
        luma = img.convert("L")
        return sum(i * n for i, n in enumerate(luma.histogram())) / pixels < _DARK_LUMA

    def _settle_frame(self, budget: int = _SETTLE_BUDGET) -> int:
        """Advance until there is something to look at; returns frames spent.

        Safe to do at a waypoint: scenarios poll state rather than count
        frames (this module's design rule), and the only thing being waited
        out is an animation the game is already running. Bounded — a
        genuinely dark scene must cost a fixed 4s, not a hang.
        """
        spent = 0
        while spent < budget and self._frame_unreviewable():
            self.run(_SETTLE_STEP)
            spent += _SETTLE_STEP
        return spent

    def note_text_frame(self) -> None:
        """Photograph the frame a message finishes drawing on.

        Called once per frame from `tap`, which is what every loop that mashes
        a script forward is built out of. Each capture overwrites the last, so
        what survives to the beat boundary is the *final* message of the scene
        — the payoff line ("You got the Running Shoes!"), not the greeting that
        opened it. See `waypoint`.

        The capture point is the **falling edge** of `text_showing`, which is
        the frame the last glyph lands on (see that method — the flag tracks
        drawing, not visibility). Two weaker rules were tried first and both
        are wrong:

        - *Any frame with `text_showing` true* photographs a half-typed
          message; the tile reads "See you later, R".
        - *`text_showing` and `text_ready`* almost never coincides, because a
          message that fits one page clears `text_showing` on the very frame
          its printer finishes. Every short line vanished from the sheet.

        Edge detection needs per-frame sampling — a short message finishes and
        is dismissed inside one 12-frame tap — hence `run`'s `on_frame` hook.
        A gap in sampling costs a missed capture, never a wrong one.
        """
        finished = self._text_was_drawing and not self.text_showing()
        self._text_was_drawing = self.text_showing()
        if self.screenshot_dir is None or not finished or self._frame_pinned:
            return
        # A box drawn over a fade is no more use for review than a plain black
        # tile, and `text_ready` asserts the page really is drawn.
        if not self.text_ready() or self._frame_unreviewable():
            return
        self._text_frame = self.screen.to_pil().convert("RGB")

    def mark_frame(self, force: bool = False) -> bool:
        """Pin *this* frame as the beat's contact-sheet tile.

        The automatic rules (`note_text_frame`'s last-completed-message, else
        the live frame at the beat boundary) fit beats that play dialogue and
        end when it does. They cannot serve a beat whose interesting moment is
        something else — a menu that is up, a cutscene's peak, an NPC standing
        somewhere before it walks off — or a beat that ends without advancing
        the emulator at all, whose live frame is then just the previous beat's
        tile over again.

        Call this at the instant worth reviewing and the beat's single tile
        becomes that frame. Pinning is **sticky**: later dialogue in the same
        beat will not silently overwrite an explicit choice, which would
        otherwise make the mark's effect depend on whether more text happened
        to follow. `waypoint` clears the pin, so it is per-beat.

        Returns whether the frame was taken. A blank/mid-fade frame is refused
        (`force=True` overrides), because pinning one would produce exactly the
        black tile `_settle_frame` exists to avoid — and silently, since a
        pinned frame skips settling.
        """
        if self.screenshot_dir is None:
            return False
        if not force and self._frame_unreviewable():
            return False
        self._text_frame = self.screen.to_pil().convert("RGB")
        self._frame_pinned = True
        return True

    def waypoint(self, beat: str, name: str = "", note: str = "",
                 failed: bool = False) -> Waypoint | None:
        """Capture a frame for the run's contact sheet (ROM_TEST_DEV §2).

        Distinct from `screenshot`, which is failure evidence: waypoints are
        the *by-eye review surface* — the frames a human scans for the
        cosmetic defect class state assertions can't see. The runner takes
        one at every beat boundary automatically; a beat calls this itself
        when something mid-beat is worth a look (a cutscene's peak, a room
        the player only passes through).

        **Which frame.** A beat that plays a scene only returns once the scene
        has been mashed to its end and the field controls are free again, so
        the live frame at the beat boundary is always the world *after* the
        event: Auntie's shoes line already dismissed, Theo's cameo already
        walked off. That is the wrong moment to review. So if any dialogue was
        seen while the beat ran (`note_text_frame`), that frame is used instead
        of the live one, and the emulator is not advanced at all. A beat with
        no dialogue (a warp, a re-cross that must *not* fire) has nothing
        stored and still captures live. A beat that wants a specific moment
        neither rule picks says so with `mark_frame`, which wins over both.

        Beat boundaries land on warps and battle transitions, so a live frame
        at that instant is often mid-fade and solid black. A live non-failure
        capture therefore waits for the screen to settle first
        (`_settle_frame`); if it never does, the frame is still captured and
        the note says so, so a blank tile on the sheet always reads as "this
        is what the game showed" rather than "the harness caught it at a bad
        moment". A *failure* waypoint never advances the emulator and never
        substitutes a stored frame — that frame is evidence.
        """
        if self.screenshot_dir is None:
            self._text_frame = None
            self._frame_pinned = False
            return None
        frame = None if failed else self._text_frame
        self._text_frame = None
        self._frame_pinned = False
        if frame is None and not failed:
            self._settle_frame()
            if self._frame_unreviewable():
                blank = f"screen still blank after {_SETTLE_BUDGET}f"
                note = f"{note} — {blank}" if note else blank
        wp_dir = self.screenshot_dir / "waypoints"
        wp_dir.mkdir(parents=True, exist_ok=True)
        slug = f"{len(self.waypoints):02d}_{beat}"
        if name:
            slug += f"_{name}"
        path = wp_dir / f"{slug}.png"
        (frame if frame is not None else self.screen.to_pil().convert("RGB")).save(path)
        wp = Waypoint(beat=beat, name=name or beat, note=note,
                      frame=self.frame, path=path, failed=failed,
                      at_text=frame is not None)
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

    def yesno_prompt_up(self) -> bool:
        """True while a `yesnobox` prompt is on screen awaiting an answer.

        Scans `gTasks` exactly as `FuncIsActiveTask` (task.c) does, for the
        handler `ScriptMenu_YesNo` installs. The task is created with the menu
        and destroyed when a choice is committed, so its lifetime *is* the
        prompt's — no frame counting, and no dependence on text speed.

        This is deliberately not `gSpecialVar_Result == 0xFF`: multichoice
        sets that sentinel too, so it cannot tell a yes/no prompt from one of
        the quiz's `dynmultichoice` questions.

        Answering is still done by button (`advance_dialog`'s `key`) — which
        option is *highlighted* remains unobservable, and A always commits the
        default YES.
        """
        o = self.offsets
        base = self.symbols["gTasks"]
        stride = o["sizeof_task"]
        for i in range(o["val_num_tasks"]):
            task = base + i * stride
            if not self.u8(task + o["off_task_is_active"]):
                continue
            if self.u32(task + o["off_task_func"]) == self._yesno_task_fn:
                return True
        return False

    def text_showing(self) -> bool:
        """True while a field message box is *drawing*.

        `sFieldMessageBoxMode`, which is narrower than it sounds and narrower
        than `field_locked` (that one is also true through fades, warps,
        scripted walk routes and battle transitions). It is set by
        `ShowFieldMessage` and cleared by `Task_DrawFieldMessage` the moment
        `RunTextPrintersAndIsPrinter0Active()` goes false — that is, when the
        last glyph lands, *not* when the box leaves the screen. The box stays
        up after this goes false, holding the finished text while the script
        waits for the player's button press.

        So this is "text is still appearing", and its falling edge is the
        frame at which a complete message is on screen. `note_text_frame`
        photographs that edge.
        """
        return self.u8(self._msgbox_addr) != 0

    def text_ready(self, window_id: int = 0) -> bool:
        """True when no glyphs are currently being drawn into `window_id`.

        The question a waypoint asks is "is the text on screen finished?", and
        there are two ways for that to be true, which is why this is phrased
        negatively:

        - A printer exists but is parked — RENDER_STATE_WAIT / CLEAR /
          SCROLL_START all mean a complete page sitting on the down-arrow
          waiting for the player. Only RENDER_STATE_HANDLE_CHAR is the printer
          still consuming characters.
        - No printer exists at all. A *final* page hits RENDER_FINISH as its
          last glyph lands, which frees the node off the list — while the box
          stays up and the script waits for its button press. So "message box
          showing, no printer" is the fully-drawn end of a one-page message,
          the single most reviewable frame there is. Requiring a parked printer
          instead would silently drop every short message (it dropped B2's
          refusal line).

        Walks `sFirstTextPrinter` exactly as `IsTextPrinterActiveOnWindow`
        does, but reads `state` rather than `active`: `active` stays TRUE for a
        printer's whole life and clears only at RENDER_FINISH, on the way to
        being freed, so it says nothing about drawing progress.

        The 16-node cap guards against following a cycle out of a torn pointer;
        the real list is a handful of nodes.
        """
        o = self.offsets
        node = self.u32(self._printer_list)
        for _ in range(16):
            if node == 0:
                return True
            if (self.u8(node + o["off_printer_type"]) == o["val_window_text_printer"]
                    and self.u8(node + o["off_printer_window_id"]) == window_id):
                return (self.u8(node + o["off_printer_state"])
                        != o["val_render_state_handle_char"])
            node = self.u32(node + o["off_printer_next"])
        return True

    # -- primitives ---------------------------------------------------------

    def tap(self, key: str, hold: int = 6, release: int = 6) -> None:
        """Press `key` for `hold` frames, then wait `release`.

        Samples for a finished page of dialogue on *every* frame, not once per
        tap. The moment worth photographing is often shorter than a single tap:
        a short message finishes drawing and is dismissed inside the same
        12-frame press/release cycle, so per-tap sampling saw it as "still
        typing" and then as "gone" with nothing in between (that is exactly how
        B2's refusal line went missing). `note_text_frame` costs two memory
        reads when there is nothing to capture, so this is cheap.
        """
        self.run(hold, [key], on_frame=self.note_text_frame)
        self.run(release, on_frame=self.note_text_frame)

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

    # -- route planning -----------------------------------------------------

    def _grid_dims_for_current_map(self) -> tuple[int, int] | None:
        """The `(width, height)` `gBackupMapLayout` will carry once the
        *current* map's layout has finished loading, or None if the header
        isn't readable yet.

        `InitBackupMapLayout` (`engine/src/fieldmap.c:171-174`) sizes the grid
        as the layout's own dimensions plus the border margin
        (`MAP_OFFSET_W` / `MAP_OFFSET_H`), so the header's layout is the
        authority on what a fully-loaded grid must look like.
        """
        o = self.offsets
        layout = self.u32(self.symbols["gMapHeader"] + o["off_mapheader_maplayout"])
        if layout == 0:
            return None
        width = self.u32(layout + o["off_maplayout_width"])
        height = self.u32(layout + o["off_maplayout_height"])
        if not (0 < width < 1024 and 0 < height < 1024):
            return None
        off = o["val_map_offset"]
        return width + (off * 2 + 1), height + off * 2

    def map_grid_loaded(self) -> bool:
        """Whether `gBackupMapLayout` describes the map the game reports.

        A warp writes `SaveBlock1.location` in `ApplyCurrentWarp`
        (`engine/src/overworld.c:620`) and only rebuilds the grid much later,
        in the `InitMap` call inside `LoadMapFromWarp`
        (`engine/src/overworld.c:982`). In between, the game reports the
        *destination* map while the grid still holds the *departure* map — so
        "the map changed" and "the grid is usable" are different events, and
        anything planning over the grid must wait for this one.

        Waiting on the field lock instead does not work: `CB2_LoadMap` calls
        `UnlockPlayerFieldControls` on the way in (`overworld.c:1953`), so
        controls read *unlocked* for the whole window.
        """
        expected = self._grid_dims_for_current_map()
        if expected is None:
            return False
        base = self.symbols["gBackupMapLayout"]
        o = self.offsets
        return (self.u32(base + o["off_backup_width"]),
                self.u32(base + o["off_backup_height"])) == expected

    def wait_for_map_grid(self, frame_budget: int = 300) -> int:
        """Run until `map_grid_loaded()`; returns the frames spent.

        Fails loud rather than letting a caller plan over another map's grid.
        That mistake is silent and destructive: a mid-warp arrival tile is
        usually itself a warp tile, so a route planned in the wrong frame of
        reference walks straight back through it onto the map just left,
        and every later assertion is then made about the wrong map.
        """
        spent = 0
        while spent < frame_budget:
            if self.map_grid_loaded():
                return spent
            self.run(2)
            spent += 2
        base = self.symbols["gBackupMapLayout"]
        o = self.offsets
        raise ScenarioError(
            f"map grid never finished loading within {frame_budget} frames "
            f"(gBackupMapLayout {self.u32(base + o['off_backup_width'])}x"
            f"{self.u32(base + o['off_backup_height'])}, expected "
            f"{self._grid_dims_for_current_map()}, "
            f"map_location={self.map_location()})")

    def _map_grid(self) -> tuple[int, int, tuple[int, ...]]:
        """The engine's own map grid for the current map: `(width, height,
        blocks)`, blocks being the packed u16s `MapGridGetCollisionAt` reads.

        Read from `gBackupMapLayout` rather than the built `map.bin` so the
        planner sees what the *running game* sees — script-applied metatile
        changes included — and so it needs no knowledge of which layout file
        belongs to the current map. Grid coordinates carry `MAP_OFFSET`;
        `player_pos()` (SaveBlock1.pos) does not, hence `_grid_index`.

        Refuses a grid that belongs to a different map than the one the game
        reports being on — see `map_grid_loaded`.
        """
        base = self.symbols["gBackupMapLayout"]
        o = self.offsets
        width = self.u32(base + o["off_backup_width"])
        height = self.u32(base + o["off_backup_height"])
        ptr = self.u32(base + o["off_backup_map"])
        if not (0 < width < 1024 and 0 < height < 1024) or ptr == 0:
            raise ScenarioError(
                f"gBackupMapLayout looks unreadable (width={width} "
                f"height={height} map=0x{ptr:08x}) — is a map loaded?")
        expected = self._grid_dims_for_current_map()
        if expected is not None and (width, height) != expected:
            raise ScenarioError(
                f"gBackupMapLayout is {width}x{height} but map_location() "
                f"{self.map_location()} wants {expected[0]}x{expected[1]} — "
                "the map is still loading; call wait_for_map_grid() first")
        raw = self.read_bytes(ptr, width * height * 2)
        return width, height, struct.unpack(f"<{width * height}H", raw)

    def _warp_tiles(self) -> set[tuple[int, int]]:
        """Map-relative coordinates of the current map's warp events.

        A route must never *enter* one it wasn't aimed at: stepping on a warp
        relocates the scenario to another map, which is the one walk failure
        mode that corrupts every assertion after it rather than failing.
        """
        o = self.offsets
        events = self.u32(self.symbols["gMapHeader"] + o["off_mapheader_events"])
        if events == 0:
            return set()
        count = self.u8(events + o["off_mapevents_warpcount"])
        warps = self.u32(events + o["off_mapevents_warps"])
        if warps == 0:
            return set()
        stride = o["sizeof_warpevent"]
        return {
            (self.u16(warps + i * stride + o["off_warpevent_x"]),
             self.u16(warps + i * stride + o["off_warpevent_y"]))
            for i in range(count)
        }

    def _plan_route(self, start: tuple[int, int],
                    goal: tuple[int, int]) -> list[tuple[int, int]] | None:
        """Shortest walkable route between two map-relative tiles, or None.

        Breadth-first over collision-0 tiles, avoiding warp tiles other than
        the goal. Elevation is deliberately not modelled — mismatched-
        elevation edges (cliff rims) would be planned through; a leg that
        hits one gets locally stuck and re-planned, and ultimately fails
        loud, which is the same outcome as any other impassable route.

        A goal outside the grid's own bounds is not an unroutable target but
        a wrong grid, and raises — see `_route_waypoints`.
        """
        width, height, blocks = self._map_grid()
        off = self.offsets["val_map_offset"]
        map_w, map_h = width - (off * 2 + 1), height - off * 2
        if not (0 <= goal[0] < map_w and 0 <= goal[1] < map_h):
            raise ScenarioError(
                f"walk_to{goal} targets a tile outside the loaded map grid "
                f"({map_w}x{map_h}, map_location={self.map_location()}) — "
                "wrong map, or the grid belongs to another one")
        avoid = self._warp_tiles() - {goal}

        def walkable(x: int, y: int) -> bool:
            if not (0 <= x < map_w and 0 <= y < map_h) or (x, y) in avoid:
                return False
            return (blocks[(x + off) + width * (y + off)] >> 10) & 0x3 == 0

        seen: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            if cur == goal:
                path = []
                node: tuple[int, int] | None = cur
                while node is not None:
                    path.append(node)
                    node = seen[node]
                return path[::-1]
            cx, cy = cur
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                nxt = (cx + dx, cy + dy)
                if nxt not in seen and walkable(*nxt):
                    seen[nxt] = cur
                    queue.append(nxt)
        return None

    def _route_waypoints(self, tx: int, ty: int) -> list[tuple[int, int]]:
        """Turn a planned route into the corner tiles `_walk_greedy` can
        reach in a straight line, ending at the target.

        If the grid can't be planned over — no route found, or the tile data
        doesn't say what the engine really allows — this degrades to the bare
        target and lets the greedy walker try anyway, so an ordinary planner
        blind spot costs a slower failure rather than a wrong answer.

        The one shape that is *not* a blind spot is a target outside the
        grid's own bounds: that means the grid is not this map's, and walking
        greedily on it is exactly the destructive case `wait_for_map_grid`
        exists to prevent, so `_plan_route` raises instead.
        """
        start = self.player_pos()
        if start == (tx, ty):
            return [(tx, ty)]
        route = self._plan_route(start, (tx, ty))
        if route is None:
            logger.warning("walk_to(%d,%d): no planned route from %s — "
                           "falling back to greedy pathing", tx, ty, start)
            return [(tx, ty)]
        corners = [
            route[i] for i in range(1, len(route) - 1)
            if (route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1])
            != (route[i + 1][0] - route[i][0], route[i + 1][1] - route[i][1])
        ]
        return corners + [(tx, ty)]

    def walk_to(self, tx: int, ty: int, frame_budget: int = 3000,
                max_sidesteps: int = 8) -> None:
        """Walk to `(tx, ty)` on the current map, planning around walls.

        The route comes from the engine's own collision grid
        (`_route_waypoints`), and each leg between two corners is walked by
        the greedy stepper below, whose step-aside retry absorbs the
        transient obstacle the grid can't see: another actor standing in the
        way. A leg that stays stuck is not a failure yet — NPCs move — so the
        walk waits briefly and re-plans, up to `_MAX_REPLANS` times, before
        failing loud with the leg's own diagnosis.

        Waits for the destination map's grid to finish loading first: a beat
        that has just crossed a warp reaches here while `gBackupMapLayout`
        still holds the map it left (`map_grid_loaded`), and planning in that
        window silently walks back through the arrival warp.
        """
        spent = 0
        spent += self.wait_for_map_grid()
        start_map = self.map_location()
        reason = f"walk_to({tx},{ty}) made no progress"
        for _ in range(_MAX_REPLANS):
            stuck = False
            for wx, wy in self._route_waypoints(tx, ty):
                arrived, used, why = self._walk_greedy(
                    wx, wy, frame_budget - spent, max_sidesteps, start_map)
                spent += used
                if not arrived:
                    stuck, reason = True, why
                    break
            if not stuck:
                return
            if spent + _REPLAN_WAIT >= frame_budget:
                break
            self.run(_REPLAN_WAIT)
            spent += _REPLAN_WAIT
        shot = self.screenshot("walk_stuck")
        raise ScenarioError(f"{reason} ({shot})")

    def _walk_greedy(self, tx: int, ty: int, frame_budget: int,
                     max_sidesteps: int, start_map: tuple[int, int],
                     ) -> tuple[bool, int, str]:
        """Greedy two-axis walk with blocked-axis fallback and step-aside
        retry.

        When both preferred directions are blocked -- typically a randomly-
        walking NPC parked on the direct line, ROM_TEST_DEV.md C6 -- this
        does not fail immediately. It steps one tile perpendicular to the
        blocked axis and re-paths toward the target from there, alternating
        which perpendicular direction it prefers and avoiding a just-tried
        sidestep tile where an alternative exists, so it can't oscillate
        between the same two tiles forever. Attempts are bounded by
        `max_sidesteps`.

        Returns `(arrived, frames_spent, reason)`. A stuck leg is *reported*,
        not raised — `walk_to` owns the decision to re-plan or give up, and
        raises with this `reason` so the two stuck shapes (impassable target
        vs. plain budget timeout) still read distinctly. The one case this
        raises itself is a changed map identity: the scenario is already on
        the wrong map, and re-planning would compound it.
        """
        spent = 0
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
                return True, spent + 16, ""
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
                self._require_same_map(start_map, tx, ty, "step")
                continue

            # Both greedy directions are blocked. Step off the direct line
            # and re-path, instead of failing on what's likely a transient
            # NPC body-block.
            if sidestep_count >= max_sidesteps:
                return False, spent, (
                    f"stuck after {sidestep_count} step-aside attempts at "
                    f"{x},{y} heading for {tx},{ty}")

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
                # Blocked on every side, not just body-blocked.
                return False, spent, (
                    f"stuck after {sidestep_count} step-aside attempts at "
                    f"{x},{y} heading for {tx},{ty}")

            visited_sidesteps.add(self.player_pos())
            self._require_same_map(start_map, tx, ty, "sidestep")

        shot = self.screenshot("walk_budget")
        raise ScenarioError(f"walk_to({tx},{ty}) frame budget exhausted ({shot})")

    def _require_same_map(self, start_map: tuple[int, int], tx: int, ty: int,
                          how: str) -> None:
        """Abort the walk if a step relocated the player to another map.

        Stepping onto a warp is the one walk mishap that doesn't fail on its
        own — the scenario would just carry on asserting against the wrong
        map — so it's checked after every move, not only after sidesteps.
        """
        here_map = self.map_location()
        if here_map != start_map:
            shot = self.screenshot("walk_map_changed")
            raise ScenarioError(
                f"walk_to({tx},{ty}) {how} changed map from "
                f"{start_map} to {here_map} — aborting ({shot})")

    def interact(self) -> None:
        """Press A; fail if no script picks up the field controls."""
        self.tap("A")
        self.run(30)
        if not self.field_locked():
            shot = self.screenshot("interact_noop")
            raise ScenarioError(f"interaction did not start a script ({shot})")

    def advance_dialog(self, key: str = "A", max_taps: int = 1500,
                       stop: Callable[[], bool] | None = None) -> int:
        """Mash `key` until the script releases the field controls.

        The single dialogue-advancing loop in the harness — every scenario and
        chapter beat goes through here, which is what makes the contact
        sheet's text-frame capture (`note_text_frame`) universal instead of
        something each beat has to remember to do.

        `key` is a parameter because a couple of beats must make a specific
        yes/no choice partway through an otherwise-uninterrupted locked
        script, and the harness has no probe for "a yesnobox is highlighted on
        option N". Two engine facts make button choice a reliable substitute,
        so this stays poll-driven rather than frame-counted:

        - Ordinary dialogue boxes advance on A or B identically throughout
          pokeemerald (the `JOY_NEW(A_BUTTON | B_BUTTON)` text-advance
          pattern), so holding one button for a whole stretch of plain
          msgboxes is safe.
        - `yesnobox` (asm/macros/event.inc): "Pressing B is equivalent to
          answering NO", and these prompts open via `ScriptMenu_YesNo` ->
          `DisplayYesNoMenuDefaultYes` (src/script_menu.c), so A commits
          whatever is highlighted, which is always YES.

        So "hold A through this stretch" deterministically answers YES at
        whichever yesnobox appears in it, and "hold B" answers NO, regardless
        of how many plain messages precede it.

        `stop` is an extra exit condition checked alongside the lock, for
        scripts that end in something other than a release — a battle gives no
        release to stop on, and mashing A into one resolves it by accident.
        """
        taps = 0
        while self.field_locked() and not (stop is not None and stop()):
            if taps >= max_taps:
                shot = self.screenshot("dialog_stuck")
                raise ScenarioError(
                    f"dialogue never released field controls ({shot})")
            self.tap(key)  # samples text frames on every frame it runs
            taps += 1
        self.note_text_frame()
        return taps
