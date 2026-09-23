"""Uranium's Bambo reward ladder (`PROFREWARDS`), read from source.

`reference/scripts_dump/213_Bambo_Reward.rb` is the single source of truth
for what each rung of the ladder pays out (CLAUDE.md §4.3). This module
parses that table; it does not re-implement the Ruby that walks it.

The distinction this module exists to make (C8 stage 7, assignment task 1):

* `jvNextReward` reads `$Trainer.pokedexOwned` to decide whether the player
  has EARNED the next rung. That is a dex quantity, which ruling (b)
  deliberately declines to model, so it refuses `party_model` and must keep
  refusing.
* `jvGiveReward` reads only `$game_variables[22]` (the claimed-rung index)
  and `$game_switches[59/60/61]` (the starter choice). Both are ordinary
  modelled state, so what it pays out IS knowable -- which is why the
  blanket `non_literal_args` refusal it carries today is wrong.

STATUS: stub (`assignments/C8/01_jvgivereward.md`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Rung:
    """One entry of `PROFREWARDS`.

    `index` is the position in the table, which is what `$game_variables[22]`
    holds. `threshold` is the `pokedexOwned` count `jvNextReward` compares
    against -- carried for completeness, never consulted here (see the module
    docstring on why this module must not need it).

    An item rung carries one or more item symbols in `items` (index 5 pays
    two) and `species is None`. An egg rung carries `is_egg=True` and either
    a species symbol or the literal `"starter"` sentinel in `species`.
    """

    index: int
    threshold: int
    items: tuple[str, ...] = ()
    species: str | None = None
    is_egg: bool = False


def load_profrewards(scripts_dump_dir: Path | None = None) -> tuple[Rung, ...]:
    """The `PROFREWARDS` table, parsed from the vendored Ruby source.

    `scripts_dump_dir` defaults to the repo's `reference/scripts_dump/`.

    Raises `FileNotFoundError` if the source is missing and `ValueError` if
    the array literal cannot be parsed -- a silently empty ladder would turn
    every rung into a no-op and the floor would under-assert without saying
    so (CLAUDE.md §4.5).

    Use `ruby_subset.parse_expression`; the table is a Ruby array literal of
    array literals, and this repo has a parser for exactly that.
    """
    raise NotImplementedError("assignments/C8/01_jvgivereward.md R1")


def rungs_for_variable(
    rungs: tuple[Rung, ...], values: frozenset[int] | None = None
) -> tuple[Rung, ...]:
    """The rungs that could fire, given what is known about variable 22.

    `values is None` means "unconstrained": every reachable rung is possible.
    An explicit set narrows to those indices.

    Index 0 pays nothing and index 11 is the original author's crash
    workaround (`[999]`, unreachable in play) -- decide what this returns for
    each and document it.

    Note this returns CANDIDATES, not a decision. Widening is safe here;
    turning a plural candidate set into floor assertions is NOT (see the task
    file's R2 -- the floor is a conjunction, and several same-key grant
    assertions contradict each other). Narrowing to a set of two is still a
    set of two.
    """
    raise NotImplementedError("assignments/C8/01_jvgivereward.md R2")
