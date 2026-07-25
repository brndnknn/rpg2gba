"""Static text-corpus validator (ROM_TEST_DEV.md §3 "text" / design ref C3).

Scans the transpiler's emitted ``.pory`` corpus at conversion time — no
emulator, exhaustive over every emitted dialogue string, runs in seconds —
for the four defects a live playtest would otherwise have to stumble across
by chance:

1. unconverted Essentials/RGSS control-code markup (``\\c[n]``, ``\\v[n]``,
   ``\\wt[n]``, ...) that slipped past the transpiler's own translation
2. Essentials' DrawTextEx rich-text tags (``<br>``, ``<c=X>``, ``<fs=X>``, ...)
   — a different markup family than (1), see ``rules.py``
3. message-box line-width overflow, measured against the real engine's
   ``FONT_NORMAL`` glyph-width table and message-box pixel width
4. characters with no glyph in the engine's ``charmap.txt``

Quickstart::

    from pathlib import Path
    from rpg2gba.text_validator import scan_output_dir

    issues = scan_output_dir(Path("output/uranium-build"), Path("engine"))
    for issue in issues:
        print(issue)

Or from the command line::

    python -m rpg2gba.text_validator scan --output output/uranium-build --engine engine
"""
from __future__ import annotations

import logging
from pathlib import Path

from .engine_metrics import Charmap, load_charmap
from .extraction import (
    ExtractedString,
    SourceLocation,
    extract_corpus,
    extract_strings,
    iter_corpus_files,
)
from .rules import TextIssue, load_allowed_chars, validate_text

logger = logging.getLogger(__name__)

__all__ = [
    "Charmap",
    "ExtractedString",
    "SourceLocation",
    "TextIssue",
    "TextGate",
    "TextGateViolation",
    "extract_corpus",
    "iter_corpus_files",
    "load_charmap",
    "scan_output_dir",
    "validate_text",
]


def scan_output_dir(output_dir: Path, engine_dir: Path) -> list[TextIssue]:
    """End-to-end convenience entry point: extract + validate one output slice.

    ``output_dir`` is a pipeline output slice (e.g. ``output/uranium-build``);
    ``engine_dir`` is the vendored pokeemerald-expansion checkout (``engine/``,
    or ``$RPG2GBA_POKEEMERALD``) — the source of the charmap and (by
    citation, embedded in ``engine_metrics.py``) the font-width table.
    """
    charmap_path = engine_dir / "charmap.txt"
    charmap = load_charmap(charmap_path)
    allowed_chars = load_allowed_chars(charmap_path)
    strings = extract_corpus(output_dir)
    return validate_text(strings, charmap=charmap, allowed_chars=allowed_chars)


class TextGateViolation(RuntimeError):
    """An emitted string carries a defect that would reach the ROM.

    Deliberately fatal (CLAUDE.md §4.5): unconverted markup and unrenderable
    glyphs are cheap to fix at conversion time and expensive to find in a
    boot walk, which is the whole reason this validator exists.
    """


class TextGate:
    """Staging-time fail-loud gate over one `.pory` text at a time.

    `scan_output_dir` scans a whole output slice after the fact; this is the
    same four rules applied to each script *as it is staged into the engine*,
    which is where the pipeline's other gate (the fork-index symbol check in
    `scripts/assemble_pathfinder.py`) already lives. Two reasons for the
    per-text shape rather than a corpus sweep at the same point:

    - **Scope.** A slice build stages 8 maps; a corpus scan would fail the
      build on defects in the other 191 maps that aren't being compiled.
    - **Ordering.** The staged text is post-`normalize_pory`, i.e. exactly
      the bytes that become the ROM — a pre-staging scan can miss (or
      falsely flag) whatever that pass rewrites.

    Construct once per assemble run (the charmap load is the expensive part),
    then call `check(text, label)` per script.
    """

    def __init__(self, engine_dir: Path) -> None:
        charmap_path = engine_dir / "charmap.txt"
        self.charmap = load_charmap(charmap_path)
        self.allowed_chars = load_allowed_chars(charmap_path)

    def issues(self, text: str, label: str) -> list[TextIssue]:
        """Findings for one `.pory` text; `label` names it in messages."""
        strings = extract_strings(text, Path(label))
        return validate_text(strings, charmap=self.charmap,
                             allowed_chars=self.allowed_chars)

    def check(self, text: str, label: str) -> None:
        """Raise `TextGateViolation` on any error-severity finding.

        Warnings are logged, not raised — the severity split is the rules'
        call, not this gate's.
        """
        errors: list[TextIssue] = []
        for issue in self.issues(text, label):
            if issue.severity == "error":
                errors.append(issue)
            else:
                logger.warning("%s", issue)
        if errors:
            lines = "\n".join(f"  {issue}" for issue in errors)
            raise TextGateViolation(
                f"text gate: {len(errors)} text defect(s) in {label} — this is "
                f"a converter bug; nothing staged:\n{lines}")


class TextGateViolation(RuntimeError):
    """An emitted string carries a defect that would reach the ROM.

    Deliberately fatal (CLAUDE.md §4.5): unconverted markup and unrenderable
    glyphs are cheap to fix at conversion time and expensive to find in a
    boot walk, which is the whole reason this validator exists.
    """
