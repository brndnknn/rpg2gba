"""Tests for `scripts/freeze_rederivation.py` and its P7 freeze artifacts.

Scaffolding for REDERIVATION_PLAN.md's re-derivation task (scheduled for
deletion at P10, same as the script it tests). The one test that matters is
`test_frozen_manifest_rows_match_blob`: it reads the manifest content back
out of the git object store by the blob sha recorded in each freeze file's
`_header`, not from the working-tree file. That is the whole point of P7 --
after P8 regenerates `reference/manifests/CHnn.manifest.json`, the working
file will disagree with the freeze on purpose, and this test must keep
checking the frozen answer against the *frozen* blob rather than silently
starting to check the new working file.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FREEZE_DIR = REPO_ROOT / "reference" / "frozen" / "rederivation"

CHAPTERS = ("CH01", "CH02", "CH03", "CH04")


def _git_cat_file(blob_sha: str) -> str:
    result = subprocess.run(
        ["git", "cat-file", "-p", blob_sha],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"git cat-file -p {blob_sha} failed: {result.stderr}")
    return result.stdout


def _import_generator():
    """Import `scripts/freeze_rederivation.py`, which is a script, not a
    package module. Expires with the script at P10."""
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import freeze_rederivation
    return freeze_rederivation


def _load_freeze(chapter: str) -> dict:
    path = FREEZE_DIR / f"{chapter}.freeze.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_freeze_file_exists_and_parses(chapter: str) -> None:
    path = FREEZE_DIR / f"{chapter}.freeze.json"
    assert path.exists(), f"missing freeze file: {path}"
    data = _load_freeze(chapter)
    assert data["_header"]["chapter"] == chapter
    for key in ("manifest_rows", "dispositions", "beats"):
        assert key in data


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_frozen_manifest_rows_match_blob(chapter: str) -> None:
    """The test that matters: the frozen manifest rows equal what the
    recorded git blob sha actually contains, checked by reading the blob
    directly out of git rather than trusting the working-tree file. Stays
    meaningful after P8 regenerates the working manifest."""
    data = _load_freeze(chapter)
    blob_sha = data["_header"]["frozen_from"]["manifest"]["blob_sha"]
    blob_text = _git_cat_file(blob_sha)
    blob_rows = json.loads(blob_text)
    blob_rows_by_id = {row["row_id"]: row for row in blob_rows}
    assert data["manifest_rows"] == blob_rows_by_id


def test_frozen_ch04_dispositions_match_blob() -> None:
    data = _load_freeze("CH04")
    blob_sha = data["_header"]["frozen_from"]["dispositions"]["blob_sha"]
    blob_text = _git_cat_file(blob_sha)
    blob_dispositions = json.loads(blob_text)
    assert data["dispositions"] == blob_dispositions


@pytest.mark.parametrize("chapter", ("CH01", "CH02", "CH03"))
def test_dispositions_null_for_undispositioned_chapters(chapter: str) -> None:
    """Guard against a future well-meaning backfill: CH01-CH03 never had a
    dispositions.json, and this freeze must not invent one."""
    data = _load_freeze(chapter)
    assert data["dispositions"] is None
    assert data["_header"]["frozen_from"]["dispositions"] is None


def test_dispositions_non_null_for_ch04() -> None:
    data = _load_freeze("CH04")
    assert data["dispositions"] is not None
    assert data["_header"]["frozen_from"]["dispositions"] is not None


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_manifest_row_count_matches_header(chapter: str) -> None:
    data = _load_freeze(chapter)
    assert data["_header"]["frozen_from"]["manifest"]["rows"] == len(
        data["manifest_rows"])


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_beat_count_matches_header(chapter: str) -> None:
    data = _load_freeze(chapter)
    assert data["_header"]["frozen_from"]["chapter_module"]["beats"] == len(
        data["beats"])


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_blind_spots_are_non_empty_strings(chapter: str) -> None:
    data = _load_freeze(chapter)
    blind_spots = data["_header"]["blind_spots"]
    assert isinstance(blind_spots, list)
    assert len(blind_spots) > 0
    for entry in blind_spots:
        assert isinstance(entry, str)
        assert entry.strip() != ""


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_beats_have_expected_keys(chapter: str) -> None:
    data = _load_freeze(chapter)
    for beat in data["beats"]:
        assert set(beat.keys()) == {"name", "own", "map_constant", "group", "rows"}
        assert isinstance(beat["rows"], list)
        assert isinstance(beat["own"], bool)


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_own_beats_are_the_unprefixed_ones(chapter: str) -> None:
    """`load_chapter` returns the COMPOSED beat list -- a chapter's own beats
    plus every predecessor's -- so CH01's 17 beats appear in all four freeze
    files and CH04's 74 are only 13 of its own. `own` is what makes a
    per-chapter beat diff mean anything; without it CH04's diff lights up
    whenever CH01 changes. A predecessor's beats carry a `CHnn:` name prefix,
    the chapter's own are bare, and that is the discriminator."""
    data = _load_freeze(chapter)
    frozen_from = data["_header"]["frozen_from"]["chapter_module"]

    own = [b for b in data["beats"] if b["own"]]
    inherited = [b for b in data["beats"] if not b["own"]]

    assert all(not re.match(r"^CH\d\d:", b["name"]) for b in own)
    assert all(re.match(r"^CH\d\d:", b["name"]) for b in inherited)
    assert frozen_from["beats_own"] == len(own)
    assert frozen_from["beats"] == len(data["beats"])
    assert frozen_from["beats_own_with_rows"] == sum(1 for b in own if b["rows"])


