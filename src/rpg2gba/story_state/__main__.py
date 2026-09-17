"""CLI for the derived story-state model (REDERIVATION_PLAN.md §16.3 C2b).

    python -m rpg2gba.story_state report --chapter CH03
"""
from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import click

from rpg2gba.chapter_atlas.binding import load_binding
from rpg2gba.story_state.model import ChapterStory, build_chapter_stories

_CHAIN = ["CH01", "CH02", "CH03", "CH04", "CH05"]


def _out_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "uranium-build"


def _story_dir() -> Path:
    return Path(os.environ.get("RPG2GBA_OUTPUT", "output")) / "story_state"


def _story_to_dict(story: ChapterStory) -> dict:
    return {
        "chapter_id": story.chapter_id,
        "seed_from": story.seed_from,
        "rows": [asdict(r) for r in story.rows],
        "end_state": [[k, list(v)] for k, v in story.end_state],
        "intro_maps": list(story.intro_maps) if story.intro_maps is not None else None,
        # Triggered-common-event pseudo-rows (REDERIVATION_PLAN.md §16.3 C2
        # ruling (e)) -- reported separately from `rows`, since they belong
        # to no map (ChapterStory.common_events docstring).
        "common_events": [asdict(r) for r in story.common_events],
        # Keys whose cross-page maximal writers disagreed with no route yet
        # to order them (REDERIVATION_PLAN.md §16.3 C2b handback, lead
        # ruling 2026-09-16) -- C2 joins and records rather than failing;
        # C6's route recomputes the real answer.
        "order_dependent": [asdict(o) for o in story.order_dependent],
    }


@click.group()
def cli() -> None:
    """Derived story-state model over CH01-CH05."""


@cli.command()
@click.option("--chapter", required=True, help="Chapter id, e.g. CH03.")
def report(chapter: str) -> None:
    """Build the story-state model through `--chapter` and write its report."""
    binding = load_binding()
    binding.chapter(chapter)  # fail loud on an unknown id
    if chapter not in _CHAIN:
        raise click.ClickException(
            f"{chapter!r} is outside the modelled R13 scope {_CHAIN}")
    chain = _CHAIN[: _CHAIN.index(chapter) + 1]

    stories = build_chapter_stories(
        chain, build_dir=_out_dir(), chapters_path=Path("reference/chapters.json"))
    story = stories[chapter]

    out_dir = _story_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{chapter}.json"
    payload = _story_to_dict(story)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    status_counts: Counter[str] = Counter(r.status for r in story.rows)
    blocker_tally: Counter[str] = Counter()
    refusal_tally: Counter[str] = Counter()
    for r in story.rows:
        for b in r.blockers:
            blocker_tally[b.split(":", 1)[0]] += 1
        for code in r.refusals:
            refusal_tally[code.split(":", 1)[0]] += 1

    click.echo(f"{chapter}: wrote {out_path}")
    click.echo(f"  rows: {dict(status_counts)}")
    click.echo(f"  blockers: {dict(blocker_tally)}")
    click.echo(f"  refusals: {dict(refusal_tally)}")
    click.echo(f"  end-state keys: {len(story.end_state)}")
    click.echo(f"  common_events: {len(story.common_events)}")
    click.echo(f"  order_dependent: {len(story.order_dependent)}")
    for o in story.order_dependent:
        click.echo(f"    {o.key}: {list(o.writers)} -> {list(o.values)}")


if __name__ == "__main__":
    cli()
