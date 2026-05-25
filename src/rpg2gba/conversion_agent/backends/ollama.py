"""Optional local conversion backend: Ollama on the Ubuntu desktop (fallback).

Not the primary path (that's the headless Claude Code backend, decision F4), but
implemented behind the same ABC so it's selectable for a local-only bulk run.
Point OLLAMA_HOST at the desktop when driving it over Tailscale.

Ollama's `/api/chat` with `format: "json"` returns `{"message": {"content":
"<json string>"}}`; the conversion agent's structured object (per
prompts/system.md) is that content string.
"""
from __future__ import annotations

import json
import logging
import os

from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult
from rpg2gba.conversion_agent.backends.claude_code import _to_result

logger = logging.getLogger(__name__)


class OllamaBackend(ConversionBackend):
    def __init__(
        self,
        system_prompt: str,
        *,
        host: str | None = None,
        model: str = "qwen3:7b",
        timeout: float = 300.0,
    ) -> None:
        self.system_prompt = system_prompt
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model
        self.timeout = timeout

    def convert_event(
        self,
        event_json: dict,
        registry_state: dict,
        prompt: str,
    ) -> ConversionResult:
        import requests  # lazy: the optional fallback shouldn't force the dep

        resp = requests.post(
            f"{self.host.rstrip('/')}/api/chat",
            json={
                "model": self.model,
                "format": "json",
                "stream": False,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return _parse_chat(resp.json())


def _parse_chat(payload: dict) -> ConversionResult:
    try:
        content = payload["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"unexpected Ollama response shape: {sorted(payload)}") from exc
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama returned non-JSON content: {exc}") from exc
    return _to_result(data)
