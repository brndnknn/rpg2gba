"""The human review view (Q6.4): a rendering of the manifest rows, not a
second artifact.

`render_review` reads the same `ManifestRow`/`Disposition` objects the
checker reads. Grouping and collapsing is a presentation choice made at
render time, not a fact recorded anywhere else — so the review view cannot
drift from what the checker enforces, because there is nowhere for it to
drift to.
"""
from __future__ import annotations

from .schema import _VERDICTS, Disposition, ManifestRow

# Every verdict is either collapsed to a one-line-each list or expanded in
# full, and the two sets together must cover `schema._VERDICTS` exactly. The
# assertion below is the point of splitting them out as constants: `boundary`
# (PROJECT_TODO #72/#73) was added to the schema without being added here, and
# because the bucketing loop used `setdefault`, every `boundary` row was
# silently dropped from the rendered review -- present in the manifest,
# invisible to the human reading it. A verdict added to the schema from now on
# fails loud at import (CLAUDE.md §4.5) instead of quietly vanishing from the
# one artifact a reviewer actually reads.
_COLLAPSED_VERDICTS: tuple[str, ...] = ("cosmetic",)

_EXPANDED_SECTIONS: tuple[tuple[str, str], ...] = (
    ("beat", "Beats"),
    ("blocked", "Blocked"),
    ("boundary", "Boundary"),
    ("unreachable", "Unreachable"),
    ("undispositioned", "Undispositioned"),
)

# `undispositioned` is this module's own synthetic bucket for a row with no
# disposition at all, not a schema verdict, so it is excluded from the cover
# check rather than added to `_VERDICTS`.
_RENDERED_VERDICTS: frozenset[str] = frozenset(_COLLAPSED_VERDICTS) | {
    verdict for verdict, _heading in _EXPANDED_SECTIONS
} - {"undispositioned"}

if _RENDERED_VERDICTS != _VERDICTS:
    raise AssertionError(
        "chapter_manifest/render.py does not render every schema verdict: "
        f"missing {sorted(_VERDICTS - _RENDERED_VERDICTS)!r}, unknown "
        f"{sorted(_RENDERED_VERDICTS - _VERDICTS)!r} -- add the verdict to "
        "_COLLAPSED_VERDICTS or _EXPANDED_SECTIONS"
    )


def render_review(rows: list[ManifestRow], dispositions: dict[str, Disposition]) -> str:
    """Render `rows`/`dispositions` as a Markdown review document.

    `cosmetic` rows collapse to a count plus a compact one-line-each list.
    Everything else — `beat`, `blocked`, `boundary`, `unreachable`, undispositioned,
    and any row where `needs_citation` is True (even if disposed cosmetic-
    adjacent) — is expanded with its condition, effect tags, requirements,
    unhandled count, and (for seams) endpoints/offsets.
    """
    lines: list[str] = []
    rows_by_disposition: dict[str, list[ManifestRow]] = {
        verdict: [] for verdict in (*_VERDICTS, "undispositioned")
    }
    citation_owed: list[ManifestRow] = []

    for row in rows:
        disp = dispositions.get(row.row_id)
        bucket = disp.verdict if disp is not None else "undispositioned"
        # Not `setdefault`: a bucket this module does not know about is a
        # verdict it cannot render, and the import-time cover check above
        # exists precisely so that cannot happen silently.
        rows_by_disposition[bucket].append(row)
        if row.needs_citation:
            citation_owed.append(row)

    total = len(rows)
    lines.append("# Chapter manifest review")
    lines.append("")
    lines.append(f"- total rows: {total}")
    for verdict in sorted(_VERDICTS):
        lines.append(f"- {verdict}: {len(rows_by_disposition.get(verdict, []))}")
    lines.append(f"- undispositioned: {len(rows_by_disposition.get('undispositioned', []))}")
    lines.append(f"- citation owed: {len(citation_owed)}")
    lines.append("")

    cosmetic_rows = rows_by_disposition.get("cosmetic", [])
    lines.append(f"## Cosmetic ({len(cosmetic_rows)})")
    lines.append("")
    if cosmetic_rows:
        for row in cosmetic_rows:
            lines.append(f"- `{row.row_id}` — {_short_label(row)}")
    else:
        lines.append("(none)")
    lines.append("")

    for verdict, heading in _EXPANDED_SECTIONS:
        expand_rows = rows_by_disposition.get(verdict, [])
        lines.append(f"## {heading} ({len(expand_rows)})")
        lines.append("")
        if not expand_rows:
            lines.append("(none)")
            lines.append("")
            continue
        for row in expand_rows:
            lines.extend(_render_expanded(row, dispositions.get(row.row_id)))
        lines.append("")

    lines.append(f"## Citation owed ({len(citation_owed)})")
    lines.append("")
    if citation_owed:
        # Rows already expanded above (see `_EXPANDED_SECTIONS`)
        # are not repeated in full; only rows that would otherwise have been
        # collapsed (cosmetic, or missing a disposition) are shown here in full.
        for row in citation_owed:
            disp = dispositions.get(row.row_id)
            if disp is not None and disp.verdict not in _COLLAPSED_VERDICTS:
                lines.append(f"- `{row.row_id}` — see {disp.verdict} section above")
            else:
                lines.extend(_render_expanded(row, disp))
    else:
        lines.append("(none)")
    lines.append("")

    return "\n".join(lines)


def _short_label(row: ManifestRow) -> str:
    condition = row.condition.describe() if row.condition is not None else "always"
    effects = ",".join(row.effects) if row.effects else "none"
    return f"{condition}; effects=[{effects}]"


def _render_expanded(row: ManifestRow, disp: Disposition | None) -> list[str]:
    out: list[str] = [f"### `{row.row_id}`"]
    if disp is not None:
        out.append(f"- disposition: `{disp.spec}`")
        if disp.source:
            out.append(f"- source: {disp.source}")
        if disp.assertable is not None:
            out.append(f"- assertable: {disp.assertable}")
        if disp.negative_beat:
            out.append(f"- negative beat: {disp.negative_beat}")
        if disp.note:
            out.append(f"- note: {disp.note}")
    else:
        out.append("- disposition: (none)")

    if row.kind == "seam" and row.seam is not None:
        seam = row.seam
        out.append(
            f"- seam: map{seam.map_id:03d} {seam.direction}@{seam.offset} "
            f"<-> map{seam.other_map_id:03d} {seam.other_direction}@{seam.other_offset}"
        )
    else:
        condition = row.condition.describe() if row.condition is not None else "always"
        out.append(f"- condition: {condition}")
        if row.trigger:
            out.append(f"- trigger: {row.trigger}")

    out.append(f"- effects: {list(row.effects)}")
    if row.requires:
        out.append(f"- requires: {list(row.requires)}")
    if row.unhandled:
        out.append(f"- unhandled: {row.unhandled}")
    elif row.unhandled is None:
        # Distinct from a measured 0: the reader must be able to tell "this
        # map was never transpiled, the queue says nothing" apart from
        # "transpiled and clean" at a glance.
        out.append("- unhandled: null (map never staged)")
    if row.unrecognized_heads:
        out.append(f"- unrecognized heads: {list(row.unrecognized_heads)}")
    if row.other_codes:
        out.append(f"- other codes: {list(row.other_codes)}")
    out.append("")
    return out
