"""Backend abstraction for the conversion agent's LLM provider.

The orchestrator calls convert_event() on whichever backend is configured.
Two backends are supported:

  OllamaBackend     — local model on the Ubuntu desktop; used for bulk Stage B runs
  ClaudeCodeBackend — interactive queue-review helper for Stage C; not a programmatic
                      LLM call, but a tool for presenting the unhandled queue in a
                      Claude Code session and writing results back to the pipeline

No paid API backend is used. All conversion is either local (Ollama) or interactive
(Claude Code via existing Pro subscription).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ConversionResult:
    script: str
    new_flags: dict[str, str] = field(default_factory=dict)
    new_vars: dict[str, str] = field(default_factory=dict)
    unhandled: list[dict] = field(default_factory=list)


class ConversionBackend(ABC):
    @abstractmethod
    def convert_event(
        self,
        event_json: dict,
        registry_state: dict,
        prompt: str,
    ) -> ConversionResult:
        raise NotImplementedError