def test_no_chapter_before_ch05_claims_manifest_rows_from_a_beat() -> None:
    """The scope fact P8 rests on: not one CH01-CH04 beat carries `rows=`.

    CH05 registers 19 own beats and all 19 claim rows; CH01-CH04 register 74
    own beats between them and none do. So the beat-to-manifest-row join that
    makes CH05's checks meaningful does not exist for any chapter being
    re-derived, and P8 cannot lean on it. Pinned here because it is an
    assumption, and an assumption that quietly stops being true is worse than
    one that fails loudly."""
    for chapter in CHAPTERS:
        data = _load_freeze(chapter)
        own_with_rows = [
            b["name"] for b in data["beats"] if b["own"] and b["rows"]
        ]
        assert own_with_rows == [], (
            f"{chapter}: beats now claim manifest rows ({own_with_rows}); "
            "REDERIVATION_PLAN.md P7/P8's scope facts need revisiting"
        )


def test_generator_is_deterministic() -> None:
    """Building the same chapter twice produces identical bytes.

    This is the half of the old idempotence test that is true forever. The
    other half -- that regeneration reproduces the COMMITTED freeze -- was
    only true until P8 derived its first manifest, because `build_freeze`
    reads the working tree. It failed the moment CH01 was re-derived, which
    is the freeze working as designed, so asserting it was asserting that
    P8 had not started yet.
    """
    mod = _import_generator()
    for chapter in CHAPTERS:
        first = mod._dump(mod.build_freeze(chapter))
        second = mod._dump(mod.build_freeze(chapter))
        assert first == second, f"{chapter}: not deterministic"


def test_write_refuses_to_clobber_an_existing_freeze() -> None:
    """A freeze that can be silently overwritten is not a freeze.

    `write` reads the working tree, so running it after P8 has derived would
    replace the pre-derivation record with the post-derivation state -- and
    the diff P8 depends on would compare the new answer against itself. It
    must refuse without `--force`.
    """
    from click.testing import CliRunner

    mod = _import_generator()
    result = CliRunner().invoke(mod.cli, ["write"])
    assert result.exit_code != 0
    assert "refusing to overwrite" in result.output


def test_check_verifies_against_pinned_blobs_not_the_working_tree() -> None:
    """`check` must stay green after P8 regenerates a manifest.

    The freeze's claim is "these bytes are what <path> held at blob <sha>",
    which is checkable forever. A check defined as "regeneration matches
    disk" instead goes red the moment the derivation it exists to police
    actually runs -- and a check that fails when things are going right is
    one people learn to ignore.
    """
    from click.testing import CliRunner

    mod = _import_generator()
    result = CliRunner().invoke(mod.cli, ["check"])
    assert result.exit_code == 0, result.output
