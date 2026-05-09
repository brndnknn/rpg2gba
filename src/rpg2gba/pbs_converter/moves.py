from dataclasses import dataclass
from pathlib import Path


@dataclass
class Move:
    pass


def parse(path: Path) -> list[Move]:
    raise NotImplementedError


def emit_c(records: list[Move], out: Path) -> None:
    raise NotImplementedError


def round_trip_check(path: Path) -> bool:
    raise NotImplementedError
