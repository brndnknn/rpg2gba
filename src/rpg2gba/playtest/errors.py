"""Shared exception, import-safe without the mGBA bindings installed."""


class ScenarioError(RuntimeError):
    """A scenario step failed; a diagnostic screenshot may accompany it."""
