from dataclasses import dataclass
from pathlib import Path


@dataclass
class Ability:
    pass


def parse(path: Path) -> list[Ability]:
    raise NotImplementedError


def emit_c(records: list[Ability], out: Path) -> None:
    raise NotImplementedError


def round_trip_check(path: Path) -> bool:
    raise NotImplementedError
