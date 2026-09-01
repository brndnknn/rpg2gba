"""The enforced frame rule (Q7, DECIDED 2026-08-27 in
`PLAYTEST_AUTHORING_IMPROVEMENT_V2.md`).

CH04 produced two confidently-wrong write-ups in one day, both negative
claims -- "nothing runs", "the object is not rendered" -- and both were
eventually corrected by the operator hand-walking the ROM to capture the
one frame that would have refuted them immediately. A written rule ("attach
a frame to negative claims") was considered and rejected: it is exactly the
kind of fix that depends on someone remembering, and both wrong write-ups
happened *despite* the author knowing better in the abstract. So the rule is
enforced by the runner instead -- a beat that fails with a negative claim
and never called `emu.mark_frame()` has its failure refused, not recorded.

This module is the pure classification half only. It decides whether a
beat's failure *message* reads as a negative claim, and whether that claim
is backed by a captured frame. It imports nothing from `emulator.py` and
does no I/O; the runner (`runner.py`) is the one that knows what
`frames_marked` and `screenshots_enabled` actually mean for a live attempt,
and it is the one that raises `FrameRuleError` when this module says to.

Known limitation, stated up front: classifying prose failure messages with
regexes is inherently approximate. A harness at hundreds of `ScenarioError`
call sites will keep growing wording this module has never seen. The list
below is therefore deliberately conservative -- it is tuned to miss a
negative claim (a false negative just means an author isn't asked for a
frame they'd have wanted anyway) rather than to misfire on an unrelated,
positive failure ("the wrong trainer was fought", "expected 3, got 5"),
which would force an author to bolt on a `mark_frame()` call that has
nothing to do with their actual bug. The escape hatch in both directions is
the same: any author can satisfy the rule for any beat by adding one
`emu.mark_frame()` call at the moment the claim is about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class _Pattern:
    """One negative-claim shape: a compiled regex plus the class it names."""

    label: str
    regex: re.Pattern[str]


def _pat(label: str, *phrases: str) -> _Pattern:
    """Build a case-insensitive, word-boundary-anchored regex over `phrases`.

    Word-boundary anchoring matters here specifically because the corpus
    is prose written by many chapter authors: without `\\b`, the substring
    "nothing" would match inside an unrelated word, and a literal space in
    a phrase like "no script" would happily match across punctuation it
    shouldn't. `re.escape` keeps phrases like "yes/no" literal.
    """
    alternation = "|".join(re.escape(p) for p in phrases)
    return _Pattern(label, re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE))


# Ordered tuple: first match wins. Order only matters when two patterns could
# both match the same text (e.g. "never fired" also containing "fired"); each
# phrase below is written to be class-distinct, so ordering is mostly cosmetic
# but is kept stable (roughly the order Q7's own examples were listed in) so
# `classify_claim`'s output for an ambiguous message doesn't depend on set
# iteration order.
NEGATIVE_CLAIM_PATTERNS: tuple[_Pattern, ...] = (
    _pat(
        "nothing-happened",
        "nothing runs", "nothing happened", "nothing fired",
    ),
    _pat(
        "script-did-not-start",
        # The doc's own wording ("no script started") plus the two shapes
        # the harness actually raises for this class -- `interact()` and
        # the mart-counter beats say "did not start/open a script", not
        # "script did not start" (emulator.py:2503, chapters/ch03.py).
        "no script started", "script did not start", "never started",
        "did not start a script", "did not open a script",
    ),
    _pat(
        "not-rendered",
        "not rendered", "is not rendered", "was not drawn", "not drawn",
    ),
    _pat(
        "did-not-fire",
        "did not fire", "never fired", "does not fire",
    ),
    _pat(
        "did-not-appear",
        "did not appear", "never appeared", "no object",
    ),
    _pat(
        "no-text",
        "no text", "no message", "no dialogue", "no dialog",
    ),
    _pat(
        "did-not-move",
        "did not move", "never moved",
    ),
    _pat(
        "not-present",
        "was not present", "not present", "absent",
    ),
)


@dataclass(frozen=True)
class ClaimVerdict:
    """The result of classifying one failure message.

    `negative=False` carries an empty `label` and `matched` -- there is
    nothing to report, and leaving them empty (rather than `None`) keeps
    `to_dict()` trivially JSON-serialisable without a null-handling case.
    """

    negative: bool
    label: str
    matched: str

    def to_dict(self) -> dict[str, bool | str]:
        return {"negative": self.negative, "label": self.label, "matched": self.matched}


_NOT_NEGATIVE = ClaimVerdict(negative=False, label="", matched="")


def classify_claim(text: str | None) -> ClaimVerdict:
    """Classify a beat failure message as a negative claim or not.

    A `None` or blank/whitespace-only message is not a claim at all -- there
    is nothing here to doubt, so it is not negative. This matters because
    `check_frame_rule` is meant to gate on what the failure *says*, not to
    invent a claim where the caller supplied none.
    """
    if text is None or not text.strip():
        return _NOT_NEGATIVE
    for pattern in NEGATIVE_CLAIM_PATTERNS:
        match = pattern.regex.search(text)
        if match:
            return ClaimVerdict(negative=True, label=pattern.label, matched=match.group(0))
    return _NOT_NEGATIVE


@dataclass(frozen=True)
class FrameRuleResult:
    """The outcome of checking one beat failure against the frame rule."""

    enforced: bool
    refused: bool
    verdict: ClaimVerdict
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "enforced": self.enforced,
            "refused": self.refused,
            "verdict": self.verdict.to_dict(),
            "reason": self.reason,
        }


def check_frame_rule(claim: str | None, *, frames_marked: int,
                      screenshots_enabled: bool) -> FrameRuleResult:
    """Decide whether a beat failure with message `claim` may be recorded.

    `screenshots_enabled=False` is an explicit, stated skip -- a headless or
    unit-test run that captures no frames at all cannot possibly satisfy the
    rule, and refusing every negative-claim failure in that mode would just
    make such runs unusable rather than enforcing anything. This is a
    deliberate carve-out, not the rule silently failing to apply; the
    `reason` says so.

    Otherwise:
      - a non-negative claim is always allowed (`refused=False`) -- the rule
        has nothing to say about a positive failure like a wrong coordinate.
      - a negative claim backed by at least one marked frame is allowed.
      - a negative claim with zero marked frames is refused, with a `reason`
        that names the offending substring, its class label, and the exact
        remedy: call `emu.mark_frame()` at the instant the claim is about,
        inside that beat.
    """
    if not screenshots_enabled:
        return FrameRuleResult(
            enforced=False,
            refused=False,
            verdict=_NOT_NEGATIVE,
            reason=(
                "frame rule not enforced: this run has screenshots disabled "
                "(no frames are ever captured), so the rule cannot be "
                "checked -- this is an explicit skip for headless/unit-test "
                "runs, not a silent one"
            ),
        )

    verdict = classify_claim(claim)

    if not verdict.negative:
        return FrameRuleResult(
            enforced=True,
            refused=False,
            verdict=verdict,
            reason="claim is not a negative claim; frame rule does not apply",
        )

    if frames_marked > 0:
        return FrameRuleResult(
            enforced=True,
            refused=False,
            verdict=verdict,
            reason=(
                f"negative claim ({verdict.label}: {verdict.matched!r}) is "
                f"backed by {frames_marked} marked frame(s)"
            ),
        )

    return FrameRuleResult(
        enforced=True,
        refused=True,
        verdict=verdict,
        reason=(
            f"refused: negative claim {verdict.matched!r} (class "
            f"{verdict.label!r}) has no marked frame to back it. Call "
            f"emu.mark_frame() at the instant this claim is about, inside "
            f"the failing beat, before raising the failure"
        ),
    )


class FrameRuleError(RuntimeError):
    """Raised by the runner (never by this module) when a beat's negative
    failure claim is refused for lack of a marked frame.

    `frame_rule.py` only classifies and decides; it is the runner's job to
    turn a refused `FrameRuleResult` into a raised error at the point it
    would otherwise have recorded the beat's failure. Kept as a distinct
    exception type (not a plain `ScenarioError`) so the runner and any
    caller can tell "the beat's own assertion failed" from "the beat's
    failure was refused for missing evidence" -- the two need different
    triage: the first is a bug in the game or the assertion, the second is a
    missing `mark_frame()` call in the test itself.
    """

    def __init__(self, beat: str, claim: str, verdict: ClaimVerdict) -> None:
        self.beat = beat
        self.claim = claim
        self.verdict = verdict
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"{self.beat}: refused to record failure {self.claim!r} -- "
            f"this is a negative claim (class {self.verdict.label!r}, "
            f"matched {self.verdict.matched!r}) with no marked frame behind "
            f"it. Add emu.mark_frame() at the instant this claim is about, "
            f"inside {self.beat}, then re-run."
        )


def refusal_error(beat: str, claim: str, result: FrameRuleResult) -> FrameRuleError:
    """Build the `FrameRuleError` for a refused `FrameRuleResult`.

    A thin factory rather than inlining `FrameRuleError(...)` at every call
    site in the runner -- it keeps the "what goes into the error" decision
    in one place, next to the rest of the frame-rule logic, instead of
    duplicated at each raise point.
    """
    return FrameRuleError(beat, claim, result.verdict)
