from dataclasses import dataclass
from pathlib import Path


@dataclass
class Trainer:
    pass


def parse(path: Path) -> list[Trainer]:
    raise NotImplementedError


def emit_c(records: list[Trainer], out: Path) -> None:
    raise NotImplementedError


def round_trip_check(path: Path) -> bool:
    raise NotImplementedError
