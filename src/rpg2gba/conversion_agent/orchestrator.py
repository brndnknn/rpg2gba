"""Drives the event-to-Poryscript conversion loop.

For each map JSON: loads events, calls the conversion agent backend once per event,
validates output through the Poryscript compiler, updates the flag registry, and
writes checkpoint state so runs are resumable.
"""
from pathlib import Path

from rpg2gba.conversion_agent.backends import ConversionBackend
from rpg2gba.conversion_agent.flag_registry import FlagRegistry


class Orchestrator:
    def __init__(self, backend: ConversionBackend, registry: FlagRegistry, output_dir: Path) -> None:
        raise NotImplementedError

    def convert_map(self, map_json_path: Path) -> None:
        raise NotImplementedError

    def convert_all(self, map_dir: Path) -> None:
        raise NotImplementedError
