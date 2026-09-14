"""Tests for `dispositions.proposal_digest`, `render.render_blocked_proposals`,
and the `affirm` subcommand of `rpg2gba.chapter_manifest`'s CLI.

Reuses the map/page/command fixture builders from `test_chapter_manifest_cli.py`
(`_page`, `_cmd`, `_write_traversable_map`, `_write_tilesets`) rather than
duplicating them -- that file's own convention is already to duplicate a
local copy per test module, but importing here keeps this file smaller and
that file is off limits to edit.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from rpg2gba.chapter_manifest.__main__ import cli
from rpg2gba.chapter_manifest.derivation import DerivedEntry
from rpg2gba.chapter_manifest.dispositions import load_dispositions, proposal_digest
from rpg2gba.chapter_manifest.render import EventFacts, render_blocked_proposals
from rpg2gba.chapter_manifest.schema import ManifestRow
from tests.test_chapter_manifest_cli import (
    _cmd,
    _page,
    _write_tilesets,
    _write_traversable_map,
)

# --- proposal_digest ---------------------------------------------------


def test_proposal_digest_ignores_non_proposals_and_is_order_independent() -> None:
    proposed = {
        "map001/ev001/p0": DerivedEntry(
            disposition="blocked:rock_smash", derived_hash="aaa", proposed=True),
        "map001/ev002/p0": DerivedEntry(
            disposition="blocked:surf", derived_hash="bbb", proposed=True),
    }
    clerical = {
        "map001/ev003/p0": DerivedEntry(disposition="cosmetic", derived_hash="ccc"),
    }

    digest_proposed_only = proposal_digest(proposed)
    digest_with_clerical = proposal_digest({**proposed, **clerical})
    assert digest_proposed_only == digest_with_clerical

    reordered = {
        "map001/ev002/p0": proposed["map001/ev002/p0"],
        "map001/ev001/p0": proposed["map001/ev001/p0"],
    }
    assert proposal_digest(reordered) == digest_proposed_only


def test_proposal_digest_changes_with_hash_or_disposition() -> None:
    base = {
        "map001/ev001/p0": DerivedEntry(
            disposition="blocked:rock_smash", derived_hash="aaa", proposed=True),
    }
    changed_hash = {
        "map001/ev001/p0": DerivedEntry(
            disposition="blocked:rock_smash", derived_hash="zzz", proposed=True),
    }
    changed_spec = {
        "map001/ev001/p0": DerivedEntry(
            disposition="blocked:surf", derived_hash="aaa", proposed=True),
    }
    d0 = proposal_digest(base)
    assert d0 != proposal_digest(changed_hash)
    assert d0 != proposal_digest(changed_spec)


def test_proposal_digest_empty_is_stable() -> None:
    assert proposal_digest({}) == proposal_digest({})
    assert len(proposal_digest({})) == 16


# --- render_blocked_proposals -------------------------------------------


def _row(row_id: str, map_id: int, event_id: int, page_idx: int, *, requires=("rock_smash",),
         effects=("switch_write",), script_heads=("pbRockSmash",)) -> ManifestRow:
    return ManifestRow(
        row_id=row_id, kind="page", map_id=map_id, content_hash=f"hash-{row_id}",
        effects=effects, script_heads=script_heads, requires=requires,
        event_id=event_id, page_idx=page_idx,
    )


def test_render_blocked_proposals_groups_by_spec_and_merges_pages() -> None:
    rows = [
        _row("map050/ev001/p0", 50, 1, 0),
        _row("map050/ev001/p1", 50, 1, 1, effects=("text",), script_heads=()),
        _row("map050/ev002/p0", 50, 2, 0, requires=("surf",), script_heads=("pbSurf",)),
    ]
    derived = {
        "map050/ev001/p0": DerivedEntry(
            disposition="blocked:rock_smash", derived_hash="hash-map050/ev001/p0", proposed=True),
        "map050/ev001/p1": DerivedEntry(
            disposition="blocked:rock_smash", derived_hash="hash-map050/ev001/p1", proposed=True),
        "map050/ev002/p0": DerivedEntry(
            disposition="blocked:surf", derived_hash="hash-map050/ev002/p0", proposed=True),
    }
    events = {
        (50, 1): EventFacts(map_name="Rockville", event_name="Rock", x=1, y=1),
        (50, 2): EventFacts(map_name="Rockville", event_name="Lake", x=3, y=3),
    }

    text = render_blocked_proposals("CH50", derived, rows, events)

    digest = proposal_digest(derived)
    assert f"`{digest}`" in text
    assert (
        f"python -m rpg2gba.chapter_manifest affirm --chapter CH50 --digest {digest} --all"
        in text
    )
    assert "/map/<id>?mode=events" in text
    assert "## `blocked:rock_smash`" in text
    assert "## `blocked:surf`" in text
    # Both rock_smash pages merged onto one event row, "p0, p1".
    assert "p0, p1" in text
    assert "map050 -- Rockville" in text
    assert "ev001 -- Rock" in text
    assert "(1, 1)" in text
    assert "ev002 -- Lake" in text
    assert "(3, 3)" in text
    assert "3 page row(s) total across all proposals." in text


def test_render_blocked_proposals_zero_proposals_says_so() -> None:
    text = render_blocked_proposals("CH50", {}, [], {})
    assert "No proposals awaiting affirmation." in text
    assert "CH50" in text


def test_render_blocked_proposals_missing_facts_degrade_not_crash() -> None:
    rows = [_row("map050/ev001/p0", 50, 1, 0)]
    derived = {
        "map050/ev001/p0": DerivedEntry(
            disposition="blocked:rock_smash", derived_hash="hash-map050/ev001/p0", proposed=True),
    }
    text = render_blocked_proposals("CH50", derived, rows, {})
    assert "name unavailable" in text


# --- CLI fixtures --------------------------------------------------------


def _setup_chokepoint_chapter_with_names(
    tmp_path: Path, chapter_id: str, map_id: int,
) -> tuple[Path, Path]:
    events = [
        {
            "id": 1, "name": "Rock", "x": 1, "y": 1,
            "pages": [_page([_cmd(355, ["Kernel.pbRockSmash(1)"])])],
        },
        {
            "id": 2, "name": "Sign", "x": 1, "y": 2,
            "pages": [_page([_cmd(101, ["Beyond the rock"])])],
        },
    ]
    build_dir = tmp_path / "build"
    (build_dir / "maps").mkdir(parents=True)
    _write_traversable_map(
        build_dir / "maps" / f"Map{map_id:03d}.json", map_id, 3, 3, events,
        wall_cells={(0, 1), (2, 1)})
    _write_tilesets(build_dir / "tilesets.json")
    (build_dir / "connections.json").write_text("[]", encoding="utf-8")
    (build_dir / "map_infos.json").write_text(json.dumps({
        str(map_id): {"name": "Rockville"},
    }), encoding="utf-8")
    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({
        "chapters": [{"id": chapter_id, "maps": [map_id]}],
    }), encoding="utf-8")
    return build_dir, chapters_path


def _generate(tmp_path: Path, chapter_id: str, map_id: int) -> tuple[Path, Path, Path, Path, dict]:
    """Runs `generate` against a fresh chokepoint chapter (one `blocked:
    rock_smash` proposal row, one plain `cosmetic` row) and returns
    (manifest_path, derived_path, review_path, dispositions_path, hashes)."""
    build_dir, chapters_path = _setup_chokepoint_chapter_with_names(tmp_path, chapter_id, map_id)
    manifest_path = tmp_path / f"{chapter_id}.manifest.json"
    derived_path = tmp_path / f"{chapter_id}.derived.json"
    dispositions_path = tmp_path / f"{chapter_id}.dispositions.json"

    runner = CliRunner()
    result = runner.invoke(cli, [
        "generate", "--chapter", chapter_id,
        "--manifest", str(manifest_path),
        "--derived", str(derived_path),
        "--build-dir", str(build_dir),
        "--chapters", str(chapters_path),
    ])
    assert result.exit_code == 0, result.output

    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    hashes = {r["row_id"]: r["content_hash"] for r in rows}
    review_path = tmp_path / f"{chapter_id}.blocked_review.md"
    return manifest_path, derived_path, review_path, dispositions_path, hashes


def test_generate_with_manifest_writes_review_beside_it(tmp_path: Path) -> None:
    manifest_path, derived_path, _review_path, _dispositions_path, hashes = _generate(
        tmp_path, "CHR", 60)

    review_path = manifest_path.parent / "CHR.blocked_review.md"
    assert review_path.exists()
    text = review_path.read_text(encoding="utf-8")
    assert "blocked:rock_smash" in text
    assert "Rockville" in text
    assert "Rock" in text
    assert "(1, 1)" in text


def _digest_from_derived(derived_path: Path) -> str:
    from rpg2gba.chapter_manifest.dispositions import load_derived
    return proposal_digest(load_derived(derived_path))


# --- affirm ---------------------------------------------------------------


def test_affirm_all_happy_path_creates_dispositions_file(tmp_path: Path) -> None:
    chapter_id = "CHA1"
    manifest_path, derived_path, _review, dispositions_path, hashes = _generate(
        tmp_path, chapter_id, 61)
    digest = _digest_from_derived(derived_path)
    rock_row_id = "map061/ev001/p0"
    assert rock_row_id in hashes

    runner = CliRunner()
    result = runner.invoke(cli, [
        "affirm", "--chapter", chapter_id, "--digest", digest, "--all",
        "--manifest", str(manifest_path),
        "--derived", str(derived_path),
        "--dispositions", str(dispositions_path),
    ])

    assert result.exit_code == 0, result.output
    assert "affirmed 1 row(s) (0 already affirmed)" in result.output
    assert dispositions_path.exists()

    loaded = load_dispositions(dispositions_path)
    assert rock_row_id in loaded
    disp = loaded[rock_row_id]
    assert disp.spec == "blocked:rock_smash"
    assert disp.affirmed_hash == hashes[rock_row_id]


def test_affirm_merges_into_existing_dispositions(tmp_path: Path) -> None:
    chapter_id = "CHA2"
    manifest_path, derived_path, _review, dispositions_path, hashes = _generate(
        tmp_path, chapter_id, 62)
    digest = _digest_from_derived(derived_path)
    rock_row_id = "map062/ev001/p0"
    sign_row_id = "map062/ev002/p0"

    dispositions_path.write_text(json.dumps({
        sign_row_id: {"disposition": "beat:B1", "affirmed_hash": hashes[sign_row_id]},
    }), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, [
        "affirm", "--chapter", chapter_id, "--digest", digest, "--all",
        "--manifest", str(manifest_path),
        "--derived", str(derived_path),
        "--dispositions", str(dispositions_path),
    ])

    assert result.exit_code == 0, result.output
    loaded = load_dispositions(dispositions_path)
    assert loaded[sign_row_id].spec == "beat:B1"
    assert loaded[rock_row_id].spec == "blocked:rock_smash"
    assert loaded[rock_row_id].affirmed_hash == hashes[rock_row_id]


def test_affirm_by_row_is_idempotent(tmp_path: Path) -> None:
    chapter_id = "CHA3"
    manifest_path, derived_path, _review, dispositions_path, hashes = _generate(
        tmp_path, chapter_id, 63)
    digest = _digest_from_derived(derived_path)
    rock_row_id = "map063/ev001/p0"

    runner = CliRunner()
    args = [
        "affirm", "--chapter", chapter_id, "--digest", digest, "--row", rock_row_id,
        "--manifest", str(manifest_path),
        "--derived", str(derived_path),
        "--dispositions", str(dispositions_path),
    ]
    first = runner.invoke(cli, args)
    assert first.exit_code == 0, first.output
    text_after_first = dispositions_path.read_text(encoding="utf-8")

    second = runner.invoke(cli, args)
    assert second.exit_code == 0, second.output
    assert "affirmed 0 row(s) (1 already affirmed)" in second.output
    assert dispositions_path.read_text(encoding="utf-8") == text_after_first


# --- affirm refusals --------------------------------------------------------


def test_affirm_refuses_digest_mismatch_and_writes_nothing(tmp_path: Path) -> None:
    chapter_id = "CHA4"
    manifest_path, derived_path, _review, dispositions_path, _hashes = _generate(
        tmp_path, chapter_id, 64)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "affirm", "--chapter", chapter_id, "--digest", "0" * 16, "--all",
        "--manifest", str(manifest_path),
        "--derived", str(derived_path),
        "--dispositions", str(dispositions_path),
    ])

    assert result.exit_code != 0
    assert "digest mismatch" in result.output
    assert not dispositions_path.exists()


def test_affirm_refuses_row_that_is_not_a_proposal(tmp_path: Path) -> None:
    chapter_id = "CHA5"
    manifest_path, derived_path, _review, dispositions_path, hashes = _generate(
        tmp_path, chapter_id, 65)
    digest = _digest_from_derived(derived_path)
    sign_row_id = "map065/ev002/p0"  # cosmetic, not a proposal
    assert sign_row_id in hashes

    runner = CliRunner()
    result = runner.invoke(cli, [
        "affirm", "--chapter", chapter_id, "--digest", digest, "--row", sign_row_id,
        "--manifest", str(manifest_path),
        "--derived", str(derived_path),
        "--dispositions", str(dispositions_path),
    ])

    assert result.exit_code != 0
    assert "not a current proposal" in result.output
    assert not dispositions_path.exists()


def test_affirm_refuses_stale_hash_versus_manifest(tmp_path: Path) -> None:
    chapter_id = "CHA6"
    manifest_path, derived_path, _review, dispositions_path, _hashes = _generate(
        tmp_path, chapter_id, 66)
    digest = _digest_from_derived(derived_path)
    rock_row_id = "map066/ev001/p0"

    # Mutate the manifest's content_hash for the proposed row, simulating a
    # manifest that has moved on since the sidecar was written.
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in rows:
        if row["row_id"] == rock_row_id:
            row["content_hash"] = "stale-hash-value"
    manifest_path.write_text(json.dumps(rows), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, [
        "affirm", "--chapter", chapter_id, "--digest", digest, "--all",
        "--manifest", str(manifest_path),
        "--derived", str(derived_path),
        "--dispositions", str(dispositions_path),
    ])

    assert result.exit_code != 0
    assert "stale" in result.output
    assert not dispositions_path.exists()


def test_affirm_refuses_conflicting_existing_disposition(tmp_path: Path) -> None:
    chapter_id = "CHA7"
    manifest_path, derived_path, _review, dispositions_path, hashes = _generate(
        tmp_path, chapter_id, 67)
    digest = _digest_from_derived(derived_path)
    rock_row_id = "map067/ev001/p0"

    dispositions_path.write_text(json.dumps({
        rock_row_id: {"disposition": "blocked:surf", "affirmed_hash": hashes[rock_row_id]},
    }), encoding="utf-8")
    original_text = dispositions_path.read_text(encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, [
        "affirm", "--chapter", chapter_id, "--digest", digest, "--all",
        "--manifest", str(manifest_path),
        "--derived", str(derived_path),
        "--dispositions", str(dispositions_path),
    ])

    assert result.exit_code != 0
    assert "conflicting" in result.output
    assert dispositions_path.read_text(encoding="utf-8") == original_text


@pytest.mark.parametrize("extra_args", [[], ["--all", "--row", "map068/ev001/p0"]])
def test_affirm_requires_exactly_one_of_all_or_row(tmp_path: Path, extra_args: list[str]) -> None:
    chapter_id = "CHA8"
    manifest_path, derived_path, _review, dispositions_path, _hashes = _generate(
        tmp_path, chapter_id, 68)
    digest = _digest_from_derived(derived_path)

    runner = CliRunner()
    result = runner.invoke(cli, [
        "affirm", "--chapter", chapter_id, "--digest", digest,
        "--manifest", str(manifest_path),
        "--derived", str(derived_path),
        "--dispositions", str(dispositions_path),
        *extra_args,
    ])

    assert result.exit_code != 0
    assert not dispositions_path.exists()


def test_affirm_round_trip_parses_and_carries_affirmed_hash(tmp_path: Path) -> None:
    chapter_id = "CHA9"
    manifest_path, derived_path, _review, dispositions_path, hashes = _generate(
        tmp_path, chapter_id, 69)
    digest = _digest_from_derived(derived_path)
    rock_row_id = "map069/ev001/p0"

    runner = CliRunner()
    result = runner.invoke(cli, [
        "affirm", "--chapter", chapter_id, "--digest", digest, "--all",
        "--manifest", str(manifest_path),
        "--derived", str(derived_path),
        "--dispositions", str(dispositions_path),
    ])
    assert result.exit_code == 0, result.output

    loaded = load_dispositions(dispositions_path)
    disp = loaded[rock_row_id]
    assert disp.verdict == "blocked"
    assert disp.argument == "rock_smash"
    assert disp.affirmed_hash == hashes[rock_row_id]

    # Re-serializing and re-parsing must round-trip identically (same
    # convention `write_dispositions`'s own docstring promises).
    from rpg2gba.chapter_manifest.dispositions import write_dispositions
    roundtrip_path = tmp_path / "roundtrip.json"
    write_dispositions(loaded, roundtrip_path)
    reloaded = load_dispositions(roundtrip_path)
    assert reloaded[rock_row_id].affirmed_hash == hashes[rock_row_id]
    assert reloaded[rock_row_id].spec == disp.spec
