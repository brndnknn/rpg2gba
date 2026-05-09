from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult


class ClaudeCodeBackend(ConversionBackend):
    """Interactive backend for Stage A (prompt calibration) and Stage C (refinement).

    Presents events to the user for review in a Claude Code session rather than
    running fully autonomously.
    """

    def convert_event(self, event_json: dict, registry_state: dict, prompt: str) -> ConversionResult:
        raise NotImplementedError
