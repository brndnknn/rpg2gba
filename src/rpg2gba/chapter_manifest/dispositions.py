"""Loader/writer for the authored disposition file (Q6, Q6.1, Q6.2).

The manifest is split into two files (PLAYTEST_AUTHORING_IMPROVEMENT.md Q6):
the *generated* row facts (owned by `generator.py`) and the *authored*
per-row decisions this module reads and writes. The generator never writes
here — that separation is the whole point, since CLAUDE.md §11 forbids
editing generated output and a hand-made decision has to live somewhere the
generator cannot clobber it.

Path convention: ``reference/manifests/<chapter_id>.dispositions.json``,
sibling to the generated manifest at
``reference/manifests/<chapter_id>.manifest.json`` (owned by
``generator.py``; this module does not read it). `<chapter_id>` is the
chapter identifier used throughout the repo (e.g. ``CH04``).

File shape — a JSON object mapping ``row_id`` to either:

* a bare string spec, e.g. ``"cosmetic"``, ``"beat:B12"``,
  ``"blocked:rock_smash"`` — the common case, kept to one line per row; or
* an object ``{"disposition": "...", "source": "...",
  "affirmed_hash": "...", "assertable": true, "negative_beat": "...",
  "note": "..."}`` when the row also carries a citation, an affirmed content
  hash, an assertability judgment, or a free-text note.

Both forms parse into `schema.Disposition` via `Disposition.parse`, which
already validates the verdict and its argument — this module does not
duplicate that validation.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .schema import Disposition, DispositionError

logger = logging.getLogger(__name__)

MANIFESTS_DIR = Path("reference") / "manifests"


class DispositionFileError(ValueError):
    """The disposition file is malformed (bad JSON, bad row entry)."""


def disposition_path(chapter_id: str, *, root: Path | None = None) -> Path:
    """Path convention: ``reference/manifests/<chapter_id>.dispositions.json``."""
    base = root if root is not None else MANIFESTS_DIR
    return base / f"{chapter_id}.dispositions.json"


def load_dispositions(path: Path) -> dict[str, Disposition]:
    """Parse the authored disposition file into `row_id -> Disposition`.

    Fails loud (CLAUDE.md §4.5) on malformed JSON, a non-object top level, a
    non-string/non-object row entry, or a row whose spec `Disposition.parse`
    rejects — never silently drops or defaults a row.
    """
    with path.open(encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as exc:
            raise DispositionFileError(f"{path}: invalid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise DispositionFileError(
            f"{path}: expected a JSON object mapping row_id -> disposition, "
            f"got {type(raw).__name__}"
        )

    result: dict[str, Disposition] = {}
    for row_id, entry in raw.items():
        result[row_id] = _parse_entry(path, row_id, entry)
    return result


def _parse_entry(path: Path, row_id: str, entry: Any) -> Disposition:
    if isinstance(entry, str):
        try:
            return Disposition.parse(row_id, entry)
        except DispositionError as exc:
            raise DispositionFileError(f"{path}: {exc}") from exc

    if isinstance(entry, dict):
        spec = entry.get("disposition")
        if not isinstance(spec, str):
            raise DispositionFileError(
                f"{path}: row {row_id!r} entry is missing a string 'disposition' field"
            )
        rest = {
            key: entry[key]
            for key in ("source", "affirmed_hash", "note", "assertable", "negative_beat")
            if key in entry
        }
        try:
            return Disposition.parse(row_id, spec, **rest)
        except DispositionError as exc:
            raise DispositionFileError(f"{path}: {exc}") from exc

    raise DispositionFileError(
        f"{path}: row {row_id!r} entry must be a string or object, "
        f"got {type(entry).__name__}"
    )


def write_dispositions(dispositions: dict[str, Disposition], path: Path) -> None:
    """Serialize `row_id -> Disposition` deterministically.

    Not part of the generate path — `generator.py` never calls this. It
    exists for tooling that helps a human author affirm hashes (e.g. a
    "stamp the current content_hash onto every row I already decided"
    helper), so the output is meant to be re-read, hand-edited, and
    re-written without spurious diffs: sorted keys, indent 2, trailing
    newline, and the compact string form whenever a row carries nothing but
    a verdict/argument.
    """
    payload: dict[str, Any] = {}
    for row_id in sorted(dispositions):
        disp = dispositions[row_id]
        extras = {
            key: value
            for key, value in (
                ("source", disp.source),
                ("affirmed_hash", disp.affirmed_hash),
                ("assertable", disp.assertable),
                ("negative_beat", disp.negative_beat),
                ("note", disp.note),
            )
            if value is not None
        }
        payload[row_id] = disp.spec if not extras else {"disposition": disp.spec, **extras}

    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    logger.info("wrote %d disposition(s) to %s", len(dispositions), path)
