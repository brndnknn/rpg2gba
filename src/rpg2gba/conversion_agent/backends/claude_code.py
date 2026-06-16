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

import datetime as _dt
import json
import logging
import re
import subprocess
import time
from pathlib import Path

from rpg2gba.conversion_agent.backends import (
    BackendTransportError,
    ConversionBackend,
    ConversionResult,
    RateLimitError,
)

logger = logging.getLogger(__name__)

_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

# Substrings (case-insensitive) that mark a *usage cap* in the `claude` CLI output —
# distinct from a transient transport hiccup. Tuned conservatively; if a future CLI
# version phrases a limit differently, the bulk runner logs the raw text of any
# unclassified failure so these can be extended. A weekly cap additionally matches
# _WEEKLY_MARKERS and is a hard stop for the runner (vs the 5-hour window it waits out).
_RATE_LIMIT_MARKERS = (
    "usage limit",
    "rate limit",
    "rate_limit",
    "limit reached",
    "limit will reset",
    "resets at",
    "reset at",
    "too many requests",
    "quota exceeded",
    "http 429",
    "status 429",
    "error 429",
)
_WEEKLY_MARKERS = ("week",)
_RESET_HINT_RE = re.compile(r"reset[^.\n]*", re.IGNORECASE)


def _error_text(proc: subprocess.CompletedProcess) -> str | None:
    """Return the text to scan for a failure cause, or None if the spawn succeeded.

    A spawn is a success when it exits 0 with a JSON envelope that is not flagged
    ``is_error`` (the normal conversion case) — that output is returned to the parser
    untouched and never scanned, so a clean conversion can't be mistaken for a cap.
    Otherwise (non-zero exit, or a returncode-0 envelope with ``is_error``) we return
    the provider's own error message (envelope ``result``/``subtype``) plus stderr,
    which is the only text that should be tested against the usage-cap markers."""
    envelope: dict | None
    try:
        parsed = json.loads((proc.stdout or "").strip())
        envelope = parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        envelope = None
    if proc.returncode == 0 and (envelope is None or not envelope.get("is_error")):
        return None
    parts: list[str] = []
    if envelope is not None:
        if envelope.get("result"):
            parts.append(str(envelope["result"]))
        if envelope.get("subtype"):
            parts.append(str(envelope["subtype"]))
    else:
        parts.append(proc.stdout or "")
    parts.append(proc.stderr or "")
    return "\n".join(p for p in parts if p)


