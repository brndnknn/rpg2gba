from dataclasses import dataclass
from pathlib import Path


@dataclass
class Species:
    pass


def parse(path: Path) -> list[Species]:
    raise NotImplementedError


def emit_c(records: list[Species], out: Path) -> None:
    raise NotImplementedError


def round_trip_check(path: Path) -> bool:
    raise NotImplementedError
