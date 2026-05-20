"""Single source of truth for Uranium internal name → expansion constant.

Per CLAUDE.md §6 and §4.3, every `SPECIES_*`, `MOVE_*`, `ITEM_*`, `ABILITY_*`,
`TRAINER_*`, `TRAINER_CLASS_*`, and `TYPE_*` constant minted by Phase 2 passes
through this map. `add()` is idempotent on identical pairs; a conflicting
constant for the same internal name raises `IdMapConflictError` (fail-loud).

The map lives at `reference/uranium_id_map.json` and is committed to git.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CATEGORIES: tuple[str, ...] = (
    "species",
    "moves",
    "items",
    "abilities",
    "trainers",
    "trainer_classes",
    "types",
)

NEEDS_ENGINE_CATEGORIES: tuple[str, ...] = ("moves", "abilities", "items", "species")


class IdMapError(Exception):
    """Base class for id-map errors."""


class IdMapConflictError(IdMapError):
    """Raised when two different constants are minted for the same internal name."""


class IdMapUnknownCategoryError(IdMapError):
    """Raised when a caller passes a category that isn't part of CATEGORIES."""


@dataclass
class IdMap:
    """In-memory copy of `reference/uranium_id_map.json`."""

    version: int = 1
    by_category: dict[str, dict[str, str]] = field(default_factory=dict)
    needs_engine: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for cat in CATEGORIES:
            self.by_category.setdefault(cat, {})
        for cat in NEEDS_ENGINE_CATEGORIES:
            self.needs_engine.setdefault(cat, [])

    @classmethod
    def load(cls, path: Path | str) -> "IdMap":
        path = Path(path)
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        obj = cls(version=raw.get("version", 1))
        for cat in CATEGORIES:
            obj.by_category[cat] = dict(raw.get(cat, {}))
        for cat in NEEDS_ENGINE_CATEGORIES:
            obj.needs_engine[cat] = list(raw.get("needs_engine", {}).get(cat, []))
        return obj

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {"version": self.version}
        for cat in CATEGORIES:
            payload[cat] = dict(sorted(self.by_category[cat].items()))
        payload["needs_engine"] = {
            cat: sorted(set(self.needs_engine[cat])) for cat in NEEDS_ENGINE_CATEGORIES
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def get(self, category: str, internal: str) -> str | None:
        self._check_category(category)
        return self.by_category[category].get(internal)

    def add(
        self,
        category: str,
        internal: str,
        constant: str,
        *,
        needs_engine: bool = False,
    ) -> str:
        """Mint or look up an internal→constant binding.

        - First add of (internal → constant) records it and returns constant.
        - Re-adding the exact same pair is a no-op (idempotent).
        - Re-adding a *different* constant for the same internal raises
          `IdMapConflictError` (fail-loud per CLAUDE.md §4.5).
        """
        self._check_category(category)
        existing = self.by_category[category].get(internal)
        if existing is not None and existing != constant:
            raise IdMapConflictError(
                f"id_map[{category}][{internal!r}] = {existing!r} but caller tried to "
                f"re-bind to {constant!r}"
            )
        self.by_category[category][internal] = constant
        if needs_engine:
            self._mark_needs_engine(category, constant)
        return constant

    def mark_needs_engine(self, category: str, constant: str) -> None:
        """Mark an already-bound constant as needing Phase 6 engine work."""
        self._mark_needs_engine(category, constant)

    def _mark_needs_engine(self, category: str, constant: str) -> None:
        if category not in NEEDS_ENGINE_CATEGORIES:
            raise IdMapUnknownCategoryError(
                f"needs_engine not tracked for category {category!r} — "
                f"allowed: {NEEDS_ENGINE_CATEGORIES}"
            )
        bucket = self.needs_engine[category]
        if constant not in bucket:
            bucket.append(constant)

    def _check_category(self, category: str) -> None:
        if category not in CATEGORIES:
            raise IdMapUnknownCategoryError(
                f"unknown category {category!r} — allowed: {CATEGORIES}"
            )
