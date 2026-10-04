"""The beat generator's per-row status record, read back from a generated
chapter module (PROJECT_TODO #124, operator ruling 2026-10-04 "emit + derive").

`beat_gen.emit` writes four row-keyed dicts into every generated module:
`ELSEWHERE` (row -> `"<status>[: <detail>]"`), `REFUSED` (row ->
`"<blocker>: <reason>..."`), `NEVER_FIRES` and `EMPTY_PAGES` (row -> proof).
This module turns them into disposition specs once, at construction, so
`derivation.derive_entry` stays pure and does a dict lookup per row:

- `ELSEWHERE` `unreachable[: d]` -> `unreachable:<d or a fixed reason>`
  (ruling R8: live in no chapter is the existing `unreachable:` head);
- any other `ELSEWHERE` value  -> `elsewhere:<value>`;
- `NEVER_FIRES`/`EMPTY_PAGES`  -> `elsewhere:never_fires: <proof>` /
  `elsewhere:empty_page: <proof>`;
- `REFUSED`                    -> `refused:<value>`.

Every spec is parsed through `Disposition.parse` here, so a malformed record
fails loud at load, not when the sidecar is read back.

Modules generated before 2026-10-04 lack `ELSEWHERE`/`REFUSED`: that reads as
empty, logged once at INFO -- not an error, they simply predate the record.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from types import ModuleType

from .schema import Disposition

logger = logging.getLogger(__name__)

#: The `unreachable:` argument when the generator's record carries no detail
#: (the story model's "live in no chapter" verdict has none of its own).
UNREACHABLE_DEFAULT_REASON = "beat_gen: the story model places it in no chapter"

#: `ELSEWHERE`/`REFUSED` arrived 2026-10-04 (a module may predate them);
#: `NEVER_FIRES`/`EMPTY_PAGES` predate this record and are read as-is.
_NEW_DICTS = ("ELSEWHERE", "REFUSED")
_OLD_DICTS = ("NEVER_FIRES", "EMPTY_PAGES")


@dataclass(frozen=True)
class GeneratorStatus:
    """Row id -> derived disposition spec, from one chapter module."""

    specs: Mapping[str, str]

    def spec_for(self, row_id: str) -> str | None:
        return self.specs.get(row_id)


def _elsewhere_spec(value: str) -> str:
    status, _, detail = value.partition(":")
    if status.strip() == "unreachable":
        return f"unreachable:{detail.strip() or UNREACHABLE_DEFAULT_REASON}"
    return f"elsewhere:{value}"


def _read_dict(module: ModuleType, name: str) -> dict[str, str] | None:
    value = getattr(module, name, None)
    if value is None:
        return None
    if not isinstance(value, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise TypeError(
            f"{module.__name__}.{name} must be a dict[str, str], got {value!r:.200}")
    return value


def status_from_module(module: ModuleType) -> GeneratorStatus:
    """Build the spec table from a loaded chapter module. A row named by two
    dicts is a generator bug (each row lands in exactly one bucket) and
    raises `ValueError`."""
    missing = [name for name in _NEW_DICTS if not hasattr(module, name)]
    if missing:
        logger.info(
            "%s has no %s -- generated before the 2026-10-04 status record; "
            "its refused/Elsewhere rows derive nothing until it is regenerated",
            module.__name__, "/".join(missing))
    sources: list[tuple[str, dict[str, str]]] = []
    for name in (*_NEW_DICTS, *_OLD_DICTS):
        table = _read_dict(module, name)
        if table is not None:
            sources.append((name, table))

    specs: dict[str, str] = {}
    seen_in: dict[str, str] = {}
    for name, table in sources:
        for row_id, value in table.items():
            if name == "ELSEWHERE":
                spec = _elsewhere_spec(value)
            elif name == "REFUSED":
                spec = f"refused:{value}"
            elif name == "NEVER_FIRES":
                spec = f"elsewhere:never_fires: {value}"
            else:
                spec = f"elsewhere:empty_page: {value}"
            if row_id in specs:
                raise ValueError(
                    f"{module.__name__}: {row_id} is in both {seen_in[row_id]} "
                    f"and {name}; a generated row lands in exactly one bucket")
            Disposition.parse(row_id, spec)  # fail loud on a malformed record
            specs[row_id] = spec
            seen_in[row_id] = name
    return GeneratorStatus(specs=specs)


def build_generator_status(chapter_id: str) -> GeneratorStatus | None:
    """The status table for `chapter_id`'s generated module (suite `gen`),
    or None when the chapter has no module yet -- same degrade as
    `beat_model.build_beat_model`. A module that exists but fails to import
    raises through (CLAUDE.md §4.5)."""
    from rpg2gba.playtest.chapter import load_chapter_module

    try:
        module = load_chapter_module(chapter_id)
    except KeyError:
        logger.info("no generated module for %s -- no generator status to derive from",
                    chapter_id)
        return None
    return status_from_module(module)
