"""Single source of truth for FLAG_*/VAR_* name assignments.

The registry assigns pokeemerald-expansion flag/var names to RPG Maker switch/variable IDs.
It is stateful during a pipeline run and persists assignments across all map conversions.
All flag name proposals from the conversion agent must pass through here before acceptance.

Usage:
    python -m rpg2gba.conversion_agent.flag_registry validate
"""
from __future__ import annotations

import click


class FlagRegistry:
    def __init__(self) -> None:
        raise NotImplementedError

    def get_flag(self, switch_id: int) -> str | None:
        raise NotImplementedError

    def propose_flag(self, switch_id: int, name: str) -> str:
        raise NotImplementedError

    def get_var(self, variable_id: int) -> str | None:
        raise NotImplementedError

    def propose_var(self, variable_id: int, name: str) -> str:
        raise NotImplementedError

    def dump_header(self, out_path: str) -> None:
        raise NotImplementedError


@click.group()
def main() -> None:
    pass


@main.command()
def validate() -> None:
    """Validate the current registry state."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
