"""Standalone CLI for the text-corpus validator (ROM_TEST_DEV.md §3 "text").

    python -m rpg2gba.text_validator scan
    python -m rpg2gba.text_validator scan --output output/uranium-build --engine engine
    python -m rpg2gba.text_validator scan --rule TEXT_HTML_TAG

Exits non-zero (fail loud, CLAUDE.md §4.5) if any issue is found, so it can
gate a pipeline stage the same way a test suite does.
"""
from __future__ import annotations

import logging
import sys
from collections import Counter
from pathlib import Path

import click

from .engine_metrics import load_charmap
from .extraction import extract_corpus
from .rules import TextIssue, load_allowed_chars, validate_text

logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """rpg2gba text-corpus validator."""


@cli.command("scan")
@click.option(
    "--output", "output_dir", type=click.Path(exists=True, path_type=Path),
    default=Path("output/uranium-build"),
    help="Pipeline output slice directory to scan (default: output/uranium-build).",
)
@click.option(
    "--engine", "engine_dir", type=click.Path(exists=True, path_type=Path),
    default=Path("engine"), envvar="RPG2GBA_POKEEMERALD",
    help="Vendored/fork engine checkout, for charmap.txt (default: engine/).",
)
@click.option(
    "--rule", "rule_filter", multiple=True,
    help="Only report these rule IDs (repeatable). Default: all rules.",
)
def scan(output_dir: Path, engine_dir: Path, rule_filter: tuple[str, ...]) -> None:
    """Scan an output slice's emitted .pory corpus and print a grouped report."""
    charmap_path = engine_dir / "charmap.txt"
    charmap = load_charmap(charmap_path)
    allowed_chars = load_allowed_chars(charmap_path)

    strings = extract_corpus(output_dir)
    issues = validate_text(strings, charmap=charmap, allowed_chars=allowed_chars)
    if rule_filter:
        issues = [i for i in issues if i.rule_id in rule_filter]

    click.echo(f"scanned {len(strings)} string literal(s) under {output_dir}")
    if not issues:
        click.echo("no issues found")
        return

    by_rule: dict[str, list[TextIssue]] = {}
    for issue in issues:
        by_rule.setdefault(issue.rule_id, []).append(issue)

    counts = Counter(i.rule_id for i in issues)
    click.echo(f"{len(issues)} issue(s) across {len(by_rule)} rule(s):")
    for rule_id, count in counts.most_common():
        click.echo(f"  {rule_id}: {count}")
    click.echo("")

    for rule_id in sorted(by_rule):
        click.echo(f"--- {rule_id} ({len(by_rule[rule_id])}) ---")
        for issue in by_rule[rule_id]:
            click.echo(f"  {issue.location}: {issue.message}")
        click.echo("")

    sys.exit(1)


if __name__ == "__main__":
    cli()
