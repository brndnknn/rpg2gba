from dataclasses import dataclass
from pathlib import Path


@dataclass
class EncounterTable:
    pass


def parse(path: Path) -> list[EncounterTable]:
    raise NotImplementedError


def emit_c(records: list[EncounterTable], out: Path) -> None:
    raise NotImplementedError


def round_trip_check(path: Path) -> bool:
    raise NotImplementedError
