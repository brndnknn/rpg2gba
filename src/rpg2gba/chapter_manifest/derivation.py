"""Pure derivation of one row's machine verdict -- the logic shared by the
sidecar writer (`generator.write_derived`) and the checker's own recheck
(`checker.check_chapter`'s per-row loop).

No file I/O lives here on purpose: `generate` and `check` each have their own
reasons to call `derive_entry` (writing the sidecar vs. never trusting it),
and keeping the derivation itself pure and side-effect-free is what lets the
checker recompute it independently rather than trusting whatever the
generator wrote earlier (CLAUDE.md §4.5 -- never trust a stored claim's mere
presence).

Operator ruling (2026-09-14): the generator derives FOUR verdicts (three
more generator-sourced heads since 2026-10-04, see below).
`cosmetic`, `beat:`, `boundary` are CLERICAL -- accepted on `derived_hash`
alone, no human affirmation. `blocked:` is derived only as a PROPOSAL -- it
never dispositions a row until a human copies it into the dispositions file
with an `affirmed_hash` (`DerivedEntry.proposed`).

Precedence is `boundary > beat > blocked > cosmetic`
(`REDERIVATION_PLAN.md` §14.4), matching `ManifestRow.may_be_derived`'s own
docstring.

2026-10-04 (PROJECT_TODO #124, operator ruling "emit + derive"): a FIFTH,
lowest-precedence source -- the beat generator's own per-row status record
(`generator_status.GeneratorStatus`, read from the generated module's
`ELSEWHERE`/`REFUSED`/`NEVER_FIRES`/`EMPTY_PAGES`). It derives
`elsewhere:<status>...`, `refused:<blocker>...` or `unreachable:<reason>`,
all CLERICAL. Lowest, not between beat and blocked, on purpose: it only
fills rows that derived None before, so every pre-existing sidecar entry is
left byte-identical (no churn), and the generator's record never overrides a
verdict the manifest itself supports.

CORRECTION (operator ruling 2026-10-15, "owned rows outrank cosmetic"): the
paragraph above is true of every generator record EXCEPT an `elsewhere:`
record whose reason starts with `later:` (another, earlier chapter owns the
row, e.g. `elsewhere:later: CH01`). That one record is consulted BEFORE
rule 5's `cosmetic` and wins over it: a revisit chapter's retalk page of a
trainer beaten earlier would otherwise derive `cosmetic` and fail the
checker's `archetype_conformance` (a trainer page prescribes a beat;
`elsewhere:` satisfies that, `cosmetic` does not). Narrow on purpose --
`refused:`, `unreachable:` and every other `elsewhere:` stay lowest. This
does change a pre-existing `cosmetic` entry to `elsewhere:later:` where
both apply.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .schema import Disposition, DispositionError, ManifestRow, parse_blocked_argument

if TYPE_CHECKING:
    # Protocols only -- this module never imports `checker` at runtime, same
    # discipline `checker.py` itself uses for `rpg2gba.playtest` et al.: a
    # `Protocol` is the seam, not a hard dependency.
    from .checker import BeatModel, BoundaryModel
    from .generator_status import GeneratorStatus


@dataclass(frozen=True)
class DerivedEntry:
    """One machine-derived verdict for one row -- the sidecar's unit.

    `derived_hash` is always the row's `content_hash` at derivation time
    (mirrors a hand disposition's `affirmed_hash`, but a derived entry can
    never carry `source`, `note`, or any of the other hand-authored fields --
    `is_dispositionable`/`needs_citation` are checked before any verdict is
    derived at all, precisely so a derived entry never needs to express
    them).

    `proposed` is True only for a `blocked:` verdict: it names a candidate
    disposition, not an accepted one. Never True for `cosmetic`/`beat:`/
    `boundary` -- those are clerical and self-affirming.
    """

    disposition: str
    derived_hash: str
    proposed: bool = False

    def to_disposition(self, row_id: str) -> Disposition:
        """The `Disposition` this entry stands for, for the given row.

        Only meaningful for a CLERICAL entry (`proposed=False`) -- a
        checker/generator that calls this on a proposal is asserting the row
        is dispositioned when the whole point of `proposed` is that it is
        not; callers are responsible for gating on `proposed` first."""
        return Disposition.parse(row_id, self.disposition)


def _beat_family_head(beat_id: str) -> str:
    """The prefix-family reduction `beat_model.py`'s `_matches` uses, in
    reverse: the text before the first `_`, e.g. `B4_battle` -> `B4`. A beat
    id with no `_` at all reduces to itself.
    """
    head, _, _ = beat_id.partition("_")
    return head


def derive_entry(
    row: ManifestRow,
    *,
    beat_model: "BeatModel | None",
    boundary_model: "BoundaryModel | None",
    generator_status: "GeneratorStatus | None" = None,
    hand_dispositions: Mapping[str, Disposition] | None = None,
) -> DerivedEntry | None:
    """The machine verdict for `row`, or None if nothing can be derived and a
    human must decide.

    Rules, in precedence order (`boundary > beat > blocked > cosmetic`):

    1. `not row.is_dispositionable or row.needs_citation` -> only the
       GENERATOR's verdict (its beat claim, or its ELSEWHERE/REFUSED record)
       stands in for the human classification/citation; otherwise None
       (`_generator_cited_entry`, operator ruling 2026-10-04, #124).
    2. `boundary_model.is_forward_crossing(row.row_id)` -> `"boundary"`.
    3. `beat_model.claiming_beats(row.row_id)` non-empty -> reduce every
       claim to its family head (`_beat_family_head`); if all claims share
       one head, `"beat:<head>"`. If they span more than one head, the claim
       set is ambiguous and this returns None (a human decision, not a
       derivation bug).
    4. `row.requires` non-empty -> `"blocked:<a>+<b>+..."`, PROPOSED. Every
       entry in `row.requires` is required simultaneously (AND), never an
       alternative -- see the module-level note on `_HEAD_REQUIRES`/
       `_reachability_requires` in `generator.py`: `requires` is a
       `set.union` of two AND-only sources (per-head capability names, and
       the single cheapest minimal capability SET
       `derive_blocked_verdict_for_event_from_starts` returns), and any
       independent alternative sets that source found are explicitly
       dropped before reaching `ManifestRow.requires` (the alternatives
       survive only in the disposition layer, per that function's own
       comment) -- so nothing about `requires`'s shape can ever encode an
       OR. The `blocked:` grammar's `+` (AND) is therefore the only
       operator this derivation ever needs; `|` (OR) has no source data to
       come from here. EXCEPTION (operator ruling 2026-10-04, #124): on a
       BRANCH-ARM row (`.../bN`) whose parent page row carries a HAND
       disposition with verdict `blocked` and a parsed argument equal to this
       row's spec, the entry is CLERICAL (`proposed=False`) -- arms exist only
       because C1 split a page the human already decided. Narrow carve-out of
       the "a `blocked:` proposal is never accepted without a human" rule;
       every other `blocked:` stays a proposal. `hand_dispositions` supplies
       the parent lookup (None -> no carve-out).
    5. `row.may_be_derived` -> `"cosmetic"`, CLERICAL. (Already implies
       `requires` is empty and no citation is owed -- rule 4 above returns
       before this is ever reached when `requires` is non-empty.) EXCEPTION
       (operator ruling 2026-10-15, "owned rows outrank cosmetic"): if the
       generator's record for the row is an `elsewhere:` spec whose reason
       starts with `later:` (an earlier chapter owns the row), that record
       wins over `cosmetic` -- see the module docstring.
    6. `generator_status.spec_for(row.row_id)` -> that spec
       (`elsewhere:`/`refused:`/`unreachable:`), CLERICAL. Otherwise reached
       only when rules 2-5 derive nothing, so it adds entries and does not
       change one; the sole exception is the `elsewhere:later:` record
       moved above rule 5 (2026-10-15, operator).
       Not reached for rule 1 (a human must still classify/cite) or for an
       ambiguous multi-family beat claim (rule 3 returns None outright).
    7. Otherwise None.

    `derived_hash` is always `row.content_hash`.
    """
    if not row.is_dispositionable or row.needs_citation:
        return _generator_cited_entry(row, beat_model=beat_model,
                                      generator_status=generator_status)

    if boundary_model is not None and boundary_model.is_forward_crossing(row.row_id):
        return DerivedEntry(disposition="boundary", derived_hash=row.content_hash)

    claims = beat_model.claiming_beats(row.row_id) if beat_model is not None else ()
    if claims:
        heads = {_beat_family_head(claim) for claim in claims}
        if len(heads) == 1:
            head = next(iter(heads))
            return DerivedEntry(disposition=f"beat:{head}", derived_hash=row.content_hash)
        return None

    if row.requires:
        argument = "+".join(sorted(set(row.requires)))
        spec = f"blocked:{argument}"
        # Validates the grammar (and, as a side effect, that `requires`
        # contains only valid capability tokens) -- fails loud rather than
        # writing a spec the dispositions loader would later reject.
        Disposition.parse(row.row_id, spec)
        clerical = _parent_hand_blocked_matches(row.row_id, argument, hand_dispositions)
        return DerivedEntry(disposition=spec, derived_hash=row.content_hash,
                            proposed=not clerical)

    spec = generator_status.spec_for(row.row_id) if generator_status is not None else None

    if row.may_be_derived:
        if spec is not None and _is_owned_elsewhere(spec):
            return DerivedEntry(disposition=spec, derived_hash=row.content_hash)
        return DerivedEntry(disposition="cosmetic", derived_hash=row.content_hash)

    if spec is not None:
        return DerivedEntry(disposition=spec, derived_hash=row.content_hash)

    return None


def _is_owned_elsewhere(spec: str) -> bool:
    """True for an `elsewhere:later:...` spec -- another, earlier chapter owns
    the row (operator ruling 2026-10-15). Tolerates whitespace after the
    colons (`elsewhere:later: CH01`)."""
    head, _, rest = spec.partition(":")
    return head == "elsewhere" and rest.lstrip().startswith("later:")


_ARM_SUFFIX = re.compile(r"^(?P<parent>.+)/b\d+$")


def _parent_hand_blocked_matches(
    row_id: str,
    argument: str,
    hand_dispositions: Mapping[str, Disposition] | None,
) -> bool:
    """True iff `row_id` is a branch arm and its parent page row has a hand
    `blocked` disposition whose parsed argument equals `argument` (compared as
    alternative-sets, not text)."""
    if not hand_dispositions:
        return False
    m = _ARM_SUFFIX.match(row_id)
    if m is None:
        return False
    parent = hand_dispositions.get(m.group("parent"))
    if parent is None or parent.verdict != "blocked" or not parent.argument:
        return False
    try:
        return (frozenset(parse_blocked_argument(parent.argument))
                == frozenset(parse_blocked_argument(argument)))
    except DispositionError:
        return False  # e.g. `tooling:` form: never a capability set


def _generator_cited_entry(
    row: ManifestRow,
    *,
    beat_model: "BeatModel | None",
    generator_status: "GeneratorStatus | None",
) -> DerivedEntry | None:
    """Rule 1's one way through: the GENERATOR's verdict on a row that owes a
    human citation (unrecognized head, unclassified condition).

    Operator ruling 2026-10-04 (PROJECT_TODO #124): when the generated module
    claims such a row, or records it in ELSEWHERE/REFUSED, that verdict is
    the citation -- the generator decided it from the row's RMXP source (its
    floor, R11), or refused it under a named blocker. Only those two sources
    count: `boundary`/`blocked:`/`cosmetic` are read off manifest structure,
    which is exactly what this row's structure fails to determine, so a row
    the generator says nothing about still returns None for a human. The
    checker relies on this: a derived entry on a citation-owing row can only
    have come from here (`checker._check_row_verdict_rules(generator_cited=)`).
    """
    claims = beat_model.claiming_beats(row.row_id) if beat_model is not None else ()
    if claims:
        heads = {_beat_family_head(claim) for claim in claims}
        if len(heads) != 1:
            return None
        return DerivedEntry(disposition=f"beat:{next(iter(heads))}",
                            derived_hash=row.content_hash)
    spec = generator_status.spec_for(row.row_id) if generator_status is not None else None
    if spec is not None:
        return DerivedEntry(disposition=spec, derived_hash=row.content_hash)
    return None
