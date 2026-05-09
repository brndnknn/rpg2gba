from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult


class OllamaBackend(ConversionBackend):
    def __init__(self, host: str, model: str) -> None:
        raise NotImplementedError

    def convert_event(self, event_json: dict, registry_state: dict, prompt: str) -> ConversionResult:
        raise NotImplementedError
