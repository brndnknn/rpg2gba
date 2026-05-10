"""Orchestrator — drives the per-map event conversion loop.

For each map JSON:
  1. Check checkpoint — skip if already converted and validated
  2. Load the event list
  3. For each event, build a prompt and call the configured backend
  4. Parse the response: Poryscript block, new flag/var proposals, unhandled annotations
  5. Compile the output through Poryscript immediately
  6. On success: update registry, write .pory file, write checkpoint
  7. On compile failure: retry once with the compiler error appended to the prompt
  8. On second failure: append to output/unhandled.jsonl, move on

The backend is swappable:
  - Stage B: OllamaBackend (bulk overnight run)
  - Stage C: ClaudeCodeBackend (interactive queue review in a Claude Code session)
"""
from pathlib import Path

from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult
from rpg2gba.conversion_agent.flag_registry import FlagRegistry


class Orchestrator:
    def __init__(
        self,
        backend: ConversionBackend,
        registry: FlagRegistry,
        output_dir: Path,
    ) -> None:
        raise NotImplementedError

    def convert_map(self, map_json_path: Path) -> None:
        raise NotImplementedError

    def convert_all(self, map_dir: Path) -> None:
        raise NotImplementedError
