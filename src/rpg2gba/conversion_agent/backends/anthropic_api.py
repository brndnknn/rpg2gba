from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult


class AnthropicAPIBackend(ConversionBackend):
    """Direct Anthropic API backend for Stage D fallback.

    Use prompt caching aggressively — the stable system prompt chunk is cacheable.
    Prefer claude-opus-4-7 for hard maps, claude-sonnet-4-6 for routine ones.
    """

    def __init__(self, api_key: str, model: str) -> None:
        raise NotImplementedError

    def convert_event(self, event_json: dict, registry_state: dict, prompt: str) -> ConversionResult:
        raise NotImplementedError
