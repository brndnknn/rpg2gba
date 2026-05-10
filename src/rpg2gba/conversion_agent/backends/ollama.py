import os

from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult


class OllamaBackend(ConversionBackend):
    """Local Ollama backend for Stage B bulk runs.

    Sends event JSON + prompt to the local model via HTTP, parses the structured
    JSON response, and returns a ConversionResult. Configure OLLAMA_HOST to point
    at the Ubuntu desktop when running over Tailscale.
    """

    def __init__(self, host: str | None = None, model: str = "qwen3:7b") -> None:
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self.model = model

    def convert_event(
        self,
        event_json: dict,
        registry_state: dict,
        prompt: str,
    ) -> ConversionResult:
        raise NotImplementedError
