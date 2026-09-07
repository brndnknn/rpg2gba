"""Shared id → `CONSTANT` resolution for the PBS converters.

Every PBS converter carries a private `_Resolver` dataclass that turns Uranium's
numeric ids into pokeemerald constants, registers the mapping in the `IdMap`, and
flags anything the fork doesn't define (`needs_engine`). Five of them had grown
byte-identical copies of `move_constant`, three of `species_constant`, two each of
`item_constant` and `type_constant` — and the copies had already diverged once: the
2026-09-07 repo audit found three of the five `move_constant` copies guarded
`move_id == 0` and two did not, so the same input produced `MOVE_NONE` in one
converter and a `ValueError` in another (finding 8 / Q3).

The mixins below are the single definition. Each is a plain class, **not** a
dataclass: it declares no runtime annotations, so inheriting it contributes no
fields and cannot disturb a subclass's dataclass field order. The fields each mixin
reads are declared under `TYPE_CHECKING` for readers and type checkers only — that
block never executes, so nothing lands in `__annotations__`.

A converter mixes in only what it needs:

    @dataclass
    class _Resolver(MoveResolverMixin, SpeciesResolverMixin):
        id_map: IdMap
        species_internal: dict[int, str]
        move_internal: dict[int, str]
        move_names: dict[int, str]
        fork_species: set[str]
        fork_moves: set[str]

Declaring the fields stays the subclass's job — that is what keeps each converter's
`_build_resolver` honest about which reference tables it actually loads.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ._naming import to_constant

if TYPE_CHECKING:  # pragma: no cover - annotations only, never executed
    from ._id_map import IdMap


# Uranium's internal type name → the expansion constant, where `to_constant`
# can't get there on its own. Shared by moves.py and pokemon.py.
TYPE_NAME_OVERRIDES: dict[str, str] = {"QMARKS": "TYPE_MYSTERY"}


class MoveResolverMixin:
    """`move_constant` — move id → `MOVE_*`.

    Id 0 is Uranium's empty move slot (an unfilled trainer party move, a blank TM
    row), not move index 0; it resolves to `MOVE_NONE` rather than failing.
    """

    if TYPE_CHECKING:
        id_map: IdMap
        move_internal: dict[int, str]
        move_names: dict[int, str]
        fork_moves: set[str]

    def move_constant(self, move_id: int) -> str:
        if move_id == 0:
            return "MOVE_NONE"
        internal = self.move_internal.get(move_id)
        if internal is None:
            raise ValueError(f"move id {move_id} absent from move_internal_names.json")
        const = to_constant("MOVE", self.move_names.get(move_id) or internal)
        needs = bool(self.fork_moves) and const not in self.fork_moves
        self.id_map.add("moves", internal, const, needs_engine=needs)
        return const


class SpeciesResolverMixin:
    """`species_constant` — species id → `SPECIES_*`.

    No id-0 guard: unlike moves/items/abilities, no PBS table uses species 0 as an
    empty slot, so a 0 here is a real data defect and must fail loud (§4.5).
    """

    if TYPE_CHECKING:
        id_map: IdMap
        species_internal: dict[int, str]
        fork_species: set[str]

    def species_constant(self, species_id: int) -> str:
        internal = self.species_internal.get(species_id)
        if internal is None:
            raise ValueError(f"species id {species_id} absent from species_internal_names.json")
        const = to_constant("SPECIES", internal)
        needs = bool(self.fork_species) and const not in self.fork_species
        self.id_map.add("species", internal, const, needs_engine=needs)
        return const


class ItemResolverMixin:
    """`item_constant` — item id → `ITEM_*`; id 0 is the empty held-item slot."""

    if TYPE_CHECKING:
        id_map: IdMap
        item_internal: dict[int, str]
        item_names: dict[int, str]
        fork_items: set[str]

    def item_constant(self, item_id: int) -> str:
        if item_id == 0:
            return "ITEM_NONE"
        internal = self.item_internal.get(item_id)
        if internal is None:
            raise ValueError(f"item id {item_id} absent from item_internal_names.json")
        const = to_constant("ITEM", self.item_names.get(item_id) or internal)
        needs = bool(self.fork_items) and const not in self.fork_items
        self.id_map.add("items", internal, const, needs_engine=needs)
        return const


class AbilityResolverMixin:
    """`ability_constant` — ability id → `ABILITY_*`; id 0 is the empty slot."""

    if TYPE_CHECKING:
        id_map: IdMap
        ability_internal: dict[int, str]
        ability_names: dict[int, str]
        fork_abilities: set[str]

    def ability_constant(self, ability_id: int) -> str:
        if ability_id == 0:
            return "ABILITY_NONE"
        internal = self.ability_internal.get(ability_id)
        if internal is None:
            raise ValueError(f"ability id {ability_id} absent from ability_internal_names.json")
        const = to_constant("ABILITY", self.ability_names.get(ability_id) or internal)
        needs = bool(self.fork_abilities) and const not in self.fork_abilities
        self.id_map.add("abilities", internal, const, needs_engine=needs)
        return const


class TypeResolverMixin:
    """`type_constant` — type index → `TYPE_*`.

    No fork gate: the expansion's type set is fixed and Uranium's one addition
    (Nuclear) is tracked as engine work, not as a per-call `needs_engine` flag.
    """

    if TYPE_CHECKING:
        id_map: IdMap
        type_internal: dict[int, str]

    def type_constant(self, type_idx: int) -> str:
        internal = self.type_internal.get(type_idx)
        if internal is None:
            raise ValueError(f"type index {type_idx} absent from type_internal_names.json")
        const = TYPE_NAME_OVERRIDES.get(internal, to_constant("TYPE", internal))
        self.id_map.add("types", internal, const)
        return const
