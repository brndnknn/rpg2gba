"""Backend abstraction for the conversion agent's LLM provider.

The orchestrator calls convert_event() on whichever backend is configured.

  ClaudeCodeBackend — PRODUCTION: headless `claude -p` per event on the frozen
                      bulk-run model (Pro subscription, no API key)
  OllamaBackend     — optional local fallback; rejected for production
                      (silent-wrong risk — see ROADMAP Phase 4 strategy)

Wrappers (compose around either):

  CappingBackend    — bound a run to N spawns (`run_bulk.py --limit`)
  NullBackend       — spend-nothing guard for maintenance replays
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ConversionResult:
    """One event's conversion output — mirrors prompts/system.md's JSON schema.

    new_flags / new_vars are lists of proposals the orchestrator feeds to the
    flag registry, each `{switch_id|var_id, name, reason}`. unhandled is a list of
    `{command_code, description, event_id, page, line}`. Lists (not dicts) so the
    agent's `reason` survives for logging + the unhandled-queue triage.
    """

    script: str
    new_flags: list[dict] = field(default_factory=list)
    new_vars: list[dict] = field(default_factory=list)
    unhandled: list[dict] = field(default_factory=list)


class RateLimitError(Exception):
    """The provider refused the request because a usage cap was hit.

    Distinct from a conversion failure: the *event* is fine — we simply cannot spend
    right now. The orchestrator must NOT queue the event (that would record good work
    as a permanent failure); it re-raises so the bulk runner can pause or stop.
    ``weekly`` distinguishes the long weekly cap (the runner treats it as a hard
    stop) from the rolling 5-hour window (the runner waits it out and resumes).
    ``reset_hint`` carries any human-readable reset time the provider mentioned.
    """

    def __init__(
        self, message: str, *, weekly: bool = False, reset_hint: str | None = None
    ) -> None:
        super().__init__(message)
        self.weekly = weekly
        self.reset_hint = reset_hint


class BackendTransportError(Exception):
    """A non-usage infrastructure failure (non-zero exit, timeout, network) that
    survived the backend's own retries. Re-raised rather than queued — the event is
    convertible, the transport just failed — so the run aborts cleanly and resumes
    on restart instead of poisoning the queue with spurious 'backend error' rows."""


class BudgetReached(Exception):
    """The run hit its self-imposed ``--limit`` on backend spawns for this invocation.

    Like RateLimitError, the *event* is fine — we simply chose to stop spending after
    N conversions. Re-raised (not queued) so the run aborts cleanly, checkpoints hold,
    and the next invocation resumes from where this one stopped. ``limit`` is the cap
    that was reached, for the runner's exit summary."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"reached --limit of {limit} LLM conversion(s) this run")
        self.limit = limit


class ConversionBackend(ABC):
    @abstractmethod
    def convert_event(
        self,
        event_json: dict,
        registry_state: dict,
        prompt: str,
    ) -> ConversionResult:
        raise NotImplementedError


class CappingBackend(ConversionBackend):
    """Wraps a backend, raising BudgetReached before the ``(limit+1)``-th convert_event.

    Lets a bulk run be bounded to N LLM spawns for cheap, controlled, resumable rounds
    ("run it once / five / any number"). Only real backend calls count: deterministic
    pre-filter matches and memo reuse never reach the backend, so free progress keeps
    flowing and only paid conversions are rationed. A retry (a second convert_event for
    one event) counts as its own spawn, since it costs budget. Delegates ``system_prompt``
    so the orchestrator's memo fingerprint is unaffected by the wrapper."""

    def __init__(self, inner: ConversionBackend, limit: int) -> None:
        if limit < 1:
            raise ValueError(f"--limit must be >= 1, got {limit}")
        self.inner = inner
        self.limit = limit
        self.count = 0

    @property
    def system_prompt(self) -> str:
        return getattr(self.inner, "system_prompt", "")

    def convert_event(
        self,
        event_json: dict,
        registry_state: dict,
        prompt: str,
    ) -> ConversionResult:
        if self.count >= self.limit:
            raise BudgetReached(self.limit)
        self.count += 1
        return self.inner.convert_event(event_json, registry_state, prompt)


class NullBackend(ConversionBackend):
    """A spend-nothing guard for maintenance replays (`scripts/regen_outputs.py`).

    Wraps the production backend ONLY for its ``system_prompt`` — the memo manifest
    is fingerprinted by it, so a replay must look identical to the real run or every
    entry would be discarded as cross-prompt reuse. Any actual ``convert_event`` call
    means the replay needed a real spawn; raise ``BudgetReached`` so the run aborts
    cleanly (fail loud) instead of spending."""

    def __init__(self, inner: ConversionBackend) -> None:
        self.inner = inner

    @property
    def system_prompt(self) -> str:
        return getattr(self.inner, "system_prompt", "")

    def convert_event(
        self,
        event_json: dict,
        registry_state: dict,
        prompt: str,
    ) -> ConversionResult:
        raise BudgetReached(0)
