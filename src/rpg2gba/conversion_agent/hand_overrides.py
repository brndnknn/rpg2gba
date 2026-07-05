"""Hand-override layer for the deterministic event->Poryscript transpiler.

A handful of branch-heavy story events are hand-converted rather than
transpiled: committed ``.pory`` files under ``hand_conversions/`` that the
driver (``transpile_driver.transpile_map``) splices into a map's output
verbatim, skipping both the idiom-collapse classifiers (``deterministic.py``)
and the general transpiler (``transpiler.py``) for that event entirely.

Each override file is named ``Map{mmm:03d}_EV{eee:03d}.pory`` and must contain
the event's *complete* Poryscript — every page's script block, plus any
``text``/``movement``/``mart`` blocks it needs — already in the canonical
``Map{m:03d}_EV{e:03d}_Page{n}`` label scheme the transpiler emits (see
``transpiler._page_label`` / ``metadata_wiring.page_label``). Loading
validates that every top-level definition in the file stays inside its own
event's label namespace, so a copy-pasted or hand-edited label can't silently
collide with another event's symbols on the same map (CLAUDE.md §4.5 — fail
loud, don't guess).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_PKG = Path(__file__).resolve().parent
_HAND_CONVERSIONS = _PKG / "hand_conversions"

# Override filenames: MapNNN_EVNNN.pory.
_FILENAME_RE = re.compile(r"^Map(\d{3})_EV(\d{3})\.pory$")

# A top-level Poryscript definition: `script NAME {`, `text NAME {`,
# `movement NAME {`, or `mart NAME {`, unindented (column 0).
_DEFINITION_RE = re.compile(
    r"^(script|text|movement|mart)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{", re.MULTILINE
)

# A definition name's namespace: MapNNN_EVNNN, optionally with a free-form
# `_suffix` (e.g. `_Page1`, `_Mart`, `_Page1_Move1`).
_NAMESPACE_RE = re.compile(r"^Map(\d{3})_EV(\d{3})(?:_.+)?$")


@dataclass(frozen=True)
class HandOverride:
    """One committed hand-conversion override for a single map event.

    ``text`` is the complete Poryscript for the event — the driver splices it
    in verbatim in place of whatever the classifier/transpiler would have
    produced, and runs no further processing over it (see
    ``transpile_driver.transpile_map``).
    """

    map_id: int
    event_id: int
    path: Path
    text: str


def _validate(filename: str, map_id: int, event_id: int, text: str) -> None:
    """Fail-loud checks for one override file's text (CLAUDE.md §4.5).

    1. Non-empty.
    2. Defines at least one ``script Map{mmm}_EV{eee}_...`` block for its own
       ids — an entry point in its own namespace.
    3. Every top-level definition (``script``/``text``/``movement``/``mart``)
       carries the file's own map/event ids. A definition that isn't
       ``MapNNN_EVNNN``-shaped at all, or that names another event's ids, is
       the cross-event label-collision hazard this whole layer guards
       against.
    """
    if not text.strip():
        raise ValueError(f"hand_overrides: {filename} is empty")

    own_prefix = f"Map{map_id:03d}_EV{event_id:03d}"
    definitions = _DEFINITION_RE.findall(text)

    if not any(
        keyword == "script" and name.startswith(own_prefix + "_")
        for keyword, name in definitions
    ):
        raise ValueError(
            f"hand_overrides: {filename} defines no 'script {own_prefix}_...' "
            f"block — every override must define at least one entry script in "
            f"its own namespace"
        )

    for keyword, name in definitions:
        ns_match = _NAMESPACE_RE.match(name)
        if ns_match is None:
            raise ValueError(
                f"hand_overrides: {filename} defines {keyword} {name!r}, which "
                f"is not MapNNN_EVNNN-shaped — every definition in an override "
                f"must stay in its own Map{{mmm}}_EV{{eee}} namespace"
            )
        def_map, def_event = int(ns_match.group(1)), int(ns_match.group(2))
        if (def_map, def_event) != (map_id, event_id):
            raise ValueError(
                f"hand_overrides: {filename} defines {keyword} {name!r} under "
                f"Map{def_map:03d}_EV{def_event:03d}'s namespace, not its own "
                f"Map{map_id:03d}_EV{event_id:03d} — this is the cross-event "
                f"label collision hazard hand overrides must avoid"
            )


def load_hand_overrides(
    overrides_dir: Path | None = None,
) -> dict[tuple[int, int], HandOverride]:
    """Load and validate every committed hand-override file.

    Default directory is the package's own ``hand_conversions/`` (same
    resolution pattern as ``prompt_builder._PROMPTS``). ``README.md`` is
    skipped; any other non-``.pory`` file, or any ``.pory`` file whose
    filename doesn't match ``Map\\d{3}_EV\\d{3}\\.pory``, is a hard error — a
    stray file in this directory is a mistake, not something to silently
    ignore.
    """
    directory = overrides_dir if overrides_dir is not None else _HAND_CONVERSIONS
    overrides: dict[tuple[int, int], HandOverride] = {}
    if not directory.is_dir():
        return overrides

    for path in sorted(directory.iterdir()):
        if path.name == "README.md":
            continue
        if path.suffix != ".pory":
            raise ValueError(
                f"hand_overrides: unexpected file {path.name!r} in {directory} "
                f"— only MapNNN_EVNNN.pory override files and README.md are "
                f"allowed here"
            )
        m = _FILENAME_RE.match(path.name)
        if m is None:
            raise ValueError(
                f"hand_overrides: malformed override filename {path.name!r} — "
                f"expected MapNNN_EVNNN.pory (e.g. Map012_EV003.pory)"
            )
        map_id, event_id = int(m.group(1)), int(m.group(2))
        text = path.read_text(encoding="utf-8")
        _validate(path.name, map_id, event_id, text)
        overrides[(map_id, event_id)] = HandOverride(
            map_id=map_id, event_id=event_id, path=path, text=text
        )
    return overrides
