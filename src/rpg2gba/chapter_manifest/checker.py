"""The rules that fail a chapter's manifest (Q1, Q6, Q8.2, Q11).

`check_chapter` joins the generated rows against the authored dispositions
and reports every way the two can disagree. Nothing here mutates either
side — CLAUDE.md §11 forbids editing generated output, and the disposition
file is edited only by a human (or `dispositions.write_dispositions`, for
tooling, never from this module).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .schema import Disposition, ManifestRow

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Finding:
    """One thing wrong with one row (or, for orphans, one disposition)."""

    row_id: str
    rule: str
    message: str
    severity: Severity


# --- rule ids ----------------------------------------------------------
#
# One constant per rule so callers/tests can filter or assert on `rule`
# without restating the literal string.

RULE_UNDISPOSITIONED = "undispositioned"
RULE_ORPHAN_DISPOSITION = "orphan_disposition"
RULE_STALE_DISPOSITION = "stale_disposition"
RULE_UNAFFIRMED_DISPOSITION = "unaffirmed_disposition"
RULE_UNDISPOSITIONABLE_ROW_DECIDED = "undispositionable_row_decided"
RULE_ILLEGAL_COSMETIC = "illegal_cosmetic"
RULE_MISSING_CITATION = "missing_citation"
RULE_BLOCKED_NO_GRANTING_CHAPTER = "blocked_no_granting_chapter"
RULE_CAPABILITY_MODEL_UNENFORCED = "capability_model_unenforced"
RULE_BLOCKED_MISSED_ASSERTION = "blocked_missed_assertion"
RULE_APPROACH_MODEL_UNENFORCED = "approach_model_unenforced"
RULE_REACHABILITY_UNENFORCED = "reachability_unenforced"


class CapabilityModel(Protocol):
    """The seam `blocked:<capability set>` validation plugs into (Q8.2, Q3).

    Not implemented here — deliberately. `check_chapter`'s `capabilities`
    argument accepts anything satisfying this Protocol; the agent building
    the capability model (Q3's `chapters.json` "capabilities" block, or a
    derivation off green seed blobs) only needs to provide one method.
    """

    def grants_capability(self, name: str) -> str | None:
        """Return the chapter id that grants `name`, or None if no chapter does.

        A `blocked:<name set>` row is legitimate only when every capability in
        the set returns a chapter id; when one returns None the row must be
        dispositioned `unreachable`, not `blocked` (Q8.2). `blocked:tooling:*`
        rows are never checked here — a missing harness primitive isn't a
        chapter-granted capability (Q10).
        """
        ...


class ApproachModel(Protocol):
    """The offline-reachability check behind `RULE_BLOCKED_MISSED_ASSERTION`
    (Q3 decision 3's checker half).

    Not implemented here — deliberately, same reasoning as `CapabilityModel`:
    `check_chapter`'s `approach` argument accepts anything satisfying this
    Protocol. `approach_model.GraphApproachModel` is the concrete adapter the
    CLI wires in, built over `traversal.reachability.adjacent_approach_cells`
    and `MapGraph.is_walkable`.
    """

    def has_walkable_approach(self, row: ManifestRow) -> bool | None:
        """Three-state, not boolean, because "no" and "can't tell" must never
        collapse into the same answer -- a `False` here SUPPRESSES
        `RULE_BLOCKED_MISSED_ASSERTION`, so treating "unanswerable" as False
        would silently swallow a real missed-assertion warning.

        True: `row`'s event has at least one orthogonally-adjacent tile that
        is walkable RIGHT NOW (no capability held) -- i.e. the player can
        already stand next to the blocked thing and press A, whatever the
        verdict says. Ground truth from the graph, not the author's own
        `assertable` self-report -- that is what lets this rule catch a row
        the author marked `assertable: false` (or left unjudged) by mistake.

        False: every adjacent tile is genuinely not walkable.

        None: this model cannot derive an answer for `row` at all -- e.g. a
        seam row (no event, so no cell to test), or a row on a map this
        model has no vetted traversal data for. Treated by `check_chapter`
        exactly like "no approach model was supplied"
        (`RULE_APPROACH_MODEL_UNENFORCED`), never as False.
        """
        ...


def check_chapter(
    rows: list[ManifestRow],
    dispositions: dict[str, Disposition],
    *,
    capabilities: CapabilityModel | None = None,
    approach: ApproachModel | None = None,
) -> list[Finding]:
    """Check one chapter's generated rows against its authored dispositions.

    `rows` is the generated manifest (already loaded by the caller — see
    the module docstring on why this module does not read the manifest
    file itself). `dispositions` is `row_id -> Disposition`, as returned by
    `dispositions.load_dispositions`.
    """
    findings: list[Finding] = []
    rows_by_id = {row.row_id: row for row in rows}

    for row in rows:
        disp = dispositions.get(row.row_id)
        if disp is None:
            findings.append(Finding(
                row_id=row.row_id,
                rule=RULE_UNDISPOSITIONED,
                message="row has no disposition entry",
                severity="error",
            ))
            continue

        if not row.is_dispositionable:
            findings.append(Finding(
                row_id=row.row_id,
                rule=RULE_UNDISPOSITIONABLE_ROW_DECIDED,
                message=(
                    "row carries an unrecognized script head or command code "
                    f"(unrecognized_heads={list(row.unrecognized_heads)}, "
                    f"other_codes={list(row.other_codes)}) and must be classified "
                    "by a human before it can be dispositioned"
                ),
                severity="error",
            ))
            # Still worth checking the other rules on this row's disposition;
            # an unrecognized row that is ALSO stale, uncited, etc. should
            # surface every problem, not just this one.

        if disp.affirmed_hash is None:
            findings.append(Finding(
                row_id=row.row_id,
                rule=RULE_UNAFFIRMED_DISPOSITION,
                message="disposition has never been affirmed against a content_hash",
                severity="error",
            ))
        elif disp.affirmed_hash != row.content_hash:
            findings.append(Finding(
                row_id=row.row_id,
                rule=RULE_STALE_DISPOSITION,
                message=(
                    f"affirmed_hash {disp.affirmed_hash!r} does not match current "
                    f"content_hash {row.content_hash!r}; row content changed since "
                    "this decision was made and it must be re-affirmed"
                ),
                severity="error",
            ))

        if disp.verdict == "cosmetic" and not row.may_be_cosmetic:
            if row.unhandled:
                findings.append(Finding(
                    row_id=row.row_id,
                    rule=RULE_ILLEGAL_COSMETIC,
                    message=(
                        f"disposed cosmetic but row has {row.unhandled} unhandled "
                        "transpile queue entr(y/ies) - this is a dead conversion "
                        "with no beat written at all, not decoration"
                    ),
                    severity="error",
                ))
            else:
                findings.append(Finding(
                    row_id=row.row_id,
                    rule=RULE_ILLEGAL_COSMETIC,
                    message=(
                        "disposed cosmetic but row carries state-writing effect "
                        f"tags {list(row.blocking_tags())}"
                    ),
                    severity="error",
                ))

        if row.needs_citation and not disp.source:
            findings.append(Finding(
                row_id=row.row_id,
                rule=RULE_MISSING_CITATION,
                message=(
                    "row has an unrecognized script head or a script-typed "
                    "conditional (code-111 params[0]==12) and needs a source "
                    "citation, but the disposition has none"
                ),
                severity="error",
            ))

        if disp.verdict == "blocked":
            capability_spec = disp.argument or ""
            if capability_spec.startswith("tooling:"):
                # blocked:tooling:<primitive> is a harness debt, not a
                # chapter-granted capability -- CapabilityModel has nothing to
                # say about it (Q10).
                pass
            elif capabilities is None:
                findings.append(Finding(
                    row_id=row.row_id,
                    rule=RULE_CAPABILITY_MODEL_UNENFORCED,
                    message=(
                        f"blocked:{capability_spec} could not be checked against a "
                        "granting chapter because no capability model was supplied "
                        "(this rule is unenforced without one)"
                    ),
                    severity="warning",
                ))
            else:
                ungranted = [
                    c for c in capability_spec.split("|")
                    if capabilities.grants_capability(c) is None
                ]
                if ungranted:
                    findings.append(Finding(
                        row_id=row.row_id,
                        rule=RULE_BLOCKED_NO_GRANTING_CHAPTER,
                        message=(
                            f"blocked:{capability_spec} names capability(ies) "
                            f"{ungranted} that no chapter in reference/chapters.json "
                            "grants; this row is unreachable, not blocked"
                        ),
                        severity="error",
                    ))

            if approach is None:
                findings.append(Finding(
                    row_id=row.row_id,
                    rule=RULE_APPROACH_MODEL_UNENFORCED,
                    message=(
                        "could not check for a missed negative-beat opportunity "
                        "because no approach model was supplied (this rule is "
                        "unenforced without one)"
                    ),
                    severity="warning",
                ))
            else:
                approach_answer = approach.has_walkable_approach(row)
                if approach_answer is None:
                    findings.append(Finding(
                        row_id=row.row_id,
                        rule=RULE_APPROACH_MODEL_UNENFORCED,
                        message=(
                            "the approach model could not determine a walkable-"
                            "approach answer for this row (no event cell to test, "
                            "or this row's map has no vetted traversal data) -- "
                            "this rule is unenforced for this row, not negative"
                        ),
                        severity="warning",
                    ))
                elif approach_answer and disp.negative_beat is None:
                    findings.append(Finding(
                        row_id=row.row_id,
                        rule=RULE_BLOCKED_MISSED_ASSERTION,
                        message=(
                            "row is blocked but an adjacent tile is reachable from the "
                            "chapter's start cell with nothing held, and no "
                            "negative beat recorded -- the player can already walk up "
                            "and be refused; this is a missed authoring opportunity, "
                            "not an error"
                        ),
                        severity="warning",
                    ))

    for row_id, disp in dispositions.items():
        if row_id not in rows_by_id:
            findings.append(Finding(
                row_id=row_id,
                rule=RULE_ORPHAN_DISPOSITION,
                message=(
                    f"disposition {disp.spec!r} matches no row in the generated "
                    "manifest; content was likely deleted or renamed"
                ),
                severity="error",
            ))

    unconsulted_maps = sorted({row.map_id for row in rows if not row.reachability_consulted})
    for map_id in unconsulted_maps:
        findings.append(Finding(
            row_id=f"map{map_id:03d}",
            rule=RULE_REACHABILITY_UNENFORCED,
            message=(
                f"map{map_id:03d}: the offline reachability source was not "
                "consulted for this map, so terrain-gated capabilities (surf, "
                "waterfall) cannot appear in requires[] for any row here, and "
                "_HEAD_REQUIRES structurally cannot express them either -- "
                "blocked: verdicts on this map's rows have not been checked "
                "against the terrain-gate half of the capability model"
            ),
            severity="warning",
        ))

    findings.sort(key=lambda f: (f.row_id, f.rule))
    return findings


def exit_code(findings: list[Finding]) -> int:
    """0 if no finding is an error; 1 otherwise. Warnings alone do not fail."""
    return 1 if any(f.severity == "error" for f in findings) else 0