def _classify_rate_limit(text: str) -> RateLimitError | None:
    """Return a RateLimitError if `text` looks like a usage cap, else None."""
    low = text.lower()
    if not any(m in low for m in _RATE_LIMIT_MARKERS):
        return None
    weekly = any(m in low for m in _WEEKLY_MARKERS)
    hint = _RESET_HINT_RE.search(text)
    return RateLimitError(
        text.strip()[:500], weekly=weekly, reset_hint=hint.group(0).strip() if hint else None
    )


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
        timeout: float = 600.0,
        usage_log_path: Path | None = None,
        max_attempts: int = 3,
        effort: str | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.claude_path = claude_path
        self.model = model
        # When set, one JSON line of token/cost usage is appended per spawn so a long
        # unattended run can be tallied (scripts/run_stats.py) without re-parsing logs.
        self.usage_log_path = Path(usage_log_path) if usage_log_path is not None else None
        # Transient transport failures (non-zero exit / timeout that is NOT a usage
        # cap) are retried with exponential backoff up to this many total attempts;
        # a usage cap is never retried (it is raised immediately to abort the run).
        self.max_attempts = max(1, max_attempts)
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
        self.effort = effort

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
        if self.effort is not None:
            cmd += ["--effort", self.effort]
        cmd += self.extra_args
        return cmd

    def _run(self, prompt: str) -> str:
        """Spawn `claude -p`, returning stdout. Usage caps raise RateLimitError
        immediately; transient transport failures are retried then raise
        BackendTransportError. Both are re-raised by the orchestrator (not queued)."""
        transport: BackendTransportError | None = None
        for attempt in range(self.max_attempts):
            try:
                proc = subprocess.run(
                    self._build_cmd(),
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=Path.home(),  # run outside the repo so CLAUDE.md isn't found
                )
            except subprocess.TimeoutExpired:
                transport = BackendTransportError(f"claude timed out after {self.timeout}s")
                self._backoff(attempt)
                continue
            # Only classify a usage cap when there is a genuine error signal — a
            # non-zero exit, or a returncode-0 envelope explicitly flagged is_error.
            # A clean, successful spawn is NEVER scanned: its telemetry (session_id,
            # duration_ms) and the agent's own conversion text can innocently contain
            # a marker substring (a number with "429", the word "reset"), which used
            # to abort a healthy run with a phantom rate limit.
            error_text = _error_text(proc)
            if error_text is None:
                return proc.stdout
            rate = _classify_rate_limit(error_text)
            if rate is not None:
                raise rate
            transport = BackendTransportError(
                f"claude exited {proc.returncode}: "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
            self._backoff(attempt)
            continue
        assert transport is not None  # loop ran at least once and never returned
        raise transport

    def _backoff(self, attempt: int) -> None:
        """Sleep before a retry; no-op after the final attempt."""
        if attempt + 1 < self.max_attempts:
            delay = 2.0 ** attempt
            logger.warning("transient claude failure — retrying in %.0fs", delay)
            time.sleep(delay)

    def convert_event(
        self,
        event_json: dict,
        registry_state: dict,
        prompt: str,
    ) -> ConversionResult:
        raw = self._run(prompt)
        if self.usage_log_path is not None:
            self._record_usage(raw)
        return _parse_response(raw)

    def _record_usage(self, raw: str) -> None:
        """Append one JSON line of this spawn's token/cost usage to usage_log_path."""
        try:
            envelope = json.loads(raw.strip())
        except json.JSONDecodeError:
            return
        if not isinstance(envelope, dict):
            return
        usage = envelope.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        line = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "model": self.model,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
            "cost_usd": envelope.get("total_cost_usd"),
        }
        try:
            self.usage_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.usage_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line) + "\n")
        except OSError:
            logger.warning("could not append usage log %s", self.usage_log_path)


def _parse_response(raw: str) -> ConversionResult:
    """Unwrap the `claude -p` JSON envelope, then parse the agent's structured object."""
    text = raw.strip()
    # Unwrap the CLI envelope if present; otherwise treat stdout as the object.
    try:
        envelope = json.loads(text)
        if isinstance(envelope, dict) and "result" in envelope:
            _log_cache_usage(envelope)  # dedup Phase B: confirm the system prompt caches
            text = envelope["result"]
        elif isinstance(envelope, dict) and "script" in envelope:
            return _to_result(envelope)
    except json.JSONDecodeError:
        pass
    return _to_result(_extract_object(text))


def _log_cache_usage(envelope: dict) -> None:
    """Log the `claude -p` token usage so we can confirm prompt caching engages.

    The static context now rides in the system prompt (dedup Phase B); back-to-back
    spawns should report a non-zero `cache_read_input_tokens` once the cache is warm
    (5-min TTL). If it stays zero, the restructure is still correct + harmless — the
    numbers just tell us whether the cache saved spend. No-op when usage is absent."""
    usage = envelope.get("usage")
    if not isinstance(usage, dict):
        return
    logger.info(
        "claude usage: input=%s cache_read=%s cache_creation=%s output=%s cost_usd=%s",
        usage.get("input_tokens"),
        usage.get("cache_read_input_tokens"),
        usage.get("cache_creation_input_tokens"),
        usage.get("output_tokens"),
        envelope.get("total_cost_usd"),
    )


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
