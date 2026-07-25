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

**Evidence gate (ROM_TEST_DEV.md §E1).** Writing a file into this directory
*is* the act of bucketing an event ``hand`` — the point past which nobody
re-asks whether the engine could have done it natively. That is exactly the
decision §4.7 keeps getting wrong (``healparty`` was invented while
``HealPlayerParty`` existed; day/night encounters were declared unsupported
while native). So loading also requires each override to have a matching
``hand``-bucketed entry, carrying real search evidence, in the triage ledger
(``queue_evidence.LEDGER_PATH``). An override with no ledger entry — or with
a blank evidence box — fails loud here, which is the one place the check
cannot be forgotten.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .queue_evidence import (
    LEDGER_PATH,
    QueueSchemaViolation,
    load_queue_jsonl,
)

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


def _hand_bucketed_events(ledger_path: Path) -> set[tuple[int, int]]:
    """``(map_id, event_id)`` pairs the ledger bucketed ``hand``.

    `load_queue_jsonl` does the evidence enforcement itself — it raises on
    any ``hand`` entry with a blank evidence box (and warns, rather than
    raising, for entries explicitly marked ``legacy_unaudited``). This
    function only has to collect what survived that.
    """
    if not ledger_path.is_file():
        raise QueueSchemaViolation(
            f"hand_overrides: triage ledger {ledger_path} is missing — every "
            f"hand conversion must be justified by a 'hand'-bucketed entry "
            f"with search evidence (ROM_TEST_DEV §E1)")
    pairs: set[tuple[int, int]] = set()
    for entry in load_queue_jsonl(ledger_path):
        if entry.bucket != "hand":
            continue
        map_id, event_id = entry.raw.get("map_id"), entry.raw.get("event_id")
        if map_id is not None and event_id is not None:
            pairs.add((int(map_id), int(event_id)))
    return pairs


def load_hand_overrides(
    overrides_dir: Path | None = None,
    ledger_path: Path | None = None,
) -> dict[tuple[int, int], HandOverride]:
    """Load and validate every committed hand-override file.

    Default directory is the package's own ``hand_conversions/`` (same
    resolution pattern as ``prompt_builder._PROMPTS``). ``README.md`` is
    skipped; any other non-``.pory`` file, or any ``.pory`` file whose
    filename doesn't match ``Map\\d{3}_EV\\d{3}\\.pory``, is a hard error — a
    stray file in this directory is a mistake, not something to silently
    ignore.

    Every override must additionally be justified by a ``hand``-bucketed
    entry with real search evidence in the triage ledger (``ledger_path``,
    default ``queue_evidence.LEDGER_PATH``) — see the module docstring.
    """
    directory = overrides_dir if overrides_dir is not None else _HAND_CONVERSIONS
    overrides: dict[tuple[int, int], HandOverride] = {}
    if not directory.is_dir():
        return overrides

    justified = _hand_bucketed_events(
        ledger_path if ledger_path is not None else LEDGER_PATH)

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
        if (map_id, event_id) not in justified:
            raise QueueSchemaViolation(
                f"hand_overrides: {path.name} hand-converts Map{map_id:03d}/"
                f"EV{event_id:03d}, but no 'hand'-bucketed triage entry with "
                f"search evidence exists for it — record the engine searches "
                f"that ruled out a native analog (ROM_TEST_DEV §E1, CLAUDE.md "
                f"§4.7) in the ledger before hand-converting")
        text = path.read_text(encoding="utf-8")
        _validate(path.name, map_id, event_id, text)
        overrides[(map_id, event_id)] = HandOverride(
            map_id=map_id, event_id=event_id, path=path, text=text
        )
    return overrides
