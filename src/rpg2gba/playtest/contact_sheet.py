"""Screenshot contact sheets (ROM_TEST_DEV.md §2, build-order item 6).

A green chapter suite proves the *state* is right — flags, vars, positions,
party contents. It cannot see the by-eye defect class: a sprite drawn behind
a wall, a wrong palette, a layout that doesn't read. Those stay §9 manual
work, but they do not have to stay *interactive*: the runner drives to a
waypoint at every beat boundary, and this module tiles those frames into a
few PNG pages that can be reviewed on a phone in a minute instead of played
for thirty (ROM_TEST_DEV §2's "screenshots replace the watching").

Both run outcomes produce one. A green run's sheet goes next to the review
ROM; a failing run's sheet goes into the repro bundle, ending on the frame
that failed — which is usually the fastest way to see *why*.

Nothing here touches the emulator: it works from `Waypoint` records
(a beat name, a caption, and a PNG on disk), so the sheet builder is
testable without mGBA and re-runnable over an old bundle.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# One GBA frame is 240x160; 2x is legible on a phone without making the
# sheet unwieldy (3 columns -> ~1500px wide).
SCALE = 2
COLUMNS = 3
PER_PAGE = 12

_CAPTION_H = 34
_PAD = 10
_BG = (24, 24, 28)
_FG = (236, 236, 240)
_DIM = (150, 150, 158)
_FAIL = (232, 96, 96)

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


@dataclass(frozen=True)
class Waypoint:
    """One frame worth looking at, plus what the player had just done.

    `beat` names the chapter-doc row (B3, N1, ...) so a suspicious frame
    points straight at a doc beat, the same addressing the failure bundle
    uses. `failed` marks the frame captured at a beat failure — it gets a
    red caption so the eye lands on it first.
    """

    beat: str
    name: str
    note: str
    frame: int
    path: Path
    failed: bool = False

    @property
    def caption(self) -> str:
        return f"{self.beat} · {self.name}" if self.name != self.beat else self.beat


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "...", font=font) > max_w:
        text = text[:-1]
    return text + "..."


def _render_page(waypoints: list[Waypoint], out: Path, *, title: str,
                  columns: int, scale: int) -> Path:
    cell_w, cell_h = 240 * scale, 160 * scale
    rows = (len(waypoints) + columns - 1) // columns
    title_h = 40

    sheet_w = _PAD + columns * (cell_w + _PAD)
    sheet_h = title_h + _PAD + rows * (cell_h + _CAPTION_H + _PAD)
    sheet = Image.new("RGB", (sheet_w, sheet_h), _BG)
    draw = ImageDraw.Draw(sheet)

    title_font = _font(22)
    cap_font = _font(17)
    note_font = _font(14)

    draw.text((_PAD, _PAD), title, font=title_font, fill=_FG)

    for i, wp in enumerate(waypoints):
        col, row = i % columns, i // columns
        x = _PAD + col * (cell_w + _PAD)
        y = title_h + _PAD + row * (cell_h + _CAPTION_H + _PAD)

        try:
            frame = Image.open(wp.path).convert("RGB")
        except OSError as exc:  # a truncated/absent PNG must not sink the sheet
            logger.warning("contact sheet: could not read %s (%s)", wp.path, exc)
            frame = Image.new("RGB", (240, 160), (60, 20, 20))
        sheet.paste(frame.resize((cell_w, cell_h), Image.NEAREST), (x, y))

        cap_y = y + cell_h + 4
        cap_color = _FAIL if wp.failed else _FG
        draw.text((x, cap_y), _truncate(draw, wp.caption, cap_font, cell_w),
                   font=cap_font, fill=cap_color)
        if wp.note:
            draw.text((x, cap_y + 17), _truncate(draw, wp.note, note_font, cell_w),
                       font=note_font, fill=_DIM)

    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def build_contact_sheet(waypoints: list[Waypoint], out_dir: Path, *,
                         chapter: str, verdict: str,
                         columns: int = COLUMNS, scale: int = SCALE,
                         per_page: int = PER_PAGE) -> list[Path]:
    """Tile `waypoints` into paginated PNG sheets under `out_dir`.

    Returns the pages written, in order (empty if there were no waypoints —
    a run that failed in its first beat legitimately has nothing to show).
    Pages are named `<chapter>-sheet.png`, `<chapter>-sheet-2.png`, ...
    """
    if not waypoints:
        return []

    pages: list[Path] = []
    total_pages = (len(waypoints) + per_page - 1) // per_page
    for page_no in range(total_pages):
        chunk = waypoints[page_no * per_page : (page_no + 1) * per_page]
        suffix = "" if page_no == 0 else f"-{page_no + 1}"
        out = out_dir / f"{chapter}-sheet{suffix}.png"
        title = f"{chapter} — {verdict.upper()}"
        if total_pages > 1:
            title += f"  (page {page_no + 1}/{total_pages})"
        pages.append(_render_page(chunk, out, title=title, columns=columns, scale=scale))

    logger.info("[%s] contact sheet: %s", chapter,
                 ", ".join(str(p) for p in pages))
    return pages
