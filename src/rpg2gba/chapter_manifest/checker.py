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
RULE_DEFERRED_NO_GRANTING_CHAPTER = "deferred_no_granting_chapter"
RULE_CAPABILITY_MODEL_UNENFORCED = "capability_model_unenforced"


class CapabilityModel(Protocol):
    """The seam `deferred:<capability>` validation plugs into (Q8.2, Q3).

    Not implemented here — deliberately. `check_chapter`'s `capabilities`
    argument accepts anything satisfying this Protocol; the agent building
    the capability model (Q3's `chapters.json` "capabilities" block, or a
    derivation off green seed blobs) only needs to provide one method.
    """

    def grants_capability(self, name: str) -> str | None:
        """Return the chapter id that grants `name`, or None if no chapter does.

        A `deferred:<name>` row is legitimate only when this returns a
        chapter id; when it returns None the row must be dispositioned
        `unreachable`, not `deferred` (Q8.2).
        """
        ...


def check_chapter(
    rows: list[ManifestRow],
    dispositions: dict[str, Disposition],
    *,
    capabilities: CapabilityModel | None = None,
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

        if disp.verdict == "deferred":
            capability = disp.argument or ""
            if capabilities is None:
                findings.append(Finding(
                    row_id=row.row_id,
                    rule=RULE_CAPABILITY_MODEL_UNENFORCED,
                    message=(
                        f"deferred:{capability} could not be checked against a "
                        "granting chapter because no capability model was supplied "
                        "(this rule is unenforced without one)"
                    ),
                    severity="warning",
                ))
            elif capabilities.grants_capability(capability) is None:
                findings.append(Finding(
                    row_id=row.row_id,
                    rule=RULE_DEFERRED_NO_GRANTING_CHAPTER,
                    message=(
                        f"deferred:{capability} names a capability no chapter in "
                        "reference/chapters.json grants; this row is unreachable, "
                        "not deferred"
                    ),
                    severity="error",
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

    findings.sort(key=lambda f: (f.row_id, f.rule))
    return findings


def exit_code(findings: list[Finding]) -> int:
    """0 if no finding is an error; 1 otherwise. Warnings alone do not fail."""
    return 1 if any(f.severity == "error" for f in findings) else 0
