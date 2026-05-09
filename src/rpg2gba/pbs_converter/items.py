from dataclasses import dataclass
from pathlib import Path


@dataclass
class Item:
    pass


def parse(path: Path) -> list[Item]:
    raise NotImplementedError


def emit_c(records: list[Item], out: Path) -> None:
    raise NotImplementedError


def round_trip_check(path: Path) -> bool:
    raise NotImplementedError
