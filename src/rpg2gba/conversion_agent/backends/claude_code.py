from pathlib import Path

from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult


class ClaudeCodeBackend(ConversionBackend):
    """Stage C queue-review helper for interactive Claude Code sessions.

    This is not a programmatic LLM call. It loads events from the unhandled
    queue (output/unhandled.jsonl), formats them for review in a Claude Code
    session, and writes approved results back to the pipeline's checkpoint store.

    Usage: after a Stage B Ollama run, open the unhandled queue in a Claude Code
    session and use this backend to work through hard cases interactively.
    """

    def __init__(self, queue_path: Path, checkpoint_dir: Path) -> None:
        raise NotImplementedError

    def convert_event(
        self,
        event_json: dict,
        registry_state: dict,
        prompt: str,
    ) -> ConversionResult:
        raise NotImplementedError
