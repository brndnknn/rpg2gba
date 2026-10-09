"""Teachable-learnset overlay: Uranium TM/HM/tutor compatibility -> all_learnables.gen.json."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from rpg2gba.species_converter import teachables as t

REPO = Path(__file__).resolve().parents[1]
HELPERS = REPO / "engine" / "tools" / "learnset_helpers"

FORK_MOVES = {"MOVE_CUT", "MOVE_FEINT", "MOVE_TOXIC", "MOVE_STRENGTH"}
NEEDS_ENGINE_MOVES = {"MOVE_CORAL_BREAK"}


def _build(sidecar, *, upstream=None, staged=None, **kw):
    args = dict(
        upstream=upstream if upstream is not None else {"PIKACHU": ["MOVE_TOXIC"], "EEVEE": []},
        sidecar=sidecar,
        species_ids={"PIKACHU": "SPECIES_PIKACHU", "EEVEE": "SPECIES_EEVEE",
                     "RAPTORCH": "SPECIES_RAPTORCH", "ACTAN": "SPECIES_ACTAN"},
        needs_engine_species={"SPECIES_ACTAN"},
        staged=staged if staged is not None else {"RAPTORCH": "SPECIES_RAPTORCH"},
        fork_moves=FORK_MOVES,
        needs_engine_moves=NEEDS_ENGINE_MOVES,
    )
    args.update(kw)
    return t.build_overlay(**args)


def test_custom_species_gets_exactly_uranium_list():
    o = _build({"RAPTORCH": ["MOVE_STRENGTH", "MOVE_CUT"]})
    assert o.learnables["URANIUM_RAPTORCH"] == ["MOVE_CUT", "MOVE_STRENGTH"]
    assert o.custom_species == 1


def test_vanilla_species_gets_union_with_stock_list():
    o = _build({"PIKACHU": ["MOVE_FEINT", "MOVE_TOXIC"]})
    assert o.learnables["PIKACHU"] == ["MOVE_FEINT", "MOVE_TOXIC"]
    assert o.vanilla_species == 1 and o.added_pairs == 1
    assert o.learnables["EEVEE"] == []  # untouched


def test_upstream_not_mutated():
    up = {"PIKACHU": ["MOVE_TOXIC"]}
    _build({"PIKACHU": ["MOVE_CUT"]}, upstream=up)
    assert up == {"PIKACHU": ["MOVE_TOXIC"]}


def test_unknown_move_fails_loud():
    with pytest.raises(ValueError, match="MOVE_BOGUS"):
        _build({"RAPTORCH": ["MOVE_BOGUS"]})


def test_uranium_original_move_dropped_and_reported():
    o = _build({"RAPTORCH": ["MOVE_CUT", "MOVE_CORAL_BREAK"]})
    assert o.learnables["URANIUM_RAPTORCH"] == ["MOVE_CUT"]
    assert o.dropped_moves == ["MOVE_CORAL_BREAK"]


def test_unstaged_unavailable_species_skipped():
    o = _build({"ACTAN": ["MOVE_CUT"], "NOSUCH": ["MOVE_CUT"]})
    assert sorted(o.skipped_species) == ["ACTAN", "NOSUCH"]
    assert o.learnables == {"PIKACHU": ["MOVE_TOXIC"], "EEVEE": []}


def test_vanilla_species_missing_from_upstream_fails_loud():
    with pytest.raises(ValueError, match="no .*all_learnables"):
        _build({"PIKACHU": ["MOVE_CUT"]}, upstream={"EEVEE": []})


def test_empty_sidecar_and_no_staged_is_valid_passthrough():
    o = _build({}, staged={})
    assert o.learnables == {"PIKACHU": ["MOVE_TOXIC"], "EEVEE": []}
    assert json.loads(t.render(o)) == o.learnables


def test_render_idempotent():
    side = {"RAPTORCH": ["MOVE_CUT"], "PIKACHU": ["MOVE_FEINT"]}
    assert t.render(_build(side)) == t.render(_build(side))


def test_symbol_key_matches_generator_derivation():
    assert t.teachable_symbol("RAPTORCH") == "sUraniumRAPTORCHTeachableLearnset"
    assert t.learnables_key("RAPTORCH") == "URANIUM_RAPTORCH"
    # The generator's snakify doubles an existing underscore; we mirror it so keys still match.
    assert t.learnables_key("FOO_BAR2") == "URANIUM_FOO__BAR2"


def _load_helper(name: str):
    spec = importlib.util.spec_from_file_location(name, HELPERS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(not HELPERS.is_dir(), reason="vendored engine absent")
def test_key_matches_make_teachables_snakify():
    """Our key == what make_teachables.py derives from the symbol stage.py emits."""
    mt = _load_helper("make_teachables")
    name = t.teachable_name("RAPTORCH")
    assert mt.SNAKIFY_PAT.sub(r"_\1", name).upper() == t.learnables_key("RAPTORCH")
    line = f".teachableLearnset = {t.teachable_symbol('RAPTORCH')},"
    mtt = _load_helper("make_teaching_types")
    assert mtt.LEARNSET_PAT.match(line).group("name") == name


@pytest.mark.skipif(not HELPERS.is_dir(), reason="vendored engine absent")
def test_tutor_scanner_sees_transpiled_tutor_idiom(tmp_path, monkeypatch):
    """A map scripts.inc using `setvar VAR_0x8005` + `call ..._OpenBox` (no `special
    ChooseMonForMoveTutor` of its own) must still contribute its tutor moves."""
    mt = _load_helper("make_tutors")
    maps = tmp_path / "data" / "maps" / "Fake"
    maps.mkdir(parents=True)
    (tmp_path / "data" / "scripts").mkdir()
    (maps / "scripts.inc").write_text(
        "T::\n\tsetvar VAR_0x8005, MOVE_FEINT\n\tcall MoveTutor_EventScript_OpenBox\n"
        "\tsetvar VAR_0x8005, MOVE_NASTY_PLOT\n\tcall MoveTutor_EventScript_OpenBox\n\tend\n",
        encoding="utf-8",
    )
    other = tmp_path / "data" / "maps" / "Other"
    other.mkdir()
    (other / "scripts.inc").write_text("X::\n\tsetvar VAR_0x8005, MOVE_SPITE\n\tend\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert sorted(mt.extract_repo_tutors()) == ["MOVE_FEINT", "MOVE_NASTY_PLOT"]


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def _fake_world(tmp_path: Path) -> tuple[Path, Path]:
    fork, out = tmp_path / "fork", tmp_path / "out"
    _write(fork / "src/data/pokemon/all_learnables.json", {"PIKACHU": ["MOVE_TOXIC"]})
    (fork / "include/constants").mkdir(parents=True)
    (fork / "include/constants/moves.h").write_text(
        "#define MOVE_TOXIC 1\n#define MOVE_FEINT 2\n#define MOVE_CUT 3\n", encoding="utf-8")
    _write(out / "intermediate/uranium_tm_learnables.json",
           {"learnables": {"PIKACHU": ["MOVE_FEINT"], "RAPTORCH": ["MOVE_CUT"]}})
    _write(out / "species/species_manifest.json",
           {"species": [{"internal_name": "RAPTORCH", "species_constant": "SPECIES_RAPTORCH"}]})
    return fork, out


def _ref(tmp_path: Path) -> Path:
    ref = tmp_path / "ref"
    cats = {"species": {"PIKACHU": "SPECIES_PIKACHU", "RAPTORCH": "SPECIES_RAPTORCH"}}
    _write(ref / "uranium_id_map.json", {**cats, "needs_engine": {"moves": []}})
    return ref


def _load_assembler():
    spec = importlib.util.spec_from_file_location("ap_teach", REPO / "scripts" / "assemble_pathfinder.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("ap_teach", mod)
    spec.loader.exec_module(mod)
    return mod


def test_generate_and_write_end_to_end_idempotent(tmp_path):
    fork, out = _fake_world(tmp_path)
    ref = _ref(tmp_path)
    o1 = t.generate(out=out, fork=fork, reference_dir=ref)
    p = t.write_overlay(o1, fork)
    first = p.read_bytes()
    t.write_overlay(t.generate(out=out, fork=fork, reference_dir=ref), fork)  # base is upstream, not overlay
    assert p.read_bytes() == first
    data = json.loads(first)
    assert data == {"PIKACHU": ["MOVE_FEINT", "MOVE_TOXIC"], "URANIUM_RAPTORCH": ["MOVE_CUT"]}
    assert not (fork / "src/data/pokemon/all_learnables.json").read_text().count("FEINT")


def test_generate_missing_sidecar_fails_loud(tmp_path):
    fork, out = _fake_world(tmp_path)
    (out / "intermediate/uranium_tm_learnables.json").unlink()
    with pytest.raises(FileNotFoundError):
        t.generate(out=out, fork=fork, reference_dir=_ref(tmp_path))


def test_assembler_pass_dry_run_writes_nothing_and_flag_exists(tmp_path, monkeypatch):
    ap = _load_assembler()
    fork, out = _fake_world(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reference").symlink_to(_ref(tmp_path))
    ap.run_teachables_pass(out, fork, dry_run=True)
    assert not (fork / t.OVERLAY_RELPATH).exists()
    ap.run_teachables_pass(out, fork, dry_run=False)
    assert (fork / t.OVERLAY_RELPATH).is_file()
    assert "--skip-teachables" in subprocess.run(
        [sys.executable, str(REPO / "scripts/assemble_pathfinder.py"), "--help"],
        capture_output=True, text=True, check=True).stdout
