"""CLI for the generic beat floor (REDERIVATION_PLAN.md §16.3 C4).

    python -m rpg2gba.beat_floor report --chapter CH03
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import click

from rpg2gba.beat_floor.assertion import FloorAssertion, FloorRefusal, RowFloor
from rpg2gba.beat_floor.walk import floor_for_chapter
from rpg2gba.chapter_atlas.binding import load_binding


def _out_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"


def _report_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "beat_floor"


def _assertion_sort_key(a: FloorAssertion) -> tuple[str, int, int, str]:
    return (a.kind, a.list_index, a.code if a.code is not None else -1, repr(a.params))


def _assertion_to_dict(a: FloorAssertion) -> dict:
    return {
        "kind": a.kind,
        "list_index": a.list_index,
        "code": a.code,
        "params": [[k, v] for k, v in a.params],
        "tag": a.tag,
        "offline": a.offline,
    }


def _refusal_to_dict(r: FloorRefusal) -> dict:
    return {
        "reason": r.reason,
        "list_index": r.list_index,
        "code": r.code,
        "detail": r.detail,
    }


def _row_to_dict(row: RowFloor) -> dict:
    return {
        "row_id": row.row_id,
        "trigger": row.trigger,
        "refused": row.refused,
        "offline_eligible": row.offline_eligible,
        "assertions": [
            _assertion_to_dict(a) for a in sorted(row.assertions, key=_assertion_sort_key)
        ],
        "refusals": [
            _refusal_to_dict(r) for r in sorted(
                row.refusals, key=lambda r: (r.reason, r.list_index, repr(r.detail)))
        ],
    }


@click.group()
def cli() -> None:
    """Generic beat floor over CH01-CH05 (REDERIVATION_PLAN.md §16.3 C4)."""


@cli.command()
@click.option("--chapter", required=True, help="Chapter id, e.g. CH03.")
def report(chapter: str) -> None:
    """Compute chapter's generic beat floor and write its report."""
    binding = load_binding()
    binding.chapter(chapter)  # fail loud on an unknown id

    rows = floor_for_chapter(chapter, build_dir=_out_dir())

    out_dir = _report_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{chapter}.json"

    refusal_tally: Counter[str] = Counter()
    refused_count = 0
    offline_count = 0
    for row in rows.values():
        if row.refused:
            refused_count += 1
        if row.offline_eligible:
            offline_count += 1
        for r in row.refusals:
            refusal_tally[r.reason] += 1

    payload = {
        "chapter_id": chapter,
        "summary": {
            "rows": len(rows),
            "refused": refused_count,
            "offline_eligible": offline_count,
            "refusal_reasons": dict(sorted(refusal_tally.items())),
        },
        "rows": [_row_to_dict(rows[rid]) for rid in rows],
    }
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    click.echo(f"{chapter}: wrote {out_path}")
    click.echo(f"  rows: {len(rows)}")
    click.echo(f"  refused: {refused_count}")
    click.echo(f"  offline_eligible: {offline_count}")
    click.echo(f"  refusal_reasons: {dict(sorted(refusal_tally.items()))}")


if __name__ == "__main__":
    cli()
