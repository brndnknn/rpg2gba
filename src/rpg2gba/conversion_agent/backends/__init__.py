"""Backend abstraction for the conversion agent's LLM provider.

Three backends are supported:
  - OllamaBackend: local model on the Ubuntu desktop (Stage B)
  - ClaudeCodeBackend: interactive Claude Code sessions (Stages A and C)
  - AnthropicAPIBackend: direct API calls (Stage D fallback)
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
