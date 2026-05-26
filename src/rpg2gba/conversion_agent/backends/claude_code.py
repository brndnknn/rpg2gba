"""Primary conversion backend: headless Claude Code (`claude -p`) per event.

For each event the orchestrator spawns a fresh `claude -p --output-format json
--system-prompt <frozen>` process, feeds the assembled user prompt on stdin, and
parses the structured JSON the conversion agent returns. Each spawn is a
*separate* `claude` process — a distinct conversion-agent instance, never the
build-agent session — which keeps the two-agent boundary clean (CLAUDE.md §1).

`claude -p --output-format json` prints an envelope `{"result": "<text>", ...}`;
the agent's own structured object (per prompts/system.md) lives in `result`.

Budget note: every event spends Pro/API budget. Real runs are gated on the user
(CLAUDE.md §10); tests mock the subprocess and never spawn `claude`.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess

from rpg2gba.conversion_agent.backends import ConversionBackend, ConversionResult

logger = logging.getLogger(__name__)

_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class ClaudeCodeBackend(ConversionBackend):
    def __init__(
        self,
        system_prompt: str,
        *,
        claude_path: str = "claude",
        model: str = "claude-sonnet-4-6",
        disallowed_tools: str | None = "Bash Edit Write Read Glob Grep WebFetch WebSearch Task",
        max_budget_usd: float | None = None,
        bare: bool = False,
        extra_args: list[str] | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.system_prompt = system_prompt
        self.claude_path = claude_path
        self.model = model
        # The conversion agent is pure text I/O — deny every tool by default so a
        # spawned process can't wander off and run commands.
        self.disallowed_tools = disallowed_tools
        # Optional hard dollar cap per spawn (`claude --max-budget-usd`).
        self.max_budget_usd = max_budget_usd
        # `--bare` isolates the spawn from the repo's CLAUDE.md/hooks (cleaner
        # build/conversion boundary) BUT forces ANTHROPIC_API_KEY auth — it never
        # reads OAuth/keychain, so it bypasses a Pro subscription. Leave off unless
        # you're intentionally running on an API key.
        self.bare = bare
        self.extra_args = extra_args or []
        self.timeout = timeout

    def _build_cmd(self) -> list[str]:
        cmd = [
            self.claude_path,
            "-p",
            "--output-format",
            "json",
            "--model",
            self.model,
            "--system-prompt",
            self.system_prompt,
        ]
        if self.bare:
            cmd.append("--bare")
        if self.disallowed_tools:
            cmd += ["--disallowed-tools", self.disallowed_tools]
        if self.max_budget_usd is not None:
            cmd += ["--max-budget-usd", str(self.max_budget_usd)]
        cmd += self.extra_args
        return cmd

    def _run(self, prompt: str) -> str:
        proc = subprocess.run(
            self._build_cmd(),
            input=prompt,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc.stdout

    def convert_event(
        self,
        event_json: dict,
        registry_state: dict,
        prompt: str,
    ) -> ConversionResult:
        raw = self._run(prompt)
        return _parse_response(raw)


def _parse_response(raw: str) -> ConversionResult:
    """Unwrap the `claude -p` JSON envelope, then parse the agent's structured object."""
    text = raw.strip()
    # Unwrap the CLI envelope if present; otherwise treat stdout as the object.
    try:
        envelope = json.loads(text)
        if isinstance(envelope, dict) and "result" in envelope:
            text = envelope["result"]
        elif isinstance(envelope, dict) and "script" in envelope:
            return _to_result(envelope)
    except json.JSONDecodeError:
        pass
    return _to_result(_extract_object(text))


def _extract_object(text: str) -> dict:
    """Parse the first JSON object in `text` (the agent may add stray prose)."""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    m = _OBJECT_RE.search(text)
    if not m:
        raise RuntimeError(f"no JSON object in conversion-agent response: {text[:200]!r}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"malformed conversion-agent JSON: {exc}") from exc


def _to_result(data: dict) -> ConversionResult:
    if "script" not in data:
        raise RuntimeError(f"conversion-agent response missing 'script': {sorted(data)}")
    return ConversionResult(
        script=data["script"],
        new_flags=list(data.get("new_flags", [])),
        new_vars=list(data.get("new_vars", [])),
        unhandled=list(data.get("unhandled", [])),
    )
