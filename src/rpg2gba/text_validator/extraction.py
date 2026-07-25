"""String-literal extraction from the emitted ``.pory`` corpus.

Validates the corpus the transpiler actually emits under ``output/<slice>/``
(``scripts/*.pory``, ``staging/scripts/*.pory``, ``porymap/dispatch/*.pory``,
``CommonEvents.pory``) — i.e. what the assemble step (``scripts/assemble_pathfinder.py``)
reads and (after its own ``normalize_pory`` charmap pass) compiles into the
ROM. Comment lines (``# ...``) are skipped: poryscript strips them and they
never reach the ROM, so any control code or stray markup living only in a
``# UNHANDLED ...`` comment (the transpiler's own fail-loud queueing — see
``conversion_agent/deterministic.py``) is not a corpus-validator concern.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_BLOCK_HEADER_RE = re.compile(r"^\s*(?:script|text|movement|mapscripts|mart)\s+(\S+)\s*\{")
_STRING_LITERAL_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_FORMAT_CALL_RE = re.compile(r"\bformat\s*\(\s*$")


@dataclass(frozen=True)
class SourceLocation:
    """Where an extracted string came from, for readable issue reports."""

    file: Path
    line: int
    label: str | None  # nearest enclosing script/text/movement/mart block

    def __str__(self) -> str:
        loc = f"{self.file}:{self.line}"
        return f"{loc} ({self.label})" if self.label else loc


@dataclass(frozen=True)
class ExtractedString:
    """One double-quoted string literal pulled out of a ``.pory`` file.

    ``content`` is the literal's inner text with ``\\"`` unescaped back to
    ``"`` (matching what actually reaches the charmap/font stage — see
    ``tileset_converter.assembly.normalize_pory``, which performs the same
    unescape when it retypographs quotes). ``wrapped_in_format`` is True when
    the literal is the argument of a ``format(...)`` call, which poryscript
    re-wraps to the message-box width at compile time (see ``rules.py`` for
    how that changes what the line-width rule can check).
    """

    content: str
    wrapped_in_format: bool
    location: SourceLocation
    raw_literal: str
    """The literal's inner text exactly as written in the source line — ``\\"``
    still escaped, nothing unescaped. Kept alongside ``content`` so a rule that
    needs to re-run the real pipeline's own source-level logic (e.g. the
    charmap check, which reuses ``tileset_converter.assembly.normalize_pory``)
    can rebuild an exact ``"..."`` literal that function expects, rather than
    working from the already-unescaped display form."""


def _unescape(raw: str) -> str:
    return raw.replace('\\"', '"')


def extract_strings(text: str, file: Path) -> list[ExtractedString]:
    """All double-quoted string literals in one ``.pory`` file's text."""
    out: list[ExtractedString] = []
    current_label: str | None = None
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        m = _BLOCK_HEADER_RE.match(line)
        if m:
            current_label = m.group(1)
        for lit in _STRING_LITERAL_RE.finditer(line):
            wrapped = bool(_FORMAT_CALL_RE.search(line[: lit.start()]))
            out.append(
                ExtractedString(
                    content=_unescape(lit.group(1)),
                    wrapped_in_format=wrapped,
                    location=SourceLocation(file=file, line=line_no, label=current_label),
                    raw_literal=lit.group(1),
                )
            )
    return out


# Corpus roots the transpiler actually emits .pory into, relative to an
# output slice dir (e.g. output/uranium-build). ``staging/scripts`` is the
# post-species/dispatch-glue set that assemble_pathfinder.py actually reads
# (scripts/assemble_pathfinder.py:420-421); ``scripts`` (pre-staging) and
# ``porymap/dispatch`` are included too so a corpus-wide scan catches issues
# regardless of which stage introduced them.
_CORPUS_GLOBS = (
    "scripts/*.pory",
    "staging/scripts/*.pory",
    "porymap/dispatch/*.pory",
)


def iter_corpus_files(output_dir: Path) -> list[Path]:
    """``.pory`` files under an output slice directory, in a stable order."""
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in _CORPUS_GLOBS:
        for path in sorted(output_dir.glob(pattern)):
            if path not in seen:
                seen.add(path)
                files.append(path)
    return files


def extract_corpus(output_dir: Path) -> list[ExtractedString]:
    """All extracted strings across every ``.pory`` file under ``output_dir``."""
    strings: list[ExtractedString] = []
    for path in iter_corpus_files(output_dir):
        strings.extend(extract_strings(path.read_text(encoding="utf-8"), path))
    return strings
