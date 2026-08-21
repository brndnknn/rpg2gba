"""The human review view (Q6.4): a rendering of the manifest rows, not a
second artifact.

`render_review` reads the same `ManifestRow`/`Disposition` objects the
checker reads. Grouping and collapsing is a presentation choice made at
render time, not a fact recorded anywhere else — so the review view cannot
drift from what the checker enforces, because there is nowhere for it to
drift to.
"""
from __future__ import annotations

from .schema import Disposition, ManifestRow


def render_review(rows: list[ManifestRow], dispositions: dict[str, Disposition]) -> str:
    """Render `rows`/`dispositions` as a Markdown review document.

    `cosmetic` rows collapse to a count plus a compact one-line-each list.
    Everything else — `beat`, `deferred`, `unreachable`, undispositioned,
    and any row where `needs_citation` is True (even if disposed cosmetic-
    adjacent) — is expanded with its condition, effect tags, requirements,
    unhandled count, and (for seams) endpoints/offsets.
    """
    lines: list[str] = []
    rows_by_disposition: dict[str, list[ManifestRow]] = {
        "beat": [], "deferred": [], "cosmetic": [], "unreachable": [], "undispositioned": [],
    }
    citation_owed: list[ManifestRow] = []

    for row in rows:
        disp = dispositions.get(row.row_id)
        bucket = disp.verdict if disp is not None else "undispositioned"
        rows_by_disposition.setdefault(bucket, []).append(row)
        if row.needs_citation:
            citation_owed.append(row)

    total = len(rows)
    lines.append("# Chapter manifest review")
    lines.append("")
    lines.append(f"- total rows: {total}")
    for verdict in ("beat", "deferred", "cosmetic", "unreachable"):
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

    for verdict, heading in (
        ("beat", "Beats"),
        ("deferred", "Deferred"),
        ("unreachable", "Unreachable"),
        ("undispositioned", "Undispositioned"),
    ):
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
        # Rows already expanded above (beat/deferred/unreachable/undispositioned)
        # are not repeated in full; only rows that would otherwise have been
        # collapsed (cosmetic, or missing a disposition) are shown here in full.
        for row in citation_owed:
            disp = dispositions.get(row.row_id)
            if disp is not None and disp.verdict not in ("cosmetic",):
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
    if row.unrecognized_heads:
        out.append(f"- unrecognized heads: {list(row.unrecognized_heads)}")
    if row.other_codes:
        out.append(f"- other codes: {list(row.other_codes)}")
    out.append("")
    return out
