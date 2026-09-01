"""Versioned playtest assertion rule sets (Q7.3 / finding F/H).

A *rule* is a manifest-shaped assertion class ("every row tagged `warp` owes
a facing assertion") that a chapter's beats are expected to satisfy. Rules
are invented mid-corpus -- warp-arrival facing was invented inside
`ch03.py` while `ch01.py`/`ch02.py` were never marked stale (finding F).
Waivers were rejected as a design (they rot); this module implements the
alternative that was decided instead: **monotonic, versioned rule sets**.

The rule set itself (`RULES`, `CURRENT_VERSION`) is small, reviewed,
version-controlled data -- not a database. Adding a rule is a code change:
append a `Rule` below and bump `CURRENT_VERSION` by exactly one. A rule's
*ordinal position* in `RULES` (1-indexed) is its version number, so "rules
as of version N" is just `RULES[:N]` -- no separate version field to keep in
sync.

**What this module does NOT do**: it does not enforce rules against a
running chapter. No manifest-driven rule checker exists yet (Part 6/§9 of
`PLAYTEST_AUTHORING_IMPROVEMENT.md` -- the manifest generator itself doesn't
exist). This module gives the runner (`runner.py`) two things it needs
today:

1. `effective_rule_version` -- the mechanical detail Q7.3 calls "critical":
   when `ChapterBuilder` chains a predecessor's beats into a replay (see
   `chapter.py:115-124`, beats renamed `<owner>:<name>`), each replayed
   ancestor beat must be evaluated at *its own chapter's* last recorded
   green version, never the running chapter's -- otherwise adding one rule
   would turn every descendant chapter's gate red at once, the exact
   "halts the frontier" failure versioning exists to prevent.
2. `lag_report` -- a report generated from recorded versions, never
   hand-maintained, so it cannot drift (the failure mode of a hand-kept
   ledger, per Q7.2).

Recorded per-chapter versions are persisted as small, git-tracked JSON under
`reference/` (`DEFAULT_RECORDED_VERSIONS_PATH`). **The runner is the only
writer** (`runner.record_chapter_version` call in `run_chapter`) -- this
file is generated bookkeeping, not something to hand-edit, same rule as
every other "one source of truth" table in CLAUDE.md §4.3.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_RECORDED_VERSIONS_PATH = Path("reference/playtest_rule_versions.json")


@dataclass(frozen=True)
class Rule:
    """One versioned assertion class.

    `tag` is the manifest effect tag this rule binds to (Q1/Q2's future
    per-row effect tags, e.g. `warp`, `text`) -- once a manifest generator
    exists, a row carrying that tag owes the assertion described here.
    `primitive_exists` records honestly when the runtime primitive the
    assertion needs has not landed yet (Q7.3's "record honestly" clause) --
    false for text-content, which another agent is building concurrently;
    this module must not depend on it existing.
    """

    id: str
    tag: str
    assertion: str
    added: str  # ISO date
    reason: str
    primitive_exists: bool = True


# Ordinal position (1-indexed) IS the version number -- rule N is "live"
# starting at CURRENT_VERSION >= N. Append, never reorder or remove; a
# retired rule is not something this corpus needs yet.
RULES: tuple[Rule, ...] = (
    Rule(
        id="warp-arrival-facing",
        tag="warp",
        assertion=(
            "destination map, destination coords, and arrival facing are "
            "all asserted on every row tagged `warp`"
        ),
        added="2026-08-19",
        reason=(
            "CH03 #22: compute_arrival_facings silently skipped dest_dir==0 "
            "since 2026-07-16, undetected through two chapter gates because "
            "nothing marked CH01/CH02 stale when the assertion was invented "
            "(finding F)."
        ),
    ),
    Rule(
        id="text-content",
        tag="text",
        assertion=(
            "dialogue text content is asserted (not merely 'is text "
            "drawing') on every row tagged `text`"
        ),
        added="2026-08-20",
        reason=(
            "finding G: the harness has no text-content assertion "
            "primitive today, only text-is-drawing. The primitive does not "
            "exist yet -- it is being built concurrently by another agent; "
            "this rule is seeded now so the class is registered the moment "
            "the primitive lands, per Q7.1 (promoting a helper into the "
            "framework is the birth of a defect class)."
        ),
        primitive_exists=False,
    ),
)

CURRENT_VERSION = len(RULES)


def rules_as_of(version: int) -> tuple[Rule, ...]:
    """The rules live at `version` (1-indexed, ordinal position in RULES).
    `0` means no rules -- the pre-versioning baseline every already-gated
    chapter honestly starts at, since no rule was ever mechanically
    enforced before this module existed."""
    if version < 0 or version > len(RULES):
        raise ValueError(
            f"rule-set version {version} out of range 0..{len(RULES)} "
            f"(CURRENT_VERSION={CURRENT_VERSION})")
    return RULES[:version]


# -- ancestor version pinning (Q7.3's "critical mechanical detail") ---------

def owning_chapter(chapter: str, beat_name: str) -> str:
    """Recover the chapter that owns `beat_name` within a (possibly
    predecessor-chained) beat list.

    `ChapterBuilder._prefix_beat` (chapter.py:115-124) renames a
    predecessor's beats `<owner>:<name>`, and leaves an already-prefixed
    name untouched rather than layering a second prefix -- so the text
    before the first `:` is always the beat's true origin chapter,
    regardless of how many predecessors deep it arrived through. A bare
    name (no `:`) belongs to `chapter` itself.
    """
    if ":" in beat_name:
        return beat_name.split(":", 1)[0]
    return chapter


def effective_rule_version(chapter: str, beat_name: str, running_version: int,
                            recorded_versions: dict[str, int]) -> int:
    """The rule-set version `beat_name` should be evaluated under while
    gating `chapter`.

    A beat that belongs to `chapter` itself is evaluated at
    `running_version` (the version this run is attempting to pass under --
    normally `CURRENT_VERSION`). A beat that arrived via predecessor
    chaining is pinned to *its own* chapter's last recorded green version,
    never `running_version` -- this is the mechanical detail that keeps
    adding one rule from turning every descendant chapter's gate red at
    once (Q7.3).

    Fails loud if the owning ancestor chapter has never recorded a version
    at all (`recorded_versions` has no entry for it): that means the
    ancestor has never been gated green under this scheme, which is a
    corpus-ordering problem to fix, not something to paper over with a
    silent default.
    """
    owner = owning_chapter(chapter, beat_name)
    if owner == chapter:
        return running_version
    if owner not in recorded_versions:
        raise ValueError(
            f"beat {beat_name!r} in chapter {chapter!r} is owned by "
            f"ancestor chapter {owner!r}, which has no recorded rule-set "
            f"version -- gate {owner!r} green at least once before gating "
            f"{chapter!r}")
    return recorded_versions[owner]


# -- recorded versions (persisted; runner-only writer) -----------------------

def load_recorded_versions(
        path: Path = DEFAULT_RECORDED_VERSIONS_PATH) -> dict[str, int]:
    """Every chapter's last-recorded green rule-set version. Missing file
    means nothing has ever recorded a version yet -- an empty dict, not an
    error, since a fresh checkout legitimately starts here."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def record_chapter_version(path: Path, chapter: str, version: int) -> None:
    """Persist `chapter`'s newly-passed rule-set version.

    Callers: `runner.run_chapter`, and only `runner.run_chapter` -- a
    chapter's recorded version advances by re-running it green under newer
    rules, never by hand-editing this file (Q7.3). This function itself
    does not gate that policy; it is a plain read-merge-write, same shape
    as `flag_registry`'s persisted state -- the caller is what must not be
    duplicated.
    """
    versions = load_recorded_versions(path)
    versions[chapter] = version
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(versions, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# -- lag report (Q7.3's ledger, generated, not maintained) -------------------

@dataclass(frozen=True)
class LagReport:
    chapter: str
    recorded_version: int
    current_version: int
    lagging: tuple[Rule, ...]

    def render(self) -> str:
        if not self.lagging:
            return (f"{self.chapter} passed at rules v{self.recorded_version}; "
                     f"current is v{self.current_version}; up to date")
        names = ", ".join(
            f"{rule.id} (v{RULES.index(rule) + 1})" for rule in self.lagging)
        return (f"{self.chapter} passed at rules v{self.recorded_version}; "
                f"current is v{self.current_version}; {self.chapter} lags "
                f"{names}")


def lag_report(chapter: str, recorded_version: int,
                current_version: int = CURRENT_VERSION) -> LagReport:
    """The rules `chapter` has not yet been re-verified against, generated
    from its recorded version and the live rule set -- this *is* Q7's
    ledger; nobody writes it by hand, so it cannot drift."""
    lagging = rules_as_of(current_version)[recorded_version:]
    return LagReport(chapter=chapter, recorded_version=recorded_version,
                      current_version=current_version, lagging=lagging)


def lag_reports(path: Path = DEFAULT_RECORDED_VERSIONS_PATH,
                 current_version: int = CURRENT_VERSION) -> list[LagReport]:
    """`lag_report` for every chapter that has ever recorded a version,
    sorted by chapter name."""
    versions = load_recorded_versions(path)
    return [lag_report(chapter, version, current_version)
            for chapter, version in sorted(versions.items())]
